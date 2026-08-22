"""The chrome's provenance: every colour the theme wears is one the render owns.

The theme's whole argument is that it invents nothing — the panels are dressed in the
viewport's own backdrop, the sandstone's own hue, the wireframe's own ivory, the print
risks' own red and orange.  That claim is enforced here rather than remembered: retune a
Look default and the matching chrome constant fails loudly instead of drifting into a
second brand.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import re
from pathlib import Path

import pytest
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from mandapa.gui import theme, viewer
from mandapa.look import Look


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _rgb(hex_colour: str) -> tuple[int, int, int]:
    colour = QColor(hex_colour)
    return colour.red(), colour.green(), colour.blue()


def _bytes(colour) -> tuple[int, int, int]:
    return tuple(round(c * 255) for c in colour[:3])


def _lightness(hex_colour: str) -> float:
    return QColor(hex_colour).lightnessF()


class TestProvenance:
    def test_the_field_is_the_backdrops_horizon(self):
        assert _rgb(theme.FIELD) == _bytes(Look().background_colour)

    def test_raised_controls_are_the_sky(self):
        assert _rgb(theme.RAISED) == _bytes(Look().background_top)

    def test_the_window_is_half_way_up_the_gradient(self):
        look = Look()
        midpoint = tuple((h + s) / 2 for h, s in zip(look.background_colour, look.background_top))
        assert _rgb(theme.WINDOW) == _bytes(midpoint)

    def test_the_ink_is_the_wireframes_ivory(self):
        assert _rgb(theme.INK) == _bytes(viewer.EDGE_COLOUR)

    def test_the_accent_keeps_the_sandstones_hue(self):
        sand = QColor.fromRgbF(*Look().surface_colour)
        accent = QColor(theme.ACCENT)
        assert abs(accent.hsvHueF() - sand.hsvHueF()) < 0.01
        assert accent.valueF() == 1.0
        assert accent.hsvSaturationF() > sand.hsvSaturationF()

    def test_select_is_a_quarter_of_the_accent_over_the_field(self):
        accent = QColor(theme.ACCENT)
        field = Look().background_colour
        tint = (accent.redF(), accent.greenF(), accent.blueF())
        expected = tuple(f + (a - f) * 0.25 for f, a in zip(field, tint))
        assert _rgb(theme.SELECT) == _bytes(expected)

    def test_the_warnings_are_the_print_risk_colours(self):
        assert _rgb(theme.WARN) == _bytes(Look().overhang_colour)
        assert _rgb(theme.NOTE) == _bytes(Look().bridge_colour)

    def test_the_greys_climb_in_order(self):
        ramp = [theme.FIELD, theme.WINDOW, theme.RAISED, theme.HOVER, theme.BORDER, theme.QUIET, theme.DIM, theme.INK]
        lightness = [_lightness(c) for c in ramp]
        assert lightness == sorted(lightness), ramp

    def test_the_chrome_is_no_brighter_than_the_viewports_sky(self):
        """Frames group, they do not decorate: the docks sit below the gradient's top."""
        assert _lightness(theme.WINDOW) <= _lightness(theme.RAISED)


class TestMarks:
    """The glyphs the stylesheet can only reach as files."""

    def test_every_image_the_stylesheet_asks_for_exists(self):
        referenced = re.findall(r"url\(([^)]+)\)", theme.QSS)
        assert referenced, "no marks referenced — the sub-controls are blank again"
        missing = [path for path in referenced if not Path(path).is_file()]
        assert missing == []

    def test_the_marks_are_drawn_in_the_palettes_own_colours(self):
        marks = {name: Path(path).read_text(encoding="utf-8") for name, path in theme.MARKS.items()}
        assert theme.DIM.lower() in marks["up"].lower()
        assert theme.DIM.lower() in marks["down"].lower()
        assert theme.QUIET.lower() in marks["up_off"].lower()
        assert theme.QUIET.lower() in marks["down_off"].lower()
        assert theme.ON_ACCENT.lower() in marks["tick"].lower()
        assert theme.ON_ACCENT.lower() in marks["dot"].lower()

    def test_the_stylesheet_redraws_what_it_took_over(self):
        for sub_control in (
            "QSpinBox::up-arrow",
            "QSpinBox::down-arrow",
            "QDoubleSpinBox::up-arrow",
            "QDoubleSpinBox::down-arrow",
            "QComboBox::down-arrow",
            "QCheckBox::indicator",
            "QRadioButton::indicator",
        ):
            assert sub_control in theme.QSS, f"{sub_control} is unstyled and so unpainted"

    def test_the_accent_is_never_a_button_face(self):
        """A toggled tool button wears the tint and an accent hairline, not the accent."""
        checked = re.search(r"QToolButton:checked \{\{?([^}]*)\}", theme.QSS)
        assert checked is not None
        body = checked.group(1)
        assert f"background: {theme.SELECT}" in body
        assert f"background: {theme.ACCENT}" not in body


class TestApply:
    def test_apply_dresses_the_application(self, app):
        theme.apply(app)
        try:
            palette = app.palette()
            assert palette.color(QPalette.ColorRole.Highlight).name() == QColor(theme.ACCENT).name()
            assert palette.color(QPalette.ColorRole.Base).name() == QColor(theme.FIELD).name()
            assert "QToolButton" in app.styleSheet()
        finally:
            # Other test modules share this QApplication and met it stock.
            app.setStyleSheet("")
            app.setPalette(QPalette())
