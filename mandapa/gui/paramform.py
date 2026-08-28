"""The parameter panel: generated from the document's parameter class, driven by the Document.

Which class that is comes from the document itself (``type(document.params)``), so the
same form serves the mandapa's editor and the gopuram's: every field with the ``P()``
metadata gets a control, and the section order is the declaration order — the params
modules declare their fields grouped, so the panel reads like the file.

The form never holds the truth.  Every control submits a command and then waits to be
told what the document now says, so a value arriving from anywhere — undo, a preset, a
file — lands in the controls through the same path as a typed one, and the panel cannot
disagree with the viewer.  A slider drag submits one coalesced command per pixel and
seals the step on release, which is how two hundred motions become one Undo.

Sections fold and remember it, because forty controls is a scroll; a filter box hides
everything that does not match, because "kapota" is faster than scrolling to it.
"""

from __future__ import annotations

from functools import partial
from typing import Any

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QLineEdit,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from ..document import Document, SetParams
from ..params import ParamRecord, _resolve_type
from . import icons
from .controls import NumberControl, Section
from .prefs import Preferences

__all__ = ["FilterEdit", "ParamForm"]


class FilterEdit(QLineEdit):
    """A search field that Escape empties: the common case is "show me everything again"."""

    escaped = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.clear()
            self.escaped.emit()
            event.accept()
            return
        super().keyPressEvent(event)


class ParamForm(QScrollArea):
    """Grouped controls for every field, bound to a document."""

    def __init__(self, document: Document, prefs: Preferences | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.document = document
        self.prefs = prefs
        self.controls: dict[str, QWidget] = {}
        self.sections: dict[str, Section] = {}
        self._rows: dict[str, tuple[str, int]] = {}
        self._meta: dict[str, dict[str, Any]] = {}
        self._labels: dict[str, str] = {}
        self._defaults = type(document.params)()
        self._refreshing = False
        self._unsubscribe = document.subscribe(self._on_event)

        container = QWidget()
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(8, 6, 8, 8)
        vbox.setSpacing(4)

        self.filter = FilterEdit()
        self.filter.setPlaceholderText("Filter parameters")
        self.filter.setClearButtonEnabled(True)
        self.filter.addAction(icons.icon("search"), QLineEdit.ActionPosition.LeadingPosition)
        self.filter.setToolTip("Show only the parameters whose name or help mentions this (Ctrl+F, Esc clears)")
        self.filter.textChanged.connect(self._apply_filter)
        vbox.addWidget(self.filter)

        groups: list[str] = []
        for name, kind, meta in type(document.params).specs():
            kind = _resolve_type(kind)
            group = meta["group"]
            if group not in groups:
                groups.append(group)
            section = self.sections.get(group)
            if section is None:
                section = Section(group)
                self.sections[group] = section
            widget = self._make_control(name, kind, meta)
            tooltip = meta["help"] or self._range_hint(meta)
            row = section.add_row(meta["label"], widget, tooltip)
            self.controls[name] = widget
            self._rows[name] = (group, row)
            self._meta[name] = meta
            self._labels[name] = meta["label"]

        for group in groups:
            section = self.sections.get(group)
            if section is None:
                continue
            vbox.addWidget(section)
            section.toggled.connect(partial(self._remember, group))
            section.reset_requested.connect(partial(self.reset_group, group))
            if prefs is not None:
                section.set_expanded(prefs.section_expanded(group))
        vbox.addStretch(1)

        self.setWidget(container)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setMinimumWidth(340)
        self.refresh()

    @staticmethod
    def _range_hint(meta: dict[str, Any]) -> str:
        if meta["choices"] is not None:
            return "One of: " + ", ".join(meta["choices"])
        if meta["lo"] is not None:
            return f"{meta['label']}: {meta['lo']:g} to {meta['hi']:g}"
        return meta["label"]

    # ---- controls -------------------------------------------------------------------------
    def _make_control(self, name: str, kind: type, meta: dict[str, Any]) -> QWidget:
        if meta["choices"] is not None:
            combo = QComboBox()
            combo.addItems(meta["choices"])
            combo.currentTextChanged.connect(lambda text, n=name: self._submit(n, text, None))
            return combo
        if kind is bool:
            check = QCheckBox()
            check.toggled.connect(lambda on, n=name: self._submit(n, bool(on), None))
            return check
        control = NumberControl(kind, meta["lo"], meta["hi"], meta["step"])
        control.edited.connect(lambda value, n=name: self._submit(n, value, n))
        control.committed.connect(self._seal)
        return control

    def _submit(self, name: str, value: Any, coalesce: str | None) -> None:
        """One field changed by the user: one command, coalesced while a gesture lasts."""
        if self._refreshing or getattr(self.document.params, name) == value:
            return
        self.document.submit(
            SetParams({name: value}, text=f"Set {self._labels[name]}", coalesce=coalesce)
        )
        if coalesce is None:
            self.document.seal()

    def _seal(self) -> None:
        self.document.seal()

    # ---- the document ---------------------------------------------------------------------
    def set_document(self, document: Document) -> None:
        self._unsubscribe()
        self.document = document
        self._unsubscribe = document.subscribe(self._on_event)
        self.refresh()

    def _on_event(self, event: str) -> None:
        if event == "params":
            self.refresh()

    def refresh(self) -> None:
        """Show the document's parameters without submitting anything back."""
        params = self.document.params
        self._refreshing = True
        try:
            for name, widget in self.controls.items():
                value = getattr(params, name)
                if isinstance(widget, QComboBox):
                    with QSignalBlocker(widget):
                        widget.setCurrentText(value)
                elif isinstance(widget, QCheckBox):
                    with QSignalBlocker(widget):
                        widget.setChecked(bool(value))
                else:
                    widget.setValue(value)
        finally:
            self._refreshing = False
        for group, section in self.sections.items():
            section.set_reset_enabled(bool(self._changes_for_reset(group)))

    def values(self) -> ParamRecord:
        """What the controls show — the document's parameters, by construction."""
        return self.document.params

    # ---- sections -------------------------------------------------------------------------
    def _group_fields(self, group: str) -> list[str]:
        return [name for name, (g, _) in self._rows.items() if g == group]

    def _changes_for_reset(self, group: str) -> dict[str, Any]:
        params = self.document.params
        return {
            name: getattr(self._defaults, name)
            for name in self._group_fields(group)
            if getattr(params, name) != getattr(self._defaults, name)
        }

    def reset_group(self, group: str) -> None:
        """Every field of one section back to its default, as a single undo step."""
        changes = self._changes_for_reset(group)
        if not changes:
            return
        self.document.seal()
        self.document.submit(SetParams(changes, text=f"Reset {group}"))
        self.document.seal()

    def _remember(self, group: str, expanded: bool) -> None:
        if self.prefs is not None and not self.filter.text().strip():
            self.prefs.set_section_expanded(group, expanded)

    # ---- filtering ------------------------------------------------------------------------
    def _apply_filter(self, text: str) -> None:
        tokens = text.lower().split()
        shown: dict[str, bool] = {group: False for group in self.sections}
        for name, (group, row) in self._rows.items():
            meta = self._meta[name]
            hay = f"{meta['label']} {name} {meta['help']} {group}".lower()
            visible = all(token in hay for token in tokens)
            self.sections[group].set_row_visible(row, visible)
            shown[group] = shown[group] or visible
        for group, section in self.sections.items():
            section.setVisible(shown[group])
            if tokens:
                # A match inside a folded section is a match the author cannot see.
                section.set_expanded(True)
            else:
                section.set_expanded(self.prefs.section_expanded(group) if self.prefs else True)

    def focus_filter(self) -> None:
        self.filter.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.filter.selectAll()
