"""Draw the icon files PyInstaller embeds, from the editors' own glyphs.

The editors have no icon files: :mod:`mandapa.gui.icons` draws every glyph with QPainter so
the chrome's colours can be sourced from the render.  An executable needs a file, though, so
this renders each app's window glyph — "temple" for the mandapa pair, "gopuram" for its
sister — on a plate in the viewer's horizon tone and writes ``build/icons/<name>.ico``
(256 px, Windows), ``<name>.icns`` (512 px, macOS) and ``<name>.png`` (256 px).  Qt's own ICO
and ICNS writers do the encoding, so nothing new is depended on.  ``build/`` is ignored by
git and the spec leaves an icon out when a file is absent, which is also why a missing ICNS
writer (the plugin is not in every wheel) is a warning here, not a failure.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "build" / "icons"
SIZES = {"ico": 256, "icns": 512, "png": 256}
PLATE = "#21252a"  # the viewer's horizon tone (mandapa.look defaults), so the icon is the window
REQUIRED = {"ico", "png"}


def draw(concept: str, size: int) -> QImage:
    from mandapa.gui import icons, theme

    glyph = icons.pixmap(concept, theme.ACCENT, int(size * 0.78)).toImage()
    image = QImage(size, size, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(PLATE))
    radius = size * 0.2
    painter.drawRoundedRect(QRect(0, 0, size, size), radius, radius)
    inset = (size - glyph.width()) // 2
    painter.drawImage(inset, inset, glyph)
    painter.end()
    return image


def main() -> int:
    _app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    OUT.mkdir(parents=True, exist_ok=True)
    status = 0
    for name, concept in (("mandapa", "temple"), ("gopuram", "gopuram")):
        for suffix, size in SIZES.items():
            path = OUT / f"{name}.{suffix}"
            if draw(concept, size).save(str(path)):
                print(path)
            elif suffix in REQUIRED:
                print(f"could not write {path}: Qt has no {suffix} writer here", file=sys.stderr)
                status = 1
            else:
                print(f"warning: no {suffix} writer in this Qt; {path.name} skipped", file=sys.stderr)
    return status


if __name__ == "__main__":
    sys.exit(main())
