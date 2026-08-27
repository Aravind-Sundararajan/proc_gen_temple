"""Every document in ``examples/gopuram/`` opens, builds, unions watertight, and is its
own design — the same promise the mandapa's examples make, held by the same checks."""

from pathlib import Path

import pytest

from gopuram.builder import build
from gopuram.document import GopuramDocument
from gopuram.io import load_any, load_gopuram, save_gopuram
from mandapa.export import body_count, inspect_mesh, make_mesh
from mandapa.io import load_temple
from mandapa.look import Look

EXAMPLES = Path(__file__).resolve().parent.parent / "examples" / "gopuram"
FILES = sorted(EXAMPLES.glob("*.xml"))
BED_MM = 220.0


def test_there_are_examples():
    assert len(FILES) >= 2


def test_the_mandapas_examples_menu_cannot_see_them():
    """The two apps' example menus glob their own directories; the mandapa's is
    non-recursive, so the subdirectory keeps the families' menus apart."""
    mandapa_examples = sorted((EXAMPLES.parent).glob("*.xml"))
    assert mandapa_examples and not set(FILES) & set(mandapa_examples)


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_each_example_builds_and_unions_watertight(path):
    file = load_any(path)
    result = build(file.params)
    for solid in result.solids():
        solid.check()
    mesh = make_mesh(result, union=True)
    report = inspect_mesh(mesh, result.notes)
    assert report.watertight and report.volume_cm3 > 0
    assert body_count(mesh) == 1
    assert max(report.size_mm) <= BED_MM


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_each_example_is_fully_authored(path):
    file = load_gopuram(path)
    assert file.name, "an example has a title"
    assert file.ignored == (), "an example states nothing this build ignores"
    assert file.look != Look(), "an example authors its look"
    assert file.look.validate() == file.look
    assert file.camera is not None and file.camera["distance"] > 0
    assert file.params.clamped() == file.params, "an example is within the panel's ranges"


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_each_example_round_trips_through_the_writer(path, tmp_path):
    file = load_gopuram(path)
    again = tmp_path / path.name
    save_gopuram(again, file.params, file.look, file.camera, file.name)
    back = load_gopuram(again)
    assert (back.params, back.look, back.camera, back.name) == (
        file.params, file.look, file.camera, file.name
    )


def test_the_examples_are_distinct_designs():
    files = [load_gopuram(p) for p in FILES]
    assert len({f.name for f in files}) == len(files)
    designs = [f.params for f in files]
    assert all(a != b for i, a in enumerate(designs) for b in designs[i + 1 :])
    assert len({f.look for f in files}) == len(files)
    assert len({f.params.talas for f in files}) == len(files), "each example is its own height of tower"


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_each_example_opens_as_a_clean_document(path):
    doc = GopuramDocument.open(path)
    assert doc.path == path and doc.name == path.stem and doc.title
    assert not doc.dirty and not doc.can_undo and doc.camera is not None


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_a_mandapa_build_refuses_them_by_name(path):
    with pytest.raises(Exception, match="<gopuram>"):
        load_temple(path)
