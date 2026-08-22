"""The ornament primitives: closed, outward, placed the right way round, and printable when asked."""

import math

import numpy as np
import pytest

from mandapa import ornament as O
from mandapa.meshlib import extrude, overhang_mask, signed_area


def _steep(solid, floor_z=None):
    """Any face steeper than 45°, ignoring the flat base every sunk ornament has at its lowest z."""
    if floor_z is None:
        floor_z = float(solid.vertices[:, 2].min())
    return bool(overhang_mask(solid, 45.0, floor_z).any())


def test_facing_turns_plus_z_into_each_wall_normal_without_mirroring():
    disc = O.medallion(1.0, 0.3).check()
    for direction, axis in (("+x", (1, 0, 0)), ("-x", (-1, 0, 0)), ("+y", (0, 1, 0)), ("-y", (0, -1, 0))):
        s = O.facing(disc, direction).check()
        assert s.vertices @ np.array(axis, dtype=float) == pytest.approx(disc.vertices[:, 2], abs=1e-12)
        assert s.volume() == pytest.approx(disc.volume())


def test_around_visits_the_four_faces_with_their_own_lengths():
    faces = O.around(40.0, 30.0)
    assert [f[2] for f in faces] == [0.0, 90.0, 180.0, 270.0]
    assert [(f[0], f[1]) for f in faces] == [(40.0, 30.0), (30.0, 40.0), (40.0, 30.0), (30.0, 40.0)]


def test_spaced_is_symmetric_and_never_tighter_than_the_pitch():
    pos = O.spaced(10.0, 3.0)
    assert pos == pytest.approx([-p for p in reversed(pos)])
    assert min(np.diff(pos)) >= 3.0 - 1e-9
    assert O.spaced(1.0, 3.0) == [0.0]
    assert O.spaced(-1.0, 3.0) == []


def test_galapadas_bridge_the_recess_symmetrically_with_corner_blocks():
    parts = O.galapadas(40.0, 30.0, 8.5, 10.0, -0.4, 0.2, 0.9, 7.2)
    for s in parts:
        s.check()
    # four corners + interior: spaced(38.7, 7.2) has 11 points, spaced(28.7, 7.2) has 8
    assert len(parts) == 4 + 2 * 9 + 2 * 6
    lo = np.min([s.bounds[0] for s in parts], axis=0)
    hi = np.max([s.bounds[1] for s in parts], axis=0)
    assert (lo[2], hi[2]) == pytest.approx((8.5, 10.0))
    assert (hi[0], hi[1]) == pytest.approx((40.0 - 0.4 + 0.2, 30.0 - 0.4 + 0.2))
    centres = sorted(round(float((s.bounds[0][0] + s.bounds[1][0]) / 2), 6) for s in parts)
    assert centres == sorted(-c for c in centres)


def test_padma_petals_slope_up_to_the_wall_and_stay_inside_the_band():
    petals = O.padma_band(20.0, 20.0, 0.0, 1.0, 0.6, 0.4, 1.6)
    assert petals
    for s in petals:
        s.check()
        assert not _steep(s, floor_z=0.0)
        assert s.vertices[:, 2].max() <= 1.0 + 1e-9
    assert max(float(s.bounds[1][0]) for s in petals) == pytest.approx(20.0 + 0.6 + 0.4)


def test_fluted_ring_alternates_ridge_and_valley():
    ring = O.fluted_ring(3.0, 0.4, 16, 2.0)
    assert ring.shape == (32, 3) and np.all(ring[:, 2] == 2.0)
    radii = np.hypot(ring[:, 0], ring[:, 1])
    assert radii[0::2] == pytest.approx(3.0) and radii[1::2] == pytest.approx(2.6)
    assert signed_area(ring[:, :2]) > 0
    O.fluted_prism(3.0, 0.4, 16, 0.0, 10.0).check()


def test_kattu_band_and_pushpa_bud_obey_the_45_degree_rule_when_asked():
    band = O.kattu_band(2.66, 3.3, 8, 5.0, 0.8).check()
    assert not _steep(band)
    assert not _steep(O.pushpa_bud(1.0, 0.0, printable=True).check())
    assert _steep(O.pushpa_bud(1.0, 0.0, printable=False).check())


def test_cap_boss_is_shallow_enough_to_print_at_0_3_of_its_radius():
    def steep_outside_the_wall(height):
        s = O.facing(O.cap_boss(1.0, height), "+x").check()
        proud = (s.vertices[s.faces][:, :, 0] >= -1e-9).all(axis=1)  # the sunk base band is inside the wall
        return bool((overhang_mask(s, 45.0) & proud).any())

    assert not steep_outside_the_wall(0.3)
    assert steep_outside_the_wall(0.7)


def test_frieze_bosses_and_dentils_cover_all_four_faces():
    bosses = O.frieze_bosses(30.0, 20.0, 5.0, 1.0, 0.3, 2.6)
    dents = O.dentils(30.0, 20.0, 4.0, 5.0, 1.0)
    for s in bosses + dents:
        s.check()
    for parts, reach in ((bosses, 0.3), (dents, 0.8)):
        hi = np.max([s.bounds[1] for s in parts], axis=0)
        lo = np.min([s.bounds[0] for s in parts], axis=0)
        assert (hi[0], hi[1], -lo[0], -lo[1]) == pytest.approx((30.0 + reach, 20.0 + reach, 30.0 + reach, 20.0 + reach))


def test_nasi_and_knob_are_anchored_in_their_host():
    n = O.nasi(0.0, 1.2, 3.0, "yz", 0.0, 4.3).check()
    lo, hi = n.bounds
    assert (lo[0], hi[0]) == pytest.approx((0.0, 4.3)) and lo[2] == pytest.approx(3.0)
    k = O.knob(0.3, 4.0).check()
    assert k.vertices[:, 2].min() == pytest.approx(4.0 - 0.09)


def test_panjara_plan_is_convex_with_the_apse_outward():
    plan = O.apsidal_plan(8.0, 5.6)
    assert signed_area(plan) > 0
    assert plan[:, 0].max() == pytest.approx(4.0) and plan[:, 0].min() == pytest.approx(-4.0)
    parts = O.panjara(8.0, 5.6, 0.0, 4.0, 2.5, 1.0)
    for s in parts:
        s.check()
    assert max(float(s.vertices[:, 2].max()) for s in parts) == pytest.approx(4.0 - O.OVERLAP + 2.5)


def test_hipped_roof_ridge_runs_along_the_long_axis_and_the_soffit_prints():
    roof = O.hipped_roof(40.0, 30.0, 10.0, 6.0, 1.0, 30.0, printable=True).check()
    z_top = 10.0 - O.OVERLAP + 6.0 + 1.0 + (6.0 + 29.8) * math.tan(math.radians(30.0))
    assert roof.vertices[:, 2].max() == pytest.approx(z_top)
    ridge = roof.vertices[np.isclose(roof.vertices[:, 2], z_top)]
    assert np.abs(ridge[:, 1]).max() <= 0.2 + 1e-9 and np.abs(ridge[:, 0]).max() == pytest.approx(10.2)
    assert not _steep(roof, floor_z=10.0 - O.OVERLAP)
    drip = roof.vertices[np.isclose(roof.vertices[:, 0], 46.0)][:, 2].min()
    assert drip == pytest.approx(10.0 - O.OVERLAP + 6.0)  # the 45° soffit lifts the drip edge by the overhang
    flat = O.hipped_roof(40.0, 30.0, 10.0, 6.0, 1.0, 30.0, printable=False).check()
    assert flat.vertices[np.isclose(flat.vertices[:, 0], 46.0)][:, 2].min() == pytest.approx(10.0 - O.OVERLAP)


def test_lattice_holes_grow_to_fit_and_printable_rails_have_no_ceiling():
    parts = O.lattice(0.0, 20.0, 0.0, 22.0, 1.0, 3.0, printable=True)
    for s in parts:
        s.check()
    rails = [s for s in parts if len(s.vertices) == 10]
    bars = [s for s in parts if len(s.vertices) == 8]
    assert len(rails) == 6 and len(bars) == 3  # 5 rows of holes 3.2 high, 4 columns 3.75 wide
    for r in rails:
        assert not _steep(r)
    ys = sorted(float((b.bounds[0][1] + b.bounds[1][1]) / 2) for b in bars)
    assert min(np.diff([0.5] + ys + [19.5])) - 1.0 >= 3.0


def test_seat_profile_leans_outward_within_the_45_degree_rule():
    prof = O.seat_profile(-3.6, 3.15, 0.0, 3.9, 8.75, 1.45, 2.1)
    seat = extrude(prof, "xz", 0.0, 10.0).check()
    assert seat.vertices[:, 0].max() == pytest.approx(3.15 + 1.45)
    assert not _steep(seat, floor_z=0.0)


def test_pedestal_flare_is_exactly_45_degrees():
    parts = O.pedestal(6.0, 0.0, 12.0)
    for s in parts:
        s.check()
    assert not _steep(parts[1])
