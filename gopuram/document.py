"""The gopuram's document: the mandapa's, with this family's three facts filled in.

Everything behavioural — commands, coalescing, batched events, the undo rules —
is :class:`mandapa.document.Document`'s, because none of it cares which building the
record describes; the tests that pin those rules run against the base class and hold
for this one.  What differs is what a fresh document starts from and how it reaches
disk, and those are the class attributes the base class defined for exactly this.
"""

from __future__ import annotations

from mandapa.document import Document, Macro, ReplaceDesign, SetLook, SetParams

from .io import load_any, save_gopuram
from .params import GopuramParams

__all__ = ["GopuramDocument", "Macro", "ReplaceDesign", "SetLook", "SetParams"]


class GopuramDocument(Document):
    PARAMS = GopuramParams
    LOAD = staticmethod(load_any)
    SAVE = staticmethod(save_gopuram)
    KIND = "gopuram"
