"""The application: ``gopuram-gen``, the mandapa editor's shell on this family's facts.

Everything behavioural is inherited from :class:`mandapa.gui.app.MainWindow` — the
docks, the verbs and their keys, the debounced rebuild, undo, files, the headless
``--screenshot`` mode — so the two editors cannot drift apart in what a key does.
What this window states is only *whose* editor it is: the class attributes below, and
the gateway glyph on the taskbar.
"""

from __future__ import annotations

import sys
from pathlib import Path

from mandapa.gui.app import MainWindow, run_editor

from .. import help as help_module
from ..builder import build
from ..document import GopuramDocument
from ..presets import PRESETS
from ..printprep import GopuramPrintOptions, prepare_parts

__all__ = ["APP_NAME", "EXAMPLES", "GopuramWindow", "main"]

APP_NAME = "Gopuram Generator"
EXAMPLES = Path(__file__).resolve().parents[2] / "examples" / "gopuram"


class GopuramWindow(MainWindow):
    APP_NAME = APP_NAME
    DOCUMENT = GopuramDocument
    BUILD = staticmethod(build)
    PRESETS = PRESETS
    EXAMPLES = EXAMPLES
    PRINT_OPTIONS = GopuramPrintOptions
    PREPARE = staticmethod(prepare_parts)
    ABOUT = help_module
    GLYPH = "gopuram"
    FILE_FILTER = "Gopuram documents (*.xml);;All files (*)"
    SAVE_FILTER = "Gopuram documents (*.xml)"


def main(argv: list[str] | None = None) -> int:
    return run_editor(GopuramWindow, prog="gopuram-gen", description="Gopuram generator GUI.",
                      file_help="gopuram document (.xml) to open", argv=argv)


if __name__ == "__main__":
    sys.exit(main())
