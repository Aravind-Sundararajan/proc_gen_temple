"""Every document in ``examples/`` opens, builds, unions watertight, and is its own design.

An example is a promise: open it and it works.  So each file is put through the whole
pipeline here, and a few authoring rules are pinned — a title, an authored look, no
parameter this build ignores — because the files are hand-curated and nothing else checks
them.
"""

from pathlib import Path

import pytest

from mandapa.builder import build
from mandapa.document import Document
from mandapa.export import inspect_mesh, make_mesh
from mandapa.io import load_any, load_temple, save_temple
from mandapa.look import Look

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"
FILES = sorted(EXAMPLES.glob("*.xml"))
BED_MM = 220.0


def test_there_are_examples():
    assert len(FILES) >= 6


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_each_example_builds_and_unions_watertight(path):
    file = load_any(path)
    result = build(file.params)
    for solid in result.solids():
        solid.check()
    mesh = make_mesh(result, union=True)
    report = inspect_mesh(mesh, result.notes)
    assert report.watertight and report.volume_cm3 > 0
    assert max(report.size_mm) <= BED_MM


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_each_example_is_fully_authored(path):
    file = load_temple(path)
    assert file.name, "an example has a title"
    assert file.ignored == (), "an example states nothing this build ignores"
    assert file.look != Look(), "an example authors its look"
    assert file.look.validate() == file.look
    assert file.camera is not None and file.camera["distance"] > 0
    assert file.params.clamped() == file.params, "an example is within the panel's ranges"


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_each_example_round_trips_through_the_writer(path, tmp_path):
    file = load_temple(path)
    again = tmp_path / path.name
    save_temple(again, file.params, file.look, file.camera, file.name)
    back = load_temple(again)
    assert (back.params, back.look, back.camera, back.name) == (
        file.params, file.look, file.camera, file.name
    )


def test_the_examples_are_distinct_designs():
    files = [load_temple(p) for p in FILES]
    assert len({f.name for f in files}) == len(files)
    designs = [f.params for f in files]  # not hashable: compare pairwise by value
    assert all(a != b for i, a in enumerate(designs) for b in designs[i + 1 :])
    assert len({f.look for f in files}) == len(files)
    assert len({f.params.roof_style for f in files}) == 3, "hara, stepped and flat all appear"
    assert len({f.params.plinth_style for f in files}) >= 3
    assert {f.params.steps for f in files} == {True, False}


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_each_example_opens_as_a_clean_document(path):
    doc = Document.open(path)
    assert doc.path == path and doc.name == path.stem and doc.title
    assert not doc.dirty and not doc.can_undo and doc.camera is not None
