"""Controls the panels share: a number with a gesture, a folding section, a swatch.

The one idea here is that a control reports *two* things, not one.  ``edited`` fires on
every value the user passes through — each pixel of a slider drag, each click of a spin
box stepper, each keystroke — and ``committed`` fires once when the gesture ends.  The
document needs both: the first is what makes the preview live, the second is what turns
two hundred intermediate values into one undo step (:meth:`Document.seal`).  A control
that only said "changed" would force the panel to guess where a gesture ended.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QColorDialog,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from . import icons

__all__ = ["NumberControl", "Section", "Swatch"]

Colour = tuple[float, float, float]


class NumberControl(QWidget):
    """A slider for scrubbing and a spin box for exact values, kept in sync.

    The slider resolves to the field's own step where it can — 260 positions for a
    40–300 mm footprint in 1 mm steps — so scrubbing lands on the values an author would
    type, while a fine range still gets at least a hundred positions to feel continuous.
    """

    #: The user moved the value; carries the new value.  Coalesce these.
    edited = Signal(object)
    #: The gesture ended: slider released or the field's editing finished.
    committed = Signal()

    MIN_POSITIONS = 100
    MAX_POSITIONS = 2000

    def __init__(
        self,
        kind: type,
        lo: float,
        hi: float,
        step: float | None = None,
        suffix: str = "",
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.kind, self.lo, self.hi = kind, float(lo), float(hi)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        if kind is int:
            self.spin: QSpinBox | QDoubleSpinBox = QSpinBox()
            self.spin.setRange(int(lo), int(hi))
            self.spin.setSingleStep(int(step or 1))
            self.slider.setRange(int(lo), int(hi))
            self._positions = int(hi) - int(lo)
        else:
            step = step or 0.1
            self.spin = QDoubleSpinBox()
            self.spin.setDecimals(max(1, math.ceil(-math.log10(step))))
            self.spin.setRange(self.lo, self.hi)
            self.spin.setSingleStep(step)
            span = self.hi - self.lo
            wanted = round(span / step) if step > 0 else self.MIN_POSITIONS
            self._positions = max(self.MIN_POSITIONS, min(self.MAX_POSITIONS, wanted))
            self.slider.setRange(0, self._positions)
        if suffix:
            self.spin.setSuffix(suffix)
        self.spin.setFixedWidth(88)
        self.spin.setKeyboardTracking(True)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.spin)
        self.slider.valueChanged.connect(self._from_slider)
        self.slider.sliderReleased.connect(self.committed.emit)
        self.spin.valueChanged.connect(self._from_spin)
        self.spin.editingFinished.connect(self.committed.emit)

    # ---- sync ---------------------------------------------------------------------------
    def _position(self, value: float) -> int:
        if self.kind is int:
            return int(value)
        span = self.hi - self.lo
        return round((value - self.lo) / span * self._positions) if span else 0

    def _from_slider(self, raw: int) -> None:
        value = raw if self.kind is int else self.lo + (self.hi - self.lo) * raw / self._positions
        with QSignalBlocker(self.spin):
            self.spin.setValue(value)
        self.edited.emit(self.spin.value())

    def _from_spin(self, value: float) -> None:
        with QSignalBlocker(self.slider):
            self.slider.setValue(self._position(value))
        self.edited.emit(value)

    # ---- value --------------------------------------------------------------------------
    def value(self) -> float | int:
        return self.spin.value()

    def setValue(self, value: float) -> None:
        """Show ``value`` without reporting it: the document is telling the control."""
        with QSignalBlocker(self.spin), QSignalBlocker(self.slider):
            self.spin.setValue(value)
            self.slider.setValue(self._position(self.spin.value()))

    def setToolTip(self, text: str) -> None:
        super().setToolTip(text)
        self.slider.setToolTip(text)
        self.spin.setToolTip(text)


class Section(QWidget):
    """A titled, folding group: a hairline, a small label, a chevron, and a form.

    A section is not a box.  The parameter panel holds eight of them, and eight bordered
    frames stacked in a scroll area read louder than the forty values inside them.  The
    header is the only chrome: a rule above, the name in small capitals, the chevron that
    folds it, and an optional reset that is enabled only when there is something to reset.
    """

    #: The user folded or unfolded the section; carries the new expanded state.
    toggled = Signal(bool)
    #: The user asked for this section's values to go back to their defaults.
    reset_requested = Signal()

    def __init__(self, title: str, resettable: bool = True, parent: QWidget | None = None):
        super().__init__(parent)
        self.title = title
        self.header = QToolButton()
        self.header.setObjectName("sectionHeader")
        self.header.setText(title.upper())
        self.header.setCheckable(True)
        self.header.setChecked(True)
        self.header.setAutoRaise(True)
        self.header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.header.setCursor(Qt.CursorShape.PointingHandCursor)
        self.header.toggled.connect(self._on_toggled)

        self.reset_button: QToolButton | None = None
        if resettable:
            self.reset_button = QToolButton()
            self.reset_button.setObjectName("sectionTool")
            self.reset_button.setAutoRaise(True)
            self.reset_button.setIcon(icons.icon("reset"))
            self.reset_button.setToolTip(f"Reset {title} to defaults")
            self.reset_button.setEnabled(False)
            self.reset_button.clicked.connect(self.reset_requested.emit)

        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(2)
        head.addWidget(self.header, 1)
        if self.reset_button is not None:
            head.addWidget(self.reset_button)

        self.body = QWidget()
        self.form = QFormLayout(self.body)
        self.form.setContentsMargins(2, 2, 0, 6)
        self.form.setHorizontalSpacing(10)
        self.form.setVerticalSpacing(6)
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addLayout(head)
        layout.addWidget(self.body)
        self._sync_icon()

    def add_row(self, label: str, widget: QWidget, tooltip: str = "") -> int:
        """Append a labelled control; returns the row index for later show/hide."""
        row = self.form.rowCount()
        self.form.addRow(label, widget)
        if tooltip:
            widget.setToolTip(tooltip)
            label_item = self.form.itemAt(row, QFormLayout.ItemRole.LabelRole)
            if label_item is not None and label_item.widget() is not None:
                label_item.widget().setToolTip(tooltip)
        return row

    def set_row_visible(self, row: int, visible: bool) -> None:
        self.form.setRowVisible(row, visible)

    @property
    def expanded(self) -> bool:
        return self.header.isChecked()

    def set_expanded(self, expanded: bool) -> None:
        """Fold or unfold without announcing it — for restoring a remembered state."""
        with QSignalBlocker(self.header):
            self.header.setChecked(expanded)
        self.body.setVisible(expanded)
        self._sync_icon()

    def set_reset_enabled(self, enabled: bool) -> None:
        if self.reset_button is not None:
            self.reset_button.setEnabled(enabled)

    def _on_toggled(self, checked: bool) -> None:
        self.body.setVisible(checked)
        self._sync_icon()
        self.toggled.emit(checked)

    def _sync_icon(self) -> None:
        self.header.setIcon(icons.icon("chevron_down" if self.expanded else "chevron_right"))


class Swatch(QPushButton):
    """A colour as a button: the field of colour, its hex, and a picker on click.

    A swatch is the one control that *is* a field of colour by definition, so it is the
    one place the chrome paints a full face — the colour is the content, not decoration.
    """

    #: The user picked a colour; carries ``(r, g, b)`` in 0..1.
    picked = Signal(object)

    def __init__(self, title: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("swatch")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._title = title
        self._colour: Colour = (0.5, 0.5, 0.5)
        self._dialog: Callable[[QColor], QColor | None] = self._ask
        self.clicked.connect(self._pick)
        self.set_colour(self._colour)

    def colour(self) -> Colour:
        return self._colour

    def set_colour(self, rgb: Colour) -> None:
        self._colour = tuple(float(c) for c in rgb)
        qc = QColor.fromRgbF(*(max(0.0, min(1.0, c)) for c in self._colour))
        ink = "#141414" if qc.lightnessF() > 0.5 else "#f4f4f4"
        self.setText(qc.name())
        self.setStyleSheet(f"background-color: {qc.name()}; color: {ink};")

    def _ask(self, initial: QColor) -> QColor | None:
        chosen = QColorDialog.getColor(initial, self, self._title)
        return chosen if chosen.isValid() else None

    def _pick(self) -> None:
        chosen = self._dialog(QColor.fromRgbF(*(max(0.0, min(1.0, c)) for c in self._colour)))
        if chosen is not None:
            self.picked.emit((chosen.redF(), chosen.greenF(), chosen.blueF()))
