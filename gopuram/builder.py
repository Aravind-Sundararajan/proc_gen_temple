"""Assembles the gopuram from the primitives in :mod:`mandapa.meshlib` and
:mod:`mandapa.ornament`, and from the mandapa's own miniature shrines.

Heights stack bottom-up: two flank plinths (adhishthana) either side of the passage →
the wall (pada): jambs, the lintel mass, pilasters and niches → the base prastara
that caps the whole oblong and bridges the passage → the talas, each a shrinking wall
with its own cornice carrying a hara of miniature shrines and the framed opening over
the passage → the crown: griva, the barrel-vaulted sala sikhara with a mahanasi on each
end, and the odd row of kalasas.

Why the passage is assembled, not cut
-------------------------------------
The mesh kit has no boolean subtraction, so the dvara is the gap the masonry leaves:
two jamb walls under a lintel, exactly as the garbhagriha's doorway is made — and as
the real ones are, course by course.  The lintel is what keeps the union one body, and
its soffit is the one bridge in the building, reported when it spans further than FDM
likes.  The adhishthana's mouldings wrap each flank and therefore run through the
passage, as they do in the built gateways; the price is a passage a little narrower
between the plinths than between the walls, and the build log states the clear figure.

Why the shrines are the mandapa's
---------------------------------
A gopuram's hara is the same kuta-sala-panjara row the mandapa's parapet carries, at
tala scale; :func:`mandapa.builder.kuta`, ``sala``, ``stupi`` and ``nasi_radius`` take
their dimensions as arguments and read only ``finial``, ``nasi``, ``printable_overhangs``
and the printer off the parameter record, all of which :class:`GopuramParams` states.
One spelling of a kuta, two buildings — the alternative was a second copy that drifts.
The shrines sink 0.3 mm into the wall of the storey they ring, because the built haras
lean on their talas and because a merely-touching contact is a coplanar face pair the
boolean engine must not be handed.

Where the proportions come from
-------------------------------
The oblong plan with the long axis along the enclosure wall, the one or two masonry
storeys under a brick superstructure, and the sala sikhara with an odd kalasa row are
the constants of the type from the Cholas to Madurai.  The plan tapers at ``tala_ratio``
per tala while the heights taper at the gentler ``(2 + ratio) / 3``, which is what
leans the profile inward; each tala keeps 0.74 of its height as wall, 0.16 as kapota
and the rest as slab.  The dvara keeps the texts' floor of twice as high as wide.

Printing
--------
The mandapa's two rules run through every function: no underside steeper than 45° when
``printable_overhangs`` is on (the kapota curves flatten, projections cap at 0.8 ×
height), and nothing thinner than ``min_feature`` — enlarged where that does not change
its reading, dropped with a note where it would.  A gopuram prints upright as built;
the passage soffit is the one span that may want supports, and the log says when.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from mandapa.builder import (
    KANTHA,
    KANTHA_D,
    Build,
    Profile,
    kudu_row,
    kuta,
    nasi_radius,
    note_once,
    plinth_profile,
    sala,
    stupi,
)
from mandapa.meshlib import Solid, box_between, extrude, rect_sweep
from mandapa.ornament import (
    OVERLAP,
    galapadas,
    nasi,
    padma_band,
    panjara,
    placed,
    spaced,
    wall_frame,
)

from .params import GopuramParams

__all__ = ["GopuramLayout", "Tala", "build", "compute_layout", "scale_for_passage"]

#: How far a hara shrine sinks into the storey wall behind it: enough that the union
#: has a volume to melt, never a coplanar kiss.
HARA_SINK = 0.3


@dataclass
class Tala:
    """One storey of the superstructure: its half-extents and its z-span (mm)."""

    hx: float
    hy: float
    z0: float
    z1: float


@dataclass
class GopuramLayout:
    """Derived dimensions shared by all parts (mm, world frame).

    ``floor_z`` and ``wall_top`` are the two horizontal lines other modules read:
    the plinth top, and the top of the base prastara's slab — the seam
    :mod:`gopuram.printprep` splits at.  ``door_w`` × ``door_h`` is the dvara between
    the walls; ``clear_w`` is what actually passes at full height, narrower because
    the plinth mouldings project into the passage.
    """

    plinth_h: float
    proj: float
    body_hx: float
    body_hy: float
    floor_z: float
    flank_hx: float  # half-width of each flank plinth (and jamb wall)
    flank_cx: float  # centre of the +X flank; the -X flank mirrors
    door_w: float
    door_h: float
    clear_w: float
    lintel_h: float
    wall_h: float
    storey_z: float | None  # the storey course line, or None for one storey
    ent_z0: float  # top of the plumb wall: where the base prastara begins
    frieze_h: float
    kapota_h: float
    kapota_p: float
    slab_h: float
    wall_top: float  # top of the base prastara slab: the print-prep seam
    talas: list[Tala] = field(default_factory=list)
    crown_z: float = 0.0
    crown_hl: float = 0.0  # vault half-length (along X) and half-width
    crown_hw: float = 0.0


# ---- layout ---------------------------------------------------------------------------


def compute_layout(p: GopuramParams, notes: list[str]) -> GopuramLayout:
    """Every shared dimension, derived once from the clamped parameters.

    The dvara is resolved here because three members read it: the height is capped so
    a lintel of at least 0.15 of the wall remains, the width is narrowed to keep the
    opening at least twice as high as it is wide (the texts' floor; real gopuram
    passages are taller still), and narrowed again if the flanks would drop below
    what a jamb can be.  The kapota projection is capped at 0.8 × height under the
    45° rule, the same line the mandapa draws, and the passage soffit is reported
    when it bridges more than 30 mm.
    """
    H = p.plinth_height
    fx, fy = p.base_width / 2.0, p.base_depth / 2.0
    proj = p.plinth_projection * H
    if proj > 0.35 * min(fx, fy):
        # A projection deeper than the flanks are wide would fold the kantha recess
        # through the body; the mandapa never meets this because its base is one piece.
        proj = 0.35 * min(fx, fy)
        notes.append(f"plinth projection limited to {proj:.1f} mm so the mouldings fit the flanks")
    body_hx, body_hy = fx - proj, fy - proj
    floor_z = H

    wall_h = p.wall_height
    lintel = max(0.15 * wall_h, 2.0 * p.min_feature, 1.5)
    door_h = min(p.dvara_height * wall_h, wall_h - lintel)
    door_w = p.dvara_width * p.base_width
    if door_h < 2.0 * door_w:
        door_w = door_h / 2.0
        notes.append(f"dvara narrowed to {door_w:.1f} mm so the opening stays twice as high as wide")
    # A jamb keeps its own mouldings: wider than the kantha recess is deep (0.3 x the
    # projection per flank half), and never under 3 mm or four printer features.
    min_flank = max(3.0, 4.0 * p.min_feature, 0.7 * proj + 1.0)
    if body_hx - door_w / 2.0 < min_flank:
        door_w = max(2.0 * (body_hx - min_flank), 1.0)
        notes.append(f"dvara narrowed to {door_w:.1f} mm to keep {min_flank:.1f} mm jambs beside it")
    if door_w > 30.0:
        notes.append(f"the passage soffit bridges {door_w:.0f} mm; print with supports or accept the sag")
    padma = p.plinth_padma and p.plinth_style != "plain"
    # The mouldings' reach is linear in the projection; a projection that would leave
    # less than a fifth of the dvara clear between the two flanks' kumudas is cut back,
    # because a gateway whose passage the base seals is not a gateway.
    reach = max(d for d, _ in plinth_profile(p.plinth_style, H, 1.0, padma))
    limit = (door_w - max(1.0, 0.2 * door_w)) / (2.0 * reach)
    if proj > limit:
        proj = max(limit, 0.0)
        body_hx, body_hy = fx - proj, fy - proj
        notes.append(f"plinth projection limited to {proj:.1f} mm so the passage stays open")

    flank_hx = (body_hx - door_w / 2.0) / 2.0
    flank_cx = door_w / 2.0 + flank_hx

    kh = p.kapota_height
    kp = p.kapota_projection
    if p.printable_overhangs and kp > 0.8 * kh:
        kp = 0.8 * kh
        notes.append(f"kapota projection limited to {kp:.1f} mm for the 45 deg rule")
    frieze_h = 0.6 * kh
    slab_h = max(1.5, 0.6 * kh)
    ent_z0 = floor_z + wall_h
    wall_top = ent_z0 + frieze_h + kh + slab_h - OVERLAP
    storey_z = floor_z + 0.55 * wall_h if p.wall_storeys == 2 else None
    # What actually passes: the dvara minus the deepest thing beside it — the plinth
    # mouldings, or the storey course, which runs through the passage as the built
    # gateways' interior cornices do.
    course = 0.7 * kp if storey_z is not None and kh >= 0.5 else 0.0
    clear_w = door_w - 2.0 * max(reach * proj, course)

    # The plan tapers at the stated ratio, the heights at (2 + r) / 3 — nearer one, so
    # the storeys stay legible while the silhouette leans in.
    r = p.tala_ratio
    rh = (2.0 + r) / 3.0
    talas: list[Tala] = []
    hx, hy, th = 0.92 * body_hx, 0.92 * body_hy, p.tala_height
    z = wall_top - OVERLAP
    for k in range(p.talas):
        # The first tala is built whatever its size — a gopuram with no superstructure
        # is a wall — and the taper stops with a note when a later one gets too thin.
        if k > 0 and (hx < 3.0 or hy < 3.0 or th < 1.5):
            notes.append(f"only {k} of {p.talas} talas fit the taper; the rest would be thinner than a wall")
            break
        talas.append(Tala(hx, hy, z, z + th))
        z = z + th - OVERLAP
        hx, hy, th = hx * r, hy * r, th * rh

    top = talas[-1]
    # The vault is long before it is wide — about 4 : 1 on the default massing — which
    # is what separates a gopuram's crest from a sala shrine grown large.
    crown_hl, crown_hw = 0.88 * top.hx, max(0.45 * top.hy, 1.2)
    return GopuramLayout(
        plinth_h=H, proj=proj, body_hx=body_hx, body_hy=body_hy, floor_z=floor_z,
        flank_hx=flank_hx, flank_cx=flank_cx,
        door_w=door_w, door_h=door_h, clear_w=clear_w, lintel_h=lintel,
        wall_h=wall_h, storey_z=storey_z, ent_z0=ent_z0,
        frieze_h=frieze_h, kapota_h=kh, kapota_p=kp, slab_h=slab_h, wall_top=wall_top,
        talas=talas, crown_z=top.z1, crown_hl=crown_hl, crown_hw=crown_hw,
    )


# ---- shared courses -------------------------------------------------------------------


def cornice(p: GopuramParams, hx: float, hy: float, z0: float, kh: float, kp: float,
            slab_h: float, name: str = "kapota") -> Solid:
    """A flexed kapota with its slab, swept around a rectangle: the base prastara's top,
    the storey course, and every tala's eave are this one course at three sizes.

    The underside is the mandapa's quadratic curve; under the 45° rule it runs straight
    (scoop 0), otherwise it sags the way the cut stone does.  Degenerates to a plain
    riser when the course is too small to flex.
    """
    prof: Profile = [(0.0, z0)]
    if kp > 0.05 and kh > 0.05:
        scoop = 0.0 if p.printable_overhangs else 0.5
        p0, p2 = (0.0, z0), (kp, z0 + 0.8 * kh)
        ctrl = ((1 - scoop) * kp / 2 + scoop * kp, (1 - scoop) * (z0 + 0.4 * kh) + scoop * z0)
        for i in range(1, 7):
            t = i / 6.0
            d = (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * ctrl[0] + t * t * p2[0]
            z = (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * ctrl[1] + t * t * p2[1]
            prof.append((d, z))
        prof.append((kp, z0 + 0.88 * kh))  # drip lip
        for t in np.linspace(0, math.pi / 2, 5)[1:]:  # roll over the top
            prof.append((0.35 * kp + 0.65 * kp * math.cos(t), z0 + 0.88 * kh + 0.12 * kh * math.sin(t)))
        prof.append((0.35 * kp, z0 + kh + slab_h))
    else:
        prof.append((0.0, z0 + kh + slab_h))
    return rect_sweep(prof, hx, hy, name=name)


def frame_on_y_faces(dist: float, cx: float, z0: float, width: float, height: float,
                     band: float, proud: float, name: str) -> list[Solid]:
    """A :func:`~mandapa.ornament.wall_frame` on both ±Y faces at ``x = cx``.

    The frame is built on a +X face and turned a quarter, so the +Y copy lands at
    ``-cx`` before the turn — the same mapping the sanctum's niches use.
    """
    parts = placed(wall_frame(dist, -cx, z0, width, height, band, proud, name), 0.0, 0.0, 90.0)
    parts += placed(wall_frame(dist, cx, z0, width, height, band, proud, name), 0.0, 0.0, 270.0)
    return parts


def proud_of(p: GopuramParams) -> float:
    """How far relief stands off a wall: under 1.5 mm it prints as surface texture
    (see :mod:`mandapa.ornament`), and never under the printer's feature size."""
    return min(max(0.5, 0.8 * p.min_feature), 1.2)


# ---- the base -------------------------------------------------------------------------


def plinth(p: GopuramParams, L: GopuramLayout, notes: list[str]) -> list[Solid]:
    """Two flank adhishthanas, one either side of the passage, with their ornament.

    Each flank is a complete moulded base — the mouldings wrap its passage face too,
    which is what a visitor walking through actually sees.  Ornament rules are the
    mandapa's: galapadas need a real recess, the padma band a real upana.
    """
    H, pr = L.plinth_h, L.proj
    u = H / 24.0
    padma = p.plinth_padma and p.plinth_style != "plain"
    flank = [rect_sweep(plinth_profile(p.plinth_style, H, pr, padma), L.flank_hx, L.body_hy, name="plinth")]
    if p.plinth_style != "plain":
        if p.plinth_galapadas:
            kz0, kz1 = KANTHA[0] * u, KANTHA[1] * u
            width = max(0.6 * (kz1 - kz0), p.min_feature)
            if pr < 0.7 or width > 1.5 * (kz1 - kz0):
                notes.append("kantha too shallow or too low for galapadas; skipped")
            else:
                flank += galapadas(
                    L.flank_hx, L.body_hy, kz0 - OVERLAP, kz1 + OVERLAP, KANTHA_D * pr, 0.15 * pr, width, 0.6 * H
                )
        if padma:
            band_h = 2.0 * u
            width = max(2.2 * u, 2 * p.min_feature)
            if pr < 0.85 or band_h < 0.5:
                notes.append("upana too small for a padma band; skipped")
            else:
                flank += padma_band(L.flank_hx, L.body_hy, 0.0, band_h, 0.6 * pr, 0.3 * pr, width)
    return placed(flank, L.flank_cx, 0.0, 0.0) + placed(flank, -L.flank_cx, 0.0, 0.0)


def walls(p: GopuramParams, L: GopuramLayout) -> list[Solid]:
    """The pada masonry: a jamb wall on each flank, the lintel mass over the dvara,
    and the storey course when there are two storeys."""
    z0, z1 = L.floor_z - OVERLAP, L.ent_z0 + OVERLAP
    w = L.door_w / 2.0
    parts = [
        box_between((w, -L.body_hy, z0), (L.body_hx, L.body_hy, z1), name="wall"),
        box_between((-L.body_hx, -L.body_hy, z0), (-w, L.body_hy, z1), name="wall"),
        box_between((-w - OVERLAP, -L.body_hy, L.floor_z + L.door_h), (w + OVERLAP, L.body_hy, z1), name="lintel"),
    ]
    if L.storey_z is not None and L.kapota_h >= 0.5:
        kh, kp = 0.7 * L.kapota_h, 0.7 * L.kapota_p
        for s in (1, -1):
            course = cornice(p, L.flank_hx, L.body_hy, L.storey_z - kh / 2.0, kh, kp, 0.3 * L.kapota_h)
            parts.append(course.translated(s * L.flank_cx, 0.0, 0.0))
    return parts


def prastara(p: GopuramParams, L: GopuramLayout) -> list[Solid]:
    """The base prastara: a frieze band and the kapota-and-slab course around the whole
    oblong.  It rides over the lintel, so it is the first member since the ground to run
    unbroken round the building — and what makes the union one body over the passage.
    Kudus go on its kapota face."""
    parts = [
        rect_sweep([(0.0, L.ent_z0 - OVERLAP), (0.0, L.ent_z0 + L.frieze_h)],
                   L.body_hx, L.body_hy, name="frieze"),
        cornice(p, L.body_hx, L.body_hy, L.ent_z0 + L.frieze_h - OVERLAP,
                L.kapota_h, L.kapota_p, L.slab_h),
    ]
    parts += kudu_row(p, L.body_hx, L.body_hy, L.kapota_p, L.kapota_h, L.ent_z0 + L.frieze_h - OVERLAP)
    return parts


def pilasters(p: GopuramParams, L: GopuramLayout, notes: list[str]) -> list[Solid]:
    """Flat wall pilasters: along both long faces of each flank, and on the two end
    faces of the base.  None face the passage — the dvara surround frames that."""
    if not p.pilasters:
        return []
    wp = max(1.2 * p.min_feature, 0.035 * p.base_width)
    proud = proud_of(p)
    if wp > 0.5 * L.flank_hx:
        note_once(notes, "flanks too narrow for pilasters at this printer setting; skipped")
        return []
    z0, z1 = L.floor_z - OVERLAP, L.ent_z0 + OVERLAP
    pitch = max(2.5 * wp, 0.11 * p.base_width)
    parts: list[Solid] = []
    for s in (1, -1):  # which flank
        for c in spaced(L.flank_hx - 0.75 * wp, pitch):
            x = s * L.flank_cx + c
            parts.append(box_between((x - wp / 2, L.body_hy - OVERLAP, z0), (x + wp / 2, L.body_hy + proud, z1), name="pilaster"))
            parts.append(box_between((x - wp / 2, -L.body_hy - proud, z0), (x + wp / 2, -L.body_hy + OVERLAP, z1), name="pilaster"))
    for c in spaced(L.body_hy - 0.75 * wp, pitch):  # the end faces
        parts.append(box_between((L.body_hx - OVERLAP, c - wp / 2, z0), (L.body_hx + proud, c + wp / 2, z1), name="pilaster"))
        parts.append(box_between((-L.body_hx - proud, c - wp / 2, z0), (-L.body_hx + OVERLAP, c + wp / 2, z1), name="pilaster"))
    return parts


def base_relief(p: GopuramParams, L: GopuramLayout, notes: list[str]) -> list[Solid]:
    """The dvara surround on both faces, a devakoshtha on each flank's lower storey,
    and the niche over the lintel that starts the vertical line of openings."""
    proud = proud_of(p)
    parts: list[Solid] = []
    band = max(0.1 * L.door_w, p.min_feature)
    if 0.3 <= band <= 0.8 * (2.0 * L.flank_hx - 1.0):
        parts += frame_on_y_faces(L.body_hy, 0.0, L.floor_z, L.door_w, L.door_h, band, proud, "dvara")
    else:
        note_once(notes, "jambs too narrow for a dvara surround at this printer setting; skipped")
    if not p.niches:
        return parts
    nh = 0.42 * L.wall_h
    nw = min(0.55 * nh, 1.1 * L.flank_hx)
    nband = max(0.08 * nw, p.min_feature)
    if nw < 3.0 * nband or nw < 2.0 or nw + 2.0 * nband > 2.0 * L.flank_hx - 1.0:
        note_once(notes, "flanks too narrow for devakoshtha niches at this printer setting; skipped")
    else:
        z0 = L.floor_z + 0.08 * L.wall_h
        for s in (1, -1):
            parts += frame_on_y_faces(L.body_hy, s * L.flank_cx, z0, nw, nh, nband, proud, "niche")
    head = L.wall_h - L.door_h  # the lintel zone the over-door niche lives in
    oh, ow = 0.55 * head, min(0.7 * 0.55 * head, 0.8 * L.door_w)
    oband = max(0.08 * ow, p.min_feature)
    if oh >= 2.5 and ow >= 3.0 * oband:
        parts += frame_on_y_faces(L.body_hy, 0.0, L.floor_z + L.door_h + 0.18 * head, ow, oh, oband, proud, "niche")
    return parts


# ---- the superstructure ---------------------------------------------------------------


def tala_block(p: GopuramParams, t: Tala) -> list[Solid]:
    """One tala: a plumb wall keeping 0.74 of the height under its own kapota course
    (0.16 kapota, the rest slab), the base prastara's proportions at storey scale."""
    th = t.z1 - t.z0
    kh = 0.16 * th
    kp = 0.8 * kh if p.printable_overhangs else kh
    wall_z1 = t.z0 + 0.74 * th
    return [
        rect_sweep([(0.0, t.z0), (0.0, wall_z1)], t.hx, t.hy, name="tala"),
        cornice(p, t.hx, t.hy, wall_z1 - OVERLAP, kh, kp, t.z1 - wall_z1 - kh),
    ]


def tala_hara(p: GopuramParams, L: GopuramLayout, k: int, notes: list[str]) -> list[Solid]:
    """The parapet of miniature shrines on tala ``k``'s terrace, ringing what stands
    above it (the next tala, or the crown's griva).

    Corner kutas; ``salas_per_tala`` salas mirrored about the centre of each long face,
    so the central bay stays open for the tala's own opening; one sala across each end.
    Each shrine sinks :data:`HARA_SINK` into the wall it rings and never overhangs the
    terrace edge — a tala too steep in taper to seat a shrine skips the row with a note.
    """
    t = L.talas[k]
    if k + 1 < len(L.talas):
        inner_hx, inner_hy = L.talas[k + 1].hx, L.talas[k + 1].hy
    else:
        inner_hx, inner_hy = 0.92 * L.crown_hl, 0.85 * L.crown_hw
    th = t.z1 - t.z0
    ph = 0.38 * th
    kw = min(1.0 * ph, 0.45 * inner_hx, 0.45 * inner_hy,
             t.hx - inner_hx + HARA_SINK, t.hy - inner_hy + HARA_SINK)
    if kw < max(1.2, 2.0 * p.min_feature):
        note_once(notes, "the terraces are too narrow for hara shrines; skipped")
        return []
    z0 = t.z1 - OVERLAP
    qx, qy = inner_hx + kw / 2.0 - HARA_SINK, inner_hy + kw / 2.0 - HARA_SINK
    parts: list[Solid] = []
    for sx in (-1, 1):
        for sy in (-1, 1):
            parts += kuta(sx * qx, sy * qy, z0, kw, ph, p, notes)

    n = p.salas_per_tala
    length = min(2.2 * kw, 0.5 * qx)
    if n > 0 and length > 0.8 * kw:
        for j in range(1, n + 1):
            c = (qx - kw) * j / (n + 1)
            if c - length / 2.0 < 0.35 * kw:  # keep the central bay open for the opening
                continue
            for sx in (1, -1):
                for sy in (1, -1):
                    parts += sala(sx * c, sy * qy, z0, length, kw, ph, "x", p, notes)
        end_len = min(2.2 * kw, 0.9 * qy)
        if end_len > 0.8 * kw:
            for sx in (1, -1):  # one sala across each end face
                parts += sala(sx * qx, 0.0, z0, end_len, kw, ph, "y", p, notes)
    if p.panjaras:
        pj_w = 0.7 * kw
        first = 0.35 * kw + (length if n > 0 else 0.0)  # inner edge of the free stretch
        c = (first + qx - kw) / 2.0
        if qx - kw - first >= pj_w + 0.3 * kw:
            r_n = nasi_radius(kw, p, notes)
            for sx in (1, -1):
                for sy in (1, -1):
                    angle = 90.0 if sy > 0 else 270.0
                    parts += placed(panjara(kw, pj_w, z0, 0.5 * ph, 0.32 * ph, r_n), sx * c, sy * qy, angle)
                    if p.finial:
                        parts += stupi(sx * c, sy * qy, z0 + 0.5 * ph + 0.9 * 0.32 * ph, 0.1 * kw, 0.12 * ph, p)
        else:
            note_once(notes, "no room for panjaras between the hara shrines; skipped")
    return parts


def tala_opening(p: GopuramParams, t: Tala, notes: list[str]) -> list[Solid]:
    """The framed opening over the passage on one tala, front and back."""
    th = t.z1 - t.z0
    w, h = 0.45 * th, 0.62 * th
    band = max(0.12 * w, p.min_feature)
    if w < 3.0 * band or w < 1.5 or w + 2.0 * band > 1.6 * t.hx:
        note_once(notes, "talas too small for their openings at this printer setting; skipped")
        return []
    return frame_on_y_faces(t.hy, 0.0, t.z0 + 0.06 * th, w, h, band, proud_of(p), "taladvara")


def talas(p: GopuramParams, L: GopuramLayout, notes: list[str]) -> list[Solid]:
    parts: list[Solid] = []
    for k, t in enumerate(L.talas):
        parts += tala_block(p, t)
        if p.hara:
            parts += tala_hara(p, L, k, notes)
        if p.tala_openings:
            parts += tala_opening(p, t, notes)
    return parts


# ---- the crown ------------------------------------------------------------------------


def crown(p: GopuramParams, L: GopuramLayout, notes: list[str]) -> list[Solid]:
    """Griva, the sala-sikhara vault along the long axis, the mahanasi on each end, and
    the kalasa row — always odd, as on every built gopuram, so an even count is lowered
    by one with a note, and thinned to what the ridge can seat."""
    hl, hw = L.crown_hl, L.crown_hw
    if hl < 2.0 or hw < 1.2:
        notes.append("top tala too small for the crown; skipped")
        return []
    gh, vh = 0.35 * p.crown_height, 0.65 * p.crown_height
    z0 = L.crown_z - OVERLAP
    parts = [rect_sweep([(0.0, z0), (0.0, z0 + gh)], 0.92 * hl, 0.85 * hw, name="griva")]

    zb = z0 + gh - OVERLAP
    poly = [(-hw, zb), (hw, zb), (hw, zb + 0.25 * vh)]
    for t in np.linspace(0, math.pi, 11)[1:-1]:
        poly.append((hw * math.cos(t), zb + 0.25 * vh + 0.75 * vh * math.sin(t)))
    poly.append((-hw, zb + 0.25 * vh))
    parts.append(extrude(poly, "yz", -hl, hl, name="sikhara"))
    ridge_z = zb + vh

    n = p.kalasas
    if n % 2 == 0:
        n -= 1
        notes.append(f"a kalasa row is odd on every built gopuram; {n} used")
    margin = min(0.24 * hl, 1.5 * hw)
    while n > 1 and 2.0 * (hl - margin) / (n - 1) < 0.45 * hw:
        n -= 2  # pots closer than half their width read as a blob, not a row
    if n < p.kalasas - (1 - p.kalasas % 2):
        notes.append(f"kalasa row thinned to the {n} the ridge can seat")
    xs = [float(v) for v in np.linspace(-(hl - margin), hl - margin, n)] if n > 1 else [0.0]
    for x in xs:
        parts += stupi(x, 0.0, ridge_z - 0.05 * vh, 0.16 * hw, max(0.45 * p.crown_height, 1.0), p)

    if p.mahanasi:
        r = 0.55 * hw
        if r < max(0.6, 1.5 * p.min_feature):
            note_once(notes, "vault too small for mahanasi arches at this printer setting; skipped")
        else:
            zn = zb + 0.1 * vh
            for s in (1, -1):
                parts.append(nasi(0.0, r, zn, "yz", 0.0, s * (hl + 0.25 * r)))
    return parts


# ---- assembly -------------------------------------------------------------------------


def build(params: GopuramParams) -> Build:
    """Assemble every member into named groups: plinth, base, talas, crown.

    The groups are what the GUI's parts menu and :mod:`gopuram.printprep` read: the
    split's seam runs between ``base`` (everything to the top of the base prastara)
    and ``talas``.  Parameters are clamped first, as the mandapa's builder clamps, so
    a hand-edited file builds a nearby legal gateway instead of raising half-way.  The
    result is the mandapa's :class:`~mandapa.builder.Build` — the union, the reports
    and the viewer read only what both parameter families provide.
    """
    p = params.clamped()
    notes: list[str] = []
    L = compute_layout(p, notes)
    notes.append(
        f"dvara {L.door_w:.1f} x {L.door_h:.1f} mm; the mouldings narrow the passage to "
        f"{L.clear_w:.1f} mm, so a {L.clear_w:.1f} x {L.door_h:.1f} mm object passes "
        f"({p.base_depth:.0f} mm deep)"
    )
    parts = {
        "plinth": plinth(p, L, notes),
        "base": walls(p, L) + prastara(p, L) + pilasters(p, L, notes) + base_relief(p, L, notes),
        "talas": talas(p, L, notes),
    }
    top = crown(p, L, notes)
    if top:
        parts["crown"] = top
    return Build(parts=parts, notes=notes, layout=L, params=p)


def scale_for_passage(
    params: GopuramParams, size: tuple[float, float], clearance: float = 1.0
) -> GopuramParams:
    """The same design with its export scale set so the dvara passes an object of
    ``size`` — width, height in mm — with ``clearance`` beside and above it.

    The gopuram's counterpart of the mandapa's ``--vigraham``: a gateway is sized by
    what processes through it.  The governing width is the clear width between the
    plinth mouldings, not the dvara between the walls, because a full-height object
    meets the mouldings first.
    """
    L = build(params.with_(scale=1.0)).layout
    need = max((size[0] + 2.0 * clearance) / L.clear_w, (size[1] + clearance) / L.door_h)
    return params.with_(scale=math.ceil(need * 1000.0) / 1000.0)  # rounded up: the clearance holds
