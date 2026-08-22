import math
import os

import numpy as np
import pytest

from mandapa.builder import OVERLAP, build
from mandapa.export import body_count, inspect_mesh, make_mesh
from mandapa.meshlib import overhang_mask
from mandapa.params import GROUPS, SIDE_SETS, MandapaParams, _resolve_type


def test_default_build_parts_are_valid_solids():
    result = build(MandapaParams())
    solids = result.solids()
    assert len(solids) > 50
    for s in solids:
        s.check()
    assert result.parts["pillars"] and result.parts["crown"] and result.parts["steps"]


def test_default_union_is_watertight_and_sized():
    p = MandapaParams()
    result = build(p)
    mesh = make_mesh(result, union=True)
    report = inspect_mesh(mesh, result.notes)
    assert report.watertight
    plinth_lo, plinth_hi = result.parts["plinth"][0].bounds
    assert abs((plinth_hi[0] - plinth_lo[0]) - p.footprint_x) < 1e-6
    assert abs((plinth_hi[1] - plinth_lo[1]) - p.footprint_y) < 1e-6
    x, y, z = report.size_mm
    assert x >= p.footprint_x  # kapota eaves overhang the plinth
    assert y > p.footprint_y  # steps stick out the front
    assert z > p.plinth_height + p.pillar_height
    assert report.volume_cm3 > 10


@pytest.mark.parametrize("seed", range(6))
def test_randomised_designs_build(seed):
    p = MandapaParams().randomized(seed)
    result = build(p)
    for s in result.solids():
        s.check()
    mesh = make_mesh(result, union=True)
    assert mesh.is_watertight


@pytest.mark.parametrize(
    "changes",
    [
        {"roof_style": "flat", "steps": False, "kudus": False},
        {"roof_style": "stepped", "tiers": 5, "finial": False},
        {"plinth_style": "plain", "plinth_projection": 0.0},
        {"plinth_style": "pratibandha", "shaft_style": "round"},
        {"plinth_style": "kapotabandha", "shaft_style": "varied", "seed": 7},
        {"kapota_height": 0.0, "kapota_projection": 0.0, "frieze_height": 0.0},
        {"printable_overhangs": False, "kapota_scoop": 1.0, "corbel_style": "bevel"},
        {"pillars_x": 2, "pillars_y": 2, "footprint_x": 40, "footprint_y": 40, "pillar_width": 4},
        {"pillars_x": 8, "pillars_y": 8, "footprint_x": 300, "footprint_y": 200, "salas_per_side": 4},
        {"printer_profile": "resin", "scale": 0.5},
    ],
)
def test_variants_union_cleanly(changes):
    p = MandapaParams().with_(**changes)
    result = build(p)
    for s in result.solids():
        s.check()
    mesh = make_mesh(result, union=True)
    assert mesh.is_watertight
    assert mesh.volume > 0


def test_printable_rule_limits_kapota_projection():
    p = MandapaParams(kapota_projection=10.0, kapota_height=4.0, printable_overhangs=True)
    result = build(p)
    assert result.layout.kapota_p == pytest.approx(3.2)
    assert any("kapota projection" in n for n in result.notes)


def test_params_roundtrip(tmp_path):
    p = MandapaParams().randomized(3)
    path = tmp_path / "p.json"
    p.save(path)
    assert MandapaParams.load(path) == p
    assert MandapaParams.from_dict({"pillars_x": "3", "bogus": 1}).pillars_x == 3


def test_clamped_pulls_values_into_range():
    p = MandapaParams(pillars_x=50, plinth_style="nope").clamped()
    assert p.pillars_x == 8 and p.plinth_style == "padabandha"
    assert np.isfinite(p.footprint_x)


# ---- parameter contract ----------------------------------------------------------------


def _build(**changes):
    result = build(MandapaParams().with_(**changes))
    for s in result.solids():
        s.check()
    return result


def _named(result, group, name):
    return [s for s in result.parts.get(group, []) if s.name == name]


def _steep(solid, floor_z=None):
    """Any face steeper than 45°, ignoring the flat base every sunk ornament has at its lowest z."""
    if floor_z is None:
        floor_z = float(solid.vertices[:, 2].min())
    return bool(overhang_mask(solid, 45.0, floor_z).any())


def test_every_field_has_complete_metadata_for_the_gui():
    defaults = MandapaParams()
    for name, kind, meta in MandapaParams.specs():
        kind = _resolve_type(kind)
        assert kind in (int, float, bool, str), name
        assert meta["label"] and meta["group"] in GROUPS, name
        if meta["choices"] is not None:
            assert kind is str and getattr(defaults, name) in meta["choices"], name
        elif kind is not bool:
            assert meta["lo"] is not None and meta["hi"] > meta["lo"] and meta["step"], name
            assert meta["lo"] <= getattr(defaults, name) <= meta["hi"], name


def test_side_sets_cover_every_choice_and_the_front_stays_open_by_default():
    metas = {name: meta for name, _, meta in MandapaParams.specs()}
    for field in ("kakshasana", "jali", "steps_sides"):
        assert all(c in SIDE_SETS for c in metas[field]["choices"])
    p = MandapaParams()
    assert p.sides("steps_sides") == ("S",) and p.sides("kakshasana") == () and p.sides("jali") == ()
    assert "S" not in SIDE_SETS["back+sides"]


def test_from_dict_reads_boolean_words():
    assert MandapaParams.from_dict({"kudus": "false"}).kudus is False
    assert MandapaParams.from_dict({"kudus": "True"}).kudus is True


def test_layout_keeps_the_print_prep_seams():
    L = build(MandapaParams()).layout
    assert L.floor_z == pytest.approx(12.0) and L.beam_z0 == pytest.approx(47.0)
    assert L.corbel_top == pytest.approx(L.beam_z0 - OVERLAP)
    assert len(L.pillar_xs) == 4 and len(L.pillar_ys) == 4


# ---- plinth ------------------------------------------------------------------------------


def test_galapadas_bridge_the_kantha_and_need_a_real_projection():
    result = _build()
    gala = _named(result, "plinth", "galapada")
    assert len(gala) > 8 and result.parts["plinth"][0].name == "plinth"
    u = 12.0 / 24.0
    for s in gala:
        lo, hi = s.bounds
        assert (lo[2], hi[2]) == pytest.approx((17 * u - OVERLAP, 20 * u + OVERLAP))
    assert not _named(_build(plinth_galapadas=False), "plinth", "galapada")
    flat = _build(plinth_projection=0.0)
    assert not _named(flat, "plinth", "galapada") and any("galapadas" in n for n in flat.notes)


def test_padma_band_fills_the_upana_without_growing_the_footprint():
    result = _build(plinth_padma=True)
    petals = _named(result, "plinth", "padma")
    assert petals
    assert max(float(s.bounds[1][0]) for s in petals) < 50.0
    assert result.parts["plinth"][0].bounds[1][0] == pytest.approx(50.0)
    for s in petals:
        assert not _steep(s, floor_z=0.0)


# ---- pillars -----------------------------------------------------------------------------


def test_medallions_sit_on_square_blocks_and_drop_below_the_minimum_feature():
    assert len(_named(_build(), "pillars", "medallion")) == 16 * 2 * 4  # chola: two blocks, four faces
    assert len(_named(_build(shaft_style="octagonal"), "pillars", "medallion")) == 16 * 4
    thin = _build(pillar_width=2.0)
    assert not _named(thin, "pillars", "medallion") and any("medallions" in n for n in thin.notes)
    assert not _named(_build(medallions=False), "pillars", "medallion")


def test_kattu_bands_sit_exactly_on_the_section_changes():
    result = _build()
    bands = _named(result, "pillars", "kattu")
    assert len(bands) == 16 * 2
    L = result.layout
    zone, z_start = L.shaft_h + 4 * OVERLAP, L.floor_z - 4 * OVERLAP
    z1 = z_start + 0.28 * zone
    centres = sorted({round(float(s.bounds[0][2] + s.bounds[1][2]) / 2, 4) for s in bands})
    assert centres == pytest.approx([z1, z1 + 0.52 * zone], abs=1e-3)
    for s in bands:
        assert not _steep(s)


def test_fluted_shaft_has_sixteen_flutes_and_sixteen_more_when_coarse():
    shafts = _named(_build(shaft_style="fluted"), "pillars", "shaft")
    assert sum(len(s.vertices) == 64 for s in shafts) == 16
    coarse = _named(_build(shaft_style="fluted", pillar_width=2.5), "pillars", "shaft")
    assert sum(len(s.vertices) == 32 for s in coarse) == 16  # eight flutes when the pitch is under the nozzle


def test_varied_alternates_by_row_or_column_never_per_pillar():
    for seed in range(6):
        result = _build(shaft_style="varied", seed=seed)
        by_pillar: dict[tuple[float, float], list[int]] = {}
        for s in _named(result, "pillars", "shaft"):
            lo, hi = s.bounds
            key = (round(float(lo[0] + hi[0]) / 2, 3), round(float(lo[1] + hi[1]) / 2, 3))
            by_pillar.setdefault(key, []).append((len(s.vertices), round(s.volume(), 3)))
        sig = {k: tuple(sorted(v)) for k, v in by_pillar.items()}
        assert len(set(sig.values())) == 2
        xs = sorted({k[0] for k in sig})
        ys = sorted({k[1] for k in sig})
        by_col = all(len({sig[(x, y)] for y in ys}) == 1 for x in xs)
        by_row = all(len({sig[(x, y)] for x in xs}) == 1 for y in ys)
        assert by_col != by_row, f"seed {seed}: styles must alternate along exactly one axis"


def test_pushpa_corbels_hang_a_bud_under_every_arm():
    result = _build(corbel_style="pushpa")
    buds = _named(result, "pillars", "pushpa")
    assert len(buds) == 16 * 4 and len(_named(result, "pillars", "stem")) == 16 * 4
    for s in buds:
        assert not _steep(s)
    assert _steep(_named(_build(corbel_style="pushpa", printable_overhangs=False), "pillars", "pushpa")[0])
    short = _build(corbel_style="pushpa", corbel_reach=0.8)
    assert not _named(short, "pillars", "pushpa") and any("pushpa" in n for n in short.notes)


# ---- entablature -------------------------------------------------------------------------


def test_dentils_and_bhuta_row_share_the_frieze():
    result = _build(dentils=True, bhuta_frieze=True, printer_profile="resin", frieze_height=3.0)
    dents, bosses = _named(result, "roof", "dentil"), _named(result, "roof", "boss")
    assert dents and bosses
    L = result.layout
    size = 0.35 * 3.0
    for s in dents:
        assert (s.bounds[0][2], s.bounds[1][2]) == pytest.approx((L.kapota_z0 - size, L.kapota_z0 + OVERLAP))
    for s in bosses:
        assert float(s.bounds[0][2] + s.bounds[1][2]) / 2 == pytest.approx(L.beam_z1 + (3.0 - size) / 2, abs=1e-6)
    assert _named(_build(bhuta_frieze=True), "roof", "boss")  # 2.5 mm frieze: 1 mm bosses, fine on FDM
    low = _build(bhuta_frieze=True, frieze_height=1.5)
    assert not _named(low, "roof", "boss") and any("bhuta" in n for n in low.notes)


def test_nasi_dormers_and_kudu_finials_follow_the_printer():
    resin = _build(nasi=True, printer_profile="resin")
    assert len(_named(resin, "crown", "nasi")) == 4 * 4 + 4 * 2  # four per kuta, two per sala
    assert _named(resin, "roof", "knob")
    fdm = _build(nasi=True)
    assert _named(fdm, "crown", "nasi") and not _named(fdm, "roof", "knob")
    assert not _named(_build(), "crown", "nasi")


# ---- roof --------------------------------------------------------------------------------


@pytest.mark.parametrize("shape,sides", [("square", 4), ("octagonal", 8), ("round", 24)])
def test_sikhara_shape_sets_the_plan_of_neck_and_dome(shape, sides):
    result = _build(roof_style="stepped", sikhara_shape=shape)
    for name in ("griva", "sikhara"):
        s = _named(result, "crown", name)[0]
        z0 = s.vertices[:, 2].min()
        assert int(np.isclose(s.vertices[:, 2], z0).sum()) == sides
    assert not _steep(_named(result, "crown", "sikhara")[0])


def test_panjaras_fill_the_gaps_between_kutas_and_salas_when_there_is_room():
    result = _build(panjaras=True, footprint_x=120, footprint_y=120)
    assert len(_named(result, "crown", "panjara")) == 4 * 2 * 2  # two gaps per side, body + roof
    crowded = _build(panjaras=True, salas_per_side=4, footprint_x=60, footprint_y=60)
    assert not _named(crowded, "crown", "panjara") and any("panjaras" in n for n in crowded.notes)


def test_kerala_roof_overhangs_the_slab_with_a_printable_soffit():
    result = _build(roof_style="kerala", eave_overhang=6.0, roof_pitch=30.0)
    roof = _named(result, "crown", "roof")[0]
    L = result.layout
    _, hi = roof.bounds
    assert (hi[0], hi[1]) == pytest.approx((L.slab_hx + 6.0, L.slab_hy + 6.0))
    rise = (6.0 + min(L.slab_hx, L.slab_hy) - 0.2) * math.tan(math.radians(30.0))
    assert hi[2] == pytest.approx(L.roof_z - OVERLAP + 6.0 + 1.0 + rise)
    assert not _steep(roof, floor_z=L.roof_z - OVERLAP)
    assert len(_named(result, "crown", "stupi")) == 1  # square plan: apex finial only
    oblong = _build(roof_style="kerala", footprint_y=80)
    assert len(_named(oblong, "crown", "stupi")) == 2 and _named(oblong, "crown", "ridge")
    # the drip edge: lifted by the 45° soffit when printable, level with the slab top otherwise
    def drip_z(build_result):
        r = _named(build_result, "crown", "roof")[0]
        edge = r.vertices[np.isclose(r.vertices[:, 0], r.vertices[:, 0].max())]
        return float(edge[:, 2].min())

    assert drip_z(result) == pytest.approx(L.roof_z - OVERLAP + 6.0)
    authentic = _build(roof_style="kerala", printable_overhangs=False)
    assert drip_z(authentic) == pytest.approx(authentic.layout.roof_z - OVERLAP)


# ---- plan --------------------------------------------------------------------------------


def test_kakshasana_runs_round_the_chosen_sides_and_opens_for_the_steps():
    result = _build(kakshasana="back+sides")
    seats = _named(result, "enclosure", "kakshasana")
    assert len(seats) == 3
    L = result.layout
    z_top, z_seat = 0.25 * 35.0, 0.45 * 0.25 * 35.0
    lean = 0.3 * (z_top - z_seat)
    for s in seats:
        assert s.bounds[1][2] == pytest.approx(L.floor_z + z_top)
        assert not _steep(s, floor_z=L.floor_z - OVERLAP)
    back = max(seats, key=lambda s: s.bounds[1][1])
    assert back.bounds[1][1] == pytest.approx(L.pillar_ys[-1] + 3.15 + lean)
    closed = _named(_build(kakshasana="all"), "enclosure", "kakshasana")
    assert len(closed) == 5
    front = [s for s in closed if s.bounds[1][1] < -L.pillar_ys[-1] + 6.0]  # the seat is 3.6 mm deep inboard
    assert len(front) == 2 and all(min(abs(s.bounds[0][0]), abs(s.bounds[1][0])) >= 22.0 - 1e-6 for s in front)
    assert not _named(_build(), "enclosure", "kakshasana")


def test_jali_fills_the_bays_but_leaves_the_door_open():
    result = _build(jali="all", printer_profile="resin")
    bars = _named(result, "enclosure", "jali")
    L = result.layout
    assert bars and all(min(s.bounds[1] - s.bounds[0]) >= 1.08 - 1e-6 for s in bars)
    assert not [s for s in bars if s.bounds[1][1] < -L.pillar_ys[-1] + 1.0]  # front: steps bay
    assert [s for s in bars if s.bounds[0][1] > L.pillar_ys[-1] - 1.0]  # back
    rails = [s for s in bars if len(s.vertices) == 10]
    assert rails and all(not _steep(r) for r in rails)
    seated = _build(jali="back", kakshasana="back")
    lowest = min(float(s.bounds[0][2]) for s in _named(seated, "enclosure", "jali"))
    assert lowest == pytest.approx(seated.layout.floor_z + 0.25 * 35.0 - OVERLAP)


def test_centre_feature_needs_a_free_centre():
    pitha = _named(_build(centre_feature="pitha"), "enclosure", "pitha")
    assert len(pitha) == 1 and pitha[0].bounds[1][0] - pitha[0].bounds[0][0] <= 2 * 1.2 * 6.0 + 1e-6
    assert pitha[0].bounds[0][2] == pytest.approx(12.0 - OVERLAP)
    assert len(_named(_build(centre_feature="pedestal"), "enclosure", "pedestal")) == 2
    odd = _build(centre_feature="pitha", pillars_x=3, pillars_y=3)
    assert not _named(odd, "enclosure", "pitha") and any("centre feature" in n for n in odd.notes)


def test_steps_sink_past_the_kantha_so_galapadas_seal_no_void():
    # plinth 15 mm at 0.12 projection: the recess is 0.54 mm deep, deeper than the old 0.5 mm sink
    result = _build(plinth_height=15.0, plinth_projection=0.12, steps_sides="all")
    mesh = make_mesh(result, union=True)
    assert mesh.is_watertight and body_count(mesh) == 1
    assert body_count(make_mesh(_build(), union=True)) == 1


def test_steps_on_every_side_with_a_hastihasta_curl():
    result = _build(steps_sides="all")
    assert len(_named(result, "steps", "step")) == 4 * 4
    lo = np.min([s.bounds[0] for s in result.parts["steps"]], axis=0)
    hi = np.max([s.bounds[1] for s in result.parts["steps"]], axis=0)
    assert lo[0] < -50 and hi[0] > 50 and lo[1] < -50 and hi[1] > 50
    rails = _named(result, "steps", "balustrade")
    assert len(rails) == 8 and all(len(r.vertices) == 20 for r in rails)
    for r in rails:
        assert not _steep(r, floor_z=0.0)
    plain = _named(_build(hastihasta=False), "steps", "balustrade")
    assert all(len(r.vertices) == 10 for r in plain)
    curled = _named(_build(printable_overhangs=False), "steps", "balustrade")
    assert all(_steep(r, floor_z=0.0) for r in curled)  # the trunk rolls right under


# ---- fuzz --------------------------------------------------------------------------------

FUZZ = int(os.environ.get("MANDAPA_FUZZ", "0"))


def _edge_cases():
    """Min and max of every numeric field, every choice, alternating the printable rule."""
    cases = []
    base = MandapaParams()
    for name, kind, meta in MandapaParams.specs():
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
    by default and on every case under MANDAPA_FUZZ>=30."""
    result = _build(**changes)
    assert result.parts["plinth"] and result.parts["pillars"] and result.parts["roof"]
    index = _EDGES.index(changes)
    if FUZZ >= 30 or index % 7 == 0:
        assert make_mesh(result, union=True).is_watertight, changes


@pytest.mark.parametrize("seed", range(FUZZ or 12))
def test_fuzz_randomized_designs_union_watertight(seed):
    p = MandapaParams().randomized(1000 + seed)
    result = build(p)
    for s in result.solids():
        s.check()
    mesh = make_mesh(result, union=True)
    assert mesh.is_watertight, p
    assert body_count(mesh) == 1, p
