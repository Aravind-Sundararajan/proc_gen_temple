"""Serialisation.  Depends on ``params`` and ``look``; nothing in them depends on this.

:mod:`~mandapa.io.temple_xml` is the format to write: the versioned ``<temple>``
document.  :func:`load_any` also reads the parameters JSON the CLI wrote before the
format existed, and never writes it.  Nothing here imports Qt, OpenGL or a mesh library;
a machine that can import :mod:`mandapa.params` can read and write a design.
"""

from .temple_xml import (
    CAMERA_KEYS,
    FORMAT_VERSION,
    TempleFile,
    TempleFormatError,
    load_any,
    load_temple,
    save_temple,
)

__all__ = [
    "CAMERA_KEYS",
    "FORMAT_VERSION",
    "TempleFile",
    "TempleFormatError",
    "load_any",
    "load_temple",
    "save_temple",
]
