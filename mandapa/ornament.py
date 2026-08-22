"""The small repeated solids that turn a massing model into a Dravidian building.

Everything here is *relief*: bosses, bands, petals, pilasters, dormers, buds.  None
of it changes the layout in :mod:`mandapa.builder` and none of it is allowed to
fail the build — an ornament that cannot be made at the requested size is
enlarged to the printer's minimum feature or dropped with a note, never drawn
too thin.  That rule is what lets every feature default to "on" without anyone
checking the print report first.

Why separate solids rather than carving the host
------------------------------------------------
The mesh kit has no boolean subtraction, and the final union in
:mod:`mandapa.export` is what makes the model one manifold shell.  So a medallion
is a disc that sinks a little into its block, a galapada is a box that sinks into
the recess behind it, and a flute is a ring shape rather than a cut.  Sinking by
a positive depth (rather than sharing a face) keeps the union free of coplanar
face pairs, which is where boolean kernels lose precision.

Printing rules baked in
-----------------------
A boss on a vertical face has an underside.  Below about 1.5 mm of protrusion
FDM prints it regardless (the bulge is a few layers of slightly longer
perimeter), so medallions and frieze bosses are kept that shallow instead of
being chamfered into something that no longer reads as a lotus.  Anything
larger — the pushpa bud, a kattu band — carries a 45° underside when the design
asks for printable overhangs and its authentic rounded profile otherwise.

Local frames
------------
Most ornaments are built once in a local frame (protruding along +Z, or sitting
on the +X face of a rectangle) and then rotated into place with
:func:`facing` / :func:`around`.  Building four copies in four frames by hand is
where the sign errors live.
"""

from __future__ import annotations

import numpy as np

from .meshlib import Solid, box_between, extrude, loft, ngon_ring, ngon_sweep, rect_sweep

OVERLAP = 0.05  # mm that neighbouring solids sink into each other (same as the builder)

Profile = list[tuple[float, float]]

# Rotations that take a solid built along +Z onto an outward-facing wall normal.
_FACING: dict[str, np.ndarray] = {
    "+x": np.array([[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [-1.0, 0.0, 0.0]]),
    "-x": np.array([[0.0, 0.0, -1.0], [0.0, 1.0, 0.0], [1.0, 0.0, 0.0]]),
    "+y": np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 1.0], [0.0, -1.0, 0.0]]),
    "-y": np.array([[1.0, 0.0, 0.0], [0.0, 0.0, -1.0], [0.0, 1.0, 0.0]]),
}


def facing(solid: Solid, direction: str) -> Solid:
    """Rotate a solid built protruding along +Z so that it protrudes along ``direction``."""
    return solid.transformed(_FACING[direction])


def around(hx: float, hy: float) -> list[tuple[float, float, float]]:
    """The four faces of an axis-aligned rectangle as ``(face distance, half length, angle)``.

    Build an ornament on the +X face (face at ``x = dist``, running along y) and rotate
    it by ``angle`` degrees about Z to reach the other three; the rotation keeps the
    winding, a mirror would not.
    """
    return [(hx, hy, 0.0), (hy, hx, 90.0), (hx, hy, 180.0), (hy, hx, 270.0)]


def spaced(half_len: float, pitch: float, margin: float = 0.0) -> list[float]:
    """Positions along ``[-half_len + margin, half_len - margin]`` at roughly ``pitch``.

    Symmetric about zero so the pattern reads the same from both corners; the pitch
    is stretched, never squeezed, so the end spacing is the one the design asked for.
    """
    usable = half_len - margin
    if usable <= 0:
        return []
    count = int(2 * usable // pitch) + 1
    if count < 2:
        return [0.0]
    return [float(v) for v in np.linspace(-usable, usable, count)]


# ---- plinth --------------------------------------------------------------------------


def galapadas(
    hx: float, hy: float, z0: float, z1: float, d_face: float, d_out: float, width: float, pitch: float
) -> list[Solid]:
    """Pilasters bridging a recess around a rectangle whose recessed face sits at offset ``d_face``.

    A block on every corner plus evenly spaced ones along each side: the kantha of a
    Pallava or Chola base is never left empty, and the corners are where the eye
    checks that the course is continuous.
    """
    parts: list[Solid] = []
    fx, fy = hx + d_face, hy + d_face
    for sx in (-1, 1):
        for sy in (-1, 1):
            lo = (min(sx * (fx - width), sx * (fx + d_out)), min(sy * (fy - width), sy * (fy + d_out)), z0)
            hi = (max(sx * (fx - width), sx * (fx + d_out)), max(sy * (fy - width), sy * (fy + d_out)), z1)
            parts.append(box_between(lo, hi, name="galapada"))
    for dist, half, angle in around(hx, hy):
        face = dist + d_face
        for c in spaced(half + d_face - width, pitch)[1:-1]:
            block = box_between((face - OVERLAP, c - width / 2, z0), (face + d_out, c + width / 2, z1), name="galapada")
            parts.append(block.rotated_z(angle) if angle else block)
    return parts


def padma_band(
    hx: float, hy: float, z0: float, z1: float, d_face: float, depth: float, width: float
) -> list[Solid]:
    """Lotus petals as a saw-tooth ring on the upana.

    Each petal is a triangular prism in plan whose tip leans back into the wall near
    the top, so the band reads as pointed petals rather than a zig-zag and every face
    of it slopes *up* towards the wall — nothing to support.
    """
    parts: list[Solid] = []
    for dist, half, angle in around(hx, hy):
        face = dist + d_face
        for c in spaced(half + d_face - width / 2, width):
            rings = [
                _petal_ring(face, c, width, depth, z0),
                _petal_ring(face, c, width, depth, z0 + 0.55 * (z1 - z0)),
                _petal_ring(face, c, width, 0.15 * depth, z1),
            ]
            petal = loft(rings, name="padma")
            parts.append(petal.rotated_z(angle) if angle else petal)
    return parts


def _petal_ring(face: float, c: float, width: float, tip: float, z: float) -> np.ndarray:
    return np.array([[face - OVERLAP, c - width / 2, z], [face + tip, c, z], [face - OVERLAP, c + width / 2, z]])


# ---- pillars -------------------------------------------------------------------------


def medallion(radius: float, depth: float, n: int = 16) -> Solid:
    """Flat lotus boss, built protruding along +Z from a base sunk 0.3 mm into the host face.

    A disc with a shallow conical top: the cone gives the rim a highlight in the viewer
    and the slicer a few shrinking perimeters instead of one abrupt step.
    """
    rings = [
        ngon_ring(radius, n, -0.3, phase=0.0),
        ngon_ring(radius, n, 0.7 * depth, phase=0.0),
        ngon_ring(0.55 * radius, n, depth, phase=0.0),
    ]
    return loft(rings, name="medallion")


def fluted_ring(apothem: float, depth: float, flutes: int, z: float) -> np.ndarray:
    """Ring of ``2 * flutes`` points alternating between ridge and valley radius.

    A valley is centred on each axis so the flutes face the viewer on all four sides.
    """
    n = 2 * flutes
    t = np.pi / n + 2.0 * np.pi * np.arange(n) / n
    r = np.where(np.arange(n) % 2 == 0, apothem, apothem - depth)
    return np.column_stack([r * np.cos(t), r * np.sin(t), np.full(n, z)])


def fluted_prism(apothem: float, depth: float, flutes: int, z0: float, z1: float, name: str = "shaft") -> Solid:
    return loft([fluted_ring(apothem, depth, flutes, z0), fluted_ring(apothem, depth, flutes, z1)], name=name)


def kattu_band(inner: float, outer: float, n: int, z: float, height: float) -> Solid:
    """Thin raised band centred on ``z`` with 45° chamfers above and below.

    The chamfers make it printable when it stands proud of a narrower shaft section
    and make it read as a moulding rather than a washer when it does not.
    """
    t = outer - inner
    prof = [
        (inner, z - height / 2 - t),
        (outer, z - height / 2),
        (outer, z + height / 2),
        (inner, z + height / 2 + t),
    ]
    return ngon_sweep(prof, n, name="kattu")


def pushpa_bud(radius: float, z_top: float, printable: bool) -> Solid:
    """Pendant lotus bud hanging from ``z_top`` (which must lie inside the host), built at the origin.

    Printable: a short cylinder ending in a 45° point, the steepest underside the
    45° rule allows.  Authentic: the rounded teardrop of the Vijayanagara pushpa-potika.
    """
    r = radius
    if printable:
        prof: Profile = [(0.0, z_top - 1.9 * r), (r, z_top - 0.9 * r), (r, z_top)]
    else:
        prof = [
            (0.0, z_top - 2.1 * r), (0.45 * r, z_top - 1.85 * r), (0.85 * r, z_top - 1.4 * r),
            (r, z_top - 0.8 * r), (0.85 * r, z_top - 0.3 * r), (0.8 * r, z_top),
        ]
    return ngon_sweep(prof, 12, name="pushpa")


# ---- entablature ---------------------------------------------------------------------


def dentils(hx: float, hy: float, z0: float, z1: float, size: float) -> list[Solid]:
    """Row of cubes on every face, one ``size`` apart, with a block at each corner.

    Protrusion is 0.8 of the size: a full cube casts a shadow that reads as a second
    cornice in the viewer; a shallower block reads as teeth under the kapota.
    """
    parts: list[Solid] = []
    for dist, half, angle in around(hx, hy):
        for c in spaced(half - size / 2, 2 * size):
            block = box_between((dist - OVERLAP, c - size / 2, z0), (dist + 0.8 * size, c + size / 2, z1), name="dentil")
            parts.append(block.rotated_z(angle) if angle else block)
    return parts


def cap_boss(radius: float, height: float, n: int = 12) -> Solid:
    """Spherical cap of base ``radius`` standing ``height`` proud of a wall, built along +Z.

    The base ring is sunk 0.3 mm so the union has a real overlap to work with.  Keeping
    ``height`` under 0.5 × radius keeps the rim normal within 53° of horizontal, which
    with the small size is what lets these print as surface texture without support.
    """
    R = (radius * radius + height * height) / (2.0 * height)
    theta0 = np.arcsin(min(radius / R, 1.0))
    rings = [ngon_ring(radius, n, -0.3, phase=0.0)]
    for t in np.linspace(theta0, 0.0, 5)[:-1]:
        rings.append(ngon_ring(R * np.sin(t), n, R * np.cos(t) - (R - height), phase=0.0))
    rings.append(np.array([[0.0, 0.0, height]]))
    return loft(rings, name="boss")


def frieze_bosses(hx: float, hy: float, z: float, radius: float, height: float, pitch: float) -> list[Solid]:
    """The bhuta-gana row: one boss every ``pitch`` along each face, centred on ``z``."""
    source = cap_boss(radius, height)
    spots: list[tuple[float, float, float, str]] = []
    for c in spaced(hy - radius, pitch):
        spots += [(hx, c, z, "+x"), (-hx, c, z, "-x")]
    for c in spaced(hx - radius, pitch):
        spots += [(c, hy, z, "+y"), (c, -hy, z, "-y")]
    return on_faces(source, spots)


def semicircle(c: float, r: float, zb: float, n: int = 9) -> list[tuple[float, float]]:
    """Closed half-disc outline standing on ``zb``, centred at ``c`` along the face, CCW."""
    pts = [(c - r, zb)]
    for t in np.linspace(0, np.pi, n)[::-1][1:-1]:
        pts.append((c + r * np.cos(t), zb + r * np.sin(t)))
    pts.append((c + r, zb))
    return pts


def knob(f: float, z_top: float) -> Solid:
    """Tiny kalasa-shaped finial of radius ``f`` whose base sinks 0.3 f into the host at ``z_top``."""
    prof: Profile = [(0.5 * f, z_top - 0.3 * f), (0.9 * f, z_top + 0.3 * f), (0.5 * f, z_top + 0.9 * f), (0.0, z_top + 1.4 * f)]
    return ngon_sweep(prof, 8, name="knob")


def nasi(c: float, r: float, zb: float, axes: str, w0: float, w1: float) -> Solid:
    """Horseshoe dormer: a half-disc slab from the shrine's centre plane out past its face.

    Extruding from the centre plane rather than from the face means the slab is anchored
    in whatever the shrine's roof does above the body — dome, barrel or apse — without
    this function having to know the roof's profile.
    """
    return extrude(semicircle(c, r, zb), axes, w0, w1, name="nasi")


# ---- roof ----------------------------------------------------------------------------


def apsidal_plan(kw: float, w: float, n_arc: int = 9) -> np.ndarray:
    """U-shaped plan for a panjara: rectangle from ``-kw/2`` with a semicircular end at ``+kw/2``.

    CCW, centred on the parapet line (x = 0), apse pointing along +X.
    """
    r = w / 2.0
    cx = kw / 2.0 - r
    pts = [(-kw / 2.0, -r)]
    for t in np.linspace(-np.pi / 2, np.pi / 2, n_arc):
        pts.append((cx + r * np.cos(t), r * np.sin(t)))
    pts.append((-kw / 2.0, r))
    return np.array(pts, dtype=np.float64)


def panjara(kw: float, w: float, z0: float, body_h: float, roof_h: float, r_nasi: float) -> list[Solid]:
    """Apsidal miniature shrine in its local frame: apse towards +X, centred on the parapet line.

    The roof is the plan lofted inwards to an apex: on the straight end that gives a
    hip, on the round end the quarter-dome the gajaprishtha ("elephant back") roof is
    named for.  Every roof face slopes up, so the form is printable at any size.
    """
    plan = apsidal_plan(kw, w)
    body = extrude(plan, "xy", z0, z0 + body_h, name="panjara")
    zb = z0 + body_h - OVERLAP
    rings = [np.column_stack([plan * s, np.full(len(plan), zb + f * roof_h)]) for s, f in
             ((1.0, 0.0), (0.92, 0.2), (0.7, 0.6), (0.4, 0.9))]
    rings.append(np.array([[0.0, 0.0, zb + roof_h]]))
    parts = [body, loft(rings, name="panjara")]
    if r_nasi > 0:
        parts.append(nasi(0.0, r_nasi, z0 + body_h - 0.3 * r_nasi, "yz", 0.0, kw / 2.0 + 0.25 * r_nasi))
    return parts


def hipped_roof(hx: float, hy: float, z0: float, eave: float, fascia: float, pitch_deg: float, printable: bool) -> Solid:
    """Kerala roof: four planes at ``pitch_deg`` meeting at a ridge (or an apex on a square plan).

    Swept as an offset profile around the slab rectangle, so the short axis closes
    first and the ridge runs along the long one by construction.  Under the 45° rule the
    eave's soffit rises at 45° from the slab edge to the drip; otherwise it is the flat
    underside a real eave has.  The ridge keeps a 0.4 mm flat rather than a knife edge:
    a loft cannot end in a line, and a slicer would drop the knife edge anyway.
    """
    tan = float(np.tan(np.radians(pitch_deg)))
    prof: Profile = [(0.0, z0 - OVERLAP)]
    if eave > 0:
        prof.append((eave, z0 - OVERLAP + (eave if printable else 0.0)))
    z_f = prof[-1][1] + fascia
    prof.append((eave, z_f))
    d_top = -(min(hx, hy) - 0.2)
    prof.append((d_top, z_f + (eave - d_top) * tan))
    return rect_sweep(prof, hx, hy, name="roof")


# ---- plan: seats, screens, altar ------------------------------------------------------


def seat_profile(d_in: float, d_out: float, z0: float, z_seat: float, z_top: float, lean: float, t: float) -> Profile:
    """Kakshasana section in (outward offset, z): a bench with a back-rest leaning outward.

    The back-rest leans by ``lean`` over its height, the Hoysala/Vijayanagara angle of
    about 17° from vertical — comfortable to lean on, and far inside the 45° rule, so
    its outer face never needs support.
    """
    return [
        (d_in, z0), (d_out, z0), (d_out, z_seat), (d_out + lean, z_top),
        (d_out + lean - t, z_top), (d_out - t, z_seat), (d_in, z_seat),
    ]


def rail(x0: float, x1: float, z0: float, bar: float, y0: float, y1: float, printable: bool) -> Solid:
    """Horizontal jali rail between ``y0`` and ``y1`` (local frame; the screen lies in the y-z plane).

    Printable rails carry a 45° V underside so the hole below has no flat ceiling to
    bridge; otherwise a plain bar, which is what the stone one is.
    """
    if printable:
        poly = [(x0, z0 + bar), (x1, z0 + bar), (x1, z0 + bar / 2), ((x0 + x1) / 2, z0), (x0, z0 + bar / 2)]
    else:
        poly = [(x0, z0), (x1, z0), (x1, z0 + bar), (x0, z0 + bar)]
    return extrude(poly, "xz", y0, y1, name="jali")


def lattice(y0: float, y1: float, z0: float, z1: float, bar: float, hole: float, printable: bool) -> list[Solid]:
    """Grid of square holes filling a bay ``y0..y1`` × ``z0..z1``, centred on x = 0.

    Bars are ``bar`` square; the hole count is whatever fits at least ``hole`` clear, so
    holes grow rather than shrink when the bay is not a multiple of the pitch.  The
    bottom rail and the end bars sink into floor and pillars; the top rail is expected
    to sink into the block above by the caller's choice of ``z1``.
    """
    parts: list[Solid] = []
    span_y, span_z = y1 - y0, z1 - z0
    ny = max(1, int((span_y - bar) // (hole + bar)))
    nz = max(1, int((span_z - bar) // (hole + bar)))
    py, pz = (span_y - bar) / ny, (span_z - bar) / nz
    for k in range(nz + 1):
        parts.append(rail(-bar / 2, bar / 2, z0 + k * pz, bar, y0 - OVERLAP, y1 + OVERLAP, printable))
    for k in range(1, ny):
        c = y0 + bar / 2 + k * py
        parts.append(box_between((-bar / 2, c - bar / 2, z0), (bar / 2, c + bar / 2, z1 + bar), name="jali"))
    return parts


def pedestal(s: float, z0: float, h: float) -> list[Solid]:
    """Square base, octagonal shaft, 45° lotus flare and a flat top: a pitha for an image or lamp."""
    base_h = 0.15 * h
    parts = [box_between((-0.6 * s, -0.6 * s, z0), (0.6 * s, 0.6 * s, z0 + base_h), name="pedestal")]
    z = z0 + base_h - OVERLAP
    flare = 0.25 * s
    prof: Profile = [(0.4 * s, z), (0.4 * s, z0 + h - flare - 0.1 * h), (0.65 * s, z0 + h - 0.1 * h), (0.65 * s, z0 + h)]
    parts.append(ngon_sweep(prof, 8, name="pedestal"))
    return parts


def wall_frame(
    face: float, c: float, z0: float, width: float, height: float, band: float, proud: float, name: str
) -> list[Solid]:
    """Raised surround of an opening or a panel on the +X face at ``x = face``: two jambs and a
    lintel, ``band`` wide and ``proud`` high, sunk OVERLAP into the wall.  ``width`` and
    ``height`` are the clear size inside the frame, centred on ``c`` along y and standing on
    ``z0``; the jambs run the full height so the corners are one piece.

    A framed rectangle is what makes a doorway read as a dvara and a flat panel as a niche —
    the eye takes the frame for an opening before it looks for depth, which is why a
    devakoshtha can be relief here instead of a recess the mesh kit cannot cut.  ``proud``
    stays under 1.5 mm (see the module note on bosses) so the lintel's underside prints as
    it is.
    """
    x0, x1 = face - OVERLAP, face + proud
    lo, hi = c - width / 2.0, c + width / 2.0
    return [
        box_between((x0, lo - band, z0), (x1, lo, z0 + height + band), name=name),
        box_between((x0, hi, z0), (x1, hi + band, z0 + height + band), name=name),
        box_between((x0, lo - OVERLAP, z0 + height), (x1, hi + OVERLAP, z0 + height + band), name=name),
    ]


# ---- generic placement ---------------------------------------------------------------


def on_faces(source: Solid, positions: list[tuple[float, float, float, str]]) -> list[Solid]:
    """Copies of a +Z-built ornament on wall faces: ``(x, y, z, direction)`` per copy."""
    return [facing(source, direction).translated(x, y, z) for x, y, z, direction in positions]


def placed(parts: list[Solid], x: float, y: float, angle: float) -> list[Solid]:
    """Rotate a local-frame assembly about Z by ``angle`` degrees, then move it to ``(x, y)``."""
    return [(s.rotated_z(angle) if angle else s).translated(x, y, 0.0) for s in parts]
