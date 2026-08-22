"""Splitting, pegs, hollowing, bed fitting and the CLI, end to end.

The numbers asserted here are the tolerance contract of :mod:`mandapa.printprep`: the
cut gap, the peg and socket sizes, the clearance, and where the volume goes.
"""

from dataclasses import MISSING, fields

import numpy as np
import pytest
import trimesh

import mandapa.cli
from mandapa.builder import OVERLAP, build
from mandapa.export import body_count, make_mesh, read_3mf, to_trimesh
from mandapa.io import save_temple
from mandapa.meshlib import box_between
from mandapa.params import MandapaParams
from mandapa.presets import PRESETS
from mandapa.printprep import (
    CUT_GAP,
    DRAIN_DIAMETER,
    HOLE_EXTRA_DEPTH,
    PEG_CLEARANCE,
    PEG_HEIGHT,
    PEG_SIDES,
    PrintOptions,
    peg_plan,
    prepare_parts,
)

FLOAT_FIELD_TYPES = {"bool", "float", "int", "str", "tuple[float, float, float] | None"}


@pytest.fixture(scope="module")
def default_build():
    return build(MandapaParams())


@pytest.fixture(scope="module")
def split_parts(default_build):
    return prepare_parts(default_build, PrintOptions(split=True))


def slab_volume(mesh: trimesh.Trimesh, z0: float, z1: float) -> float:
    lo, hi = mesh.bounds
    box = box_between((lo[0] - 5, lo[1] - 5, z0), (hi[0] + 5, hi[1] + 5, z1))
    return float(trimesh.boolean.intersection([mesh, to_trimesh(box)], engine="manifold").volume)


def contains(mesh: trimesh.Trimesh, points) -> np.ndarray:
    """Point-in-solid by vertical ray parity (trimesh's own needs rtree, absent here).

    Rays go straight up, so a point must not sit under a triangle edge: callers nudge
    their probes off the symmetry axes of the pegs and sockets.
    """
    a, b, c = mesh.triangles[:, 0], mesh.triangles[:, 1], mesh.triangles[:, 2]
    det = (b[:, 1] - c[:, 1]) * (a[:, 0] - c[:, 0]) + (c[:, 0] - b[:, 0]) * (a[:, 1] - c[:, 1])
    flat = np.abs(det) > 1e-12  # skip faces the vertical ray runs along
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


NUDGE = (0.0137, 0.0071)  # off the socket's fan diagonals, well inside any peg


def regular_polygon(radius: float, n: int, phase: float = 0.0) -> np.ndarray:
    t = phase + 2 * np.pi * np.arange(n) / n
    return np.column_stack([radius * np.cos(t), radius * np.sin(t)])


def distance_to_edges(point: np.ndarray, polygon: np.ndarray) -> float:
    best = np.inf
    for a, b in zip(polygon, np.roll(polygon, -1, axis=0)):
        ab = b - a
        t = np.clip(np.dot(point - a, ab) / np.dot(ab, ab), 0.0, 1.0)
        best = min(best, float(np.linalg.norm(point - (a + t * ab))))
    return best


# ---- options contract -----------------------------------------------------------------


def test_print_options_are_dialog_friendly():
    for f in fields(PrintOptions):
        assert f.default is not MISSING, f.name
        assert str(f.type) in FLOAT_FIELD_TYPES, (f.name, f.type)
        assert f.metadata.get("label") and f.metadata.get("help"), f.name
    assert [f.name for f in fields(PrintOptions)] == [
        "split", "hollow_wall_mm", "bed_mm", "fit_to_bed", "flip_roof",
    ]


# ---- default and split ----------------------------------------------------------------


def test_default_is_one_part_resting_on_the_bed(default_build):
    parts = prepare_parts(default_build)
    assert [p.name for p in parts] == ["mandapa"]
    part = parts[0]
    assert part.notes == [] and part.colour is None
    assert part.mesh.is_watertight
    assert part.mesh.volume == pytest.approx(make_mesh(default_build).volume)
    assert part.mesh.bounds[0][2] == pytest.approx(0.0)


def test_split_parts_are_printable_and_sit_on_the_bed(default_build, split_parts):
    L, p = default_build.layout, default_build.params
    whole = make_mesh(default_build)
    assert [part.name for part in split_parts] == ["base", "colonnade", "roof"]
    for part in split_parts:
        assert part.mesh.is_watertight, part.name
        assert part.mesh.volume > 0, part.name
        assert part.mesh.bounds[0][2] == pytest.approx(0.0, abs=1e-6), part.name
        assert part.colour is not None
    base, colonnade, roof = split_parts
    floor_seam, beam_seam = L.floor_z, L.beam_z0 - OVERLAP
    # base: plinth up to the seam, pegs standing PEG_HEIGHT proud of the cut face, and the
    # balustrade tops (which rise above the plinth) glued back on rather than left floating
    assert base.mesh.bounds[1][2] >= floor_seam - CUT_GAP / 2 + PEG_HEIGHT - 1e-6
    assert body_count(base.mesh) == 1
    assert any("plinth ornament" in n for n in base.notes)
    # colonnade: one loose pillar per grid point, cut gap removed, pegs on top
    assert body_count(colonnade.mesh) == p.pillars_x * p.pillars_y
    expected_h = (beam_seam - floor_seam - CUT_GAP) + PEG_HEIGHT
    assert colonnade.mesh.bounds[1][2] == pytest.approx(expected_h, abs=1e-4)
    assert any("loose pieces" in n for n in colonnade.notes)
    # roof: everything above the beam seam, not flipped
    assert body_count(roof.mesh) == 1
    assert roof.mesh.bounds[1][2] == pytest.approx(whole.bounds[1][2] - beam_seam - CUT_GAP / 2, abs=1e-4)
    assert roof.notes == []


def test_split_volume_budget(default_build, split_parts):
    """Parts = whole - the two cut gaps + pegs - sockets, to within a couple of mm3."""
    whole = make_mesh(default_build)
    L = default_build.layout
    half = CUT_GAP / 2
    gap = slab_volume(whole, L.floor_z - half, L.floor_z + half)
    gap += slab_volume(whole, L.beam_z0 - OVERLAP - half, L.beam_z0 - OVERLAP + half)
    floor, beam, notes = peg_plan(default_build)
    assert floor is not None and beam is not None and notes == []
    pegs = floor.peg_volume() + beam.peg_volume()
    holes = floor.hole_volume() + beam.hole_volume()
    assert pegs > 400 and holes > 600  # the budget is meaningful: far above the tolerance
    total = sum(part.mesh.volume for part in split_parts)
    assert total == pytest.approx(whole.volume - gap + pegs - holes, abs=2.0)
    assert gap < 100.0  # the 0.01 mm gap costs a tenth of a layer, not material


def test_pegs_fit_their_sockets_with_the_clearance(default_build, split_parts):
    L = default_build.layout
    floor, beam, _ = peg_plan(default_build)
    assert floor.radius == pytest.approx(0.3 * L.pillar_w)
    assert len(floor.points) == len(L.pillar_xs) * len(L.pillar_ys)
    assert len(beam.points) == 4
    assert {abs(x) for x, _ in beam.points} == {abs(L.pillar_xs[-1])}
    for pegs in (floor, beam):
        assert pegs.hole_radius == pytest.approx(pegs.radius + PEG_CLEARANCE)
        assert pegs.hole_depth == pytest.approx(pegs.height + HOLE_EXTRA_DEPTH)
        assert pegs.height <= PEG_HEIGHT
        peg = regular_polygon(pegs.radius, PEG_SIDES)
        socket = regular_polygon(pegs.hole_radius / np.cos(np.pi / PEG_SIDES), PEG_SIDES)
        for vertex in peg:  # every peg vertex inside the socket, at least the clearance away
            assert distance_to_edges(vertex, socket) >= PEG_CLEARANCE - 1e-9
            assert np.linalg.norm(vertex) < pegs.hole_radius
    # and on the meshes: peg material on the base, a void in every pillar foot
    base, colonnade, roof = split_parts
    dx, dy = NUDGE
    base_face = floor.lower_face_z
    above = [[x + dx, y + dy, base_face + 1.0] for x, y in floor.points]
    assert contains(base.mesh, above).all()
    feet = [[x + dx, y + dy, 1.0] for x, y in floor.points]
    assert not contains(colonnade.mesh, feet).any()
    beside = [[x + floor.hole_radius + 0.4, y + dy, 1.0] for x, y in floor.points]
    assert contains(colonnade.mesh, beside).all()
    # the roof's sockets sit over the corner corbels
    roof_sockets = [[x + dx, y + dy, 1.0] for x, y in beam.points]
    assert not contains(roof.mesh, roof_sockets).any()
    top = colonnade.mesh.bounds[1][2]
    corner_pegs = [[x + dx, y + dy, top - 1.0] for x, y in beam.points]
    assert contains(colonnade.mesh, corner_pegs).all()


def test_thin_members_drop_their_pegs_with_a_note():
    result = build(MandapaParams(pillar_width=2.5))
    floor, beam, notes = peg_plan(result)
    assert floor is None and beam is None
    assert len(notes) == 2 and all("no pegs" in n for n in notes)
    parts = prepare_parts(result, PrintOptions(split=True))
    assert [p.name for p in parts] == ["base", "colonnade", "roof"]
    assert all(p.mesh.is_watertight and p.mesh.volume > 0 for p in parts)
    assert any("no pegs under the pillars" in n for n in parts[0].notes)
    assert any("no pegs under the roof" in n for n in parts[1].notes)


@pytest.mark.parametrize(
    "changes",
    [
        {"roof_style": "flat", "steps": False},
        {"roof_style": "stepped", "plinth_style": "plain", "shaft_style": "round"},
        {"pillars_x": 2, "pillars_y": 3, "footprint_x": 40, "footprint_y": 60, "pillar_width": 4},
        {"printer_profile": "resin", "scale": 0.5},
        {"scale": 1.5, "corbel_style": "bevel", "balustrades": False},
    ],
)
def test_split_variants_stay_watertight(changes):
    result = build(MandapaParams().with_(**changes))
    parts = prepare_parts(result, PrintOptions(split=True))
    assert [p.name for p in parts] == ["base", "colonnade", "roof"]
    for part in parts:
        assert part.mesh.is_watertight, part.name
        assert part.mesh.volume > 0, part.name
        assert part.mesh.bounds[0][2] == pytest.approx(0.0, abs=1e-6)


# ---- flip, hollow, bed ----------------------------------------------------------------


def test_flip_roof_only_for_flat_roofs(default_build):
    flat = build(MandapaParams(roof_style="flat"))
    L = flat.layout
    roof = prepare_parts(flat, PrintOptions(split=True, flip_roof=True))[2]
    assert any("flipped" in n and "sockets facing up" in n for n in roof.notes)
    down = roof.mesh.face_normals[:, 2] < -0.999
    on_bed = down & (roof.mesh.triangles_center[:, 2] < 1e-4)
    assert roof.mesh.area_faces[on_bed].sum() == pytest.approx(4 * L.slab_hx * L.slab_hy, rel=0.02)
    _, beam, _ = peg_plan(flat)
    top = roof.mesh.bounds[1][2]
    dx, dy = NUDGE
    sockets = [[x + dx, -y + dy, top - 1.0] for x, y in beam.points]  # 180 deg about X: y -> -y
    assert not contains(roof.mesh, sockets).any()
    beside = [[x + beam.hole_radius + 0.3, -y + dy, top - 1.0] for x, y in beam.points]
    assert contains(roof.mesh, beside).all()
    assert roof.mesh.is_watertight and roof.mesh.volume > 0

    hara = prepare_parts(default_build, PrintOptions(split=True, flip_roof=True))[2]
    assert any("not flipped" in n and "hara" in n for n in hara.notes)
    unsplit = prepare_parts(default_build, PrintOptions(flip_roof=True))[0]
    assert any("not flipped" in n for n in unsplit.notes)


def test_hollowing_drops_volume_and_stays_watertight(default_build):
    wall = 1.2
    L = default_build.layout
    plinth = next(s for s in default_build.parts["plinth"] if s.name == "plinth")
    hx = float(np.abs(plinth.vertices[:, 0]).min()) - wall
    hy = float(np.abs(plinth.vertices[:, 1]).min()) - wall
    cavity = (2 * hx) * (2 * hy) * (L.floor_z - 2 * wall)
    r = DRAIN_DIAMETER / 2
    drains = 2 * (0.5 * 32 * r * r * np.sin(2 * np.pi / 32)) * wall
    solid = prepare_parts(default_build)[0]
    hollow = prepare_parts(default_build, PrintOptions(hollow_wall_mm=wall))[0]
    assert hollow.mesh.is_watertight
    assert body_count(hollow.mesh) == 1  # the drains open the cavity to the outside
    assert solid.mesh.volume - hollow.mesh.volume == pytest.approx(cavity + drains, rel=5e-3)
    assert any("hollowed" in n and "drain" in n for n in hollow.notes)


def test_hollowing_is_refused_when_it_cannot_be_done():
    short = build(MandapaParams(plinth_height=3.0))
    part = prepare_parts(short, PrintOptions(hollow_wall_mm=1.2))[0]
    assert any("shorter than three" in n for n in part.notes)
    assert part.mesh.volume == pytest.approx(make_mesh(short).volume)
    thin = prepare_parts(short, PrintOptions(hollow_wall_mm=0.3))[0]
    assert any("below the printer" in n for n in thin.notes)


def test_hollowing_a_split_model_touches_only_the_base(default_build, split_parts):
    parts = prepare_parts(default_build, PrintOptions(split=True, hollow_wall_mm=1.2))
    base, colonnade, roof = parts
    assert base.mesh.volume < split_parts[0].mesh.volume * 0.5
    assert base.mesh.is_watertight and body_count(base.mesh) == 1
    assert any("hollowed" in n for n in base.notes)
    assert colonnade.mesh.volume == pytest.approx(split_parts[1].mesh.volume)
    assert roof.mesh.volume == pytest.approx(split_parts[2].mesh.volume)
    assert not any("hollow" in n for n in colonnade.notes + roof.notes)


def test_bed_fit_reporting_and_scaling(default_build):
    big = prepare_parts(default_build, PrintOptions(bed_mm=(220, 220, 250)))[0]
    assert any(n == "fits the 220 x 220 x 250 mm bed" for n in big.notes)
    turned = prepare_parts(default_build, PrintOptions(bed_mm=(130, 110, 80)))[0]
    assert any("turned 90 degrees" in n for n in turned.notes)
    small = prepare_parts(default_build, PrintOptions(bed_mm=(100, 100, 50)))[0]
    assert any("exceeds" in n and "needs scaling by" in n for n in small.notes)
    assert small.mesh.extents[2] > 50

    parts = prepare_parts(default_build, PrintOptions(split=True, bed_mm=(100, 100, 50), fit_to_bed=True))
    for part in parts:
        assert (part.mesh.extents <= np.array([100, 100, 50]) + 1e-6).all(), part.name
        assert part.mesh.bounds[0][2] == pytest.approx(0.0, abs=1e-6)
        assert any(n.startswith("scaled by 0.") for n in part.notes), part.notes
        assert any(n.startswith("fits the") for n in part.notes)
    factors = {n for part in parts for n in part.notes if n.startswith("scaled by")}
    assert len(factors) == 1  # one uniform factor for every part
    ignored = prepare_parts(default_build, PrintOptions(fit_to_bed=True))[0]
    assert any("no bed size" in n for n in ignored.notes)


# ---- CLI ------------------------------------------------------------------------------


def test_cli_default_and_split_runs(tmp_path, capsys):
    out = tmp_path / "m.stl"
    assert mandapa.cli.main(["--out", str(out)]) == 0
    assert out.exists()
    text = capsys.readouterr().out
    assert "watertight yes" in text and "weight     ~" in text

    split = tmp_path / "s.stl"
    assert mandapa.cli.main(["--out", str(split), "--split", "--bed", "220,220,250", "--hollow", "1.2"]) == 0
    for name in ("s_base.stl", "s_colonnade.stl", "s_roof.stl"):
        assert (tmp_path / name).exists()
    text = capsys.readouterr().out
    assert text.count("watertight yes") == 3 and "part       colonnade" in text
    assert "fits the 220 x 220 x 250 mm bed" in text and "hollowed" in text


def test_cli_3mf_with_flipped_flat_roof(tmp_path):
    out = tmp_path / "t.stl"
    argv = ["--out", str(out), "--format", "3mf", "--split", "--flip-roof", "--set", "roof_style=flat"]
    assert mandapa.cli.main(argv) == 0
    parts = read_3mf(tmp_path / "t.3mf")
    assert [p.name for p in parts] == ["base", "colonnade", "roof"]
    assert all(p.mesh.is_watertight for p in parts)
    assert all(p.colour is not None for p in parts)


def test_cli_presets_and_parameter_files(tmp_path, capsys):
    assert mandapa.cli.main(["--list-presets"]) == 0
    names = capsys.readouterr().out.splitlines()
    assert names == list(PRESETS)

    first = names[0]
    out = tmp_path / "p.stl"
    assert mandapa.cli.main(["--out", str(out), "--preset", first.lower()]) == 0
    assert out.exists()

    design = tmp_path / "design.xml"
    save_temple(design, MandapaParams(pillars_x=3))
    saved_json, saved_xml = tmp_path / "eff.json", tmp_path / "eff.xml"
    argv = ["--out", str(tmp_path / "x.stl"), "--params", str(design), "--save-params", str(saved_json)]
    assert mandapa.cli.main(argv) == 0
    assert MandapaParams.load(saved_json).pillars_x == 3
    argv = ["--out", str(tmp_path / "y.stl"), "--params", str(saved_json), "--set", "pillars_y=2",
            "--save-params", str(saved_xml)]
    assert mandapa.cli.main(argv) == 0
    assert saved_xml.read_text(encoding="utf-8").startswith("<?xml")
    assert mandapa.cli.main(["--out", str(tmp_path / "z.stl"), "--params", str(saved_xml), "--no-union"]) == 0
    effective = mandapa.cli.load_any(saved_xml).params
    assert effective.pillars_x == 3 and effective.pillars_y == 2


@pytest.mark.parametrize(
    "argv",
    [
        ["--bed", "1,2"],
        ["--bed", "0,220,250"],
        ["--preset", "no such preset"],
        ["--params", "missing_file.json"],
        ["--no-union", "--split"],
        ["--no-union", "--format", "3mf"],
        ["--set", "pillars_x"],
    ],
)
def test_cli_rejects_bad_invocations(tmp_path, argv):
    with pytest.raises(SystemExit) as exc:
        mandapa.cli.main(["--out", str(tmp_path / "bad.stl"), *argv])
    assert exc.value.code == 2


def test_cli_exit_status_follows_watertightness(tmp_path, monkeypatch):
    from mandapa.export import Report

    def leaky(parts):
        zero = (0.0, 0.0, 0.0)
        return [Report(False, 0, (zero, zero), 0.0, 0.0, 0.0, 0.0, [], name=p.name) for p in parts]

    monkeypatch.setattr(mandapa.cli, "inspect_parts", leaky)
    assert mandapa.cli.main(["--out", str(tmp_path / "leaky.stl")]) == 1
