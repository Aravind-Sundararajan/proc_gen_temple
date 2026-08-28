"""Serialisation: the versioned ``<gopuram>`` document, through the mandapa's engine.

Nothing here imports Qt, OpenGL or a mesh library; a machine that can import
:mod:`gopuram.params` can read and write a design.
"""

from .gopuram_xml import (
    CAMERA_KEYS,
    FORMAT_VERSION,
    TempleFile,
    TempleFormatError,
    load_any,
    load_gopuram,
    save_gopuram,
)

__all__ = [
    "CAMERA_KEYS",
    "FORMAT_VERSION",
    "TempleFile",
    "TempleFormatError",
    "load_any",
    "load_gopuram",
    "save_gopuram",
]
