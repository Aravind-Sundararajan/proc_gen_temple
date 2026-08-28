"""Gopuram print preparation: one seam, four pegs over the jambs, honest options.

The peg tolerance contract and the cut mechanics are the mandapa's, pinned in
:mod:`tests.test_printprep`; this file pins the gopuram's anatomy — where the seam
runs, where the pegs stand, and that the options offered are exactly the ones that
can work.
"""

from dataclasses import fields

import pytest

from gopuram.builder import build
from gopuram.params import GopuramParams
from gopuram.printprep import GopuramPrintOptions, peg_plan, prepare_parts
from mandapa.printprep import CUT_GAP, PEG_CLEARANCE


def test_the_whole_export_is_one_watertight_part_on_the_bed():
    parts = prepare_parts(build(GopuramParams()))
    assert len(parts) == 1 and parts[0].name == "gopuram"
    assert parts[0].mesh.is_watertight
    assert parts[0].mesh.bounds[0][2] == pytest.approx(0.0)


def test_the_split_parts_at_the_base_prastara_with_pegs():
    result = build(GopuramParams())
    parts = prepare_parts(result, GopuramPrintOptions(split=True))
    assert [p.name for p in parts] == ["base", "superstructure"]
    base, top = parts
    assert base.mesh.is_watertight and top.mesh.is_watertight
    seam = result.layout.wall_top
    pegs, notes = peg_plan(result)
    assert pegs is not None and notes == []
    assert len(pegs.points) == 4
    # the base rests on the bed and rises to the seam plus the pegs standing proud
    assert base.mesh.bounds[1][2] == pytest.approx(seam - CUT_GAP / 2 + pegs.height, abs=1e-3)
    assert all(p.colour is not None for p in parts)
    assert any("pegs" in n for n in base.notes)


def test_pegs_stand_over_the_jambs_never_the_passage():
    result = build(GopuramParams())
    pegs, _ = peg_plan(result)
    L = result.layout
    for x, y in pegs.points:
        assert abs(x) > L.door_w / 2.0 + pegs.radius
        assert abs(x) < L.talas[0].hx and abs(y) < L.talas[0].hy
    assert pegs.hole_radius == pegs.radius + PEG_CLEARANCE


def test_the_socket_stays_inside_a_thin_first_tala():
    result = build(GopuramParams(tala_height=3.0))
    pegs, notes = peg_plan(result)
    if pegs is None:
        assert any("too thin" in n for n in notes)
    else:
        assert pegs.height + 0.3 <= (result.layout.talas[0].z1 - result.layout.wall_top) + 1e-6


def test_the_options_offered_are_the_ones_that_work():
    """No hollow, no flip: a flag that can only apologise is not offered."""
    names = {f.name for f in fields(GopuramPrintOptions)}
    assert names == {"split", "bed_mm", "fit_to_bed"}
    for f in fields(GopuramPrintOptions):
        assert f.metadata.get("label") and f.metadata.get("help"), f.name


def test_the_bed_check_reports_and_the_fit_scales():
    result = build(GopuramParams())
    checked = prepare_parts(result, GopuramPrintOptions(bed_mm=(220.0, 220.0, 250.0)))
    assert any("fits the" in n for n in checked[0].notes)
    small = prepare_parts(result, GopuramPrintOptions(bed_mm=(60.0, 60.0, 60.0), fit_to_bed=True))
    assert any("scaled by" in n for n in small[0].notes)
    lo, hi = small[0].mesh.bounds
    assert max(hi - lo) <= 60.0 + 1e-6
