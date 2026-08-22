"""The garbhagriha: where the cell stands, what fits inside it, and that the building stays one body.

A sanctum exists so that an image can stand in it, so the numbers pinned here are the ones a
vigraham meets — the clear cavity, the doorway, the raised floor — and the one a printer
meets: the doorway is the only way in, and the union stays one shell because of it.
"""

import math

import numpy as np
import pytest

import mandapa.cli
from mandapa.builder import OVERLAP, build, centred_run, scale_for_vigraham
from mandapa.export import body_count, make_mesh
from mandapa.params import MandapaParams
from mandapa.printprep import PrintOptions, peg_plan, prepare_parts

NUDGE = (0.0137, 0.0071)  # off every symmetry axis, so a vertical probe ray never grazes an edge


def _build(**changes):
    result = build(MandapaParams().with_(**changes))
    for s in result.solids():
        s.check()
    return result


def _named(result, group, name):
    return [s for s in result.parts.get(group, []) if s.name == name]


def contains(mesh, points) -> np.ndarray:
    """Point-in-solid by vertical ray parity, as in test_printprep (trimesh's own needs rtree)."""
    a, b, c = mesh.triangles[:, 0], mesh.triangles[:, 1], mesh.triangles[:, 2]
    det = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
    flat = np.abs(det) > 1e-12
    safe = np.where(flat, det, 1.0)
    result = []
    for px, py, pz in np.asarray(points, dtype=float):
        l1 = ((b[:, 1] - c[:, 1]) * (px - c[:, 0]) + (c[:, 0] - b[:, 0]) * (py - c[:, 1])) / safe
        l2 = ((c[:, 1] - a[:, 1]) * (px - c[:, 0]) + (a[:, 0] - c[:, 0]) * (py - c[:, 1])) / safe
        l3 = 1.0 - l1 - l2
        under = flat & (l1 >= 0) & (l2 >= 0) & (l3 >= 0)
        z = l1 * a[:, 2] + l2 * b[:, 2] + l3 * c[:, 2]
        result.append(int(np.sum(under & (z > pz))) % 2 == 1)
    return np.array(result)


# ---- where the cell stands -------------------------------------------------------------


@pytest.mark.parametrize(
    "n_bays,k,expected",
    [
        (3, 1, (1, 2)), (3, 2, (1, 2)), (3, 3, (0, 3)),  # four pillars: the middle bay, or all
        (2, 1, (0, 2)),  # three pillars: no centre bay, only a centre pillar
        (4, 1, (1, 3)), (4, 3, (1, 3)), (4, 2, (1, 3)),
        (1, 1, (0, 1)), (5, 2, (2, 3)), (6, 3, (2, 4)),
    ],
)
def test_a_run_of_bays_is_centred_or_moved_to_the_nearest_count_that_is(n_bays, k, expected):
    i0, i1 = centred_run(n_bays, k)
    assert (i0, i1) == expected
    assert i0 == n_bays - i1, "the same number of bays on either side"


def test_the_default_hall_has_no_sanctum():
    result = build(MandapaParams())
    assert "sanctum" not in result.parts and result.layout.cell is None
    assert len(result.layout.pillar_points) == 16


def test_back_cell_stands_in_the_back_bay_on_the_pillar_lines():
    result = _build(sanctum="back")
    L, cell = result.layout, result.layout.cell
    assert (cell.i0, cell.i1, cell.j0, cell.j1) == (1, 2, 2, 3)
    assert (cell.x0, cell.x1) == (L.pillar_xs[1], L.pillar_xs[2])
    assert (cell.y0, cell.y1) == (L.pillar_ys[2], L.pillar_ys[3])
    assert cell.t == pytest.approx(1.15 * 6.0)
    walls = _named(result, "sanctum", "wall")
    assert len(walls) == 3
    assert len(_named(result, "sanctum", "jamb")) == 2 and len(_named(result, "sanctum", "lintel")) == 1
    back = max(walls, key=lambda s: s.bounds[1][1])
    assert back.bounds[1][1] == pytest.approx(cell.y1 + cell.t / 2)
    assert back.bounds[0][2] == pytest.approx(L.floor_z - OVERLAP)
    assert back.bounds[1][2] == pytest.approx(L.beam_z0 + OVERLAP), "the wall sinks into the beam"
    w, d, h = cell.clear
    assert w == pytest.approx(L.pillar_xs[2] - L.pillar_xs[1] - cell.t) and d == pytest.approx(w)
    assert cell.z_floor == pytest.approx(L.floor_z + 0.08 * 35.0) and h == pytest.approx(35.0 - 2.8)
    assert len(L.pillar_points) == 16, "a one-bay cell swallows its four pillars, it does not lose them"
    line = next(n for n in result.notes if n.startswith("garbhagriha:"))
    assert f"{w:.1f} x {d:.1f} mm between the walls, {h:.1f} mm" in line
    assert f"dvara {cell.door_w:.1f} x {cell.door_h:.1f} mm" in line


def test_centre_cell_is_centred_with_an_ambulatory_round_it():
    result = _build(sanctum="centre")
    cell = result.layout.cell
    assert (cell.i0, cell.i1, cell.j0, cell.j1) == (1, 2, 1, 2)
    assert cell.cx == pytest.approx(0.0) and cell.cy == pytest.approx(0.0)
    xo0, xo1, yo0, yo1 = cell.outer
    medallions = _named(result, "pillars", "medallion")
    assert len(medallions) == 16 * 2 * 4
    outside = [
        m for m in medallions
        if m.bounds[1][0] < xo0 or m.bounds[0][0] > xo1 or m.bounds[1][1] < yo0 or m.bounds[0][1] > yo1
    ]
    assert len(outside) == 12 * 8, "twelve pillars stand free; four are inside the walls"


def test_cells_follow_the_grid_parity_and_say_so():
    odd = _build(sanctum="centre", pillars_x=3, pillars_y=3)
    c = odd.layout.cell
    assert (c.i0, c.i1, c.j0, c.j1) == (0, 2, 0, 2)
    assert any("widened to 2 bay(s)" in n for n in odd.notes)
    assert any("takes the whole hall" in n for n in odd.notes)
    five = _build(sanctum="centre", pillars_x=5, pillars_y=5, footprint_x=140, footprint_y=140)
    assert (five.layout.cell.i0, five.layout.cell.i1) == (1, 3)
    two = _build(sanctum="back", sanctum_bays=2)
    c = two.layout.cell
    assert (c.i0, c.i1, c.j0, c.j1) == (1, 2, 1, 3), "narrowed across, two bays deep"
    assert any("narrowed to 1 bay(s)" in n for n in two.notes)
    shallow = _build(sanctum="back", pillars_y=2)
    assert (shallow.layout.cell.j0, shallow.layout.cell.j1) == (0, 1)
    crowded = _build(sanctum="back", footprint_x=45, footprint_y=45, pillar_width=8)
    assert crowded.layout.cell is None and "sanctum" not in crowded.parts
    assert any("too close for a sanctum" in n for n in crowded.notes)


# ---- the doorway and the cavity --------------------------------------------------------


def test_the_dvara_is_twice_as_high_as_wide_and_the_only_way_in():
    result = _build(sanctum="back")
    L, cell = result.layout, result.layout.cell
    assert cell.door_w == pytest.approx(0.5 * cell.clear[0])
    assert cell.door_h == pytest.approx(2.0 * cell.door_w)
    mesh = make_mesh(result, union=True)
    assert mesh.is_watertight and body_count(mesh) == 1, "the cell is open, not a sealed void"
    dx, dy = NUDGE
    y_wall = cell.y0 + dy
    zc = cell.z_floor + cell.door_h / 2
    sill_z = L.floor_z + 0.5 * (cell.z_floor - L.floor_z)
    assert not contains(mesh, [[cell.cx + dx, y_wall, zc]]).any(), "the doorway is open"
    solid = [
        [cell.cx + cell.door_w / 2 + 1.0 + dx, y_wall, zc],  # jamb
        [cell.cx + dx, y_wall, cell.z_floor + cell.door_h + 0.5],  # lintel
        [cell.cx + dx, y_wall, sill_z],  # udumbara
        [cell.cx + dx, cell.cy + dy, sill_z],  # raised floor
    ]
    assert contains(mesh, solid).all()
    cavity = [[cell.cx + dx, cell.cy + dy, cell.z_floor + 0.5], [cell.cx + dx, cell.cy + dy, cell.z_top - 0.5]]
    assert not contains(mesh, cavity).any(), "nothing stands in the cell"

    low = _build(sanctum="back", dvara_width=0.8, pillar_height=20.0)
    c = low.layout.cell
    wall_h = c.z_top - c.z_floor
    assert c.door_h == pytest.approx(wall_h - max(0.15 * wall_h, 1.6)) and c.door_h == pytest.approx(2 * c.door_w)
    assert c.door_w < 0.8 * c.clear[0], "narrowed to keep its proportion, not squashed"
    level = _build(sanctum="back", sanctum_floor=0.0)
    assert not _named(level, "sanctum", "floor") and not _named(level, "sanctum", "udumbara")


def test_pillars_inside_the_cell_and_in_its_doorway_are_not_built():
    result = _build(
        sanctum="centre", sanctum_bays=2, pillars_x=5, pillars_y=5, footprint_x=140, footprint_y=140
    )
    L = result.layout
    assert len(L.pillar_points) == 23
    assert (2, 2) not in L.pillar_points, "the middle of the cell"
    assert (2, 1) not in L.pillar_points, "the middle of the doorway"
    assert len(_named(result, "pillars", "phalaka")) == 23
    floor, _beam, _ = peg_plan(result)
    assert len(floor.points) == 23
    parts = prepare_parts(result, PrintOptions(split=True))
    assert [p.name for p in parts] == ["base", "colonnade", "roof"]
    assert all(p.mesh.is_watertight and p.mesh.volume > 0 for p in parts)
    assert body_count(parts[1].mesh) < 23, "the walls join the pillars they swallow"


def test_the_pitha_moves_on_to_the_cell_floor_and_reports_the_height_left():
    result = _build(sanctum="back", centre_feature="pitha")
    cell = result.layout.cell
    pitha = _named(result, "enclosure", "pitha")
    assert len(pitha) == 1
    lo, hi = pitha[0].bounds
    assert (lo[0] + hi[0]) / 2 == pytest.approx(cell.cx) and (lo[1] + hi[1]) / 2 == pytest.approx(cell.cy)
    assert lo[2] == pytest.approx(cell.z_floor - OVERLAP)
    assert hi[0] - lo[0] <= 0.6 * cell.clear[0] + 1e-6
    H = max(0.35 * 12.0, 1.5)
    assert f"pitha on the garbhagriha floor: {cell.clear[2] - H:.1f} mm clear above it" in result.notes


# ---- the walls' relief and what gives way to them -------------------------------------


def test_niches_frame_every_blind_bay_and_the_dvara_has_its_surround():
    one = _build(sanctum="back")
    assert len(_named(one, "sanctum", "niche")) == 3 * 3, "back and both flanks, three bands each"
    assert len(_named(one, "sanctum", "dvara")) == 3
    wide = _build(sanctum="back", sanctum_bays=3)  # three bays across, two deep: nine blind bays
    assert len(_named(wide, "sanctum", "niche")) == 9 * 3
    assert not _named(_build(sanctum="back", sanctum_niches=False), "sanctum", "niche")
    small = _build(sanctum="back", footprint_x=55, footprint_y=55)
    assert not _named(small, "sanctum", "niche") and _named(small, "sanctum", "dvara")
    assert any("devakoshtha" in n and "skipped" in n for n in small.notes)


def test_seats_and_screens_give_way_to_the_walls():
    result = _build(sanctum="back", kakshasana="back+sides", jali="back+sides", printer_profile="resin")
    cell = result.layout.cell
    xo0, xo1, _, _ = cell.outer
    seats = _named(result, "enclosure", "kakshasana")
    assert len(seats) == 4, "the back seat is cut in two by the cell; the flanks run whole"
    back_seats = [s for s in seats if s.bounds[1][0] - s.bounds[0][0] > 10 and s.bounds[1][1] > cell.y1]
    assert len(back_seats) == 2
    assert all(s.bounds[1][0] <= xo0 + 1e-6 or s.bounds[0][0] >= xo1 - 1e-6 for s in back_seats)
    bars = _named(result, "enclosure", "jali")
    back_bars = [s for s in bars if s.bounds[0][1] > cell.y1 - 1.0]
    assert back_bars
    assert all(s.bounds[1][0] <= cell.x0 + 1e-6 or s.bounds[0][0] >= cell.x1 - 1e-6 for s in back_bars)
    whole = _build(sanctum="centre", pillars_x=3, pillars_y=3, kakshasana="all", jali="all")
    assert not _named(whole, "enclosure", "kakshasana") and not _named(whole, "enclosure", "jali")


# ---- the vimana ------------------------------------------------------------------------


def test_the_vimana_rises_from_the_cell_walls_inside_the_hara():
    result = _build(sanctum="back")
    L, cell = result.layout, result.layout.cell
    tiers = _named(result, "crown", "tier")
    assert len(tiers) == 3 and _named(result, "crown", "sikhara") and _named(result, "crown", "kuta")
    xo0, xo1, yo0, yo1 = cell.outer
    lowest = tiers[0].vertices[np.isclose(tiers[0].vertices[:, 2], tiers[0].vertices[:, 2].min())]
    assert lowest[:, 2].min() == pytest.approx(L.roof_z - OVERLAP)
    assert (lowest[:, 0].min(), lowest[:, 0].max()) == pytest.approx((xo0, xo1))
    assert (lowest[:, 1].min(), lowest[:, 1].max()) == pytest.approx((yo0, yo1))
    assert not _named(_build(sanctum="back", vimana=False), "crown", "tier")
    stepped = _build(sanctum="back", roof_style="stepped")
    assert len(_named(stepped, "crown", "tier")) == 3, "the roof's own tiers; no second tower"
    assert _named(stepped, "crown", "tier")[0].bounds[1][0] > xo1 + 10
    flat = _build(sanctum="centre", roof_style="flat")
    assert len(_named(flat, "crown", "tier")) == 3 and len(_named(flat, "crown", "sikhara")) == 1


def test_a_kerala_cell_gets_its_own_roof_through_the_ridge():
    result = _build(sanctum="centre", roof_style="kerala")
    L, cell = result.layout, result.layout.cell
    roofs = sorted(_named(result, "crown", "roof"), key=lambda s: s.bounds[0][2])
    assert len(roofs) == 2
    main, upper = roofs
    assert upper.bounds[0][2] > main.bounds[1][2] - 1e-6, "the second roof's eaves clear the first's ridge"
    band = _named(result, "crown", "upper")
    assert len(band) == 1 and band[0].bounds[0][2] == pytest.approx(L.roof_z - OVERLAP)
    xo0, xo1, yo0, yo1 = cell.outer
    assert (band[0].bounds[0][0], band[0].bounds[1][0]) == pytest.approx((xo0, xo1))
    assert (band[0].bounds[0][1], band[0].bounds[1][1]) == pytest.approx((yo0, yo1))
    assert len(_named(result, "crown", "stupi")) == 2
    mesh = make_mesh(result, union=True)
    assert mesh.is_watertight and body_count(mesh) == 1


# ---- sizing to the image ---------------------------------------------------------------


def test_scale_for_vigraham_fits_the_cavity_with_clearance(tmp_path, capsys):
    params = MandapaParams(sanctum="back")
    fitted = scale_for_vigraham(params, (20.0, 20.0, 40.0))
    w, d, h = build(params).layout.cell.clear
    assert fitted.scale == pytest.approx(math.ceil(max(22.0 / w, 22.0 / d, 41.0 / h) * 1000) / 1000)
    assert fitted.scale * h >= 41.0 - 1e-3 and fitted.scale * w >= 22.0 - 1e-3
    with pytest.raises(ValueError):
        scale_for_vigraham(MandapaParams(), (20.0, 20.0, 40.0))

    out, saved = tmp_path / "v.stl", tmp_path / "v.xml"
    argv = ["--out", str(out), "--set", "sanctum=back", "--vigraham", "20,20,40", "--save-params", str(saved)]
    assert mandapa.cli.main(argv) == 0
    text = capsys.readouterr().out
    assert "scaled by" in text and "20 x 20 x 40 mm vigraham" in text
    assert "goes in before the roof" in text, "wider than the dvara"
    assert mandapa.cli.load_any(saved).params.scale == pytest.approx(fitted.scale)
    for bad in (["--vigraham", "20,20,40"], ["--set", "sanctum=back", "--vigraham", "20,20"]):
        with pytest.raises(SystemExit) as exc:
            mandapa.cli.main(["--out", str(out), *bad])
        assert exc.value.code == 2


@pytest.mark.parametrize("seed", range(8))
def test_random_halls_with_sanctums_union_to_one_body(seed):
    p = MandapaParams().randomized(2000 + seed).with_(sanctum=("back", "centre")[seed % 2])
    result = build(p)
    assert result.layout.cell is not None, p
    for s in result.solids():
        s.check()
    mesh = make_mesh(result, union=True)
    assert mesh.is_watertight, p
    assert body_count(mesh) == 1, p
