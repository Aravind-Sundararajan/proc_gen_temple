"""Gopuram presets are period types: each must build, and stay the type it claims."""

import time

import pytest

from gopuram.builder import build
from gopuram.presets import PRESETS
from mandapa.export import body_count, inspect_mesh, make_mesh


def test_presets_are_the_four_named_gateways_plus_the_default():
    assert "Default (five-tala gateway)" in PRESETS
    assert len(PRESETS) == 5
    assert len({n.casefold() for n in PRESETS}) == 5  # the CLI matches names case-insensitively


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
    assert body_count(mesh) == 1, "a preset must print as one piece"
    x, y, z = mesh.bounds[1] - mesh.bounds[0]
    assert 55 <= x <= 200 and 38 <= y <= 150 and 35 <= z <= 220
    assert z > x, "a gopuram is tall before it is wide"
    # a preset exists to show a feature off; a note saying the feature was dropped is a bug
    assert not [n for n in result.notes if "skipped" in n], (name, result.notes)


def test_presets_keep_their_distinguishing_choices():
    chola = PRESETS["Early Chola gateway"]
    assert chola.talas == 3 and chola.wall_storeys == 2 and not chola.panjaras

    raya = PRESETS["Rayagopuram (Vijayanagara)"]
    assert raya.talas == 7 and raya.panjaras and raya.plinth_style == "kapotabandha"
    assert raya.wall_height >= 40

    madurai = PRESETS["Madurai Nayaka tower"]
    assert madurai.talas == 9 and madurai.kalasas == 9
    assert madurai.printer_profile == "fdm_0.25", "nine storeys of shrines need the finer nozzle"

    desk = PRESETS["Desk gopuram"]
    assert desk.base_width == 60.0 and desk.printer_profile == "fdm_0.4"
    assert desk.printable_overhangs and not desk.finial and not desk.kudus


def test_the_towers_actually_step_in_height():
    """The row Early Chola < Rayagopuram is the point of having both."""
    heights = {
        name: build(p).height for name, p in PRESETS.items() if name != "Default (five-tala gateway)"
    }
    assert heights["Early Chola gateway"] < heights["Rayagopuram (Vijayanagara)"]
    assert heights["Desk gopuram"] == min(heights.values())


def test_desk_gopuram_prints_without_supports():
    result = build(PRESETS["Desk gopuram"])
    report = inspect_mesh(make_mesh(result, union=True), result.notes)
    assert report.watertight
    assert report.overhang_fraction < 0.03, report.summary()
