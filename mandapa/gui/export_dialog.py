"""The export dialog: the print options, the format, the destination, a worker.

Built from ``dataclasses.fields()`` of the options class rather than by hand so the
print-prep module can grow an option and the dialog grows a control — the same rule the
parameter panel follows with its parameter class.  The class defaults to the mandapa's
:class:`PrintOptions`; the gopuram's window passes its own, together with the prepare
function that understands it.  A bool is a check box, a number a spin box, text a line
edit, and an optional ``(x, y, z)`` a line edit that reads three numbers or nothing.
Field metadata, when present, names and explains the control.

The union and the splitting run in :class:`ExportWorker`; the dialog shows a busy bar,
disables its form, and never blocks the window behind it.  The per-part report goes to
the build log through :attr:`logged`, because that is where reports live.
"""

from __future__ import annotations

import importlib.util
import typing
from dataclasses import MISSING, fields
from pathlib import Path
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .. import export as export_module
from ..builder import Build
from ..printprep import PrintOptions, prepare_parts
from .workers import ExportOutcome, ExportWorker

__all__ = ["FORMATS", "ExportDialog", "option_kind", "threemf_available"]

#: Format key -> (menu label, suffix).
FORMATS: dict[str, tuple[str, str]] = {
    "stl": ("STL", ".stl"),
    "3mf": ("3MF", ".3mf"),
}


def threemf_available() -> bool:
    """trimesh's 3MF writer needs ``networkx``; without it the option would only fail."""
    if getattr(export_module, "export_parts", None) is not None:
        return True
    return importlib.util.find_spec("networkx") is not None


def option_kind(annotation: Any) -> str:
    """Classify a ``PrintOptions`` field: ``bool``, ``int``, ``float``, ``str`` or ``xyz``.

    Annotations arrive as strings under ``from __future__ import annotations`` and as
    types otherwise; both are handled so the dialog survives either spelling.
    """
    if isinstance(annotation, str):
        text = annotation.replace(" ", "")
        if text.startswith("bool"):
            return "bool"
        if text.startswith("int"):
            return "int"
        if text.startswith("float"):
            return "float"
        if text.startswith("tuple"):
            return "xyz"
        return "str"
    if annotation is bool:
        return "bool"
    if annotation is int:
        return "int"
    if annotation is float:
        return "float"
    if annotation is str:
        return "str"
    origin = typing.get_origin(annotation)
    if origin is tuple:
        return "xyz"
    args = typing.get_args(annotation)
    if args and any(typing.get_origin(a) is tuple for a in args):
        return "xyz"
    return "str"


def _annotations(options_cls: type = PrintOptions) -> dict[str, Any]:
    try:
        return typing.get_type_hints(options_cls)
    except Exception:  # noqa: BLE001 - fall back to the raw (string) annotations
        return {f.name: f.type for f in fields(options_cls)}


class ExportDialog(QDialog):
    #: Lines for the build log: the per-part report, or the failure.
    logged = Signal(str)
    #: The paths written.
    exported = Signal(list)

    def __init__(
        self,
        result: Build,
        parent: QWidget | None = None,
        suggested: Path | None = None,
        bed: tuple[float, float, float] | None = None,
        options_cls: type = PrintOptions,
        prepare=prepare_parts,
    ):
        super().__init__(parent)
        self.setWindowTitle("Export for printing")
        # Not ``self.result``: QDialog.result() is a method, and shadowing it breaks exec().
        self.build_result = result
        self.options_cls = options_cls
        self.prepare = prepare
        self._worker: ExportWorker | None = None
        self.widgets: dict[str, QWidget] = {}
        self.kinds: dict[str, str] = {}

        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        self.form = QFormLayout()
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        hints = _annotations(options_cls)
        for field in fields(options_cls):
            kind = option_kind(hints.get(field.name, field.type))
            default = field.default if field.default is not MISSING else None
            if field.default_factory is not MISSING:  # type: ignore[misc]
                default = field.default_factory()  # type: ignore[misc]
            if kind == "xyz" and default is None and bed is not None and "bed" in field.name:
                default = bed
            widget = self._widget(kind, default)
            label = field.metadata.get("label") or field.name.replace("_", " ").capitalize()
            help_text = field.metadata.get("help") or ""
            if help_text:
                widget.setToolTip(help_text)
            self.form.addRow(label, widget)
            self.widgets[field.name] = widget
            self.kinds[field.name] = kind
        layout.addLayout(self.form)

        # Built before the format radios: choosing a format rewrites this field's suffix.
        self.path_edit = QLineEdit(str(suggested or Path.cwd() / "mandapa.stl"))

        formats = QHBoxLayout()
        self.format_buttons: dict[str, QRadioButton] = {}
        for key, (label, _) in FORMATS.items():
            button = QRadioButton(label)
            self.format_buttons[key] = button
            formats.addWidget(button)
            button.toggled.connect(self._sync_suffix)
        formats.addStretch(1)
        if not threemf_available():
            self.format_buttons["3mf"].setEnabled(False)
            self.format_buttons["3mf"].setToolTip("3MF needs the networkx package, which is not installed")
        self.format_buttons["stl"].setChecked(True)
        self.form.addRow("Format", formats)

        destination = QHBoxLayout()
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse)
        destination.addWidget(self.path_edit, 1)
        destination.addWidget(browse)
        self.form.addRow("Destination", destination)

        self.note = QLabel(
            "A split model goes to <name>_<part>.stl files beside the destination, or into the one 3MF."
        )
        self.note.setObjectName("note")
        self.note.setWordWrap(True)
        layout.addWidget(self.note)

        self.busy = QProgressBar()
        self.busy.setRange(0, 0)
        self.busy.setTextVisible(False)
        self.busy.hide()
        layout.addWidget(self.busy)

        self.buttons = QDialogButtonBox()
        self.export_button = self.buttons.addButton("Export", QDialogButtonBox.ButtonRole.AcceptRole)
        self.close_button = self.buttons.addButton(QDialogButtonBox.StandardButton.Close)
        self.export_button.setDefault(True)
        self.buttons.accepted.connect(self.start)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)
        self.resize(460, self.sizeHint().height())

    # ---- the form ---------------------------------------------------------------------------
    @staticmethod
    def _widget(kind: str, default: Any) -> QWidget:
        if kind == "bool":
            check = QCheckBox()
            check.setChecked(bool(default))
            return check
        if kind == "int":
            spin = QSpinBox()
            spin.setRange(0, 100000)
            spin.setValue(int(default or 0))
            return spin
        if kind == "float":
            dspin = QDoubleSpinBox()
            dspin.setRange(0.0, 100000.0)
            dspin.setDecimals(2)
            dspin.setSingleStep(0.1)
            dspin.setValue(float(default or 0.0))
            return dspin
        edit = QLineEdit()
        if kind == "xyz":
            edit.setPlaceholderText("x y z (mm), or empty")
            if default is not None:
                edit.setText(" ".join(f"{float(v):g}" for v in default))
        elif default is not None:
            edit.setText(str(default))
        return edit

    def options(self) -> PrintOptions:
        """Read the form back into the options class; raises ``ValueError`` on bad text."""
        values: dict[str, Any] = {}
        for name, widget in self.widgets.items():
            kind = self.kinds[name]
            if kind == "bool":
                values[name] = widget.isChecked()
            elif kind in ("int", "float"):
                values[name] = widget.value()
            elif kind == "xyz":
                text = widget.text().strip().replace(",", " ")
                if not text:
                    values[name] = None
                else:
                    parts = [float(v) for v in text.split()]
                    if len(parts) != 3:
                        raise ValueError(f"{name}: expected three numbers, got {text!r}")
                    values[name] = tuple(parts)
            else:
                values[name] = widget.text()
        return self.options_cls(**values)

    def format(self) -> str:
        for key, button in self.format_buttons.items():
            if button.isChecked():
                return key
        return "stl"

    def path(self) -> Path:
        return Path(self.path_edit.text().strip()).expanduser()

    def _sync_suffix(self) -> None:
        text = self.path_edit.text().strip()
        if text:
            self.path_edit.setText(str(Path(text).with_suffix(FORMATS[self.format()][1])))

    def _browse(self) -> None:
        label, suffix = FORMATS[self.format()]
        path, _ = QFileDialog.getSaveFileName(
            self, "Export destination", str(self.path()), f"{label} files (*{suffix});;All files (*)"
        )
        if path:
            self.path_edit.setText(path)

    # ---- running ------------------------------------------------------------------------------
    def start(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return
        try:
            options = self.options()
        except ValueError as exc:
            QMessageBox.warning(self, "Export", str(exc))
            return
        path = self.path()
        if not path.name:
            QMessageBox.warning(self, "Export", "Choose a destination file.")
            return
        path = path.with_suffix(FORMATS[self.format()][1])
        self._set_busy(True)
        self.logged.emit(f"exporting {path.name} ({self.format().upper()})…")
        self._worker = ExportWorker(
            self.build_result, options, path, self.format(), self, prepare=self.prepare
        )
        self._worker.done.connect(self._done)
        self._worker.failed.connect(self._failed)
        self._worker.start()

    def is_running(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def _set_busy(self, busy: bool) -> None:
        self.busy.setVisible(busy)
        self.export_button.setEnabled(not busy)
        for widget in self.widgets.values():
            widget.setEnabled(not busy)
        self.path_edit.setEnabled(not busy)

    def _done(self, outcome: ExportOutcome) -> None:
        self._set_busy(False)
        for line in outcome.lines():
            self.logged.emit(line)
        if any(not report.watertight for report in outcome.reports):
            self.logged.emit("warning: a part is not watertight — check the report above")
        self.exported.emit([str(p) for p in outcome.paths])
        self.accept()

    def _failed(self, message: str) -> None:
        self._set_busy(False)
        self.logged.emit(message)
        QMessageBox.critical(self, "Export failed", message.strip().splitlines()[-1] if message.strip() else "Export failed")

    def reject(self) -> None:
        # A running worker keeps its thread; the dialog just stops being shown.
        if self.is_running():
            self.hide()
            return
        super().reject()

    def closeEvent(self, event) -> None:
        if self.is_running():
            self.hide()
            event.ignore()
            return
        super().closeEvent(event)
