"""Turn a gopuram build into print-ready part meshes: the split, pegs, bed fit.

The machinery — the half-space cut, the peg/socket tolerance contract, the bed check —
is :mod:`mandapa.printprep`'s, imported rather than restated.  What is this module's
own is the anatomy: a gopuram has one natural seam where the mandapa has two.  The
masonry base ends at the top of the base prastara (``layout.wall_top``) and the brick
superstructure begins; cutting there parts the building where the builders parted it,
and nothing is cut through a moulding.  Four pegs stand on the slab over the jambs —
never over the passage, whose void is directly below the middle of the seam — and
their sockets rise into the first tala, which is solid.

There is no hollowing and no roof flip here: the plinth is two flanks a cavity cannot
honestly span (a box would break into the passage), and neither part has a flat top to
stand on.  Options that cannot work are not offered, rather than offered and refused.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mandapa.builder import Build
from mandapa.export import body_count, make_mesh, to_trimesh
from mandapa.printprep import (
    CUT_GAP,
    HOLE_EXTRA_DEPTH,
    MIN_PEG_HEIGHT,
    MIN_WALL,
    PEG_CLEARANCE,
    PEG_HEIGHT,
    PartMesh,
    Pegs,
    boolean_op,
    check_bed,
    drop_to_bed,
    slab,
)

__all__ = ["PART_COLOURS", "GopuramPrintOptions", "peg_plan", "prepare_parts"]

#: sRGB tints for the split parts: granite below the seam, brick above, as built.
PART_COLOURS: dict[str, tuple[float, float, float]] = {
    "base": (0.62, 0.58, 0.53),
    "superstructure": (0.78, 0.62, 0.5),
}

#: Peg circumradius as a fraction of the narrower flank; pegs locate, they do not carry.
PEG_RADIUS_FACTOR = 0.25
MIN_PEG_RADIUS = 0.5


@dataclass
class GopuramPrintOptions:
    """What the export dialog is generated from; same field contract as the mandapa's
    :class:`~mandapa.printprep.PrintOptions` (simple types, ``label``/``help`` metadata)."""

    split: bool = field(
        default=False,
        metadata={
            "label": "Split into parts",
            "help": "Cut into base and superstructure at the top of the base prastara, "
            "with 3 mm alignment pegs over the jambs and sockets 0.2 mm larger.",
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


def peg_plan(result: Build) -> tuple[Pegs | None, list[str]]:
    """Four pegs on the seam, one over each quarter of the jambs, or ``None`` with the
    reason.  Radius follows the narrower flank so the socket keeps its wall; positions
    stay inside the first tala's footprint, where the sockets are cut."""
    L, p = result.layout, result.params
    s = p.scale
    wall = max(p.min_feature, MIN_WALL)
    tala = L.talas[0]
    radius = min(PEG_RADIUS_FACTOR * 2.0 * L.flank_hx * s, 0.25 * tala.hy * s, 2.0)
    if radius < MIN_PEG_RADIUS:
        return None, [
            (
                f"no pegs on the seam: a {2 * L.flank_hx * s:.1f} mm jamb cannot take a "
                f"socket and keep a {wall:.1f} mm wall"
            )
        ]
    x = min(L.flank_cx, tala.hx - radius / s - wall / s - PEG_CLEARANCE / s)
    y = min(0.55 * tala.hy, tala.hy - radius / s - wall / s - PEG_CLEARANCE / s)
    if x * s <= (L.door_w / 2.0) * s + radius + wall or y * s <= radius + wall:
        return None, ["no pegs on the seam: the passage leaves no jamb to stand them over"]
    # The socket must stay inside the first tala rather than surface on its terrace.
    height = min(PEG_HEIGHT, (tala.z1 - L.wall_top) * s - wall - HOLE_EXTRA_DEPTH)
    if height < MIN_PEG_HEIGHT:
        return None, ["no pegs on the seam: the first tala is too thin for a socket"]
    points = tuple((sx * x * s, sy * y * s) for sx in (-1, 1) for sy in (-1, 1))
    return Pegs(L.wall_top * s, points, radius, height), []


def prepare_parts(result: Build, options: GopuramPrintOptions | None = None) -> list[PartMesh]:
    """Union the build and apply the print options; one PartMesh per printable piece.

    Every part returned is watertight with positive volume and rests on ``z = 0``.
    Build notes are not copied onto the parts; the caller reports them once.
    """
    options = options or GopuramPrintOptions()
    mesh = make_mesh(result, union=True)
    if options.split:
        seam = result.layout.wall_top * result.params.scale
        half = CUT_GAP / 2
        lo, hi = mesh.bounds
        base = slab(mesh, float(lo[2]) - 1.0, seam - half)
        top = slab(mesh, seam + half, float(hi[2]) + 1.0)
        parts = [
            PartMesh("base", base, colour=PART_COLOURS["base"]),
            PartMesh("superstructure", top, colour=PART_COLOURS["superstructure"]),
        ]
        pegs, peg_notes = peg_plan(result)
        if pegs is not None:
            parts[0].mesh = boolean_op("union", [base, to_trimesh(pegs.peg_solid())])
            parts[1].mesh = boolean_op("difference", [top, to_trimesh(pegs.hole_solid())])
            parts[0].notes.append(
                f"{len(pegs.points)} pegs (d {2 * pegs.radius:.1f} mm, {pegs.height:g} mm) "
                f"over the jambs; sockets in the first tala"
            )
        parts[0].notes += peg_notes
        for part in parts:
            pieces = body_count(part.mesh)
            if pieces > 1:
                part.notes.append(f"{part.name} is {pieces} separate shells; check the seam height")
    else:
        parts = [PartMesh("gopuram", mesh)]
    parts = [part for part in parts if len(part.mesh.faces)]
    for part in parts:
        drop_to_bed(part)
    check_bed(parts, options)
    return parts
