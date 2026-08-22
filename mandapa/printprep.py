"""Turn a build into print-ready part meshes: splitting, alignment pegs, hollowing, bed fit.

Interface contract shared by the GUI export dialog and the CLI: keep :class:`PrintOptions`,
:class:`PartMesh` and :func:`prepare_parts` stable; extend them with new fields rather
than renaming.  The GUI builds its dialog from ``dataclasses.fields(PrintOptions)``, so
every field keeps a simple type, a default and ``label``/``help`` metadata.

Why split at all
----------------
A mandapa is a plinth carrying a forest of thin pillars under a wide roof.  Printed in
one piece on FDM the ceiling bridges every bay and the cornice hangs in the air; printed
as base, colonnade and roof each piece stands on a flat cut face and the roof can even
go upside down.  The cuts are the two horizontal seams that exist in the architecture
anyway (plinth top, beam underside), so nothing is cut through a moulding.

The cut is a boolean intersection with a half-space box, which keeps every part a closed
manifold.  Two details fall out of how manifold3d behaves and are pinned by tests:

* **A cut plane never coincides with a model face.**  The plinth top lies exactly on the
  floor seam and the beam undersides exactly on the beam seam; a plane through them
  leaves zero-thickness sheets in the result (watertight, zero volume, but they weld the
  sixteen pillars into one "body" and survive as degenerate triangles).  Each cut
  therefore discards a slice :data:`CUT_GAP` thick centred on the seam: the assembled
  model is 0.02 mm shorter than the one-piece export, a tenth of a layer.
* **Ornament straddling a seam is re-glued.**  The balustrades rise above the plinth top,
  so the floor cut would leave two floating chips in the colonnade.  Any component of the
  middle slab that touches only one seam is unioned back onto that neighbour (shifted by
  one gap so it overlaps instead of merely touching).

Tolerance contract for the pegs (absolute millimetres; they do not scale with the model):
pegs are :data:`PEG_HEIGHT` tall 32-gons of circumradius ``r = 0.3 x pillar width``; the
matching sockets are 32-gons whose *apothem* is ``r + PEG_CLEARANCE`` and whose depth is
``PEG_HEIGHT + HOLE_EXTRA_DEPTH``.  Circumradius against apothem means the peg is
inscribed in its nominal circle and the socket circumscribes its nominal circle, so the
clearance is at least 0.2 mm in every direction.  ``r`` shrinks when the member holding
the socket would otherwise keep less than ``max(min_feature, MIN_WALL)`` of wall, and
pegs are dropped with a note rather than printed too thin.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import trimesh

from .builder import Build
from .export import PartMesh, body_count, face_bodies, make_mesh, to_trimesh
from .meshlib import Solid, box_between, cylinder, merge, prism

__all__ = [
    "CUT_GAP",
    "DRAIN_DIAMETER",
    "HOLE_EXTRA_DEPTH",
    "MIN_WALL",
    "PART_COLOURS",
    "PEG_CLEARANCE",
    "PEG_HEIGHT",
    "PEG_SINK",
    "PartMesh",
    "Pegs",
    "PrintOptions",
    "peg_plan",
    "prepare_parts",
]

#: Total thickness discarded at each cut (half above and half below the seam).
CUT_GAP = 0.01
#: Peg height above the cut face; the socket is this plus :data:`HOLE_EXTRA_DEPTH` deep.
PEG_HEIGHT = 3.0
#: Socket apothem minus peg circumradius: the guaranteed minimum radial clearance.
PEG_CLEARANCE = 0.2
HOLE_EXTRA_DEPTH = 0.3
#: How far a peg sinks into its part (and a socket cutter reaches past the face) so the
#: boolean never has to resolve a coplanar contact.
PEG_SINK = 0.5
#: Peg circumradius as a fraction of the pillar width (diameter 0.6 x width).
PEG_RADIUS_FACTOR = 0.3
#: Pegs thinner than this are dropped with a note: nothing that small locates anything.
MIN_PEG_RADIUS = 0.5
#: Wall kept around a socket, at least this or the printer's minimum feature.
MIN_WALL = 0.6
PEG_SIDES = 32
#: Resin drain holes through the hollowed plinth's underside.
DRAIN_DIAMETER = 3.0
#: Shortest socket worth cutting when the roof is too thin for a full-depth one.
MIN_PEG_HEIGHT = 1.0
#: Smallest cavity half-extent that leaves room for both drain holes.
MIN_CAVITY_HALF = 4.0

#: sRGB tints for the split parts so a 3MF shows them apart in the slicer.
PART_COLOURS: dict[str, tuple[float, float, float]] = {
    "base": (0.61, 0.55, 0.49),
    "colonnade": (0.79, 0.72, 0.61),
    "roof": (0.72, 0.66, 0.56),
}


@dataclass
class PrintOptions:
    split: bool = field(
        default=False,
        metadata={
            "label": "Split into parts",
            "help": "Cut into base, colonnade and roof at the plinth top and the beam "
            "underside, with 3 mm alignment pegs (0.6 x pillar width) and sockets "
            "0.2 mm larger in radius.",
        },
    )
    hollow_wall_mm: float = field(
        default=0.0,
        metadata={
            "label": "Hollow plinth wall (mm)",
            "help": "Above 0, shells the plinth to this wall thickness with two 3 mm drain "
            "holes in the underside (saves resin). 0 keeps it solid.",
        },
    )
    bed_mm: tuple[float, float, float] | None = field(
        default=None,
        metadata={
            "label": "Printer bed X, Y, Z (mm)",
            "help": "Build volume every part is checked against (rotating 90 degrees "
            "counts as fitting). Empty: no check.",
        },
    )
    fit_to_bed: bool = field(
        default=False,
        metadata={
            "label": "Scale to fit bed",
            "help": "Scale every part by the one largest factor that fits the bed. Pegs and "
            "clearances scale with it, so prefer a smaller export scale below about 0.7.",
        },
    )
    flip_roof: bool = field(
        default=False,
        metadata={
            "label": "Flip roof part",
            "help": "Print the roof part upside down on its flat top, sockets up. Flat roof "
            "style only, and only when split.",
        },
    )


# ---- pegs -----------------------------------------------------------------------------


def _polygon_area_circumradius(r: float, n: int = PEG_SIDES) -> float:
    return 0.5 * n * r * r * math.sin(2 * math.pi / n)


def _polygon_area_apothem(a: float, n: int = PEG_SIDES) -> float:
    return n * a * a * math.tan(math.pi / n)


@dataclass(frozen=True)
class Pegs:
    """Alignment pegs across one cut, in the exported (scaled) millimetres.

    ``seam_z`` is the nominal seam; the lower part's face is ``seam_z - CUT_GAP / 2`` and
    carries the pegs, the upper part's face is ``seam_z + CUT_GAP / 2`` and takes the
    sockets.  ``points`` are the peg centres.
    """

    seam_z: float
    points: tuple[tuple[float, float], ...]
    radius: float
    height: float = PEG_HEIGHT

    @property
    def hole_radius(self) -> float:
        """Apothem of the socket polygon."""
        return self.radius + PEG_CLEARANCE

    @property
    def hole_depth(self) -> float:
        return self.height + HOLE_EXTRA_DEPTH

    @property
    def lower_face_z(self) -> float:
        return self.seam_z - CUT_GAP / 2

    @property
    def upper_face_z(self) -> float:
        return self.seam_z + CUT_GAP / 2

    def peg_solid(self) -> Solid:
        """All pegs as one multi-shell solid (they never touch, so it is a valid manifold)."""
        z0, z1 = self.lower_face_z - PEG_SINK, self.lower_face_z + self.height
        return merge(
            [cylinder(self.radius, z0, z1, PEG_SIDES).translated(x, y, 0.0) for x, y in self.points],
            name="pegs",
        )

    def hole_solid(self) -> Solid:
        z0, z1 = self.upper_face_z - PEG_SINK, self.upper_face_z + self.hole_depth
        return merge(
            [
                prism(self.hole_radius, PEG_SIDES, z0, z1, phase=0.0).translated(x, y, 0.0)
                for x, y in self.points
            ],
            name="sockets",
        )

    def peg_volume(self) -> float:
        """Volume the pegs add: only the part standing proud of the face."""
        return len(self.points) * _polygon_area_circumradius(self.radius) * self.height

    def hole_volume(self) -> float:
        """Volume the sockets remove."""
        return len(self.points) * _polygon_area_apothem(self.hole_radius) * self.hole_depth


def peg_plan(result: Build) -> tuple[Pegs | None, Pegs | None, list[str]]:
    """Pegs for the floor cut (under every pillar) and the beam cut (on the four corner
    corbels, i.e. inset one corbel reach from the entablature corners), or ``None`` with a
    note when a member is too thin to take a socket and keep its wall.
    """
    L, p = result.layout, result.params
    s = p.scale
    wall = max(p.min_feature, MIN_WALL)
    notes: list[str] = []
    pillar_w = L.pillar_w * s

    # Floor cut: the socket sits in the pillar foot, a square of apothem pillar_w / 2.
    radius = min(PEG_RADIUS_FACTOR * pillar_w, 0.5 * pillar_w - wall - PEG_CLEARANCE)
    floor = None
    if radius >= MIN_PEG_RADIUS:
        points = tuple((x * s, y * s) for x in L.pillar_xs for y in L.pillar_ys)
        floor = Pegs(L.floor_z * s, points, radius)
    else:
        notes.append(
            f"no pegs under the pillars: a {pillar_w:.1f} mm pillar cannot take a socket "
            f"and keep a {wall:.1f} mm wall"
        )

    # Beam cut: the socket sits in the perimeter beam (half width beam_w / 2) and must
    # not break through the roof above it.
    seam = L.corbel_top * s
    radius = min(PEG_RADIUS_FACTOR * pillar_w, 0.5 * L.beam_w * s - wall - PEG_CLEARANCE)
    height = min(PEG_HEIGHT, (L.roof_z * s - seam) - wall - HOLE_EXTRA_DEPTH)
    beam = None
    if radius < MIN_PEG_RADIUS:
        notes.append(
            f"no pegs under the roof: a {L.beam_w * s:.1f} mm beam cannot take a socket "
            f"and keep a {wall:.1f} mm wall"
        )
    elif height < MIN_PEG_HEIGHT:
        notes.append("no pegs under the roof: the roof is too thin for a socket")
    else:
        corners = tuple(
            (sx * L.pillar_xs[-1] * s, sy * L.pillar_ys[-1] * s) for sx in (-1, 1) for sy in (-1, 1)
        )
        beam = Pegs(seam, corners, radius, height)
    return floor, beam, notes


# ---- boolean helpers ------------------------------------------------------------------


def _boolean(op: str, meshes: list[trimesh.Trimesh]) -> trimesh.Trimesh:
    fn = getattr(trimesh.boolean, op)
    return fn(meshes, engine="manifold", check_volume=True)


def _slab(mesh: trimesh.Trimesh, z0: float, z1: float) -> trimesh.Trimesh:
    """The part of ``mesh`` between two horizontal planes (intersection with a box)."""
    lo, hi = mesh.bounds
    m = 10.0
    box = box_between((lo[0] - m, lo[1] - m, z0), (hi[0] + m, hi[1] + m, z1))
    return _boolean("intersection", [mesh, to_trimesh(box)])


def _sub_mesh(mesh: trimesh.Trimesh, face_mask: np.ndarray) -> trimesh.Trimesh:
    sub = trimesh.Trimesh(vertices=mesh.vertices, faces=mesh.faces[face_mask], process=False)
    sub.remove_unreferenced_vertices()
    return sub


def _reglue_orphans(
    base: trimesh.Trimesh, mid: trimesh.Trimesh, roof: trimesh.Trimesh, floor_z: float, beam_z: float
) -> tuple[trimesh.Trimesh, trimesh.Trimesh, trimesh.Trimesh, list[str]]:
    """Give back to base / roof the pieces of the middle slab that belong to them.

    A shell of the middle slab that reaches both seams is a pillar.  One that touches only
    the floor seam is plinth ornament the floor cut sliced through (balustrade tops); one
    that touches only the beam seam hangs from the roof.  Either is shifted by one gap so
    it overlaps its owner and unioned back.  A shell touching neither is left where it is
    and reported.
    """
    if len(mid.faces) == 0:
        return base, mid, roof, []
    tol = CUT_GAP
    labels = face_bodies(mid)
    face_z = mid.vertices[mid.faces][:, :, 2]
    keep = np.ones(len(mid.faces), dtype=bool)
    to_base: list[trimesh.Trimesh] = []
    to_roof: list[trimesh.Trimesh] = []
    loose = 0
    for label in np.unique(labels):
        mask = labels == label
        z_lo, z_hi = float(face_z[mask].min()), float(face_z[mask].max())
        on_floor = z_lo <= floor_z + CUT_GAP / 2 + tol
        on_beam = z_hi >= beam_z - CUT_GAP / 2 - tol
        if on_floor and on_beam:
            continue
        if on_floor:
            piece = _sub_mesh(mid, mask)
            piece.apply_translation([0.0, 0.0, -2 * CUT_GAP])
            to_base.append(piece)
        elif on_beam:
            piece = _sub_mesh(mid, mask)
            piece.apply_translation([0.0, 0.0, 2 * CUT_GAP])
            to_roof.append(piece)
        else:
            loose += 1
            continue
        keep &= ~mask
    notes = []
    if to_base:
        base = _boolean("union", [base, *to_base])
        notes.append(f"{len(to_base)} piece(s) of plinth ornament above the floor seam kept with the base")
    if to_roof:
        roof = _boolean("union", [roof, *to_roof])
        notes.append(f"{len(to_roof)} piece(s) hanging below the beam seam kept with the roof")
    if loose:
        notes.append(f"{loose} loose fragment(s) between the seams stay in the colonnade part")
    if not keep.all():
        mid = _sub_mesh(mid, keep)
    return base, mid, roof, notes


# ---- operations -----------------------------------------------------------------------


def _plinth_inner_half_extents(result: Build) -> tuple[float, float]:
    """Half extents of the plinth at its deepest recess (the kantha), unscaled.

    Every ring vertex of the swept plinth sits at ``(+-(hx + d), +-(hy + d))``, so the
    smallest ``|x|`` over its vertices is the body half-width minus the deepest recess;
    insetting the cavity from there keeps the wall honest behind the mouldings.  Only the
    sweep itself (the solid named ``"plinth"``) is consulted: ornament in the same group
    may sit anywhere and must not shrink the cavity.
    """
    L = result.layout
    group = result.parts.get("plinth") or []
    solids = [s for s in group if s.name == "plinth"] or group
    if not solids:
        return L.body_hx, L.body_hy
    verts = np.concatenate([s.vertices for s in solids])
    return float(np.abs(verts[:, 0]).min()), float(np.abs(verts[:, 1]).min())


def _hollow(part: PartMesh, result: Build, wall: float) -> None:
    """Shell the plinth: subtract an inner box inset ``wall`` from every side, then two
    drain holes through the underside so resin can escape.  Skipped, with a note, when
    the wall is thinner than the printer can make, the plinth is shorter than three walls
    or the cavity would be too small for the drains.
    """
    p, L = result.params, result.layout
    s = p.scale
    plinth_h = L.floor_z * s
    if wall < p.min_feature:
        part.notes.append(
            f"plinth not hollowed: {wall:g} mm wall is below the printer's {p.min_feature:g} mm minimum"
        )
        return
    if plinth_h < 3 * wall:
        part.notes.append(
            f"plinth not hollowed: {plinth_h:.1f} mm plinth is shorter than three {wall:g} mm walls"
        )
        return
    in_hx, in_hy = _plinth_inner_half_extents(result)
    hx, hy = in_hx * s - wall, in_hy * s - wall
    if hx < MIN_CAVITY_HALF or hy < MIN_CAVITY_HALF:
        part.notes.append("plinth not hollowed: too small for a cavity with drain holes")
        return
    cavity = box_between((-hx, -hy, wall), (hx, hy, plinth_h - wall))
    inset = DRAIN_DIAMETER / 2 + 1.0
    drains = merge(
        [
            cylinder(DRAIN_DIAMETER / 2, -1.0, wall + 1.0).translated(k * (hx - inset), k * (hy - inset), 0.0)
            for k in (-1, 1)
        ]
    )
    before = part.mesh.volume
    part.mesh = _boolean("difference", [part.mesh, to_trimesh(cavity), to_trimesh(drains)])
    part.notes.append(
        f"plinth hollowed to a {wall:g} mm wall with two {DRAIN_DIAMETER:g} mm drain holes "
        f"underneath; {(before - part.mesh.volume) / 1000:.1f} cm3 saved"
    )


def _flip_roof(part: PartMesh, result: Build) -> None:
    if result.params.roof_style != "flat":
        part.notes.append(
            f"roof not flipped: roof style {result.params.roof_style!r} has no flat top to stand on"
        )
        return
    part.mesh.apply_transform(np.diag([1.0, -1.0, -1.0, 1.0]))  # 180 deg about X
    part.notes.append("roof part flipped: flat top on the bed, sockets facing up")


def _drop_to_bed(part: PartMesh) -> None:
    if len(part.mesh.faces):
        part.mesh.apply_translation([0.0, 0.0, -float(part.mesh.bounds[0][2])])


def _fit_factor(extents: np.ndarray, bed: tuple[float, float, float]) -> tuple[float, bool]:
    """Largest uniform scale that fits ``extents`` in ``bed`` and whether it needs a
    90 degree turn about Z to do so."""
    sx, sy, sz = (max(float(e), 1e-9) for e in extents)
    bx, by, bz = bed
    upright = min(bx / sx, by / sy)
    turned = min(by / sx, bx / sy)
    flat = max(upright, turned)
    return min(flat, bz / sz), turned > upright


def _check_bed(parts: list[PartMesh], options: PrintOptions) -> None:
    bed = options.bed_mm
    if bed is None:
        if options.fit_to_bed:
            for part in parts:
                part.notes.append("fit_to_bed ignored: no bed size given")
        return
    bed = tuple(float(v) for v in bed)
    bed_text = " x ".join(f"{v:g}" for v in bed) + " mm"
    factor = min(_fit_factor(part.mesh.extents, bed)[0] for part in parts if len(part.mesh.faces))
    if options.fit_to_bed and factor < 1.0:
        for part in parts:
            part.mesh.apply_scale(factor)
            _drop_to_bed(part)
            part.notes.append(
                f"scaled by {factor:.3f} to fit the {bed_text} bed (pegs and clearances scaled too)"
            )
    for part in parts:
        if not len(part.mesh.faces):
            continue
        f, turned = _fit_factor(part.mesh.extents, bed)
        size = " x ".join(f"{v:.1f}" for v in part.mesh.extents)
        if f >= 1.0 and not turned:
            part.notes.append(f"fits the {bed_text} bed")
        elif f >= 1.0:
            part.notes.append(f"fits the {bed_text} bed turned 90 degrees")
        else:
            part.notes.append(f"exceeds the {bed_text} bed: {size} mm needs scaling by {f:.3f}")


# ---- entry point ----------------------------------------------------------------------


def _split(result: Build, mesh: trimesh.Trimesh, options: PrintOptions) -> list[PartMesh]:
    L = result.layout
    s = result.params.scale
    floor_z = L.floor_z * s
    beam_z = L.corbel_top * s  # the seam where the corbels end and the beams begin
    half = CUT_GAP / 2
    lo, hi = mesh.bounds
    base = _slab(mesh, float(lo[2]) - 1.0, floor_z - half)
    mid = _slab(mesh, floor_z + half, beam_z - half)
    roof = _slab(mesh, beam_z + half, float(hi[2]) + 1.0)
    base, mid, roof, glue_notes = _reglue_orphans(base, mid, roof, floor_z, beam_z)

    floor_pegs, beam_pegs, peg_notes = peg_plan(result)
    if floor_pegs is not None:
        base = _boolean("union", [base, to_trimesh(floor_pegs.peg_solid())])
        mid = _boolean("difference", [mid, to_trimesh(floor_pegs.hole_solid())])
    if beam_pegs is not None:
        mid = _boolean("union", [mid, to_trimesh(beam_pegs.peg_solid())])
        roof = _boolean("difference", [roof, to_trimesh(beam_pegs.hole_solid())])

    parts = [
        PartMesh("base", base, colour=PART_COLOURS["base"]),
        PartMesh("colonnade", mid, colour=PART_COLOURS["colonnade"]),
        PartMesh("roof", roof, colour=PART_COLOURS["roof"]),
    ]
    parts[0].notes += glue_notes
    if floor_pegs is not None:
        parts[0].notes.append(
            f"{len(floor_pegs.points)} pegs (d {2 * floor_pegs.radius:.1f} mm, {floor_pegs.height:g} mm) "
            f"under the pillars; sockets in the colonnade"
        )
    if beam_pegs is not None:
        parts[1].notes.append(
            f"{len(beam_pegs.points)} pegs (d {2 * beam_pegs.radius:.1f} mm, {beam_pegs.height:g} mm) "
            f"on the corner corbels; sockets in the roof"
        )
    for note in peg_notes:
        target = parts[0] if "pillars" in note else parts[1]
        target.notes.append(note)
    pieces = body_count(mid)
    if pieces > 1:
        parts[1].notes.append(
            f"colonnade is {pieces} loose pieces (nothing joins the pillars below the beams); "
            f"slicers place them as separate bodies"
        )

    if options.hollow_wall_mm > 0:
        _hollow(parts[0], result, options.hollow_wall_mm)
    if options.flip_roof:
        _flip_roof(parts[2], result)
    parts = [part for part in parts if len(part.mesh.faces)]
    for part in parts:
        _drop_to_bed(part)
    return parts


def prepare_parts(result: Build, options: PrintOptions | None = None) -> list[PartMesh]:
    """Union the build and apply the print options; one PartMesh per printable piece.

    Every part returned is watertight with positive volume and rests on ``z = 0``.  Build
    notes (``result.notes``) are not copied onto the parts; the caller reports them once.
    """
    options = options or PrintOptions()
    mesh = make_mesh(result, union=True)
    if options.split:
        parts = _split(result, mesh, options)
    else:
        part = PartMesh("mandapa", mesh)
        if options.hollow_wall_mm > 0:
            _hollow(part, result, options.hollow_wall_mm)
        if options.flip_roof:
            part.notes.append("roof not flipped: the roof is only a separate part when split")
        _drop_to_bed(part)
        parts = [part]
    _check_bed(parts, options)
    return parts
