"""The icon vocabulary: one name per verb, drawn with QPainter, tinted from the theme.

Every glyph the window shows is painted here from a few strokes in a 24-unit box, and
every one is named here rather than at its use site: a verb that picks its own glyph in
three places grows three glyphs, and the drift is invisible until the toolbar's Fit is a
box and the menu's Fit is a pair of arrows.  Drawing them in code rather than shipping
image files keeps them in the palette's colours by construction — recolour :data:`DIM`
and every icon follows, with nothing on disk to go stale.

The choices lean on what the app *means*: Build is a mallet because the temple is built;
Front, Side and Top are the elevation, the end and the plan, the drawings an architect
would make; Union is two shells becoming one.  A metaphor an author has to learn twice is
worse than a word, which is also why the toolbar shows the word beside the glyph.
"""

from __future__ import annotations

import math
from collections.abc import Callable

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap

from . import theme

__all__ = ["GLYPHS", "icon", "pixmap"]

Glyph = Callable[[QPainter], None]

#: Logical edge of the box every glyph is drawn in.
BOX = 24.0
#: Stroke width in box units; 1.8 at 24 px is a confident line that survives 16 px.
STROKE = 1.8


def _pen(painter: QPainter, width: float = STROKE) -> None:
    pen = QPen(painter.pen().color(), width)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)


def _poly(painter: QPainter, *points: tuple[float, float], close: bool = False) -> None:
    path = QPainterPath(QPointF(*points[0]))
    for x, y in points[1:]:
        path.lineTo(x, y)
    if close:
        path.closeSubpath()
    painter.drawPath(path)


def _arrow_head(painter: QPainter, tip: tuple[float, float], angle_deg: float, size: float = 4.0) -> None:
    """An open arrow head whose point is at ``tip``, pointing along ``angle_deg``."""
    a = math.radians(angle_deg)
    left = (tip[0] - size * math.cos(a - 0.6), tip[1] - size * math.sin(a - 0.6))
    right = (tip[0] - size * math.cos(a + 0.6), tip[1] - size * math.sin(a + 0.6))
    _poly(painter, left, tip, right)


def _arc_arrow(painter: QPainter, clockwise: bool, radius: float = 7.0) -> None:
    """Three quarters of a circle with a head: the orbit, the undo, the reset.

    Qt measures arc angles counter-clockwise from three o'clock; the head sits on the
    arc's end and points along its direction of travel there.
    """
    rect = QRectF(12 - radius, 12 - radius, 2 * radius, 2 * radius)
    start, span = (60, -270) if clockwise else (120, 270)
    painter.drawArc(rect, start * 16, span * 16)
    end = math.radians(start + span)
    tip = (12 + radius * math.cos(end), 12 - radius * math.sin(end))
    sign = 1.0 if clockwise else -1.0
    heading = math.degrees(math.atan2(sign * math.cos(end), sign * math.sin(end)))
    _arrow_head(painter, tip, heading, 0.6 * radius)


# ---- the glyphs --------------------------------------------------------------------------


def _temple(p: QPainter) -> None:
    """The app: plinth, two pillars, a beam, a stepped crown with a finial."""
    _poly(p, (3, 20), (21, 20))
    _poly(p, (5, 17), (19, 17))
    _poly(p, (8, 17), (8, 11))
    _poly(p, (16, 17), (16, 11))
    _poly(p, (5, 11), (19, 11))
    _poly(p, (7, 8), (17, 8))
    _poly(p, (10, 5.5), (14, 5.5))
    _poly(p, (12, 5.5), (12, 3))


def _build(p: QPainter) -> None:
    """A mallet: the head is a rotated slab, the handle runs to the corner."""
    _poly(p, (5, 19), (12, 12))
    p.save()
    p.translate(15, 9)
    p.rotate(45)
    p.drawRoundedRect(QRectF(-6, -3, 12, 6), 1.5, 1.5)
    p.restore()


def _fit(p: QPainter) -> None:
    """Four corner brackets around a small square: frame the subject."""
    for sx in (-1, 1):
        for sy in (-1, 1):
            cx, cy = 12 + sx * 8, 12 + sy * 8
            _poly(p, (cx, cy - sy * 5), (cx, cy), (cx - sx * 5, cy))
    p.drawRect(QRectF(9.5, 9.5, 5, 5))


def _front(p: QPainter) -> None:
    """The elevation: a wide face with its plinth line."""
    p.drawRect(QRectF(4, 6, 16, 12))
    _poly(p, (4, 15), (20, 15))


def _side(p: QPainter) -> None:
    """The end: a narrower face, the same plinth line."""
    p.drawRect(QRectF(7, 6, 10, 12))
    _poly(p, (7, 15), (17, 15))


def _top(p: QPainter) -> None:
    """The plan: the roof outline with the colonnade inside it."""
    p.drawRect(QRectF(4, 4, 16, 16))
    p.drawRect(QRectF(8, 8, 8, 8))


def _ortho(p: QPainter) -> None:
    """A cube whose receding edges stay parallel — which is what orthographic means."""
    p.drawRect(QRectF(4, 9, 11, 11))
    _poly(p, (4, 9), (9, 4), (20, 4), (20, 15), (15, 20))
    _poly(p, (15, 9), (20, 4))


def _risks(p: QPainter) -> None:
    """A warning triangle: the overhangs and bridges the printer will object to."""
    _poly(p, (12, 4), (21, 20), (3, 20), close=True)
    _poly(p, (12, 10), (12, 14.5))
    p.drawPoint(QPointF(12, 17.5))


def _union(p: QPainter) -> None:
    """Two shells and the lens where they become one solid."""
    a = QPainterPath()
    a.addEllipse(QRectF(3, 7, 11, 11))
    b = QPainterPath()
    b.addEllipse(QRectF(10, 7, 11, 11))
    p.drawPath(a)
    p.drawPath(b)
    p.fillPath(a.intersected(b), p.pen().color())


def _wireframe(p: QPainter) -> None:
    """A quad split into its triangles: the mesh under the shading."""
    p.drawRect(QRectF(4, 4, 16, 16))
    _poly(p, (4, 20), (20, 4))
    _poly(p, (4, 12), (12, 4))
    _poly(p, (12, 20), (20, 12))


def _grid(p: QPainter) -> None:
    for v in (4, 9.33, 14.67, 20):
        _poly(p, (v, 4), (v, 20))
        _poly(p, (4, v), (20, v))


def _bed(p: QPainter) -> None:
    """The print bed: a plate in perspective with a small part standing on it."""
    _poly(p, (3, 18), (8, 11), (21, 11), (16, 18), close=True)
    p.drawRect(QRectF(10.5, 6.5, 4, 4.5))


def _turntable(p: QPainter) -> None:
    _arc_arrow(p, clockwise=True)
    p.drawPoint(QPointF(12, 12))


def _screenshot(p: QPainter) -> None:
    """A camera: body, lens, the bump of the viewfinder."""
    p.drawRoundedRect(QRectF(3, 7, 18, 13), 2, 2)
    p.drawEllipse(QRectF(9, 10, 7, 7))
    _poly(p, (8, 7), (9.5, 4.5), (14.5, 4.5), (16, 7))


def _randomise(p: QPainter) -> None:
    """A die showing five."""
    p.drawRoundedRect(QRectF(4, 4, 16, 16), 3, 3)
    for x, y in ((8, 8), (16, 8), (12, 12), (8, 16), (16, 16)):
        p.drawPoint(QPointF(x, y))


def _export(p: QPainter) -> None:
    """A tray and an arrow leaving it: the file goes out to the printer."""
    _poly(p, (4, 14), (4, 20), (20, 20), (20, 14))
    _poly(p, (12, 16), (12, 4))
    _arrow_head(p, (12, 4), -90, 4.5)


def _save(p: QPainter) -> None:
    """The same tray, the arrow arriving."""
    _poly(p, (4, 14), (4, 20), (20, 20), (20, 14))
    _poly(p, (12, 3), (12, 15))
    _arrow_head(p, (12, 15), 90, 4.5)


def _open(p: QPainter) -> None:
    """A folder."""
    _poly(p, (3, 7), (3, 19), (21, 19), (21, 10), (11, 10), (9, 7), close=True)


def _new(p: QPainter) -> None:
    """A page with a folded corner."""
    _poly(p, (6, 3), (14, 3), (19, 8), (19, 21), (6, 21), close=True)
    _poly(p, (14, 3), (14, 8), (19, 8))


def _undo(p: QPainter) -> None:
    _arc_arrow(p, clockwise=False)


def _redo(p: QPainter) -> None:
    _arc_arrow(p, clockwise=True)


def _reset(p: QPainter) -> None:
    """Undo's arrow at a smaller radius: back to where the defaults were."""
    _arc_arrow(p, clockwise=False, radius=5.5)


def _search(p: QPainter) -> None:
    p.drawEllipse(QRectF(4, 4, 11, 11))
    _poly(p, (13.5, 13.5), (20, 20))


def _chevron_down(p: QPainter) -> None:
    _poly(p, (7, 10), (12, 15), (17, 10))


def _chevron_right(p: QPainter) -> None:
    _poly(p, (10, 7), (15, 12), (10, 17))


def _light(p: QPainter) -> None:
    """The key light: a sun low over the horizon line."""
    p.drawEllipse(QRectF(8, 8, 8, 8))
    for k in range(8):
        a = math.radians(45 * k)
        _poly(p, (12 + 6.5 * math.cos(a), 12 + 6.5 * math.sin(a)), (12 + 9 * math.cos(a), 12 + 9 * math.sin(a)))


def _clear(p: QPainter) -> None:
    _poly(p, (7, 7), (17, 17))
    _poly(p, (17, 7), (7, 17))


#: Verb to glyph.  The toolbar, the menus and the docks all draw from this one table.
GLYPHS: dict[str, Glyph] = {
    "temple": _temple,
    "build": _build,
    "fit": _fit,
    "front": _front,
    "side": _side,
    "top": _top,
    "ortho": _ortho,
    "risks": _risks,
    "union": _union,
    "wireframe": _wireframe,
    "grid": _grid,
    "bed": _bed,
    "turntable": _turntable,
    "screenshot": _screenshot,
    "randomise": _randomise,
    "export": _export,
    "save": _save,
    "open": _open,
    "new": _new,
    "undo": _undo,
    "redo": _redo,
    "reset": _reset,
    "search": _search,
    "chevron_down": _chevron_down,
    "chevron_right": _chevron_right,
    "light": _light,
    "clear": _clear,
}

_cache: dict[tuple[str, str, int], QPixmap] = {}


def pixmap(concept: str, colour: str, size: int = 24) -> QPixmap:
    """The glyph at ``size`` pixels in one colour.  Unknown concepts raise.

    A silently blank icon is a button an author cannot find, and the typo that caused it
    would survive every test that only checks the button exists.
    """
    try:
        glyph = GLYPHS[concept]
    except KeyError:
        raise KeyError(f"no icon named {concept!r}; add it to mandapa.gui.icons.GLYPHS") from None
    key = (concept, colour, size)
    if key in _cache:
        return _cache[key]
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.scale(size / BOX, size / BOX)
    painter.setPen(QColor(colour))
    _pen(painter)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    glyph(painter)
    painter.end()
    result = QPixmap.fromImage(image)
    _cache[key] = result
    return result


def icon(concept: str, colour: str | None = None) -> QIcon:
    """The glyph for ``concept`` as a QIcon with every mode the chrome uses.

    Normal is :data:`theme.DIM` (or ``colour``), hover is :data:`theme.INK`, disabled is
    :data:`theme.QUIET`, and the *On* state of a checkable verb is the accent — the
    glyph is the mark, while the button behind it wears only the quarter-strength tint.
    """
    result = QIcon()
    normal = colour or theme.DIM
    modes = {
        QIcon.Mode.Normal: normal,
        QIcon.Mode.Active: theme.INK,
        QIcon.Mode.Selected: theme.INK,
        QIcon.Mode.Disabled: theme.QUIET,
    }
    for size in (16, 20, 24, 32, 48):
        for mode, tone in modes.items():
            result.addPixmap(pixmap(concept, tone, size), mode, QIcon.State.Off)
            on = theme.QUIET if mode == QIcon.Mode.Disabled else theme.ACCENT
            result.addPixmap(pixmap(concept, on, size), mode, QIcon.State.On)
    return result
