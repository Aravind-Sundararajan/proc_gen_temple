"""Presets are regional types: each one must build, and each must still be the type it claims."""

import time

import pytest

from mandapa.builder import build
from mandapa.export import body_count, inspect_mesh, make_mesh
from mandapa.presets import PRESETS


def test_presets_are_the_seven_named_designs_plus_the_default():
    assert "Default (Chola 16-pillar)" in PRESETS
    assert len(PRESETS) == 8
    assert len({n.casefold() for n in PRESETS}) == 8  # the CLI matches names case-insensitively


@pytest.mark.parametrize("name", list(PRESETS))
def test_preset_builds_watertight_in_under_three_seconds(name):
    p = PRESETS[name]
    assert p.clamped() == p, "a preset outside its own declared ranges is a typo"
    t0 = time.perf_counter()
    result = build(p)
    for s in result.solids():
        s.check()
    mesh = make_mesh(result, union=True)
    assert time.perf_counter() - t0 < 3.0
    assert mesh.is_watertight
    assert body_count(mesh) == 1, "a preset must print as one piece: no floating parts, no sealed voids"
    x, y, z = mesh.bounds[1] - mesh.bounds[0]
    assert 55 <= x <= 200 and 55 <= y <= 200 and 40 <= z <= 130
    # a preset exists to show a feature off; a note saying the feature was dropped is a bug
    assert not [n for n in result.notes if "skipped" in n], result.notes


def test_presets_keep_their_distinguishing_choices():
    pallava = PRESETS["Mahabalipuram shore pavilion"]
    assert (pallava.pillars_x, pallava.pillars_y) == (2, 2)
    assert pallava.roof_style == "stepped" and pallava.sikhara_shape == "octagonal"

    chola = PRESETS["Chola sixteen-pillar hall"]
    assert chola.pillars_x * chola.pillars_y == 16 and chola.roof_style == "hara"
    assert chola.plinth_galapadas and chola.medallions and chola.panjaras and chola.bhuta_frieze

    vij = PRESETS["Vijayanagara kalyana mandapa"]
    assert vij.footprint_x >= 140 and vij.kakshasana == "back+sides"
    assert vij.shaft_style == "fluted" and vij.corbel_style == "pushpa" and vij.dentils

    assert PRESETS["Kerala sloping roof"].roof_style == "kerala"
    assert PRESETS["Jali pavilion"].jali == "back+sides"

    shrine = PRESETS["Early Chola shrine"]
    assert shrine.sanctum == "back" and shrine.sanctum_bays == 3 and shrine.vimana
    assert shrine.roof_style == "hara" and shrine.sanctum_niches and shrine.centre_feature == "pitha"
    assert shrine.pillars_x % 2 == 0, "an even row puts the dvara in a bay, not behind a pillar"
    assert all(p.sanctum == "none" for n, p in PRESETS.items() if n != "Early Chola shrine"), (
        "the halls stay halls; the shrine is the one preset with a cell"
    )

    desk = PRESETS["Desk mandapa"]
    assert (desk.footprint_x, desk.footprint_y) == (60.0, 60.0)
    assert desk.printer_profile == "fdm_0.4" and desk.printable_overhangs
    assert not (desk.medallions or desk.kudus or desk.bhuta_frieze or desk.dentils)


def test_the_shrine_holds_an_image_and_prints_as_one_body():
    result = build(PRESETS["Early Chola shrine"])
    cell = result.layout.cell
    w, d, h = cell.clear
    assert w > 45 and d > 45 and h > 30, "room for a desk-sized vigraham at scale 1"
    assert cell.door_w > 12 and cell.door_h == pytest.approx(2 * cell.door_w)
    assert (cell.i0, cell.i1, cell.j0, cell.j1) == (0, 3, 1, 3), "the width of the hall, a porch in front"
    assert len(result.layout.pillar_points) == 16 - 2, "the two pillars inside the cell"
    assert len([s for s in result.parts["sanctum"] if s.name == "niche"]) == 9 * 3
    mesh = make_mesh(result, union=True)
    assert mesh.is_watertight and body_count(mesh) == 1
    assert mesh.bounds[1][2] > result.layout.roof_z + 30, "the vimana stands well above the hall roof"


def test_desk_mandapa_prints_without_supports():
    result = build(PRESETS["Desk mandapa"])
    report = inspect_mesh(make_mesh(result, union=True), result.notes)
    assert report.watertight
    # what remains steeper than 45° is the capital's kalasa and kumbha bulges, each under 1.5 mm
    assert report.overhang_fraction < 0.03, report.summary()
