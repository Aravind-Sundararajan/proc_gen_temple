"""The gopuram builder: the passage contract, the taper, the crown, and the fuzz.

The decisions live here.  The ones this file pins hardest are the ones a gateway
exists for: the dvara is at least twice as high as wide, the passage is never sealed
by the mouldings, and every design — every preset, every range edge, every seed —
unions to one watertight body with the passage still through it.
"""

import math
import os

import pytest

from gopuram.builder import HARA_SINK, build, scale_for_passage
from gopuram.params import GROUPS, GopuramParams
from mandapa.export import body_count, inspect_mesh, make_mesh
from mandapa.ornament import OVERLAP
from mandapa.params import _resolve_type


def _build(**changes):
    result = build(GopuramParams().with_(**changes))
    for s in result.solids():
        s.check()
    return result


def _named(result, group, name):
    return [s for s in result.parts.get(group, []) if s.name == name]


# ---- parameter contract ----------------------------------------------------------------


def test_every_field_has_complete_metadata_for_the_gui():
    defaults = GopuramParams()
    for name, kind, meta in GopuramParams.specs():
        kind = _resolve_type(kind)
        assert kind in (int, float, bool, str), name
        assert meta["label"] and meta["group"] in GROUPS, name
        if meta["choices"] is not None:
            assert kind is str and getattr(defaults, name) in meta["choices"], name
        elif kind is not bool:
            assert meta["lo"] is not None and meta["hi"] > meta["lo"] and meta["step"], name
            assert meta["lo"] <= getattr(defaults, name) <= meta["hi"], name


def test_the_record_carries_what_the_shared_shrines_read():
    """kuta, sala, stupi and nasi_radius are the mandapa's; they read these four."""
    p = GopuramParams()
    assert isinstance(p.finial, bool) and isinstance(p.nasi, bool)
    assert isinstance(p.printable_overhangs, bool) and p.min_feature == 0.8


def test_the_defaults_build_without_a_single_apology():
    """A note on the default design is noise the author never asked for; the one line
    the log always carries is the passage report."""
    notes = build(GopuramParams()).notes
    assert len(notes) == 1 and notes[0].startswith("dvara ")


# ---- the passage -----------------------------------------------------------------------


def test_the_dvara_keeps_the_texts_proportion():
    L = build(GopuramParams()).layout
    assert L.door_h >= 2.0 * L.door_w
    wide = _build(dvara_width=0.3, dvara_height=0.5, wall_height=20.0)
    assert wide.layout.door_h == pytest.approx(2.0 * wide.layout.door_w)
    assert any("twice as high" in n for n in wide.notes)


def test_the_lintel_keeps_its_share_of_the_wall():
    L = build(GopuramParams(dvara_height=0.85)).layout
    assert L.wall_h - L.door_h >= 0.15 * L.wall_h - 1e-9


def test_the_passage_is_never_sealed_by_the_mouldings():
    """The tiny-base, deep-plinth corner that would fold the flanks' kumudas together."""
    result = _build(base_width=40.0, base_depth=30.0, plinth_height=40.0, plinth_projection=0.3)
    L = result.layout
    assert L.clear_w >= 1.0 - 1e-9
    assert any("passage stays open" in n for n in result.notes)
    mesh = make_mesh(result, union=True)
    assert mesh.is_watertight and body_count(mesh) == 1


def test_the_clear_width_is_the_honest_figure():
    """clear_w is the dvara minus the deepest thing actually beside it — the plinth
    mouldings or the storey course — so the log's 'a W x H object passes' line cannot
    overstate the gateway."""
    p = GopuramParams().clamped()
    L = build(p).layout
    from mandapa.builder import plinth_profile

    reach = max(d for d, _ in plinth_profile(p.plinth_style, p.plinth_height, L.proj, p.plinth_padma))
    assert L.clear_w == pytest.approx(L.door_w - 2.0 * max(reach, 0.7 * L.kapota_p))
    one_storey = build(p.with_(wall_storeys=1)).layout
    assert one_storey.clear_w == pytest.approx(one_storey.door_w - 2.0 * reach)


def test_the_soffit_bridge_is_reported():
    result = _build(base_width=300.0, base_depth=100.0, dvara_width=0.3, wall_height=120.0,
                    dvara_height=0.85)
    assert result.layout.door_w > 30.0
    assert any("soffit bridges" in n for n in result.notes)


def test_the_passage_goes_all_the_way_through():
    """No solid crosses the *clear* passage volume below the lintel — the figure the
    log promises is the figure the mesh keeps, mouldings and storey course included."""
    result = _build()
    L = result.layout
    x1 = L.clear_w / 2.0 - 1e-6
    z1 = L.floor_z + L.door_h - 0.5
    for s in result.solids():
        lo, hi = s.bounds
        inside = (lo[0] < x1 and hi[0] > -x1 and lo[2] < z1 and hi[2] > L.floor_z + 0.5
                  and lo[1] < 0.0 < hi[1])
        assert not inside, f"{s.name} stands in the passage"


def test_scale_for_passage_clears_the_stated_object():
    p = scale_for_passage(GopuramParams(), (12.0, 30.0))
    L = build(p.with_(scale=1.0)).layout
    assert L.clear_w * p.scale >= 12.0 + 2.0 and L.door_h * p.scale >= 30.0 + 1.0
    assert p.scale == pytest.approx(math.ceil(max((12.0 + 2) / L.clear_w, 31.0 / L.door_h) * 1000) / 1000)


# ---- the base --------------------------------------------------------------------------


def test_two_flank_plinths_either_side_of_the_passage():
    result = _build()
    L = result.layout
    plinths = _named(result, "plinth", "plinth")
    assert len(plinths) == 2
    for s in plinths:
        lo, hi = s.bounds
        assert min(abs(lo[0]), abs(hi[0])) >= L.door_w / 2.0 - L.proj - 1e-6
    gala = _named(result, "plinth", "galapada")
    assert gala and all(min(abs(s.bounds[0][0]), abs(s.bounds[1][0])) > 0.5 for s in gala)


def test_the_prastara_runs_unbroken_and_bridges_the_passage():
    result = _build()
    L = result.layout
    frieze = _named(result, "base", "frieze")[0]
    assert frieze.bounds[1][0] - frieze.bounds[0][0] == pytest.approx(2 * L.body_hx)
    lintel = _named(result, "base", "lintel")[0]
    assert lintel.bounds[0][2] == pytest.approx(L.floor_z + L.door_h)
    assert _named(result, "base", "kudu"), "kudus ride the base prastara by default"


def test_the_storey_course_is_per_flank_and_optional():
    two = _build()
    kapotas = _named(two, "base", "kapota")
    assert len(kapotas) == 3  # the base prastara's course and one per flank
    one = _build(wall_storeys=1)
    assert len(_named(one, "base", "kapota")) == 1
    assert one.layout.storey_z is None and two.layout.storey_z == pytest.approx(
        two.layout.floor_z + 0.55 * two.layout.wall_h
    )


def test_relief_stays_shallow_enough_to_print_as_texture():
    result = _build()
    for name in ("pilaster", "dvara", "niche", "taladvara"):
        for s in _named(result, "base", name) + _named(result, "talas", name):
            lo, hi = s.bounds
            depth = min(hi - lo)
            assert depth <= 1.2 + 2 * OVERLAP + 1e-6, (name, depth)


def test_niches_sit_on_the_flanks_and_over_the_door():
    result = _build()
    niches = _named(result, "base", "niche")
    assert len(niches) == 3 * 4 + 3 * 2  # two flanks on two faces, plus the over-door pair
    assert not _named(_build(niches=False), "base", "niche")


# ---- the superstructure ----------------------------------------------------------------


def test_the_taper_leans_the_profile_inward():
    L = build(GopuramParams()).layout
    assert len(L.talas) == 5
    p = GopuramParams()
    for a, b in zip(L.talas, L.talas[1:]):
        assert b.hx == pytest.approx(a.hx * p.tala_ratio)
        # heights shrink slower than plans: that is the inward lean
        assert (b.z1 - b.z0) == pytest.approx((a.z1 - a.z0) * (2 + p.tala_ratio) / 3)
        assert (b.z1 - b.z0) / (a.z1 - a.z0) > b.hx / a.hx


def test_the_taper_stops_with_a_note_when_it_runs_out():
    result = _build(tala_ratio=0.7, talas=9)
    assert len(result.layout.talas) < 9
    assert any("talas fit the taper" in n for n in result.notes)
    assert len(_build(talas=1).layout.talas) == 1


def test_every_tala_carries_its_hara_and_the_shrines_sink_into_the_wall():
    result = _build()
    L = result.layout
    kutas = [s for s in result.parts["talas"] if s.name == "kuta"]
    assert kutas
    # corner kutas of the first tala ring the second, HARA_SINK into its wall
    t0, t1 = L.talas[0], L.talas[1]
    outermost = max(float(s.bounds[1][0]) for s in kutas)
    assert outermost <= t0.hx + 0.35 * 0.16 * (t0.z1 - t0.z0) + 1e-6, "no shrine overhangs its terrace"
    inner = min(float(s.bounds[0][0]) for s in kutas if s.bounds[0][0] > 0)
    assert inner < t1.hx - HARA_SINK + 1e-6
    assert not [s for s in _build(hara=False).parts["talas"] if s.name in ("kuta", "sala")]


def test_the_central_bay_stays_open_for_the_openings():
    """Salas mirror about the centre of the long faces; none stands over the tala's dvara."""
    result = _build(salas_per_tala=2)
    for s in result.parts["talas"]:
        if s.name != "sala":
            continue
        lo, hi = s.bounds
        if hi[1] - lo[1] > hi[0] - lo[0]:  # an end-face sala, crossing the ridge axis
            continue
        assert not (lo[0] < 0.0 < hi[0]), "a sala stands over the tala opening"
    openings = [s for s in result.parts["talas"] if s.name == "taladvara"]
    assert len(openings) == 5 * 3 * 2  # three frame pieces, front and back, per tala


def test_the_crown_is_a_vault_with_an_odd_kalasa_row_and_mahanasi():
    result = _build()
    assert _named(result, "crown", "griva") and _named(result, "crown", "sikhara")
    assert len(_named(result, "crown", "stupi")) == 5
    assert len(_named(result, "crown", "nasi")) == 2
    even = _build(kalasas=6)
    assert len(_named(even, "crown", "stupi")) == 5
    assert any("odd" in n for n in even.notes)
    assert not _named(_build(mahanasi=False), "crown", "nasi")


def test_the_kalasa_row_thins_to_what_the_ridge_seats():
    result = _build(kalasas=13, base_width=60.0, base_depth=42.0)
    n = len(_named(result, "crown", "stupi"))
    assert n < 13 and n % 2 == 1
    assert any("thinned" in n_ for n_ in result.notes)


def test_the_vault_runs_along_the_enclosure_wall():
    sikhara = _named(_build(), "crown", "sikhara")[0]
    lo, hi = sikhara.bounds
    assert hi[0] - lo[0] > 2.5 * (hi[1] - lo[1]), "the ridge runs along X, the long axis"


# ---- print rules -----------------------------------------------------------------------


def test_the_kapota_cap_and_the_authentic_scoop():
    capped = _build(kapota_projection=8.0, kapota_height=3.0)
    assert capped.layout.kapota_p == pytest.approx(2.4)
    assert any("45 deg rule" in n for n in capped.notes)
    free = _build(kapota_projection=8.0, kapota_height=3.0, printable_overhangs=False)
    assert free.layout.kapota_p == pytest.approx(8.0)


def test_the_seam_and_the_layout_lines_hold():
    L = build(GopuramParams()).layout
    p = GopuramParams()
    assert L.floor_z == pytest.approx(p.plinth_height)
    assert L.ent_z0 == pytest.approx(p.plinth_height + p.wall_height)
    assert L.wall_top == pytest.approx(L.ent_z0 + L.frieze_h + L.kapota_h + L.slab_h - OVERLAP)
    assert L.talas[0].z0 == pytest.approx(L.wall_top - OVERLAP)


# ---- the union, everywhere -------------------------------------------------------------


def test_default_union_is_watertight_one_body_and_sized():
    p = GopuramParams()
    result = build(p)
    mesh = make_mesh(result, union=True)
    report = inspect_mesh(mesh, result.notes)
    assert report.watertight and body_count(mesh) == 1
    x, y, z = report.size_mm
    assert x >= p.base_width - 1e-6 and y >= p.base_depth - 1e-6
    assert z > p.plinth_height + p.wall_height + 4 * p.tala_height


@pytest.mark.parametrize("seed", range(6))
def test_randomised_designs_union_watertight(seed):
    result = build(GopuramParams().randomized(seed))
    for s in result.solids():
        s.check()
    mesh = make_mesh(result, union=True)
    assert mesh.is_watertight and body_count(mesh) == 1


# ---- fuzz ------------------------------------------------------------------------------

FUZZ = int(os.environ.get("GOPURAM_FUZZ", os.environ.get("MANDAPA_FUZZ", "0")))


def _edge_cases():
    """Min and max of every numeric field, every choice, alternating the printable rule."""
    cases = []
    base = GopuramParams()
    for name, kind, meta in GopuramParams.specs():
        kind = _resolve_type(kind)
        if meta["choices"] is not None:
            values = meta["choices"]
        elif kind is bool:
            values = [not getattr(base, name)]
        else:
            values = [kind(meta["lo"]), kind(meta["hi"])]
        for v in values:
            cases.append({name: v, "printable_overhangs": len(cases) % 2 == 0})
    return cases


_EDGES = _edge_cases()


@pytest.mark.parametrize("changes", _EDGES, ids=[f"{next(iter(c))}={c[next(iter(c))]}" for c in _EDGES])
def test_edge_values_build_closed_solids(changes):
    """Every extreme builds and every part is a valid solid; the union runs on a sample
    by default and on every case under a fuzz of 30 or more."""
    result = _build(**changes)
    assert result.parts["plinth"] and result.parts["base"] and result.parts["talas"]
    index = _EDGES.index(changes)
    if FUZZ >= 30 or index % 7 == 0:
        mesh = make_mesh(result, union=True)
        assert mesh.is_watertight and body_count(mesh) == 1, changes


@pytest.mark.parametrize("seed", range(FUZZ or 8))
def test_fuzz_randomized_designs_union_watertight(seed):
    result = build(GopuramParams().randomized(2000 + seed))
    for s in result.solids():
        s.check()
    mesh = make_mesh(result, union=True)
    assert mesh.is_watertight, seed
    assert body_count(mesh) == 1, seed
