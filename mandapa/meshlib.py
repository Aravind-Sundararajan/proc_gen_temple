"""Minimal watertight-mesh construction on top of numpy.

Every shape the generator produces goes through :func:`loft`, which turns a
stack of polygon "rings" into a closed, consistently wound (outward-facing)
triangle mesh.  Parts are kept as separate :class:`Solid` objects and only
unioned into one manifold at export time (see :mod:`mandapa.export`).

Conventions
-----------
* Units are millimetres, +Z is up.
* A ring is a ``(k, 3)`` array of points ordered counter-clockwise when seen
  from +Z.  A ``(1, 3)`` ring is an *apex* (the tip of a cone / pyramid).
* A profile is a sequence of ``(d, z)`` pairs from bottom to top.  What ``d``
  means depends on the sweep: the apothem (centre-to-flat distance) for
  n-gons, or the outward offset from the rectangle's faces for rectangles.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

import numpy as np

Array = np.ndarray
Profile = Sequence[tuple[float, float]]

_EPS = 1e-9


@dataclass
class Solid:
    """Indexed triangle mesh whose faces are CCW when seen from outside."""

    vertices: Array
    faces: Array
    name: str = ""

    def __post_init__(self) -> None:
        self.vertices = np.ascontiguousarray(self.vertices, dtype=np.float64).reshape(-1, 3)
        self.faces = np.ascontiguousarray(self.faces, dtype=np.int64).reshape(-1, 3)

    # ---- transforms (all return new solids) -------------------------------------------
    def translated(self, dx: float = 0.0, dy: float = 0.0, dz: float = 0.0) -> Solid:
        return Solid(self.vertices + np.array([dx, dy, dz]), self.faces, self.name)

    def rotated_z(self, degrees: float) -> Solid:
        a = math.radians(degrees)
        c, s = math.cos(a), math.sin(a)
        return self.transformed(np.array([[c, -s, 0.0], [s, c, 0.0], [0.0, 0.0, 1.0]]))

    def transformed(self, matrix: Array) -> Solid:
        """Apply a 3x3 linear map; it must not mirror (det > 0) so the winding survives."""
        m = np.asarray(matrix, dtype=np.float64)
        if np.linalg.det(m) <= 0:
            raise ValueError("transform would flip face orientation")
        return Solid(self.vertices @ m.T, self.faces, self.name)

    def scaled(self, s: float) -> Solid:
        if s <= 0:
            raise ValueError("scale must be positive")
        return Solid(self.vertices * s, self.faces, self.name)

    def renamed(self, name: str) -> Solid:
        return Solid(self.vertices, self.faces, name)

    # ---- queries ----------------------------------------------------------------------
    @property
    def bounds(self) -> tuple[Array, Array]:
        return self.vertices.min(axis=0), self.vertices.max(axis=0)

    def face_normals(self) -> Array:
        v = self.vertices[self.faces]
        n = np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0])
        length = np.linalg.norm(n, axis=1)
        length[length == 0] = 1.0
        return n / length[:, None]

    def volume(self) -> float:
        """Signed volume; positive when the faces point outward."""
        v = self.vertices[self.faces]
        return float(np.einsum("ij,ij->i", v[:, 0], np.cross(v[:, 1], v[:, 2])).sum() / 6.0)

    def is_watertight(self) -> bool:
        """Closed and consistently wound: each edge used exactly twice, in opposite directions."""
        f = self.faces
        if len(f) == 0:
            return False
        directed = np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
        _, counts = np.unique(directed, axis=0, return_counts=True)
        if counts.max() != 1:
            return False
        _, counts = np.unique(np.sort(directed, axis=1), axis=0, return_counts=True)
        return bool(np.all(counts == 2))

    def check(self) -> Solid:
        """Raise unless this is a valid closed, outward-facing mesh."""
        if not self.is_watertight():
            raise ValueError(f"solid {self.name!r} is not watertight")
        if self.volume() <= 0:
            raise ValueError(f"solid {self.name!r} has non-positive volume (inverted?)")
        return self


def merge(solids: Iterable[Solid], name: str = "") -> Solid:
    """Concatenate solids into one mesh.  Not a boolean union: shells may overlap."""
    solids = list(solids)
    if not solids:
        return Solid(np.zeros((0, 3)), np.zeros((0, 3), dtype=np.int64), name)
    verts, faces, offset = [], [], 0
    for s in solids:
        verts.append(s.vertices)
        faces.append(s.faces + offset)
        offset += len(s.vertices)
    return Solid(np.concatenate(verts), np.concatenate(faces), name)


# ---- rings ----------------------------------------------------------------------------


def apex(x: float, y: float, z: float) -> Array:
    return np.array([[x, y, z]], dtype=np.float64)


def ngon_ring(apothem: float, n: int, z: float, phase: float | None = None) -> Array:
    """Regular n-gon with the given centre-to-flat distance; flats face the axes by default.

    An apothem of zero collapses to an apex.
    """
    if n < 3:
        raise ValueError("n-gon needs at least 3 sides")
    if apothem <= _EPS:
        return apex(0.0, 0.0, z)
    if phase is None:
        phase = math.pi / n
    radius = apothem / math.cos(math.pi / n)
    t = phase + 2.0 * np.pi * np.arange(n) / n
    return np.column_stack([radius * np.cos(t), radius * np.sin(t), np.full(n, z)])


def rect_ring(hx: float, hy: float, z: float, d: float = 0.0) -> Array:
    """Axis-aligned rectangle with half-extents ``hx + d`` and ``hy + d``."""
    x, y = hx + d, hy + d
    if x <= _EPS and y <= _EPS:
        return apex(0.0, 0.0, z)
    if x <= _EPS or y <= _EPS:
        raise ValueError("rectangle collapsed in one axis only")
    return np.array([[x, -y, z], [x, y, z], [-x, y, z], [-x, -y, z]], dtype=np.float64)


# ---- triangulation --------------------------------------------------------------------


def fan_triangles(k: int) -> Array:
    """Fan triangulation of a convex k-gon, CCW."""
    i = np.arange(1, k - 1)
    return np.column_stack([np.zeros_like(i), i, i + 1])


def signed_area(points: Array) -> float:
    p = np.asarray(points, dtype=np.float64)
    x, y = p[:, 0], p[:, 1]
    return float(0.5 * (np.dot(x, np.roll(y, -1)) - np.dot(y, np.roll(x, -1))))


def triangulate_polygon(points: Array) -> Array:
    """Ear-clipping triangulation of a simple CCW polygon (no holes).  Returns (m, 3) indices.

    Collinear runs are kept as zero-area ears so that the cap's edge structure still
    matches the side walls produced by :func:`loft`.
    """
    pts = np.asarray(points, dtype=np.float64)
    n = len(pts)
    if n < 3:
        raise ValueError("polygon needs at least 3 points")
    if n == 3:
        return np.array([[0, 1, 2]])
    scale = max(float(np.ptp(pts[:, 0])), float(np.ptp(pts[:, 1])), 1e-12)
    eps = 1e-10 * scale * scale

    def cross(o: Array, a: Array, b: Array) -> float:
        return float((a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]))

    idx = list(range(n))
    out: list[list[int]] = []
    while len(idx) > 3:
        m = len(idx)
        reflex = [
            idx[i] for i in range(m) if cross(pts[idx[i - 1]], pts[idx[i]], pts[idx[(i + 1) % m]]) < -eps
        ]
        found = False
        for i in range(m):
            i0, i1, i2 = idx[i - 1], idx[i], idx[(i + 1) % m]
            a, b, c = pts[i0], pts[i1], pts[i2]
            if cross(a, b, c) <= eps:
                continue
            blocked = False
            for j in reflex:
                if j in (i0, i1, i2):
                    continue
                p = pts[j]
                if cross(a, b, p) >= -eps and cross(b, c, p) >= -eps and cross(c, a, p) >= -eps:
                    blocked = True
                    break
            if blocked:
                continue
            out.append([i0, i1, i2])
            idx.pop(i)
            found = True
            break
        if not found:
            # Only degenerate (collinear) ears remain; clip one to keep the topology closed.
            for i in range(m):
                i0, i1, i2 = idx[i - 1], idx[i], idx[(i + 1) % m]
                if abs(cross(pts[i0], pts[i1], pts[i2])) <= eps:
                    out.append([i0, i1, i2])
                    idx.pop(i)
                    found = True
                    break
            if not found:
                raise ValueError("could not triangulate polygon (self-intersecting?)")
    out.append(list(idx))
    return np.array(out, dtype=np.int64)


# ---- lofting --------------------------------------------------------------------------


def loft(rings: Sequence[Array], cap_tris: Array | None = None, name: str = "") -> Solid:
    """Skin a bottom-to-top stack of rings into a closed solid.

    All polygon rings must have the same vertex count and matching order.  A single-point
    apex ring may appear at either end.  ``cap_tris`` triangulates the (possibly concave)
    ring polygon for the end caps; the default fan is only valid for convex rings.
    """
    cleaned: list[Array] = []
    for r in rings:
        r = np.asarray(r, dtype=np.float64).reshape(-1, 3)
        if cleaned and cleaned[-1].shape == r.shape and np.allclose(cleaned[-1], r, atol=_EPS):
            continue
        cleaned.append(r)
    rings = cleaned
    if len(rings) < 2:
        raise ValueError("loft needs at least two distinct rings")
    k = max(len(r) for r in rings)
    if k < 3:
        raise ValueError("rings need at least 3 vertices")
    for r in rings[1:-1]:
        if len(r) != k:
            raise ValueError("apex rings are only allowed at the ends")
    for r in (rings[0], rings[-1]):
        if len(r) not in (1, k):
            raise ValueError("ring vertex counts must match")

    offsets = np.cumsum([0] + [len(r) for r in rings])
    idx = np.arange(k)
    nxt = (idx + 1) % k
    tris: list[Array] = []
    for a in range(len(rings) - 1):
        oa, ob = offsets[a], offsets[a + 1]
        if len(rings[a]) == 1:  # apex below a polygon ring
            tris.append(np.column_stack([np.full(k, oa), ob + nxt, ob + idx]))
        elif len(rings[a + 1]) == 1:  # apex above a polygon ring
            tris.append(np.column_stack([oa + idx, oa + nxt, np.full(k, ob)]))
        else:
            tris.append(np.column_stack([oa + idx, oa + nxt, ob + nxt]))
            tris.append(np.column_stack([oa + idx, ob + nxt, ob + idx]))
    cap = fan_triangles(k) if cap_tris is None else np.asarray(cap_tris, dtype=np.int64)
    if len(rings[0]) > 1:
        tris.append(offsets[0] + cap[:, ::-1])  # bottom cap faces down
    if len(rings[-1]) > 1:
        tris.append(offsets[-2] + cap)
    return Solid(np.concatenate(rings), np.concatenate(tris), name)


# ---- sweeps and primitives ------------------------------------------------------------


def sweep(profile: Profile, ring_fn: Callable[[float, float], Array], name: str = "") -> Solid:
    """Loft ``ring_fn(d, z)`` over a bottom-to-top ``(d, z)`` profile."""
    return loft([ring_fn(float(d), float(z)) for d, z in profile], name=name)


def rect_sweep(profile: Profile, hx: float, hy: float, name: str = "") -> Solid:
    """Sweep a moulding profile around a rectangle; ``d`` is the outward offset from its faces."""
    return sweep(profile, lambda d, z: rect_ring(hx, hy, z, d), name)


def ngon_sweep(profile: Profile, n: int, phase: float | None = None, name: str = "") -> Solid:
    """Sweep a profile around the Z axis as an n-gon; ``d`` is the apothem."""
    return sweep(profile, lambda d, z: ngon_ring(d, n, z, phase), name)


def box(
    sx: float, sy: float, sz: float, center: Sequence[float] = (0.0, 0.0, 0.0), name: str = ""
) -> Solid:
    cx, cy, cz = center
    z0, z1 = cz - sz / 2.0, cz + sz / 2.0
    return rect_sweep([(0.0, z0), (0.0, z1)], sx / 2.0, sy / 2.0, name).translated(cx, cy, 0.0)


def box_between(lo: Sequence[float], hi: Sequence[float], name: str = "") -> Solid:
    lo_a, hi_a = np.asarray(lo, dtype=np.float64), np.asarray(hi, dtype=np.float64)
    size = hi_a - lo_a
    if np.any(size <= 0):
        raise ValueError("box_between needs hi > lo on every axis")
    return box(*size, center=(lo_a + hi_a) / 2.0, name=name)


def prism(
    apothem: float, n: int, z0: float, z1: float, phase: float | None = None, name: str = ""
) -> Solid:
    return ngon_sweep([(apothem, z0), (apothem, z1)], n, phase, name)


def cylinder(radius: float, z0: float, z1: float, n: int = 32, name: str = "") -> Solid:
    """Round prism; ``radius`` is the circumradius so the silhouette matches a true cylinder."""
    return prism(radius * math.cos(math.pi / n), n, z0, z1, phase=0.0, name=name)


_AXIS = {
    "x": np.array([1.0, 0.0, 0.0]),
    "y": np.array([0.0, 1.0, 0.0]),
    "z": np.array([0.0, 0.0, 1.0]),
}


def extrude(points: Array, axes: str, w0: float, w1: float, name: str = "") -> Solid:
    """Extrude a simple 2-D polygon (may be concave) into a prism.

    ``axes`` names the world axes that the polygon's ``(u, v)`` coordinates map to, e.g.
    ``"xz"``; the prism spans ``w0..w1`` along the remaining axis.
    """
    if len(axes) != 2 or any(a not in _AXIS for a in axes) or axes[0] == axes[1]:
        raise ValueError("axes must be two distinct names from 'xyz'")
    u, v = _AXIS[axes[0]], _AXIS[axes[1]]
    w = np.cross(u, v)
    third = next(a for a in "xyz" if a not in axes)
    sign = float(np.dot(w, _AXIS[third]))
    lo, hi = sorted((sign * w0, sign * w1))
    if hi - lo <= _EPS:
        raise ValueError("extrusion length must be positive")
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if signed_area(pts) < 0:
        pts = pts[::-1]
    tris = triangulate_polygon(pts)
    r0 = np.column_stack([pts, np.full(len(pts), lo)])
    r1 = np.column_stack([pts, np.full(len(pts), hi)])
    return loft([r0, r1], cap_tris=tris, name=name).transformed(np.column_stack([u, v, w]))


# ---- profile helpers ------------------------------------------------------------------


def arc(
    cd: float, cz: float, r: float, start_deg: float, end_deg: float, n: int
) -> list[tuple[float, float]]:
    """Points on a circular arc in the (d, z) profile plane; 0° points outward (+d), 90° up."""
    t = np.radians(np.linspace(start_deg, end_deg, n))
    return [(cd + r * math.cos(a), cz + r * math.sin(a)) for a in t]


def overhang_mask(solid: Solid, max_angle_deg: float = 45.0, floor_z: float | None = None) -> Array:
    """Mask of faces that face downward more steeply than ``max_angle_deg`` from vertical.

    Faces lying on the build plate (``floor_z``) are excluded.
    """
    normals = solid.face_normals()
    mask = -normals[:, 2] > math.sin(math.radians(max_angle_deg)) + 1e-6
    if floor_z is not None:
        face_z = solid.vertices[solid.faces][:, :, 2].max(axis=1)
        mask &= face_z > floor_z + 1e-6
    return mask
