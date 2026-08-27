"""The on-disk design format: ``<gopuram version="1">``, the mandapa engine's rules.

The layout, the record grammar, the refusal rules, ``<look>`` and ``<camera>`` are all
:mod:`mandapa.io.temple_xml`'s — that module's docstring is the specification, and the
functions here are the same functions bound to this family's root tag, parameter class
and version.  What is this module's own:

* **The root is ``<gopuram>``.**  Every gopuram parameter name would be "unknown" to a
  mandapa reader, so under a shared root a gopuram file would open as the default
  mandapa with a polite note — the silent misreading the format exists to refuse.  A
  mandapa build opening a gopuram file (or the reverse) fails naming both tags instead.
* **The version is this family's own**, starting again at 1.  A semantic change to a
  gopuram attribute must not force every mandapa file to a new number, nor the reverse.
* **There is no legacy JSON.**  The gopuram never had a pre-XML era, so
  :func:`load_any` reads ``.xml`` and refuses everything else by name — inventing
  support for a format no file was ever written in would be a reader with no writer.
"""

from __future__ import annotations

from pathlib import Path

from mandapa.io import CAMERA_KEYS, TempleFile, TempleFormatError, load_temple, save_temple
from mandapa.look import Look

from ..params import GopuramParams

__all__ = [
    "CAMERA_KEYS",
    "FORMAT_VERSION",
    "TempleFile",
    "TempleFormatError",
    "load_any",
    "load_gopuram",
    "save_gopuram",
]

FORMAT_VERSION = 1


def save_gopuram(
    path: str | Path,
    params: GopuramParams,
    look: Look | None = None,
    camera: dict[str, float] | None = None,
    name: str = "",
) -> None:
    """Write a version-1 ``<gopuram>`` document; the engine's guarantees apply."""
    save_temple(path, params, look, camera, name, root_tag="gopuram", version=FORMAT_VERSION)


def load_gopuram(path: str | Path) -> TempleFile:
    """Read a ``<gopuram>`` document.  Raises :class:`TempleFormatError` naming the path
    for anything this build cannot read."""
    return load_temple(path, root_tag="gopuram", params_cls=GopuramParams, version=FORMAT_VERSION)


def load_any(path: str | Path) -> TempleFile:
    """Read a ``<gopuram>`` document (``.xml``); anything else is refused by name."""
    path = Path(path)
    if path.suffix.lower() == ".xml":
        return load_gopuram(path)
    raise TempleFormatError(f"{path}: not a gopuram document (.xml)")
