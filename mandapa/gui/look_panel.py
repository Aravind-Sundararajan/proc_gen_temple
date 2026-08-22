"""The Look dock: the key light, the fill, the palette — authored, undoable, saved.

Lighting is part of the design here, not a viewer setting: the :class:`Look` rides the
document, so this panel submits :class:`SetLook` commands exactly the way the parameter
form submits :class:`SetParams`, with the same coalescing during a drag and the same seal
on release.  Undo takes a light move back; a saved file reopens under the sun it was
authored under.
"""

from __future__ import annotations

from functools import partial
from typing import Any

from PySide6.QtWidgets import QLabel, QScrollArea, QVBoxLayout, QWidget

from ..document import Document, SetLook
from ..look import Look
from .controls import NumberControl, Section, Swatch

__all__ = ["COLOURS", "NUMBERS", "LookPanel"]

#: Section title -> (field, label, lo, hi, step, suffix).
NUMBERS: dict[str, list[tuple[str, str, float, float, float, str]]] = {
    "Key light": [
        ("light_azimuth", "Azimuth", -180.0, 180.0, 1.0, "°"),
        ("light_elevation", "Elevation", -90.0, 90.0, 1.0, "°"),
        ("light_strength", "Strength", 0.0, 2.0, 0.05, ""),
    ],
    "Fill": [
        ("ambient_strength", "Ambient", 0.0, 1.0, 0.05, ""),
        ("rim_strength", "Rim", 0.0, 1.0, 0.05, ""),
    ],
}

#: Section title -> (field, label, help).
COLOURS: dict[str, list[tuple[str, str, str]]] = {
    "Colours": [
        ("surface_colour", "Surface", "The stone."),
        ("overhang_colour", "Overhang", "Faces sloping down steeper than 45°: they need support."),
        ("bridge_colour", "Bridge", "Flat undersides: ceilings that bridge between beams."),
        ("background_colour", "Horizon", "The bottom of the backdrop, and the fill from below."),
        ("background_top", "Sky", "The top of the backdrop, and the fill from above."),
    ],
}

HELP = {
    "light_azimuth": "Where the sun stands, in degrees around the temple from +X; the steps face -Y.",
    "light_elevation": "How high the sun is above the horizon.",
    "light_strength": "The key light's level.",
    "ambient_strength": "The fill's level. The backdrop's two tones give it its hue.",
    "rim_strength": "A sky-coloured edge light on faces seen nearly edge-on.",
}


class LookPanel(QScrollArea):
    def __init__(self, document: Document, parent: QWidget | None = None):
        super().__init__(parent)
        self.document = document
        self.numbers: dict[str, NumberControl] = {}
        self.swatches: dict[str, Swatch] = {}
        self.sections: dict[str, Section] = {}
        self._section_fields: dict[str, list[str]] = {}
        self._labels: dict[str, str] = {}
        self._refreshing = False
        self._unsubscribe = document.subscribe(self._on_event)

        container = QWidget()
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(8, 2, 8, 8)
        vbox.setSpacing(4)

        for title, specs in NUMBERS.items():
            section = Section(title)
            for field, label, lo, hi, step, suffix in specs:
                control = NumberControl(float, lo, hi, step, suffix=suffix)
                control.edited.connect(partial(self._submit_number, field))
                control.committed.connect(self._seal)
                section.add_row(label, control, HELP.get(field, ""))
                self.numbers[field] = control
                self._labels[field] = label
            self._add_section(vbox, title, section, [f for f, *_ in specs])

        note = QLabel(
            "The backdrop lights the temple: the sky tone fills faces that look up, the "
            "horizon tone faces that look down, so shadows cool instead of greying."
        )
        note.setObjectName("note")
        note.setWordWrap(True)
        vbox.addWidget(note)

        for title, specs in COLOURS.items():
            section = Section(title)
            for field, label, help_text in specs:
                swatch = Swatch(f"{label} colour")
                swatch.picked.connect(partial(self._submit_colour, field))
                section.add_row(label, swatch, help_text)
                self.swatches[field] = swatch
                self._labels[field] = label
            self._add_section(vbox, title, section, [f for f, *_ in specs])

        vbox.addStretch(1)
        self.setWidget(container)
        self.setWidgetResizable(True)
        self.setFrameShape(QScrollArea.Shape.NoFrame)
        self.setMinimumWidth(260)
        self.refresh()

    def _add_section(self, layout: QVBoxLayout, title: str, section: Section, fields: list[str]) -> None:
        self.sections[title] = section
        self._section_fields[title] = fields
        section.reset_requested.connect(partial(self.reset_section, title))
        layout.addWidget(section)

    # ---- commands -------------------------------------------------------------------------
    def _submit_number(self, field: str, value: float) -> None:
        if self._refreshing or getattr(self.document.look, field) == value:
            return
        self.document.submit(SetLook({field: float(value)}, text=f"Set {self._labels[field]}", coalesce=field))

    def _submit_colour(self, field: str, rgb: Any) -> None:
        if self._refreshing:
            return
        colour = tuple(float(c) for c in rgb)
        if getattr(self.document.look, field) == colour:
            return
        self.document.seal()
        self.document.submit(SetLook({field: colour}, text=f"Set {self._labels[field]} colour"))
        self.document.seal()

    def _seal(self) -> None:
        self.document.seal()

    def reset_section(self, title: str) -> None:
        """One section of the look back to the defaults, as one undo step."""
        defaults = Look()
        look = self.document.look
        changes = {
            field: getattr(defaults, field)
            for field in self._section_fields[title]
            if getattr(look, field) != getattr(defaults, field)
        }
        if not changes:
            return
        self.document.seal()
        self.document.submit(SetLook(changes, text=f"Reset {title.lower()}"))
        self.document.seal()

    # ---- the document ---------------------------------------------------------------------
    def set_document(self, document: Document) -> None:
        self._unsubscribe()
        self.document = document
        self._unsubscribe = document.subscribe(self._on_event)
        self.refresh()

    def _on_event(self, event: str) -> None:
        if event == "look":
            self.refresh()

    def refresh(self) -> None:
        look = self.document.look
        defaults = Look()
        self._refreshing = True
        try:
            for field, control in self.numbers.items():
                control.setValue(getattr(look, field))
            for field, swatch in self.swatches.items():
                swatch.set_colour(getattr(look, field))
        finally:
            self._refreshing = False
        for title, fields in self._section_fields.items():
            self.sections[title].set_reset_enabled(
                any(getattr(look, f) != getattr(defaults, f) for f in fields)
            )
