import math

import numpy as np
import pytest

from mandapa.meshlib import (
    arc,
    box,
    box_between,
    cylinder,
    extrude,
    merge,
    ngon_sweep,
    overhang_mask,
    prism,
    rect_sweep,
    triangulate_polygon,
)


def test_box_volume_and_watertight():
    b = box(10, 20, 30).check()
    assert math.isclose(b.volume(), 6000.0)
    lo, hi = b.bounds
    assert np.allclose(lo, [-5, -10, -15]) and np.allclose(hi, [5, 10, 15])


def test_box_between():
    b = box_between((1, 2, 3), (4, 6, 8)).check()
    assert math.isclose(b.volume(), 3 * 4 * 5)
    with pytest.raises(ValueError):
        box_between((0, 0, 0), (1, 0, 1))


def test_prism_and_cylinder():
    prism(5, 8, 0, 10).check()
    c = cylinder(5, 0, 10, 64).check()
    assert abs(c.volume() - math.pi * 25 * 10) < 8


def test_cones_with_apex_at_either_end():
    ngon_sweep([(5, 0), (0, 10)], 16).check()
    ngon_sweep([(0, 0), (5, 10)], 6).check()


def test_moulding_with_horizontal_steps():
    m = rect_sweep([(0, 0), (2, 0), (2, 3), (1, 3), (1, 5), (3, 5), (3, 6)], 10, 15).check()
    faces_down = overhang_mask(m, 45, floor_z=0)
    assert faces_down.sum() > 0  # the step-out undersides


def test_duplicate_profile_points_are_dropped():
    rect_sweep([(0, 0), (0, 0), (0, 5), (0, 5)], 3, 3).check()


def test_extrude_concave_polygon_every_axis_pair():
    L = [(0, 0), (4, 0), (4, 1), (1, 1), (1, 4), (0, 4)]  # area 7
    e = extrude(L, "xz", -2, 3).check()
    assert math.isclose(e.volume(), 35.0)
    lo, hi = e.bounds
    assert np.allclose(lo, [0, -2, 0]) and np.allclose(hi, [4, 3, 4])
    assert math.isclose(extrude(L[::-1], "yz", 0, 2).check().volume(), 14.0)
    assert math.isclose(extrude(L, "xy", 1, 0).check().volume(), 7.0)
    assert math.isclose(extrude(L, "zx", 0, 1).check().volume(), 7.0)


def test_extrude_rolled_corbel_profile():
    roll = [(0, 0), (6, 0)] + arc(6, 2, 2, -90, 0, 6) + [(8, 5), (0, 5)]
    extrude(roll, "xz", -1, 1).check()


def test_triangulate_polygon_keeps_collinear_vertices():
    pts = np.array([(0, 0), (1, 0), (2, 0), (2, 2), (0, 2)], dtype=float)
    tris = triangulate_polygon(pts)
    assert len(tris) == len(pts) - 2
    assert set(tris.ravel()) == set(range(len(pts)))


def test_merge_concatenates():
    a, b = box(1, 1, 1), prism(1, 6, 0, 1)
    m = merge([a, b])
    assert len(m.faces) == len(a.faces) + len(b.faces)
    assert len(m.vertices) == len(a.vertices) + len(b.vertices)


def test_transform_rejects_mirroring():
    with pytest.raises(ValueError):
        box(1, 1, 1).transformed(np.diag([-1.0, 1.0, 1.0]))
