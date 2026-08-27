"""The gopuram's document is the mandapa's machinery on this family's facts.

The command, undo and event rules are pinned in :mod:`tests.test_document` against the
base class; this file pins only the binding — that a fresh document is a gopuram, that
the file it writes is a ``<gopuram>``, and that the machinery actually runs on the
subclass rather than merely being inherited on paper.
"""

import pytest

from gopuram.document import GopuramDocument, SetParams
from gopuram.params import GopuramParams
from mandapa.document import Document


def test_a_fresh_document_is_a_gopuram():
    document = GopuramDocument()
    assert isinstance(document, Document)
    assert type(document.params) is GopuramParams
    assert document.name == "untitled" and not document.dirty


def test_save_and_open_round_trip(tmp_path):
    document = GopuramDocument(GopuramParams(talas=7))
    document.title = "Seven talas"
    path = document.save(tmp_path / "gate.xml", camera={
        "azimuth": -90.0, "elevation": 8.0, "distance": 260.0, "cx": 0.0, "cy": 0.0, "cz": 55.0,
    })
    again = GopuramDocument.open(path)
    assert type(again) is GopuramDocument and type(again.params) is GopuramParams
    assert again.params.talas == 7 and again.title == "Seven talas"
    assert again.camera is not None and not again.dirty


def test_the_error_vocabulary_names_the_family(tmp_path):
    with pytest.raises(ValueError, match="a gopuram document is XML"):
        GopuramDocument().save(tmp_path / "gate.stl")


def test_commands_and_undo_run_on_the_subclass():
    document = GopuramDocument()
    document.submit(SetParams({"talas": 7, "kalasas": 9}))
    assert document.params.talas == 7 and document.dirty
    assert document.undo()
    assert document.params == GopuramParams() and not document.dirty


def test_a_mandapa_file_does_not_open_as_a_gopuram(tmp_path):
    Document().save(tmp_path / "hall.xml")
    with pytest.raises(Exception, match="<temple>"):
        GopuramDocument.open(tmp_path / "hall.xml")
