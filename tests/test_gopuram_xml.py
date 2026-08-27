"""The ``<gopuram>`` format: the engine's guarantees under this family's binding.

The grammar itself is pinned by :mod:`tests.test_temple_xml` against the engine; this
file pins what is the binding's own — the root tag, the independent version, the
absence of a legacy era — and above all that the two families refuse each other's
files instead of quietly misreading them.
"""

import xml.etree.ElementTree as ET
from dataclasses import fields
from pathlib import Path
from typing import get_type_hints

import pytest

from gopuram.io import FORMAT_VERSION, TempleFormatError, load_any, load_gopuram, save_gopuram
from gopuram.params import GopuramParams
from mandapa.io import load_temple, save_temple
from mandapa.look import Look
from mandapa.params import MandapaParams

CAMERA = {"azimuth": -90.0, "elevation": 8.0, "distance": 260.0, "cx": 0.0, "cy": 0.0, "cz": 55.0}


def every_field_changed() -> GopuramParams:
    """A parameter set with no field at its default, typed by declaration."""
    hints = get_type_hints(GopuramParams)
    changes = {}
    for f in fields(GopuramParams):
        default, kind, choices = f.default, hints[f.name], f.metadata.get("choices")
        if kind is bool:
            changes[f.name] = not default
        elif kind is int:
            changes[f.name] = default + 1
        elif kind is float:
            changes[f.name] = default + 0.1 + 1e-9
        else:
            changes[f.name] = next(c for c in choices if c != default)
    return GopuramParams(**changes)


def test_every_field_round_trips_exactly(tmp_path):
    params = every_field_changed()
    look = Look(light_azimuth=100.0, surface_colour=(0.7, 0.6, 0.5))
    path = tmp_path / "gateway.xml"
    save_gopuram(path, params, look, CAMERA, name="test")
    file = load_gopuram(path)
    assert file.params == params and file.look == look
    assert file.camera == CAMERA and file.name == "test" and file.ignored == ()


def test_the_root_is_gopuram_and_the_version_is_stamped(tmp_path):
    path = tmp_path / "g.xml"
    save_gopuram(path, GopuramParams())
    root = ET.parse(path).getroot()
    assert root.tag == "gopuram" and root.get("version") == str(FORMAT_VERSION)


def test_the_writer_states_every_field_once_in_declaration_order(tmp_path):
    path = tmp_path / "g.xml"
    save_gopuram(path, GopuramParams())
    names = [el.get("name") for el in ET.parse(path).getroot().iterfind("./params/param")]
    assert names == [f.name for f in fields(GopuramParams)]


def test_the_families_refuse_each_others_files(tmp_path):
    """The refusal names both tags, so the reader tells you which program to open it in."""
    temple = tmp_path / "hall.xml"
    save_temple(temple, MandapaParams())
    with pytest.raises(TempleFormatError, match="<temple>.*<gopuram>"):
        load_gopuram(temple)
    gateway = tmp_path / "gate.xml"
    save_gopuram(gateway, GopuramParams())
    with pytest.raises(TempleFormatError, match="<gopuram>.*<temple>"):
        load_temple(gateway)


def test_the_version_is_this_familys_own(tmp_path):
    path = tmp_path / "future.xml"
    path.write_text('<gopuram version="99"><params/></gopuram>', encoding="utf-8")
    with pytest.raises(TempleFormatError, match="99"):
        load_gopuram(path)


def test_unknown_names_are_ignored_and_refusals_refuse(tmp_path):
    """One spot check per engine rule, to prove the binding passes them through."""
    path = tmp_path / "g.xml"
    path.write_text(
        '<gopuram version="1"><params><param name="talas" value="7"/>'
        '<param name="from_the_future" value="1"/></params></gopuram>',
        encoding="utf-8",
    )
    file = load_gopuram(path)
    assert file.params == GopuramParams(talas=7) and file.ignored == ("from_the_future",)
    bad = tmp_path / "bad.xml"
    bad.write_text(
        '<gopuram version="1"><params><param name="plinth_style" value="dome"/></params></gopuram>',
        encoding="utf-8",
    )
    with pytest.raises(TempleFormatError, match="one of"):
        load_gopuram(bad)


def test_there_is_no_legacy_json(tmp_path):
    path = tmp_path / "old.json"
    path.write_text("{}", encoding="utf-8")
    with pytest.raises(TempleFormatError, match=r"not a gopuram document \(.xml\)"):
        load_any(path)


def test_load_any_reads_xml(tmp_path):
    path = tmp_path / "g.xml"
    save_gopuram(path, GopuramParams(talas=7), Look(), CAMERA, "t")
    assert load_any(path) == load_gopuram(path)


def test_a_missing_file_is_not_a_format_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_gopuram(tmp_path / "nope.xml")


def test_the_writer_refuses_what_the_reader_would(tmp_path):
    path = tmp_path / "g.xml"
    with pytest.raises(ValueError):
        save_gopuram(path, GopuramParams(plinth_style="dome"))
    assert not path.exists()


def test_files_are_gopuram_shaped_not_path_shaped(tmp_path):
    """Round trip through Path and str spellings; suffix case does not matter."""
    upper = tmp_path / "G.XML"
    save_gopuram(str(upper), GopuramParams(kalasas=7))
    assert load_any(Path(str(upper))).params.kalasas == 7
