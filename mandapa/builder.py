"""Assembles the mandapa from the primitives in :mod:`mandapa.meshlib` and :mod:`mandapa.ornament`.

Heights stack bottom-up: plinth (adhishthana) → pillars (stambha) with capital
and corbel → beams (uttara) → roof block (valabhi frieze, kapota cornice, slab)
→ crown: a parapet of shrines (hara), stepped tiers, or a Kerala hipped roof.
Seats, screens, steps and the centre feature stand on the floor between.

Why every member is its own closed solid
----------------------------------------
Nothing here is carved out of anything else.  A pillar is a stack of prisms, a
corbel two extruded crosses, a medallion a disc sunk into its block.  Each sinks
:data:`OVERLAP` into its neighbour and the boolean union in :mod:`mandapa.export`
melts them into one shell.  The alternative — sweeping fewer, cleverer profiles —
was rejected because a single profile cannot change its polygon count half way
up, and a building does exactly that: square block, octagon, sixteen-gon, round
kalasa, square phalaka.  The cost is a union of several hundred solids, which
manifold3d does in a fifth of a second for the default hall.

Why :class:`Layout` is computed first and shared
------------------------------------------------
The print-prep step splits the model at ``floor_z`` and ``corbel_top`` and places
pegs under ``pillar_xs × pillar_ys``; the GUI reports bay spans; the ornament
needs the band heights.  One dataclass computed once, from the clamped
parameters, is the only way those numbers cannot disagree with what was built.
The fields that other modules read keep their names and meaning; new ones are
appended.

Where the proportions come from
-------------------------------
The base is the Mayamata *padabandha* in 24 parts: upana 2, jagati 6, kampa 1,
kumuda 7, kampa 1, kantha 3, kampa 1, pattika/prati 3 (see
:func:`plinth_profile`).  The capital follows the Tamil sequence kalasa, tadi,
kumbha, padma, phalaka, potika, with the padmabandha ring below (see
:func:`pillar`).  Ornament proportions are given at the function that places
them, with the precedent they are taken from.

Why the sanctum walls sit on the pillar lines
---------------------------------------------
A garbhagriha could be a box of any size on the floor, but a wall that crosses a
pillar part-way shows a sliver of shaft and half a capital.  Walls centred on the
grid lines swallow their pillars whole, and what emerges — the flare of the
capital, the corbel under the beam — is exactly the wall pilaster of a Dravidian
shrine, for free.  The cell therefore spans whole bays, centred on the hall, and
the pillars it has no use for (inside it, or standing in its doorway) are not
built at all; the peg plan reads :attr:`Layout.pillar_points` rather than the
grid for that reason.  The doorway is the one gap in the cell, which is also what
keeps the union one body: a cell without a door would be a sealed void.

Printing
--------
Two rules run through every function.  Under ``printable_overhangs`` no member
may have an underside steeper than 45° from vertical unless it is under about
1.5 mm (the kapota scoop flattens, the corbel bevel steepens, the pushpa bud
gets a 45° point, the Kerala eave a 45° soffit); with it off, authenticity wins.
And nothing is ever built thinner than ``min_feature``: it is enlarged where
that does not change its reading, dropped with a note in ``Build.notes`` where
it would.  Those notes are part of the contract — the GUI shows them — so they
are phrased for the person holding the slider, not for a log.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from itertools import pairwise

import numpy as np

from .meshlib import Solid, arc, box_between, extrude, ngon_sweep, prism, rect_sweep
from .ornament import (
    OVERLAP,
    dentils,
    fluted_prism,
    frieze_bosses,
    galapadas,
    hipped_roof,
    kattu_band,
    knob,
    lattice,
    medallion,
    nasi,
    on_faces,
    padma_band,
    panjara,
    pedestal,
    placed,
    pushpa_bud,
    seat_profile,
    wall_frame,
)
from .params import MandapaParams

Profile = list[tuple[float, float]]


def note_once(notes: list[str], text: str) -> None:
    """Ornament is placed per pillar or per side; the reader wants to hear each reason once."""
    if text not in notes:
        notes.append(text)


@dataclass
class Cell:
    """The garbhagriha as every other member sees it (mm, world frame).

    ``x0..x1`` and ``y0..y1`` are the wall centre lines, which are pillar lines of the grid
    (``i0..i1``, ``j0..j1`` their indices), and ``t`` is the wall thickness.  The dvara is
    centred on ``cx`` in the front (-Y) wall.  ``clear`` is what a vigraham gets: wall face
    to wall face, and the raised floor to the beam underside.
    """

    i0: int
    i1: int
    j0: int
    j1: int
    x0: float
    x1: float
    y0: float
    y1: float
    t: float
    z_floor: float  # top of the raised floor and of the threshold
    z_top: float  # wall top: the beam underside
    door_w: float
    door_h: float

    @property
    def cx(self) -> float:
        return (self.x0 + self.x1) / 2.0

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2.0

    @property
    def outer(self) -> tuple[float, float, float, float]:
        """``x lo, x hi, y lo, y hi`` of the outer wall faces."""
        h = self.t / 2.0
        return self.x0 - h, self.x1 + h, self.y0 - h, self.y1 + h

    @property
    def clear(self) -> tuple[float, float, float]:
        """Width, depth and height of the cavity."""
        return self.x1 - self.x0 - self.t, self.y1 - self.y0 - self.t, self.z_top - self.z_floor

    def holds(self, i: int, j: int) -> bool:
        """Whether grid point ``(i, j)`` lies strictly inside the cell."""
        return self.i0 < i < self.i1 and self.j0 < j < self.j1


@dataclass
class Layout:
    """Derived dimensions shared by all parts (mm)."""

    plinth_h: float
    proj: float
    body_hx: float
    body_hy: float
    top_hx: float
    top_hy: float
    floor_z: float
    pillar_w: float
    pillar_xs: list[float]
    pillar_ys: list[float]
    pillar_h: float
    shaft_h: float
    capital_h: float
    corbel_h: float
    corbel_reach: float
    beam_w: float
    beam_z0: float
    beam_z1: float
    corbel_top: float  # where the corbels end and the beams begin: the print-prep seam
    ent_hx: float
    ent_hy: float
    kapota_z0: float
    kapota_p: float
    kapota_h: float
    roof_z: float
    slab_hx: float
    slab_hy: float
    # appended: the sanctum, and the grid points that carry a pillar (all of them without one)
    cell: Cell | None = None
    pillar_points: list[tuple[int, int]] = field(default_factory=list)


@dataclass
class Build:
    parts: dict[str, list[Solid]]
    notes: list[str]
    layout: Layout
    params: MandapaParams = field(repr=False, default=None)

    def solids(self) -> list[Solid]:
        return [s for group in self.parts.values() for s in group]

    @property
    def height(self) -> float:
        return max(float(s.vertices[:, 2].max()) for s in self.solids())


# ---- layout ---------------------------------------------------------------------------


def compute_layout(p: MandapaParams, notes: list[str]) -> Layout:
    """Every shared dimension, derived once from the clamped parameters.

    The pillar grid is set from the plinth top rather than the footprint so that
    changing the torus projection moves the pillars with the edge they stand near;
    the entablature is set from the corbel tips so beams always land on brackets.
    Two print rules live here because they change dimensions other parts read: the
    corbel grows until its bevel clears 45°, and the kapota projection is capped at
    0.8 of its height for the same reason.  Both leave a note rather than a silent
    change.
    """
    H = p.plinth_height
    proj = p.plinth_projection * H
    fx, fy = p.footprint_x / 2.0, p.footprint_y / 2.0
    body_hx, body_hy = fx - proj, fy - proj
    top_hx, top_hy = body_hx + 0.5 * proj, body_hy + 0.5 * proj

    pw = p.pillar_width
    inset = p.pillar_inset * pw
    span_x = max(top_hx - inset, pw)
    span_y = max(top_hy - inset, pw)
    xs = [float(v) for v in np.linspace(-span_x, span_x, p.pillars_x)]
    ys = [float(v) for v in np.linspace(-span_y, span_y, p.pillars_y)]
    for axis, vals in (("X", xs), ("Y", ys)):
        spacing = vals[1] - vals[0]
        if spacing < 1.6 * pw:
            notes.append(f"pillars along {axis} are crowded: spacing {spacing:.1f} mm < 1.6x width")

    corbel_h = p.corbel_height * pw
    reach = p.corbel_reach * pw
    a = 0.75 * pw  # phalaka half-width, where the corbel bevel starts
    if p.printable_overhangs:
        needed = (reach - a) / 0.7  # bevel rises at >= 45 deg with a 30% vertical lip
        if needed > corbel_h:
            notes.append(f"corbel height raised to {needed:.1f} mm for the 45 deg rule")
            corbel_h = needed
    capital_h = p.capital_ratio * p.pillar_height
    shaft_h = p.pillar_height - capital_h - corbel_h
    if shaft_h < 0.25 * p.pillar_height:
        shaft_h = 0.25 * p.pillar_height
        capital_h = max(p.pillar_height - shaft_h - corbel_h, 0.1 * p.pillar_height)
        corbel_h = p.pillar_height - shaft_h - capital_h
        notes.append("pillar too short for the capital/corbel settings; proportions squeezed")

    floor_z = H
    beam_w = p.beam_width * pw
    bay = max(xs[1] - xs[0], ys[1] - ys[0]) - beam_w
    if bay > 30:
        notes.append(f"ceiling bridges {bay:.0f} mm between beams; add pillars or print with supports")
    beam_z0 = floor_z + p.pillar_height
    beam_z1 = beam_z0 + p.beam_height
    ent_hx, ent_hy = xs[-1] + reach, ys[-1] + reach

    kapota_p, kapota_h = p.kapota_projection, p.kapota_height
    if p.printable_overhangs and kapota_p > 0.8 * kapota_h:
        kapota_p = 0.8 * kapota_h
        notes.append(f"kapota projection limited to {kapota_p:.1f} mm for the 45 deg rule")
    kapota_z0 = beam_z1 + p.frieze_height
    roof_z = kapota_z0 + kapota_h + p.roof_slab
    slab_hx, slab_hy = ent_hx + 0.35 * kapota_p, ent_hy + 0.35 * kapota_p

    L = Layout(
        plinth_h=H, proj=proj, body_hx=body_hx, body_hy=body_hy, top_hx=top_hx, top_hy=top_hy,
        floor_z=floor_z, pillar_w=pw, pillar_xs=xs, pillar_ys=ys, pillar_h=p.pillar_height,
        shaft_h=shaft_h, capital_h=capital_h, corbel_h=corbel_h, corbel_reach=reach,
        beam_w=beam_w, beam_z0=beam_z0, beam_z1=beam_z1, corbel_top=beam_z0 - OVERLAP,
        ent_hx=ent_hx, ent_hy=ent_hy,
        kapota_z0=kapota_z0, kapota_p=kapota_p, kapota_h=kapota_h, roof_z=roof_z,
        slab_hx=slab_hx, slab_hy=slab_hy,
    )
    L.cell = cell_layout(p, L, notes)
    L.pillar_points = [
        (i, j) for i in range(len(xs)) for j in range(len(ys)) if not pillar_omitted(L, i, j)
    ]
    return L


def centred_run(n_bays: int, k: int) -> tuple[int, int]:
    """Grid indices ``(i0, i1)`` of a run of ``k`` bays centred on a row of ``n_bays``.

    A run is centred only when the bays left over split evenly between the two sides, so a
    count of the wrong parity is narrowed by one, or widened when it cannot narrow: a
    three-pillar row has no single centre bay, only a centre pillar, so its centred cell is
    both bays.
    """
    k = max(1, min(k, n_bays))
    if (n_bays - k) % 2:
        k = k - 1 if k > 1 else k + 1
    i0 = (n_bays - k) // 2
    return i0, i0 + k


def cell_layout(p: MandapaParams, L: Layout, notes: list[str]) -> Cell | None:
    """Where the garbhagriha stands and how big its dvara is, or ``None`` with a note.

    The cell spans whole bays: centred on both axes for ``centre``, centred across and
    against the back row for ``back``, where it keeps at least one bay in front of it for
    the hall when the grid has one to give.  The dvara keeps the texts' proportion, twice
    as high as wide: a wall too low for the width asked narrows the opening rather than
    squashing it, with a lintel of at least 0.15 of the wall kept above.  A cell whose walls
    would leave no cavity, or no doorway the printer can make, is not built: a sanctum
    nothing fits into is the thing this feature exists to prevent.
    """
    if p.sanctum == "none":
        return None
    xs, ys = L.pillar_xs, L.pillar_ys
    nx, ny = len(xs) - 1, len(ys) - 1
    i0, i1 = centred_run(nx, p.sanctum_bays)
    if i1 - i0 != p.sanctum_bays:
        grew = "widened" if i1 - i0 > p.sanctum_bays else "narrowed"
        notes.append(f"sanctum {grew} to {i1 - i0} bay(s) to sit centred on the {len(xs)}-pillar rows")
    if p.sanctum == "centre":
        j0, j1 = centred_run(ny, p.sanctum_bays)
        if j1 - j0 != p.sanctum_bays and j1 - j0 != i1 - i0:
            notes.append(f"sanctum made {j1 - j0} bay(s) deep to sit centred on the {len(ys)}-pillar rows")
    else:
        j1 = ny
        j0 = ny - min(p.sanctum_bays, max(ny - 1, 1))
    if i1 - i0 == nx and j1 - j0 == ny:
        notes.append("the sanctum takes the whole hall: no open bay is left round it")
    t = max(p.sanctum_wall * L.pillar_w, 2.0 * p.min_feature, 1.0)
    x0, x1, y0, y1 = xs[i0], xs[i1], ys[j0], ys[j1]
    clear_w, clear_d = x1 - x0 - t, y1 - y0 - t
    if min(clear_w, clear_d) < max(3.0, 4.0 * p.min_feature):
        notes.append("pillars too close for a sanctum with a cavity between its walls; skipped")
        return None
    z_floor = L.floor_z + p.sanctum_floor * p.pillar_height
    z_top = L.beam_z0
    wall_h = z_top - z_floor
    lintel = max(0.15 * wall_h, 2.0 * p.min_feature, 1.0)
    door_w = min(p.dvara_width * clear_w, (wall_h - lintel) / 2.0)
    door_h = 2.0 * door_w
    if min(door_w, door_h) < max(1.0, 2.0 * p.min_feature):
        notes.append("walls too low for a doorway the printer can make; sanctum skipped")
        return None
    cell = Cell(i0, i1, j0, j1, x0, x1, y0, y1, t, z_floor, z_top, door_w, door_h)
    w, d, h = cell.clear
    notes.append(
        f"garbhagriha: {w:.1f} x {d:.1f} mm between the walls, {h:.1f} mm from its floor to "
        f"the beams; dvara {door_w:.1f} x {door_h:.1f} mm"
    )
    return cell


def pillar_omitted(L: Layout, i: int, j: int) -> bool:
    """A pillar is left out where the sanctum has no use for it: inside the cell, or on the
    front wall line within the doorway, where it would stand in the door."""
    cell = L.cell
    if cell is None:
        return False
    if cell.holds(i, j):
        return True
    in_door = abs(L.pillar_xs[i] - cell.cx) < cell.door_w / 2.0 + L.pillar_w / 2.0
    return j == cell.j0 and cell.i0 <= i <= cell.i1 and in_door


# ---- profile helpers ------------------------------------------------------------------


def bulge(d0: float, d_max: float, z0: float, z1: float, n: int = 7) -> Profile:
    """Half-ellipse from (d0, z0) out to d_max and back to (d0, z1)."""
    zc, hz = (z0 + z1) / 2.0, (z1 - z0) / 2.0
    pts = []
    for t in np.linspace(-math.pi / 2, math.pi / 2, n):
        pts.append((d0 + (d_max - d0) * math.cos(t), zc + hz * math.sin(t)))
    return pts


def stupi(cx: float, cy: float, z0: float, radius: float, height: float, p: MandapaParams) -> list[Solid]:
    """Pot-shaped finial (kalasa on a stem).  Skipped when it would be thinner than the printer allows."""
    r = max(radius, p.min_feature * 0.75)
    if height <= 0.2 or r > 2.5 * radius + 0.5:
        return []
    profile = [
        (0.55 * r, z0 - OVERLAP),
        (0.55 * r, z0 + 0.18 * height),
        (1.0 * r, z0 + 0.45 * height),
        (0.85 * r, z0 + 0.65 * height),
        (0.35 * r, z0 + 0.8 * height),
        (0.0, z0 + height),
    ]
    return [ngon_sweep(profile, 12, name="stupi").translated(cx, cy, 0.0)]


# ---- parts ----------------------------------------------------------------------------


# Mayamata padabandha: 24 parts bottom to top — upana 2, jagati 6, kampa 1, kumuda 7,
# kampa 1, kantha 3, kampa 1, pattika/prati 3.  The two bands the ornaments touch are
# named so the galapadas and the padma petals cannot drift away from the profile.
UPANA = (0, 2)
KANTHA = (17, 20)
UPANA_D = 0.9  # upana face, as a fraction of the projection
KANTHA_D = -0.3  # the recess sits behind the jagati face


def plinth_profile(style: str, H: float, pr: float, padma: bool = False) -> Profile:
    """The adhishthana moulding as a bottom-to-top ``(offset, z)`` profile.

    Shared by the plinth and the miniature pitha in the centre of the hall: a pitha
    *is* an adhishthana at small scale, and giving it its own profile is how the two
    end up disagreeing.  With ``padma`` the upana face is pulled back so the petals
    of the padma band can fill out to where the plain upana would have been; the
    footprint is therefore unchanged by the band.
    """
    u = H / 24.0
    if style == "plain":
        return [(pr, 0), (pr, 3 * u), (0.3 * pr, 6 * u), (0.3 * pr, 20 * u), (0.5 * pr, 22 * u), (0.5 * pr, 24 * u)]
    upana = 0.6 * pr if padma else UPANA_D * pr
    prof: Profile = [
        (upana, 0.0), (upana, UPANA[1] * u),  # upana
        (0.0, 2 * u), (0.0, 8 * u),  # jagati
        (0.35 * pr, 8 * u), (0.35 * pr, 9 * u),  # kampa
    ]
    if style == "pratibandha":  # round torus
        prof += bulge(0.35 * pr, pr, 9 * u, 16 * u)
    else:  # tripatta kumuda: three facets
        prof += [(pr, 11 * u), (pr, 14 * u), (0.35 * pr, 16 * u)]
    prof += [
        (0.35 * pr, 17 * u),  # kampa
        (KANTHA_D * pr, KANTHA[0] * u), (KANTHA_D * pr, KANTHA[1] * u),  # kantha (recess)
        (0.35 * pr, 20 * u), (0.35 * pr, 21 * u),  # kampa
    ]
    if style == "kapotabandha":  # dripstone instead of the plain pattika
        prof += [(1.1 * pr, 22.5 * u), (1.1 * pr, 23 * u), (0.5 * pr, 23.5 * u), (0.5 * pr, 24 * u)]
    else:
        prof += [(0.7 * pr, 21 * u), (0.7 * pr, 23.5 * u), (0.5 * pr, 23.5 * u), (0.5 * pr, 24 * u)]
    return prof


def plinth(p: MandapaParams, L: Layout, notes: list[str]) -> list[Solid]:
    """Adhishthana body first (its bounds are the footprint), then the ornament on it.

    Galapadas bridge the kantha at a pitch of 0.6 plinth heights: close enough that
    the recess reads as a row of niches, the Pallava/Chola signature, rather than as
    an interrupted groove.  Both ornaments need a real projection to stand on, so a
    nearly flat plinth (projection under about 0.7 mm) gets a note instead.
    """
    pr, H = L.proj, L.plinth_h
    u = H / 24.0
    padma = p.plinth_padma and p.plinth_style != "plain"
    parts = [rect_sweep(plinth_profile(p.plinth_style, H, pr, padma), L.body_hx, L.body_hy, name="plinth")]
    if p.plinth_style == "plain":
        return parts
    if p.plinth_galapadas:
        kz0, kz1 = KANTHA[0] * u, KANTHA[1] * u
        width = max(0.6 * (kz1 - kz0), p.min_feature)
        if pr < 0.7 or width > 1.5 * (kz1 - kz0):
            notes.append("kantha too shallow or too low for galapadas; skipped")
        else:
            parts += galapadas(
                L.body_hx, L.body_hy, kz0 - OVERLAP, kz1 + OVERLAP, KANTHA_D * pr, 0.15 * pr, width, 0.6 * H
            )
    if padma:
        band_h = UPANA[1] * u
        width = max(2.2 * u, 2 * p.min_feature)
        if pr < 0.85 or band_h < 0.5:
            notes.append("upana too small for a padma band; skipped")
        else:
            parts += padma_band(L.body_hx, L.body_hy, 0.0, band_h, 0.6 * pr, 0.3 * pr, width)
    return parts


# Rotation that carries something built for the front (-Y) to each compass side.
_SIDE_ANGLE = {"S": 0.0, "E": 90.0, "N": 180.0, "W": 270.0}


def side_frame(p: MandapaParams, L: Layout, side: str) -> tuple[float, float, float, list[float]]:
    """(plinth half-depth, footprint half-depth, footprint width, outer pillar positions) for a side.

    Everything on a side is built in the front frame — the side runs along local X,
    outward is local -Y — and rotated into place, so each feature is written once.
    """
    if side in ("S", "N"):
        return L.body_hy, p.footprint_y / 2.0, p.footprint_x, L.pillar_xs
    return L.body_hx, p.footprint_x / 2.0, p.footprint_y, L.pillar_ys


def steps_opening(p: MandapaParams, L: Layout, side: str) -> float:
    """Half-width of the gap a flight of steps needs in a seat or screen on ``side``; 0 if none."""
    if not p.steps or side not in p.sides("steps_sides"):
        return 0.0
    W = p.steps_width * side_frame(p, L, side)[2]
    t = max(0.12 * W, 1.5, p.min_feature * 2) if p.balustrades else 0.0
    return W / 2.0 + t + 0.3


def wall_block(L: Layout, side: str) -> tuple[float, float] | None:
    """The stretch of ``side``'s outer pillar line that a sanctum wall occupies, in the side's
    local X (see :func:`side_frame`), or ``None`` when the cell does not reach that row.

    Seats and screens are built in a frame where every side runs along local X and is then
    turned into place; the front keeps world X, the back (turned 180°) sees -X, and the
    flanks see +Y and -Y.  Screens are built in the east frame instead, but the two frames
    agree on this mapping, so one function serves both.
    """
    cell = L.cell
    if cell is None:
        return None
    xo0, xo1, yo0, yo1 = cell.outer
    last_i, last_j = len(L.pillar_xs) - 1, len(L.pillar_ys) - 1
    if side == "S" and cell.j0 == 0:
        return xo0, xo1
    if side == "N" and cell.j1 == last_j:
        return -xo1, -xo0
    if side == "E" and cell.i1 == last_i:
        return yo0, yo1
    if side == "W" and cell.i0 == 0:
        return -yo1, -yo0
    return None


def open_spans(p: MandapaParams, L: Layout, side: str, end: float) -> list[tuple[float, float]]:
    """Stretches of ``[-end, end]`` along ``side`` a seat can run on: the steps' gap and a
    sanctum wall are taken out."""
    blocked: list[tuple[float, float]] = []
    opening = steps_opening(p, L, side)
    if opening > 0:
        blocked.append((-opening, opening))
    block = wall_block(L, side)
    if block is not None:
        blocked.append(block)
    spans = [(-end, end)]
    for lo, hi in blocked:
        cut: list[tuple[float, float]] = []
        for a, b in spans:
            if hi <= a or lo >= b:
                cut.append((a, b))
                continue
            if lo > a:
                cut.append((a, lo))
            if hi < b:
                cut.append((hi, b))
        spans = cut
    return spans


def steps(p: MandapaParams, L: Layout) -> list[Solid]:
    """Sopana on every chosen side, with optional balustrades ending in a hastihasta curl.

    The curl is the elephant-trunk volute the balustrade ends in: a half-round nose at
    the foot.  Under the 45° rule the nose stops a quarter-turn short and runs to the
    ground at 45°; authentically it rolls right under, which is the overhang that makes
    real ones read as trunks.
    """
    if not p.steps:
        return []
    parts: list[Solid] = []
    H, n = L.plinth_h, p.step_count
    rise = H / n
    tread = max(1.1 * rise, 1.5)
    for side in p.sides("steps_sides"):
        body_hy, fy, width, _ = side_frame(p, L, side)
        W = p.steps_width * width
        # Sunk past the deepest moulding (the kantha recess) into the plinth body: a flight
        # that stopped short of the recess would seal a hair-thin void against it once
        # galapadas close the ends, and a void is a second shell in the STL.
        y_in = -(body_hy + KANTHA_D * L.proj - 0.5)
        flight: list[Solid] = []
        for k in range(1, n + 1):
            y_out = -(fy + (n - k + 1) * tread)
            flight.append(box_between((-W / 2, y_out, 0.0), (W / 2, y_in, H * k / n), name="step"))
        if p.balustrades:
            t = max(0.12 * W, 1.5, p.min_feature * 2)
            y_end = -(fy + n * tread + 0.6 * tread)
            b_end = 0.35 * H
            if p.hastihasta:
                r = b_end / 2.0
                if p.printable_overhangs:
                    # the nose stops at 225° and meets the ground at exactly 45°
                    k = 1.0 - math.cos(math.radians(45.0))
                    poly = [(y_in, 0.0), (y_end + 2 * k * r, 0.0)] + arc(y_end + r, r, r, 225, 90, 7)
                else:
                    poly = [(y_in, 0.0)] + arc(y_end + r, r, r, 270, 90, 9)
                poly.append((y_in, H + 0.3 * H))
            else:
                poly = [(y_in, 0.0), (y_end, 0.0), (y_end, 0.7 * b_end), (y_end + 0.3 * tread, b_end), (y_in, H + 0.3 * H)]
            for x0 in (W / 2, -W / 2 - t):
                flight.append(extrude(poly, "yz", x0, x0 + t, name="balustrade"))
        parts += placed(flight, 0.0, 0.0, _SIDE_ANGLE[side])
    return parts


def kakshasana(p: MandapaParams, L: Layout, notes: list[str]) -> list[Solid]:
    """Seat-back parapets along the chosen sides, continuous past the pillars, open at the steps.

    A quarter of the pillar height overall, seat at 0.45 of that: the proportions of the
    Vijayanagara halls where the pillars stand on the bench.  The back-rest runs on the
    pillars' outer face so the dwarf-pillar reading survives the union.
    """
    sides = p.sides("kakshasana")
    if not sides:
        return []
    pw = L.pillar_w
    z_top = 0.25 * p.pillar_height
    if z_top < max(1.5, 2.5 * p.min_feature):
        notes.append("pillars too short for a kakshasana seat at this printer setting; skipped")
        return []
    z_seat = 0.45 * z_top
    t = max(0.35 * pw, 1.5 * p.min_feature)
    lean = 0.3 * (z_top - z_seat)
    d_in, d_out = -0.6 * pw, 0.5 * pw + 0.15
    fl = L.floor_z
    prof = seat_profile(d_in, d_out, fl - OVERLAP, fl + z_seat, fl + z_top, lean, t)
    parts: list[Solid] = []
    perpendicular = {"S": ("E", "W"), "N": ("E", "W"), "E": ("S", "N"), "W": ("S", "N")}
    for side in sides:
        _, _, _, along = side_frame(p, L, side)
        line = pillar_line(L, side)
        # front frame: the seat runs along local X on the pillar line y = -line, outward is -Y
        poly = [(-line - d, z) for d, z in prof]
        # run to the outer face of the corner pillars, and over the neighbouring seat's lean
        end = along[-1] + d_out + (lean if all(s in sides for s in perpendicular[side]) else 0.0)
        spans = open_spans(p, L, side, end)
        wall = [extrude(poly, "yz", x0, x1, name="kakshasana") for x0, x1 in spans if x1 - x0 >= 2.0]
        parts += placed(wall, 0.0, 0.0, _SIDE_ANGLE[side])
    return parts


def pillar_line(L: Layout, side: str) -> float:
    """Distance from the centre to the outer pillar row on ``side``."""
    return (L.pillar_ys if side in ("S", "N") else L.pillar_xs)[-1]


def seat_height(p: MandapaParams) -> float:
    """Top of the kakshasana back-rest above the floor, or 0 when no seat can be built."""
    z_top = 0.25 * p.pillar_height
    return z_top if z_top >= max(1.5, 2.5 * p.min_feature) else 0.0


# Rotation that carries something built on the +X side (running along Y) to each compass side.
_EAST_ANGLE = {"E": 0.0, "N": 90.0, "W": 180.0, "S": 270.0}


def jali(p: MandapaParams, L: Layout, notes: list[str]) -> list[Solid]:
    """Lattice screens in the outer bays of the chosen sides, from floor (or seat) to the shaft top.

    Holes are half a pillar width, bars 0.18 of one, both clamped to the printer's
    minimum feature; the bay with the steps stays open because that is the door.  The
    screen stops at the top of the shaft zone rather than at the beams so it never has
    to meet the flaring capital.
    """
    sides = p.sides("jali")
    if not sides:
        return []
    pw = L.pillar_w
    a = pw / 2.0
    bar = max(0.18 * pw, p.min_feature)
    hole = max(0.5 * pw, 2.5 * p.min_feature)
    z1 = L.floor_z + L.shaft_h - 0.5 - bar
    parts: list[Solid] = []
    seats = p.sides("kakshasana") if seat_height(p) else ()
    for side in sides:
        z0 = L.floor_z + (seat_height(p) if side in seats else 0.0) - OVERLAP
        if z1 - z0 < 2 * hole + 3 * bar:
            note_once(notes, "bays too low for a jali screen at this printer setting; skipped")
            continue
        _, _, _, along = side_frame(p, L, side)
        line = pillar_line(L, side)
        open_half = steps_opening(p, L, side)
        block = wall_block(L, side)
        for c0, c1 in pairwise(along):
            y0, y1 = c0 + 0.8 * a, c1 - 0.8 * a
            if open_half > 0 and y1 > -open_half and y0 < open_half:
                continue
            if block is not None and block[0] < (c0 + c1) / 2.0 < block[1]:
                continue  # a sanctum wall fills this bay
            if y1 - y0 < hole + 2 * bar:
                continue
            panel = lattice(y0, y1, z0, z1, bar, hole, p.printable_overhangs)
            angle = _EAST_ANGLE[side]
            dx, dy = {"E": (line, 0.0), "N": (0.0, line), "W": (-line, 0.0), "S": (0.0, -line)}[side]
            parts += placed(panel, dx, dy, angle)
    return parts


def centre_feature(p: MandapaParams, L: Layout, notes: list[str]) -> list[Solid]:
    """A pitha (miniature adhishthana) or an image pedestal in the middle of the floor — or,
    when there is a garbhagriha, on its floor, where the vigraham's own pitha belongs.

    Sized to 1.2 pillar widths but never closer than a pillar width to any pillar, so an
    odd-by-odd grid — which has a pillar on the centre — gets a note instead.  Inside the
    cell it is capped at 0.3 of the clear width, and the height left above it is reported,
    because that is what the image has to fit into.
    """
    if p.centre_feature == "none":
        return []
    cell = L.cell
    if cell is not None:
        w, d, h_clear = cell.clear
        s = min(1.2 * L.pillar_w, 0.3 * min(w, d))
        cx, cy, z0 = cell.cx, cell.cy, cell.z_floor - OVERLAP
    else:
        a = L.pillar_w / 2.0
        xs, ys = L.pillar_xs, L.pillar_ys
        s_max = min(max(abs(x), abs(y)) - a - 1.0 for x in xs for y in ys)
        spacing = min(xs[1] - xs[0], ys[1] - ys[0])
        s = min(1.2 * L.pillar_w, 0.3 * spacing, s_max)
        cx, cy, z0 = 0.0, 0.0, L.floor_z - OVERLAP
    if s < 1.5:
        notes.append("no room between the pillars for a centre feature; skipped")
        return []
    if p.centre_feature == "pitha":
        H = max(0.35 * L.plinth_h, 1.5)
        pr = min(max(0.12 * H, 0.4), 0.3 * s)
        prof = [(d, z + z0) for d, z in plinth_profile(p.plinth_style, H, pr)]
        parts = [rect_sweep(prof, s - pr, s - pr, name="pitha")]
    else:
        H = max(0.35 * p.pillar_height, 2.0)
        parts = pedestal(s, z0, H)
    if cell is not None:
        notes.append(f"{p.centre_feature} on the garbhagriha floor: {h_clear - H:.1f} mm clear above it")
    return placed(parts, cx, cy, 0.0)


_SHAFT_SEGMENTS: dict[str, list[tuple[int, float, float]]] = {
    # (sides, apothem factor of half-width, share of shaft height).  The 16-sided
    # segment of "fluted" is built with alternating radii instead of a plain prism.
    "chola": [(4, 1.0, 0.28), (8, 0.92, 0.52), (4, 1.0, 0.20)],
    "square": [(4, 1.0, 1.0)],
    "octagonal": [(4, 1.0, 0.15), (8, 0.92, 0.85)],
    "sixteen": [(4, 1.0, 0.15), (16, 0.94, 0.85)],
    "round": [(4, 1.0, 0.15), (32, 0.94, 0.85)],
    "fluted": [(4, 1.0, 0.15), (16, 0.94, 0.85)],
}


def shaft(p: MandapaParams, L: Layout, style: str, notes: list[str]) -> list[Solid]:
    """The shaft zone at the origin: section segments, kattu bands between them, medallions.

    Medallions go on the square blocks only — that is where the Chola mason put the
    lotus, the octagon being left plain or fluted.  Their radius is 0.3 pillar widths
    but never more than 0.42 of the block height, so a short top block gets a smaller
    boss rather than one spilling over the band above it.  Kattu bands sit exactly on
    the section changes; their outer size is the wider neighbour plus a lip, so they
    stand proud of both.
    """
    a = L.pillar_w / 2.0
    parts: list[Solid] = []
    z = L.floor_z - 4 * OVERLAP
    zone = L.shaft_h + 4 * OVERLAP
    segments = _SHAFT_SEGMENTS[style]
    spans: list[tuple[float, float]] = []
    for n, k, share in segments:
        h = zone * share
        if style == "fluted" and n == 16:
            flutes = 16 if 2 * math.pi * k * a / 32 >= 0.6 * p.min_feature else 8
            parts.append(fluted_prism(k * a, 0.12 * a, flutes, z - OVERLAP, z + h))
        else:
            parts.append(prism(k * a, n, z - OVERLAP, z + h, name="shaft"))
        spans.append((z, z + h))
        z += h

    if p.kattu_bands and len(segments) > 1:
        lip = max(0.05 * L.pillar_w, 0.4 * p.min_feature)
        height = max(0.1 * L.pillar_w, p.min_feature)
        for (n0, k0, _), (n1, k1, _), (z0, z1), (_, z2) in zip(segments, segments[1:], spans, spans[1:]):
            if height > 0.25 * min(z1 - z0, z2 - z1):
                note_once(notes, "shaft segments too short for kattu bands; skipped")
                continue
            inner, outer = min(k0, k1) * a - 0.1, max(k0, k1) * a + lip
            parts.append(kattu_band(inner, outer, 8 if max(n0, n1) >= 8 else 4, z1, height))

    if p.medallions:
        depth = max(0.25, 0.3 * p.min_feature)
        for (n, k, _), (z0, z1) in zip(segments, spans):
            if n != 4:
                continue
            r = min(0.3 * L.pillar_w, 0.42 * (z1 - z0))
            if r < p.min_feature:
                note_once(notes, "square blocks too small for lotus medallions at this printer setting; skipped")
                continue
            zm = (z0 + z1) / 2.0
            spots = [(k * a, 0.0, zm, "+x"), (-k * a, 0.0, zm, "-x"), (0.0, k * a, zm, "+y"), (0.0, -k * a, zm, "-y")]
            parts += on_faces(medallion(r, depth), spots)
    return parts


def pillar(p: MandapaParams, L: Layout, x: float, y: float, style: str, notes: list[str]) -> list[Solid]:
    """Stambha: shaft zone, then kalasa-tadi-kumbha-padma-phalaka capital, then the potika corbel."""
    a = L.pillar_w / 2.0
    parts: list[Solid] = shaft(p, L, style, notes)

    # capital
    hc = L.capital_h
    zc = L.floor_z + L.shaft_h
    bands = [0.08, 0.28, 0.08, 0.26, 0.18, 0.12]  # padmabandha, kalasa, tadi, kumbha, padma, phalaka
    z0 = zc
    zs = []
    for share in bands:
        zs.append((z0 - OVERLAP, z0 + share * hc))
        z0 += share * hc
    (pb0, pb1), (ka0, ka1), (ta0, ta1), (ku0, ku1), (pa0, pa1), (ph0, ph1) = zs
    parts.append(prism(0.86 * a, 16, pb0, pb1, name="padmabandha"))
    kh = ka1 - ka0
    parts.append(ngon_sweep(
        [(0.62 * a, ka0), (0.92 * a, ka0 + 0.45 * kh), (0.66 * a, ka0 + 0.85 * kh), (0.80 * a, ka1)],
        24, name="kalasa",
    ))
    parts.append(prism(1.0 * a, 24, ta0, ta1, name="tadi"))
    kh = ku1 - ku0
    parts.append(ngon_sweep(
        [(0.80 * a, ku0), (1.12 * a, ku0 + 0.45 * kh), (1.05 * a, ku0 + 0.7 * kh), (0.90 * a, ku1)],
        24, name="kumbha",
    ))
    parts.append(ngon_sweep([(0.90 * a, pa0), (1.36 * a, pa1)], 16, name="padma"))
    parts.append(prism(1.5 * a, 4, ph0, ph1, name="phalaka"))

    parts = [s.translated(x, y, 0.0) for s in parts]
    return parts + corbel(p, L, x, y, ph1 - OVERLAP, notes)


def corbel(p: MandapaParams, L: Layout, x: float, y: float, z0: float, notes: list[str]) -> list[Solid]:
    """Potika: cross-shaped bracket with bevelled (or rolled, taranga) arm undersides.

    The pushpa style is the Vijayanagara corbel: a plain bevel with a lotus bud on a
    short stem under each arm tip.  The stem is what lets the bud hang clear of the
    bevel — hung directly from the underside, the inner half of a bud is buried in the
    arm whenever the bevel is steep, which it always is under the 45° rule.
    """
    hc, a, reach, wc = L.corbel_h, 0.75 * L.pillar_w, L.corbel_reach, L.beam_w
    lip = 0.3 * hc
    if p.corbel_style == "taranga" and reach - a > 0.5:
        rr = min(0.25 * hc, 0.3 * (reach - a))
        half = [(a, 0.0), (reach - rr, hc - lip - rr)] + arc(reach - rr, hc - lip, rr, -90, 0, 5)[1:]
    else:
        half = [(a, 0.0), (reach, hc - lip)]
    half.append((reach, hc))
    left = [(-u, v) for (u, v) in reversed(half)]
    poly = half + left  # closes back to (a, 0) along the flat underside
    arms = [
        extrude(poly, "xz", -wc / 2, wc / 2, name="corbel"),
        extrude(poly, "yz", -wc / 2, wc / 2, name="corbel"),
    ]
    if p.corbel_style == "pushpa":
        rb = min(0.32 * wc, 0.5 * (reach - a))
        if 2 * rb < 1.5 * p.min_feature or rb < 0.3:
            note_once(notes, "corbel arms too small for pushpa buds at this printer setting; skipped")
        else:
            rs = max(0.45 * rb, 0.5 * p.min_feature)
            z_stem = hc - lip - 0.5 * rb
            for dx, dy in ((reach - rb, 0.0), (rb - reach, 0.0), (0.0, reach - rb), (0.0, rb - reach)):
                arms.append(prism(rs, 12, z_stem - OVERLAP, hc - lip + OVERLAP, name="stem").translated(dx, dy, 0.0))
                arms.append(pushpa_bud(rb, z_stem + OVERLAP, p.printable_overhangs).translated(dx, dy, 0.0))
    return [s.translated(x, y, z0) for s in arms]


def beams(p: MandapaParams, L: Layout) -> list[Solid]:
    """Uttara: a perimeter ring plus one beam per interior pillar row and column."""
    z0, z1 = L.beam_z0 - OVERLAP, L.beam_z1
    w = L.beam_w / 2.0
    ex, ey = L.ent_hx, L.ent_hy
    xs, ys = L.pillar_xs, L.pillar_ys
    parts = [
        box_between((xs[-1] - w, -ey, z0), (ex, ey, z1), name="beam"),
        box_between((-ex, -ey, z0), (xs[0] + w, ey, z1), name="beam"),
        box_between((-ex, ys[-1] - w, z0), (ex, ey, z1), name="beam"),
        box_between((-ex, -ey, z0), (ex, ys[0] + w, z1), name="beam"),
    ]
    for y in ys[1:-1]:
        parts.append(box_between((-ex, y - w, z0), (ex, y + w, z1), name="beam"))
    for x in xs[1:-1]:
        parts.append(box_between((x - w, -ey, z0), (x + w, ey, z1), name="beam"))
    return parts


def roof_block(p: MandapaParams, L: Layout) -> Solid:
    """Valabhi frieze, kapota cornice and the roof slab as one swept solid."""
    P, hk, zk0 = L.kapota_p, L.kapota_h, L.kapota_z0
    prof: Profile = [(0.0, L.beam_z1 - OVERLAP), (0.0, zk0)]
    if P > 0.05 and hk > 0.05:
        scoop = 0.0 if p.printable_overhangs else p.kapota_scoop
        # underside: quadratic curve from the wall to the drip edge; scoop sags it downward
        p0, p2 = (0.0, zk0), (P, zk0 + 0.8 * hk)
        ctrl = ((1 - scoop) * P / 2 + scoop * P, (1 - scoop) * (zk0 + 0.4 * hk) + scoop * zk0)
        steps_n = 6
        for i in range(1, steps_n + 1):
            t = i / steps_n
            d = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * ctrl[0] + t * t * p2[0]
            z = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * ctrl[1] + t * t * p2[1]
            prof.append((d, z))
        prof.append((P, zk0 + 0.88 * hk))  # drip lip
        for t in np.linspace(0, math.pi / 2, 5)[1:]:  # roll over the top
            prof.append((0.35 * P + 0.65 * P * math.cos(t), zk0 + 0.88 * hk + 0.12 * hk * math.sin(t)))
        prof.append((0.35 * P, L.roof_z))
    else:
        prof.append((0.0, L.roof_z))
    return rect_sweep(prof, L.ent_hx, L.ent_hy, name="roof")


def kudus(p: MandapaParams, L: Layout) -> list[Solid]:
    """Horseshoe-arch ornaments along the kapota face."""
    return kudu_row(p, L.ent_hx, L.ent_hy, L.kapota_p, L.kapota_h, L.kapota_z0)


def kudu_row(p: MandapaParams, hx: float, hy: float, P: float, hk: float, zk0: float) -> list[Solid]:
    """Kudus around one kapota course, stated by its own dimensions.

    Split from :func:`kudus` so the gopuram's base prastara — a kapota that is not this
    Layout's — can carry the same row; ``p`` supplies only ``kudus``, ``finial`` and the
    printer, which both parameter families state.
    """
    if not p.kudus or P <= 0.05 or hk <= 0.05:
        return []
    r = max(0.22 * hk, p.min_feature * 1.2)
    if r > 0.45 * hk:
        return []
    depth = max(0.35 * r, p.min_feature * 0.8)
    zb = zk0 + 0.8 * hk - 0.35 * r
    spacing = 3.2 * r
    margin = P + 1.8 * r
    parts = []

    def semicircle(c: float) -> list[tuple[float, float]]:
        pts = [(c - r, zb)]
        for t in np.linspace(0, math.pi, 9)[::-1][1:-1]:
            pts.append((c + r * math.cos(t), zb + r * math.sin(t)))
        pts.append((c + r, zb))
        return pts

    def positions(half_len: float) -> list[float]:
        usable = half_len - margin
        if usable < r:
            return []
        count = int(2 * usable // spacing) + 1
        return [float(v) for v in np.linspace(-usable, usable, count)] if count > 1 else [0.0]

    # A finial on each arch when the printer can make one: the knob is 0.3 r, and below
    # 0.6 of the minimum feature it would print as a blob, so it is simply left off.
    f = 0.3 * r
    crown = p.finial and f >= 0.6 * p.min_feature and f >= 0.15
    for s in (1, -1):  # +X / -X sides: polygon in yz, extruded along x
        x0, x1 = hx + P - 0.8 * r, hx + P + depth
        for c in positions(hy):
            parts.append(extrude(semicircle(c), "yz", s * x0, s * x1, name="kudu"))
            if crown:
                parts.append(knob(f, zb + r).translated(s * (x0 + x1) / 2, c, 0.0))
        y0, y1 = hy + P - 0.8 * r, hy + P + depth
        for c in positions(hx):
            parts.append(extrude(semicircle(c), "xz", s * y0, s * y1, name="kudu"))
            if crown:
                parts.append(knob(f, zb + r).translated(c, s * (y0 + y1) / 2, 0.0))
    return parts


def frieze(p: MandapaParams, L: Layout, notes: list[str]) -> list[Solid]:
    """Valabhi ornament: bhuta-gana bosses along the frieze and a dentil course under the kapota.

    Both live in the band between the beams and the kapota.  With both on, the dentils
    take the top 35 % and the bosses the rest; with one, it gets 45 % (dentils) or the
    whole band (bosses).  Each is dropped with a note when the printer's minimum
    feature would make it larger than the band it sits in.
    """
    fh = p.frieze_height
    z_lo, z_hi = L.beam_z1, L.kapota_z0
    parts: list[Solid] = []
    dent = 0.0
    if p.dentils:
        size = max((0.35 if p.bhuta_frieze else 0.45) * fh, p.min_feature)
        if fh < 1.0 or size > 0.6 * fh:
            notes.append("frieze too low for a dentil course at this printer setting; skipped")
        else:
            dent = size
            parts += dentils(L.ent_hx, L.ent_hy, z_hi - size, z_hi + OVERLAP, size)
    if p.bhuta_frieze:
        zone = fh - dent
        r = 0.4 * zone
        if r < p.min_feature or r < 0.3:
            notes.append("frieze too low for a bhuta-gana row at this printer setting; skipped")
        else:
            h = (0.3 if p.printable_overhangs else 0.5) * r
            parts += frieze_bosses(L.ent_hx, L.ent_hy, z_lo + zone / 2, r, h, 2.6 * r)
    return parts


def nasi_radius(kw: float, p: MandapaParams, notes: list[str]) -> float:
    """Dormer radius for a shrine of width ``kw``, or 0 with a note when the printer cannot make it."""
    if not p.nasi:
        return 0.0
    r = 0.16 * kw
    if r < p.min_feature or r < 0.25:
        note_once(notes, "hara shrines too small for nasi dormers at this printer setting; skipped")
        return 0.0
    return r


def kuta(cx: float, cy: float, z0: float, kw: float, ph: float, p: MandapaParams, notes: list[str]) -> list[Solid]:
    """Square miniature shrine: body, neck, four-sided dome, finial, and a nasi on each face."""
    body_h, neck_h, dome_h = 0.5 * ph, 0.06 * ph, 0.3 * ph
    parts = [box_between((cx - kw / 2, cy - kw / 2, z0), (cx + kw / 2, cy + kw / 2, z0 + body_h), name="kuta")]
    z = z0 + body_h
    parts.append(prism(0.36 * kw, 4, z - OVERLAP, z + neck_h, name="kuta"))
    z += neck_h
    dome = [(0.48 * kw, z - OVERLAP), (0.42 * kw, z + 0.45 * dome_h), (0.2 * kw, z + 0.85 * dome_h), (0.0, z + dome_h)]
    parts.append(ngon_sweep(dome, 4, name="kuta"))
    parts = [s.translated(cx, cy, 0.0) if s.name == "kuta" and s is not parts[0] else s for s in parts]
    if p.finial:
        parts += stupi(cx, cy, z + dome_h - 0.1 * dome_h, 0.14 * kw, 0.14 * ph, p)
    r = nasi_radius(kw, p, notes)
    if r:
        zb, reach = z0 + body_h - 0.3 * r, kw / 2 + 0.25 * r
        for s in (1, -1):
            parts.append(nasi(cy, r, zb, "yz", cx, cx + s * reach))
            parts.append(nasi(cx, r, zb, "xz", cy, cy + s * reach))
    return parts


def sala(
    cx: float, cy: float, z0: float, length: float, kw: float, ph: float, along: str, p: MandapaParams, notes: list[str]
) -> list[Solid]:
    """Rectangular shrine with a barrel-vault roof running along ``along`` ('x' or 'y')."""
    body_h, vault_h = 0.55 * ph, 0.3 * ph
    hl, hw = length / 2.0, kw / 2.0
    if along == "x":
        lo, hi = (cx - hl, cy - hw, z0), (cx + hl, cy + hw, z0 + body_h)
    else:
        lo, hi = (cx - hw, cy - hl, z0), (cx + hw, cy + hl, z0 + body_h)
    parts = [box_between(lo, hi, name="sala")]
    zb = z0 + body_h - OVERLAP
    poly = [(-hw, zb), (hw, zb), (hw, zb + 0.25 * vault_h)]
    for t in np.linspace(0, math.pi, 9)[1:-1]:
        poly.append((hw * math.cos(t), zb + 0.25 * vault_h + 0.75 * vault_h * math.sin(t)))
    poly.append((-hw, zb + 0.25 * vault_h))
    if along == "x":
        vault = extrude(poly, "yz", cx - hl, cx + hl, name="sala").translated(0.0, cy, 0.0)
    else:
        vault = extrude(poly, "xz", cy - hl, cy + hl, name="sala").translated(cx, 0.0, 0.0)
    parts.append(vault)
    count = 3 if length > 3.5 * kw else 1
    offsets = [float(f) for f in np.linspace(-0.3 * length, 0.3 * length, count)] if count > 1 else [0.0]
    if p.finial:
        ridge_z = zb + vault_h
        for f in offsets:
            fx, fy = (cx + f, cy) if along == "x" else (cx, cy + f)
            parts += stupi(fx, fy, ridge_z - 0.05 * vault_h, 0.1 * kw, 0.12 * ph, p)
    r = nasi_radius(kw, p, notes)
    if r:  # dormers on the long faces, under the finials
        zn, reach = z0 + body_h - 0.3 * r, hw + 0.25 * r
        for f in offsets:
            for s in (1, -1):
                if along == "x":
                    parts.append(nasi(cx + f, r, zn, "xz", cy, cy + s * reach))
                else:
                    parts.append(nasi(cy + f, r, zn, "yz", cx, cx + s * reach))
    return parts


def hara(p: MandapaParams, L: Layout, notes: list[str]) -> list[Solid]:
    """Parapet of miniature shrines on the roof: corner kutas, salas between, harantara walls."""
    ph = p.parapet_height
    qx, qy = L.slab_hx - p.parapet_inset, L.slab_hy - p.parapet_inset
    if qx < 2.0 or qy < 2.0:
        notes.append("roof too small for a parapet; skipped")
        return []
    kw = min(1.0 * ph, 0.45 * qx, 0.45 * qy)
    z0 = L.roof_z - OVERLAP
    parts: list[Solid] = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts += kuta(sx * (qx - kw / 2), sy * (qy - kw / 2), z0, kw, ph, p, notes)

    n = p.salas_per_side
    pj_w = 0.7 * kw  # panjara frontage: narrower than a kuta, as in the Chola hara
    pj_any = False
    for axis, q_along, q_across in (("y", qy, qx), ("x", qx, qy)):
        free = 2 * (q_along - kw)
        centres: list[float] = []
        length = 0.0
        if n > 0 and free > 1.5 * kw:
            length = min(2.2 * kw, 0.7 * free / n)
            centres = [-(q_along - kw) + (k + 1) * free / (n + 1) for k in range(n)]
        # The gaps between consecutive elements along the side (kuta, salas..., kuta) are
        # where panjaras go: kuta-panjara-sala-panjara-kuta when each gap is wide enough.
        edges = [-(q_along - kw)] + [e for c in centres for e in (c - length / 2, c + length / 2)] + [q_along - kw]
        gaps = [(edges[i], edges[i + 1]) for i in range(0, len(edges), 2)]
        for s in (-1, 1):
            line = s * (q_across - kw / 2)
            angle = {("y", 1): 0.0, ("y", -1): 180.0, ("x", 1): 90.0, ("x", -1): 270.0}[(axis, s)]
            for c in centres:
                cx, cy = (line, c) if axis == "y" else (c, line)
                parts += sala(cx, cy, z0, length, kw, ph, axis, p, notes)
            if not p.panjaras:
                continue
            for g0, g1 in gaps:
                if g1 - g0 < pj_w + 0.3 * kw:
                    continue
                c = (g0 + g1) / 2
                cx, cy = (line, c) if axis == "y" else (c, line)
                body_h, roof_h = 0.5 * ph, 0.32 * ph
                parts += placed(panjara(kw, pj_w, z0, body_h, roof_h, nasi_radius(kw, p, notes)), cx, cy, angle)
                if p.finial:
                    parts += stupi(cx, cy, z0 + body_h + 0.9 * roof_h, 0.1 * kw, 0.12 * ph, p)
                pj_any = True
    if p.panjaras and not pj_any:
        notes.append("no room for panjaras between the hara shrines; skipped")

    t = max(0.4 * kw, p.min_feature)
    wall_h = 0.4 * ph
    lx, ly = qx - kw / 2, qy - kw / 2
    for s in (-1, 1):
        parts.append(box_between((s * lx - t / 2, -ly, z0), (s * lx + t / 2, ly, z0 + wall_h), name="harantara"))
        parts.append(box_between((-lx, s * ly - t / 2, z0), (lx, s * ly + t / 2, z0 + wall_h), name="harantara"))
    return parts


def stepped_roof(p: MandapaParams, L: Layout, notes: list[str]) -> list[Solid]:
    """Tiered pyramid over the whole roof: :func:`tower` on the slab inside the parapet inset."""
    hx, hy = L.slab_hx - p.parapet_inset, L.slab_hy - p.parapet_inset
    return tower(p, hx, hy, L.roof_z - OVERLAP, notes, "roof")


def tower(p: MandapaParams, hx: float, hy: float, z: float, notes: list[str], what: str) -> list[Solid]:
    """Tiered pyramid on a ``2 hx × 2 hy`` footprint at the origin: shrinking storeys with small
    eaves, topped by a neck, dome and finial.

    The stepped roof over a hall and the vimana over a garbhagriha are the same form at two
    sizes — the texts count both in talas — so they are one function, and the Roof group's
    tiers, ratio and sikhara shape drive both.
    """
    th, r = p.parapet_height, p.tier_ratio
    if hx < 2.0 or hy < 2.0:
        notes.append(f"{what} too small for tiers; skipped")
        return []
    parts: list[Solid] = []
    for _ in range(p.tiers):
        eave = min(0.32 * th, 0.2 * min(hx, hy))
        prof = [
            (0.0, z), (0.0, z + 0.6 * th),
            (eave, z + 0.6 * th + eave),  # 45 deg chamfer
            (eave, z + 0.6 * th + eave + 0.04 * th),
            (0.3 * eave, z + th),
        ]
        parts.append(rect_sweep(prof, hx, hy, name="tier"))
        z += th - OVERLAP
        hx, hy = hx * r, hy * r
    gw = 0.8 * min(hx, hy)
    neck_h, dome_h = 0.4 * th, 0.8 * th
    # The griva and sikhara share one plan: square is the nagara form, octagonal the
    # dravida, round (24 sides) the vesara.  Flats face the axes so the square matches
    # the tiers below it.
    sides = {"square": 4, "octagonal": 8, "round": 24}[p.sikhara_shape]
    parts.append(ngon_sweep([(gw, z), (gw, z + neck_h)], sides, name="griva"))
    z += neck_h - OVERLAP
    if p.printable_overhangs:  # the dome's flare over the neck rises at 45° instead of jutting flat
        dome = [(0.95 * gw, z), (1.1 * gw, z + 0.15 * gw)]
    else:
        dome = [(1.1 * gw, z)]
    dome += [(1.0 * gw, z + 0.4 * dome_h), (0.6 * gw, z + 0.8 * dome_h), (0.0, z + dome_h)]
    parts.append(ngon_sweep(dome, sides, name="sikhara"))
    if p.finial:
        parts += stupi(0.0, 0.0, z + 0.9 * dome_h, 0.18 * gw, 0.5 * th, p)
    return parts


def kerala_roof(p: MandapaParams, L: Layout, notes: list[str]) -> list[Solid]:
    """Hipped timber-style roof over the slab, with a ridge crest and finials at the ridge ends.

    The eaves hang ``eave_overhang`` past the slab, which is itself wider than the
    kapota drip, so the roof shades the cornice the way a Kerala roof shades its
    walls.  Pitch is a parameter because the texts give none: 30° is the common
    tiled pitch, steeper roofs are the thatched ones.
    """
    return hipped(p, L.slab_hx, L.slab_hy, L.roof_z, p.eave_overhang, notes, "roof")


def hipped(
    p: MandapaParams, hx: float, hy: float, z0: float, eave: float, notes: list[str], what: str
) -> list[Solid]:
    """A hipped roof at the origin over a ``2 hx × 2 hy`` top at ``z0``, with its ridge crest
    and finials; the hall's roof and the sreekovil's second roof are the same form."""
    if hx < 2.0 or hy < 2.0:
        notes.append(f"{what} too small for a sloping roof; skipped")
        return []
    fascia = max(1.0, p.min_feature)
    roof = hipped_roof(hx, hy, z0, eave, fascia, p.roof_pitch, p.printable_overhangs)
    z_top = float(roof.vertices[:, 2].max())
    parts = [roof]
    ridge = max(hx, hy) - min(hx, hy)
    if ridge > 1.0:  # ridge crest along the long axis
        lo, hi = (-ridge - 0.6, -0.6, z_top - OVERLAP), (ridge + 0.6, 0.6, z_top + 0.6)
        crest = box_between(lo, hi, name="ridge")
        parts.append(crest if hx >= hy else crest.rotated_z(90.0))
        ends = [(ridge, 0.0), (-ridge, 0.0)] if hx >= hy else [(0.0, ridge), (0.0, -ridge)]
    else:
        ends = [(0.0, 0.0)]
    if p.finial:
        for fx, fy in ends:
            parts += stupi(fx, fy, z_top + (0.3 if ridge > 1.0 else -0.3), 0.04 * min(hx, hy), 0.6 * p.parapet_height, p)
    return parts


def kerala_cell_roof(p: MandapaParams, L: Layout, cell: Cell, notes: list[str]) -> list[Solid]:
    """The sreekovil's own roof: an upper wall rising through the hall roof's ridge and a second
    hipped roof over it with half the eaves — the two-tiered silhouette of a Kerala shrine.

    The upper wall starts at the ridge rather than where the slope passes over the cell, so
    the second roof's eaves always clear the first: a cell near the ridge would otherwise
    bury them in the slope and show only a stub of its apex.
    """
    xo0, xo1, yo0, yo1 = cell.outer
    hx, hy = (xo1 - xo0) / 2.0, (yo1 - yo0) / 2.0
    eave, fascia = p.eave_overhang, max(1.0, p.min_feature)
    tan = math.tan(math.radians(p.roof_pitch))
    z_drip = L.roof_z - OVERLAP + (eave if p.printable_overhangs else 0.0) + fascia
    z_ridge = z_drip + (eave + min(L.slab_hx, L.slab_hy) - 0.2) * tan
    z_b = z_ridge + max(0.12 * p.pillar_height, 2.0)
    parts = [box_between((-hx, -hy, L.roof_z - OVERLAP), (hx, hy, z_b + OVERLAP), name="upper")]
    parts += hipped(p, hx, hy, z_b, 0.5 * eave, notes, "vimana")
    return placed(parts, cell.cx, cell.cy, 0.0)


# ---- the sanctum ----------------------------------------------------------------------


def sanctum(p: MandapaParams, L: Layout, notes: list[str]) -> list[Solid]:
    """Garbhagriha: walls on the pillar lines, the dvara in the front wall, a raised floor with
    its udumbara (threshold), the door surround, and a devakoshtha on every blind bay.

    Walls run from the floor into the beams, so the pillars on their lines are swallowed whole
    and only their capitals and corbels show, which is what a Dravidian wall pilaster is; the
    doorway is the gap between two jambs under a lintel block, since nothing here is cut.  The
    floor and the threshold are one level, a step above the hall, so the image stands higher
    than the floor it is seen from, as it does in every sanctum.
    """
    cell = L.cell
    if cell is None:
        return []
    xo0, xo1, yo0, yo1 = cell.outer
    h = cell.t / 2.0
    z0, z1 = L.floor_z - OVERLAP, cell.z_top + OVERLAP
    cx, dw = cell.cx, cell.door_w
    parts = [
        box_between((xo0, cell.y1 - h, z0), (xo1, yo1, z1), name="wall"),
        box_between((xo0, yo0, z0), (cell.x0 + h, yo1, z1), name="wall"),
        box_between((cell.x1 - h, yo0, z0), (xo1, yo1, z1), name="wall"),
        box_between((xo0, yo0, z0), (cx - dw / 2, cell.y0 + h, z1), name="jamb"),
        box_between((cx + dw / 2, yo0, z0), (xo1, cell.y0 + h, z1), name="jamb"),
        box_between(
            (cx - dw / 2 - OVERLAP, yo0, cell.z_floor + cell.door_h),
            (cx + dw / 2 + OVERLAP, cell.y0 + h, z1),
            name="lintel",
        ),
    ]
    if cell.z_floor > L.floor_z + 0.1:
        parts.append(box_between(
            (cell.x0 + h - OVERLAP, cell.y0 + h - OVERLAP, z0),
            (cell.x1 - h + OVERLAP, cell.y1 - h + OVERLAP, cell.z_floor),
            name="floor",
        ))
        parts.append(box_between(
            (cx - dw / 2 - OVERLAP, yo0, z0),
            (cx + dw / 2 + OVERLAP, cell.y0 + h + OVERLAP, cell.z_floor),
            name="udumbara",
        ))
    # Relief is built on the +X face of the cell's own rectangle and turned to its wall.
    # A raised band under 1.5 mm prints as surface texture (see mandapa.ornament).
    hx, hy = (xo1 - xo0) / 2.0, (yo1 - yo0) / 2.0
    proud = min(max(0.5, 0.8 * p.min_feature), 1.2)
    band = max(0.12 * dw, p.min_feature)
    beside = (cell.x1 - h) - (cx + dw / 2.0)  # wall left beside the opening for a jamb band
    if 0.3 <= band <= 0.8 * beside:
        parts += placed(wall_frame(hy, 0.0, cell.z_floor, dw, cell.door_h, band, proud, "dvara"), cx, cell.cy, 270.0)
    else:
        note_once(notes, "doorway too narrow for a dvara surround at this printer setting; skipped")
    if p.sanctum_niches:
        parts += niches(p, L, cell, hx, hy, proud, notes)
    return parts


def niches(
    p: MandapaParams, L: Layout, cell: Cell, hx: float, hy: float, proud: float, notes: list[str]
) -> list[Solid]:
    """A devakoshtha per blind bay: a framed panel between the pilasters, 0.4 of the bay wide,
    from a tenth of the wall's height to seven tenths — under the flare of the capitals.
    Bays the doorway crosses stay plain.

    Each face is the +X face of the cell turned by a quarter; a bay's offset along the face
    is mapped with the turn (the +Y face sees -X, the -X face sees -Y), though the cell is
    symmetric about its centre, so the pattern would read the same either way.
    """
    wall_h = cell.z_top - cell.z_floor
    z0, height = cell.z_floor + 0.1 * wall_h, 0.6 * wall_h
    xs, ys = L.pillar_xs, L.pillar_ys
    cx, cy = cell.cx, cell.cy
    x_bays = [((xs[i] + xs[i + 1]) / 2.0 - cx, xs[i + 1] - xs[i]) for i in range(cell.i0, cell.i1)]
    y_bays = [((ys[j] + ys[j + 1]) / 2.0 - cy, ys[j + 1] - ys[j]) for j in range(cell.j0, cell.j1)]
    front = [(c, w) for c, w in x_bays if abs(c) >= (w + cell.door_w) / 2.0]
    faces = [
        (hx, 0.0, y_bays),
        (hy, 90.0, [(-c, w) for c, w in x_bays]),
        (hx, 180.0, [(-c, w) for c, w in y_bays]),
        (hy, 270.0, front),
    ]
    parts: list[Solid] = []
    for dist, angle, bays in faces:
        for c, w in bays:
            nw = 0.4 * w
            band = max(0.08 * nw, p.min_feature)
            if nw < 3.0 * band or nw < 2.0 or nw + 2.0 * band > w - L.pillar_w - 1.0:
                note_once(notes, "wall bays too narrow for devakoshtha niches at this printer setting; skipped")
                continue
            parts += placed(wall_frame(dist, c, z0, nw, height, band, proud, "niche"), cx, cy, angle)
    return parts


def vimana(p: MandapaParams, L: Layout, notes: list[str]) -> list[Solid]:
    """The tower over the garbhagriha: the stepped roof's tiers and sikhara on the cell's own
    footprint, rising from the slab inside the hara or from a flat roof; under a Kerala roof,
    the sreekovil's second roof instead.  The stepped style is already the tower, so it gets
    nothing more.
    """
    cell = L.cell
    if cell is None or not p.vimana or p.roof_style == "stepped":
        return []
    if p.roof_style == "kerala":
        return kerala_cell_roof(p, L, cell, notes)
    xo0, xo1, yo0, yo1 = cell.outer
    parts = tower(p, (xo1 - xo0) / 2.0, (yo1 - yo0) / 2.0, L.roof_z - OVERLAP, notes, "vimana")
    return placed(parts, cell.cx, cell.cy, 0.0)


# ---- assembly -------------------------------------------------------------------------


def build(params: MandapaParams) -> Build:
    """Assemble every member into named groups: plinth, steps, pillars, beams, roof, crown,
    enclosure, sanctum.

    Groups are what the GUI's parts menu and the print-prep split read, so the
    first three names are a contract; the ornament joins the group of the member it
    sits on (galapadas are plinth, medallions are pillars) because that is the
    piece it ends up printed with.  The parameters are clamped first so a file from
    an older version, or a hand-edited one, builds a nearby legal hall instead of
    raising half-way through.
    """
    p = params.clamped()
    notes: list[str] = []
    L = compute_layout(p, notes)
    rng = random.Random(p.seed)

    pillar_parts: list[Solid] = []
    if p.shaft_style == "varied":
        # Real halls alternate pillar types by row (or by column), never at random per
        # pillar: the seed picks the pair and the direction, the grid does the rest.
        pool = [s for s in _SHAFT_SEGMENTS if s != "square"]
        pair = rng.sample(pool, 2)
        by_column = rng.random() < 0.5
    for i, j in L.pillar_points:
        style = pair[(i if by_column else j) % 2] if p.shaft_style == "varied" else p.shaft_style
        pillar_parts += pillar(p, L, L.pillar_xs[i], L.pillar_ys[j], style, notes)

    if p.roof_style == "hara":
        crown = hara(p, L, notes)
    elif p.roof_style == "stepped":
        crown = stepped_roof(p, L, notes)
    elif p.roof_style == "kerala":
        crown = kerala_roof(p, L, notes)
    else:
        crown = []

    parts = {
        "plinth": plinth(p, L, notes),
        "steps": steps(p, L),
        "pillars": pillar_parts,
        "beams": beams(p, L),
        "roof": [roof_block(p, L)] + frieze(p, L, notes) + kudus(p, L),
        "crown": crown,
    }
    # Only present when something was built: the GUI lists every group it is given
    # and the viewer only those with solids, so an empty group is a menu entry that
    # toggles nothing.
    enclosure = kakshasana(p, L, notes) + jali(p, L, notes) + centre_feature(p, L, notes)
    if enclosure:
        parts["enclosure"] = enclosure
    cell = sanctum(p, L, notes)
    if cell:
        parts["sanctum"] = cell
        parts["crown"] += vimana(p, L, notes)
    return Build(parts=parts, notes=notes, layout=L, params=p)


def scale_for_vigraham(
    params: MandapaParams, size: tuple[float, float, float], clearance: float = 1.0
) -> MandapaParams:
    """The same design with its export scale set so the garbhagriha holds a vigraham of
    ``size`` — width, depth, height in mm — with ``clearance`` beside and above it.

    Scale is the one knob that enlarges the building without touching a proportion, which
    is what sizing a temple to its image calls for; a design without a sanctum has nothing
    to fit and is refused.  The dvara is not considered: an image wider than the doorway
    goes in before the roof, which the split export allows.
    """
    cell = build(params.with_(scale=1.0)).layout.cell
    if cell is None:
        raise ValueError("the design has no garbhagriha to hold a vigraham: set sanctum to centre or back")
    w, d, h = cell.clear
    need = max((size[0] + 2 * clearance) / w, (size[1] + 2 * clearance) / d, (size[2] + clearance) / h)
    return params.with_(scale=math.ceil(need * 1000.0) / 1000.0)  # rounded up: the clearance holds
