"""The editor's skin: the viewport's own palette, worn by the chrome.

The preview has had a look since the first frame was rendered — a dark blue-grey field
rising to a lighter sky, a sandstone temple, red and orange print warnings.  This module
does not invent a second identity for the panels around it: every constant below is
computed from a value the render already owns (the :class:`~mandapa.look.Look` defaults
and the viewer's line colours), and ``tests/test_theme.py`` holds each one to its source,
so retuning the backdrop or the sandstone moves the chrome with it instead of leaving two
brands in one window.

Fusion is the base style because it is the one Qt style that obeys a dark palette
everywhere — indicators, sliders, menus — where the platform styles paint half their
widgets from OS resources a palette never reaches.  The stylesheet covers what palettes
cannot say: dock titles, section rules, slim scrollbars, focus rings.

Two rules the chrome answers to.  **The accent is a mark, never a field**: at the size of
a focus ring, a slider handle or a checked tick it reads as "chosen"; at the size of a
button face it is louder than the render.  :data:`SELECT` — the accent at a quarter
strength over the field — is what checked and selected surfaces wear instead.  And
**frames group, they do not decorate**: a section is a hairline and a small label, not a
box; what the chrome frames is the viewport, and it must be quieter than what it frames.

Applied only by :func:`apply`, which only ``main()`` calls: tests and embedders get stock
widgets unless they opt in, so no assertion elsewhere quietly depends on a stylesheet.
"""

from __future__ import annotations

import atexit
import shutil
import tempfile
from pathlib import Path

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from ..look import Look
from .viewer import EDGE_COLOUR

__all__ = [
    "ACCENT",
    "BORDER",
    "DIM",
    "FIELD",
    "HOVER",
    "INK",
    "MARKS",
    "NOTE",
    "ON_ACCENT",
    "QSS",
    "QUIET",
    "RAISED",
    "SELECT",
    "WARN",
    "WINDOW",
    "apply",
    "mix",
    "rgb_hex",
]

Colour = tuple[float, float, float]


def mix(a: Colour, b: Colour, t: float) -> Colour:
    """Linear blend of two 0..1 colours; ``t`` is how far towards ``b``."""
    return tuple(x + (y - x) * t for x, y in zip(a, b))


def rgb_hex(colour: Colour) -> str:
    """``#rrggbb`` for a 0..1 colour, rounded the way QColor rounds."""
    return "#" + "".join(f"{round(max(0.0, min(1.0, c)) * 255.0):02x}" for c in colour)


# ----------------------------------------------------------------------------------------
# the sources: the default look and the viewer's own line colours
# ----------------------------------------------------------------------------------------

_LOOK = Look()
_HORIZON: Colour = _LOOK.background_colour
_SKY: Colour = _LOOK.background_top
_SAND: Colour = _LOOK.surface_colour
_EDGE: Colour = tuple(EDGE_COLOUR[:3])

#: The gradient's own rise, horizon to sky.  Every grey in the chrome is the horizon
#: lifted by a multiple of it, so the panels are tones the viewport already shows.
_RISE: Colour = tuple(s - h for h, s in zip(_HORIZON, _SKY))


def _lift(steps: float) -> Colour:
    return tuple(h + r * steps for h, r in zip(_HORIZON, _RISE))


# ----------------------------------------------------------------------------------------
# the palette, each colour's source named
# ----------------------------------------------------------------------------------------

#: The viewport's backdrop at its base: Look.background_colour, the gradient's horizon.
#: Deepest tone in the app; text fields and the log sit on it.
FIELD = rgb_hex(_HORIZON)

#: Panel background: half a rise above the horizon, so docks read as furniture standing
#: in front of the render rather than as holes cut into it.
WINDOW = rgb_hex(_lift(0.5))

#: Raised controls: the sky itself, Look.background_top — the top of the gradient.
RAISED = rgb_hex(_SKY)

#: Hover, a half rise above the sky.
HOVER = rgb_hex(_lift(1.5))

#: Borders and separators: two rises up — visible against WINDOW, quiet against RAISED.
BORDER = rgb_hex(_lift(2.0))

#: Text: the wireframe's ivory, viewer.EDGE_COLOUR.
INK = rgb_hex(_EDGE)

#: Secondary text: the ink stepped towards the panel, for labels, notes and readouts.
DIM = rgb_hex(mix(_EDGE, _lift(0.5), 0.42))

#: Disabled text: dim enough to read as off, light enough to read at all.
QUIET = rgb_hex(mix(_EDGE, _lift(0.5), 0.68))

#: The accent: the sandstone's own hue (Look.surface_colour) pushed to full brightness
#: and a deeper saturation — the temple in direct sun.  Focus rings, slider handles,
#: checked ticks, the one mark on a toggled tool button.
_sand = QColor.fromRgbF(*_SAND)
ACCENT = QColor.fromHsvF(_sand.hsvHueF(), min(1.0, _sand.hsvSaturationF() * 1.75), 1.0).name()
#: The accent as the eight-bit colour the chrome actually paints, so every tint derived
#: from it is derived from the value on screen rather than from a finer one nobody sees.
_accent = QColor(ACCENT)

#: Ink for anything sitting on the accent: the field, so the mark stays two-tone.
ON_ACCENT = FIELD

#: Selected and checked surfaces: the accent at a quarter strength over FIELD, not the
#: accent itself.  A button face filled edge to edge with full ACCENT was the brightest
#: thing in the window — brighter than the temple the window exists to show.
SELECT = rgb_hex(mix(_HORIZON, (_accent.redF(), _accent.greenF(), _accent.blueF()), 0.25))

#: Warnings in the chrome are the warnings in the render: the overhang red says "needs
#: support" on a face and "exceeds the bed" on the status bar, the bridge orange says
#: "mind this" in both places.
WARN = rgb_hex(_LOOK.overhang_colour)
NOTE = rgb_hex(_LOOK.bridge_colour)


# ----------------------------------------------------------------------------------------
# the marks: small glyphs the stylesheet can only reach as image files
# ----------------------------------------------------------------------------------------
#
# Qt draws a spin box's arrows, a combo's caret and a check's tick from the *style*, and
# the moment a stylesheet claims the widget it stops drawing them: every numeric field
# becomes a text box with two blank stubs where its stepper was.  The sheet can put them
# back, but ``image:`` only accepts a file, so these have to exist on disk.  They are
# generated from the constants above rather than committed, so recolouring DIM cannot
# leave a stale arrow behind in an asset nobody reopened.


def _marks() -> dict[str, str]:
    """Write the stylesheet's glyphs to a temp dir; return name -> posix path.

    Posix paths because Qt style sheets parse ``\\`` as an escape, so a Windows path
    silently yields no image at all.
    """
    directory = Path(tempfile.mkdtemp(prefix="mandapa_theme_"))
    atexit.register(shutil.rmtree, directory, True)

    def write(name: str, body: str) -> str:
        path = directory / f"{name}.svg"
        path.write_text(
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 8 8">{body}</svg>',
            encoding="utf-8",
        )
        return path.as_posix()

    def caret(name: str, points: str, colour: str) -> tuple[str, str]:
        return name, write(name, f'<polygon points="{points}" fill="{colour}"/>')

    up, down = "0.6,5.6 4,1.9 7.4,5.6", "0.6,2.4 4,6.1 7.4,2.4"
    tick = (
        '<polyline points="1.3,4.2 3.2,6.1 6.7,2.2" fill="none" '
        f'stroke="{ON_ACCENT}" stroke-width="1.5" stroke-linecap="round" '
        'stroke-linejoin="round"/>'
    )
    dot = f'<circle cx="4" cy="4" r="2" fill="{ON_ACCENT}"/>'
    return dict(
        (
            caret("up", up, DIM),
            caret("down", down, DIM),
            caret("up_off", up, QUIET),
            caret("down_off", down, QUIET),
            ("tick", write("tick", tick)),
            ("dot", write("dot", dot)),
        )
    )


#: Glyph name to file path, generated once per process from the palette above.
MARKS = _marks()


def _palette() -> QPalette:
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: WINDOW,
        QPalette.ColorRole.WindowText: INK,
        QPalette.ColorRole.Base: FIELD,
        QPalette.ColorRole.AlternateBase: WINDOW,
        QPalette.ColorRole.Text: INK,
        QPalette.ColorRole.Button: RAISED,
        QPalette.ColorRole.ButtonText: INK,
        QPalette.ColorRole.ToolTipBase: RAISED,
        QPalette.ColorRole.ToolTipText: INK,
        QPalette.ColorRole.Highlight: ACCENT,
        QPalette.ColorRole.HighlightedText: ON_ACCENT,
        QPalette.ColorRole.Link: ACCENT,
        QPalette.ColorRole.PlaceholderText: QUIET,
        QPalette.ColorRole.Light: HOVER,
        QPalette.ColorRole.Midlight: BORDER,
        QPalette.ColorRole.Mid: BORDER,
        QPalette.ColorRole.Dark: FIELD,
        QPalette.ColorRole.Shadow: rgb_hex(mix(_HORIZON, (0.0, 0.0, 0.0), 0.5)),
    }
    for group in (QPalette.ColorGroup.Active, QPalette.ColorGroup.Inactive):
        for role, colour in roles.items():
            palette.setColor(group, role, QColor(colour))
    disabled = QPalette.ColorGroup.Disabled
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        palette.setColor(disabled, role, QColor(QUIET))
    palette.setColor(disabled, QPalette.ColorRole.Highlight, QColor(BORDER))
    palette.setColor(disabled, QPalette.ColorRole.HighlightedText, QColor(DIM))
    return palette


QSS = f"""
QWidget {{
    color: {INK};
}}
QMainWindow, QDialog {{
    background: {WINDOW};
}}
QMainWindow::separator {{
    background: {WINDOW};
    width: 3px;
    height: 3px;
}}
QMainWindow::separator:hover {{
    background: {BORDER};
}}

QMenuBar {{
    background: {WINDOW};
    border-bottom: 1px solid {BORDER};
}}
QMenuBar::item {{
    padding: 4px 10px;
    background: transparent;
}}
QMenuBar::item:selected {{
    background: {HOVER};
    border-radius: 4px;
}}
QMenu {{
    background: {RAISED};
    border: 1px solid {BORDER};
    padding: 4px;
}}
QMenu::item {{
    padding: 5px 28px 5px 10px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background: {SELECT};
}}
QMenu::item:disabled {{
    color: {QUIET};
}}
QMenu::separator {{
    height: 1px;
    background: {BORDER};
    margin: 4px 8px;
}}
QMenu::icon {{
    padding-left: 6px;
}}

QDockWidget {{
    titlebar-close-icon: none;
    titlebar-normal-icon: none;
}}
QDockWidget::title {{
    background: {WINDOW};
    padding: 6px 10px;
    border-bottom: 1px solid {BORDER};
    font-size: 8pt;
    letter-spacing: 1px;
    color: {DIM};
}}
QTabBar::tab {{
    background: {WINDOW};
    color: {DIM};
    padding: 5px 12px;
    border: 1px solid {BORDER};
    border-bottom: none;
    border-top-left-radius: 5px;
    border-top-right-radius: 5px;
}}
QTabBar::tab:selected {{
    background: {RAISED};
    color: {INK};
    border-bottom: 2px solid {ACCENT};
}}
QTabBar::tab:hover:!selected {{
    background: {HOVER};
}}

/* Sections are a rule and a label, not a box: a group box inside a panel inside a dock
   stacks three outlines around six numbers, and the frames read louder than the values
   they frame.  The hairline still groups; it just stops competing. */
QGroupBox {{
    border: none;
    border-top: 1px solid {BORDER};
    margin-top: 15px;
    padding-top: 9px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 0px;
    padding: 0 8px 0 0;
    color: {DIM};
    font-size: 8pt;
    letter-spacing: 1px;
}}
QToolButton#sectionHeader {{
    background: transparent;
    border: none;
    border-top: 1px solid {BORDER};
    border-radius: 0;
    color: {DIM};
    font-size: 8pt;
    letter-spacing: 1px;
    padding: 7px 0 4px 0;
    text-align: left;
}}
QToolButton#sectionHeader:hover {{
    color: {INK};
}}
QToolButton#sectionTool {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 4px;
    padding: 0;
}}
QToolButton#sectionTool:hover {{
    background: {RAISED};
    border-color: {BORDER};
}}

QPushButton {{
    background: {RAISED};
    border: 1px solid {BORDER};
    border-radius: 5px;
    padding: 5px 14px;
}}
QPushButton:hover {{
    background: {HOVER};
    border-color: {DIM};
}}
QPushButton:pressed {{
    background: {FIELD};
}}
QPushButton:checked {{
    background: {SELECT};
    border-color: {ACCENT};
}}
QPushButton:default {{
    border-color: {ACCENT};
}}
QPushButton:disabled {{
    color: {QUIET};
    background: {WINDOW};
}}
QPushButton#swatch {{
    border: 1px solid {BORDER};
    padding: 4px 8px;
}}

QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{
    background: {FIELD};
    border: 1px solid {BORDER};
    border-radius: 5px;
    padding: 3px 8px;
    /* 18 so the field's border box is an even 26px and the two stepper buttons halve
       it exactly; at 17 they left a seam mid-field that read as a rendering fault. */
    min-height: 18px;
    selection-background-color: {ACCENT};
    selection-color: {ON_ACCENT};
}}
QSpinBox, QDoubleSpinBox {{
    /* The stepper stands inside the border, so the text needs the room back. */
    padding-right: 22px;
}}
QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QLineEdit:focus {{
    border-color: {ACCENT};
}}
QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QLineEdit:disabled {{
    color: {QUIET};
    background: {WINDOW};
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox::down-arrow {{
    image: url({MARKS["down"]});
    width: 9px;
    height: 9px;
}}
QComboBox::down-arrow:disabled {{
    image: url({MARKS["down_off"]});
}}
QComboBox QAbstractItemView {{
    background: {RAISED};
    border: 1px solid {BORDER};
    selection-background-color: {SELECT};
    selection-color: {INK};
}}

/* The stepper: claiming the field above cost these their arrows, so they are drawn back
   from the generated marks and given a hit target — a spin button Qt sized itself was
   four pixels of nothing.  One border-left up the pair's shared edge makes the two read
   as one control rather than two buttons parked beside a number. */
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 17px;
    height: 13px;
    background: transparent;
    border-left: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER};
    border-top-right-radius: 5px;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 17px;
    height: 13px;
    background: transparent;
    border-left: 1px solid {BORDER};
    border-bottom-right-radius: 5px;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {HOVER};
}}
QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed,
QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {{
    background: {SELECT};
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url({MARKS["up"]});
    width: 9px;
    height: 9px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url({MARKS["down"]});
    width: 9px;
    height: 9px;
}}
QSpinBox::up-arrow:disabled, QDoubleSpinBox::up-arrow:disabled,
QSpinBox::up-arrow:off, QDoubleSpinBox::up-arrow:off {{
    image: url({MARKS["up_off"]});
}}
QSpinBox::down-arrow:disabled, QDoubleSpinBox::down-arrow:disabled,
QSpinBox::down-arrow:off, QDoubleSpinBox::down-arrow:off {{
    image: url({MARKS["down_off"]});
}}

/* Checks and radios.  The accent is a mark at this size, so a checked box wears it. */
QCheckBox::indicator, QMenu::indicator, QGroupBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {BORDER};
    border-radius: 4px;
    background: {FIELD};
}}
QRadioButton::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {BORDER};
    border-radius: 8px;
    background: {FIELD};
}}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{
    border-color: {DIM};
}}
QCheckBox::indicator:checked, QMenu::indicator:checked, QGroupBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
    image: url({MARKS["tick"]});
}}
QRadioButton::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
    image: url({MARKS["dot"]});
}}
QCheckBox::indicator:disabled, QRadioButton::indicator:disabled {{
    background: {WINDOW};
    border-color: {BORDER};
}}
QCheckBox::indicator:checked:disabled, QRadioButton::indicator:checked:disabled {{
    background: {QUIET};
    border-color: {QUIET};
}}

/* Small print reads as small print: a note under a control, a readout on the status
   bar.  At full INK they carried the same weight as the values they describe. */
QLabel#note, QLabel#readout {{
    color: {DIM};
}}
QLabel#warn {{
    color: {WARN};
}}

QPlainTextEdit {{
    background: {FIELD};
    border: none;
    selection-background-color: {SELECT};
    selection-color: {INK};
}}

QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 5px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {DIM};
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 10px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER};
    border-radius: 5px;
    min-width: 24px;
}}
QScrollBar::handle:horizontal:hover {{
    background: {DIM};
}}
QScrollBar::add-line, QScrollBar::sub-line {{
    height: 0;
    width: 0;
}}
QScrollBar::add-page, QScrollBar::sub-page {{
    background: transparent;
}}

QSlider::groove:horizontal {{
    height: 4px;
    background: {BORDER};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT};
    width: 12px;
    height: 12px;
    margin: -4px 0;
    border-radius: 6px;
}}
QSlider::handle:horizontal:disabled {{
    background: {QUIET};
}}
QSlider::sub-page:horizontal {{
    background: {SELECT};
    border-radius: 2px;
}}

QToolBar {{
    background: {WINDOW};
    border-bottom: 1px solid {BORDER};
    padding: 3px 6px;
    spacing: 2px;
}}
QToolBar::separator {{
    width: 1px;
    background: {BORDER};
    margin: 5px 6px;
}}
QToolButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 5px;
    padding: 4px 10px;
}}
QToolButton:hover {{
    background: {HOVER};
    border-color: {BORDER};
}}
QToolButton:pressed {{
    background: {FIELD};
}}
/* A toggled verb is marked, not flooded: the quarter-strength tint and an accent
   hairline say "on" without out-shining the viewport beside it. */
QToolButton:checked {{
    background: {SELECT};
    border-color: {ACCENT};
}}
QToolButton:disabled {{
    color: {QUIET};
}}

QToolTip {{
    background: {RAISED};
    color: {INK};
    border: 1px solid {BORDER};
    padding: 5px 8px;
}}

QStatusBar {{
    background: {WINDOW};
    border-top: 1px solid {BORDER};
    color: {DIM};
}}
QStatusBar::item {{
    border: none;
}}

QProgressBar {{
    background: {FIELD};
    border: 1px solid {BORDER};
    border-radius: 4px;
    max-height: 8px;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 3px;
}}

QScrollArea, QAbstractScrollArea {{
    background: transparent;
}}
QScrollArea > QWidget > QWidget {{
    background: transparent;
}}
QSplitter::handle {{
    background: {WINDOW};
}}
"""


def apply(app: QApplication) -> None:
    """Dress the application: Fusion, the palette, the stylesheet.

    Idempotent and cheap; call once from the entrypoint.  Widgets created before or
    after both take the style, because Qt repolishes on set.
    """
    app.setStyle("Fusion")
    app.setPalette(_palette())
    app.setStyleSheet(QSS)
