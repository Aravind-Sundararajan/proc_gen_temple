"""What the editor remembers between sessions — and nothing the document should own.

Recent files, the printer's bed, which sections an author folded away, where the window
was: habits of the *person*, not facts about the *design*.  The design's facts (look,
camera) travel in the document, so a file opened on another machine renders the same;
these travel with the user, so a new file opens the way the last one was left.

A :class:`Preferences` wraps a ``QSettings`` rather than being one so the tests can hand
it an ini file in a temp directory and never touch the registry.
"""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QByteArray, QSettings
from PySide6.QtWidgets import QMainWindow

__all__ = ["DEFAULT_BED", "RECENT_LIMIT", "Preferences"]

#: The print bed assumed until the author says otherwise: a common 220 mm FDM plate.
DEFAULT_BED: tuple[float, float, float] = (220.0, 220.0, 250.0)
#: How many recent files the menu lists.  Eight fits a menu; more is a file browser.
RECENT_LIMIT = 8


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


class Preferences:
    def __init__(self, settings: QSettings | None = None):
        self.settings = settings if settings is not None else QSettings("mandapa", "Mandapa Generator")

    # ---- recent files -------------------------------------------------------------------
    def recent(self) -> list[Path]:
        """Most recent first.  Paths that no longer exist are dropped on read rather than
        kept as dead menu items; a file that comes back is simply opened again."""
        raw = self.settings.value("files/recent", [])
        if isinstance(raw, str):
            raw = [raw]
        paths = [Path(p) for p in (raw or []) if isinstance(p, str) and p]
        return [p for p in paths if p.exists()]

    def add_recent(self, path: str | Path) -> None:
        path = Path(path).resolve()
        paths = [p for p in self.recent() if p != path]
        paths.insert(0, path)
        self._write_recent(paths[:RECENT_LIMIT])

    def remove_recent(self, path: str | Path) -> None:
        path = Path(path).resolve()
        self._write_recent([p for p in self.recent() if p != path])

    def clear_recent(self) -> None:
        self._write_recent([])

    def _write_recent(self, paths: list[Path]) -> None:
        self.settings.setValue("files/recent", [str(p) for p in paths])
        self.settings.sync()

    # ---- the print bed ------------------------------------------------------------------
    def bed(self) -> tuple[float, float, float]:
        raw = self.settings.value("bed/size", "")
        try:
            x, y, z = (float(v) for v in str(raw).split())
        except ValueError:
            return DEFAULT_BED
        if min(x, y, z) <= 0:
            return DEFAULT_BED
        return (x, y, z)

    def set_bed(self, size: tuple[float, float, float]) -> None:
        self.settings.setValue("bed/size", " ".join(f"{float(v):g}" for v in size))
        self.settings.sync()

    # ---- folded sections ----------------------------------------------------------------
    def section_expanded(self, title: str) -> bool:
        return bool(self.settings.value(f"panel/expanded/{_slug(title)}", True, type=bool))

    def set_section_expanded(self, title: str, expanded: bool) -> None:
        self.settings.setValue(f"panel/expanded/{_slug(title)}", bool(expanded))

    # ---- view toggles -------------------------------------------------------------------
    def flag(self, name: str, default: bool) -> bool:
        return bool(self.settings.value(f"view/{name}", default, type=bool))

    def set_flag(self, name: str, value: bool) -> None:
        self.settings.setValue(f"view/{name}", bool(value))

    # ---- the window ---------------------------------------------------------------------
    def save_window(self, window: QMainWindow) -> None:
        self.settings.setValue("window/geometry", window.saveGeometry())
        self.settings.setValue("window/state", window.saveState())
        self.settings.sync()

    def restore_window(self, window: QMainWindow) -> bool:
        geometry = self.settings.value("window/geometry")
        state = self.settings.value("window/state")
        restored = False
        if isinstance(geometry, QByteArray) and not geometry.isEmpty():
            restored = window.restoreGeometry(geometry)
        if isinstance(state, QByteArray) and not state.isEmpty():
            window.restoreState(state)
        return bool(restored)
