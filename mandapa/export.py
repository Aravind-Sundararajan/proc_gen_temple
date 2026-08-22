"""Boolean union, print checks and the STL / 3MF writers.

Why two formats
---------------
STL is what every slicer opens and what :mod:`mandapa.cli` has always written, so the
default stays a single binary STL.  It carries nothing but triangles, though: no unit, no
part names, no colour, and one solid per file.  A multi-part print (see
:mod:`mandapa.printprep`) therefore lands as ``stem_partname.stl`` files the user has to
load one by one.  3MF fixes exactly that: the package declares ``unit="millimeter"``, holds
one named ``<object>`` per part and a ``<build>`` that places them, and can colour each
part so the slicer shows base, colonnade and roof apart.  The writer uses only ``zipfile``
and ``xml.etree`` because the format is small and a dependency on a 3MF library would buy
nothing the five elements below do not already cover.

Exactness
---------
3MF coordinates are written with four decimals (0.1 um).  That is finer than the float32
the boolean engine works in, so the file carries the mesh exactly as it was computed; a
reader that compares vertices may use a tolerance of 1e-4 mm.  STL is float32 by format.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
import zipfile
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import trimesh

from .builder import Build, build
from .meshlib import Solid, merge
from .params import MandapaParams

PLA_DENSITY_G_CM3 = 1.24

#: Thickness of the solid skin a slicer lays down with 3 perimeters at the usual 0.45 mm
#: extrusion width.  The weight estimate treats top and bottom solid layers as the same
#: thickness, which is what 4-5 layers at 0.2 mm come to.
SKIN_MM = 3 * 0.45
#: Infill density the weight estimate assumes.
INFILL = 0.15

#: Gap between parts when a multi-part 3MF lays them out in a row on the build.
PART_GAP_MM = 10.0

# 3MF Core Specification 1.x package layout.
_NS_MODEL = "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"
_NS_CONTENT_TYPES = "http://schemas.openxmlformats.org/package/2006/content-types"
_NS_RELATIONSHIPS = "http://schemas.openxmlformats.org/package/2006/relationships"
_REL_MODEL = "http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"
_MODEL_PATH = "3D/3dmodel.model"
_CONTENT_TYPES = {
    "rels": "application/vnd.openxmlformats-package.relationships+xml",
    "model": "application/vnd.ms-package.3dmanufacturing-3dmodel+xml",
}


@dataclass
class Report:
    """Print report of one mesh.  ``summary()`` is a fixed-label-column block for a log."""

    watertight: bool
    faces: int
    bounds_mm: tuple[tuple[float, float, float], tuple[float, float, float]]
    volume_cm3: float
    overhang_area_mm2: float
    overhang_fraction: float
    bridge_area_mm2: float
    notes: list[str]
    area_mm2: float = 0.0
    bodies: int = 1
    name: str = ""

    @property
    def size_mm(self) -> tuple[float, float, float]:
        lo, hi = self.bounds_mm
        return tuple(round(h - l, 2) for l, h in zip(lo, hi))

    @property
    def weight_g(self) -> float:
        """Grams of PLA if printed solid (100 % infill)."""
        return self.volume_cm3 * PLA_DENSITY_G_CM3

    @property
    def weight_estimate_g(self) -> float:
        """Grams of PLA at :data:`INFILL` with 3 perimeters.  An estimate, not a slicer figure.

        Model: the surface carries a solid skin :data:`SKIN_MM` thick (``area * SKIN_MM``,
        capped at the volume so a thin finial is not counted twice) and the remaining
        interior is filled at :data:`INFILL`.  Real figures depend on layer height, top and
        bottom layer counts and the infill pattern; expect the slicer within about 20 %.
        """
        volume = self.volume_cm3 * 1000.0
        skin = min(self.area_mm2 * SKIN_MM, volume)
        return (skin + INFILL * (volume - skin)) / 1000.0 * PLA_DENSITY_G_CM3

    def summary(self) -> str:
        x, y, z = self.size_mm
        lines = [f"part       {self.name}"] if self.name else []
        lines += [
            f"size       {x} x {y} x {z} mm",
            f"faces      {self.faces}",
            f"volume     {self.volume_cm3:.1f} cm3  (~{self.weight_g:.0f} g PLA at 100% infill)",
            f"weight     ~{self.weight_estimate_g:.0f} g PLA at {INFILL:.0%} infill, 3 perimeters (estimate)",
            f"overhangs  {self.overhang_fraction * 100:.1f}% of surface slopes down steeper than 45 deg",
            f"bridges    {self.bridge_area_mm2 / 100:.0f} cm2 of flat underside (ceilings etc.)",
            f"watertight {'yes' if self.watertight else 'NO'}",
        ]
        if self.bodies != 1:
            lines.append(f"bodies     {self.bodies} separate shells")
        lines += [f"note       {n}" for n in self.notes]
        return "\n".join(lines)


@dataclass
class PartMesh:
    """One printable piece: its name (file suffix / 3MF object name), mesh and print notes.

    ``colour`` is sRGB in 0..1 and only reaches the 3MF writer; STL has no honest colour
    field, so a coloured part prints its geometry and keeps the tint for 3MF.
    """

    name: str
    mesh: trimesh.Trimesh
    notes: list[str] = field(default_factory=list)
    colour: tuple[float, float, float] | None = None


def to_trimesh(solid: Solid) -> trimesh.Trimesh:
    return trimesh.Trimesh(vertices=solid.vertices, faces=solid.faces, process=False)


def union_solids(solids: list[Solid]) -> trimesh.Trimesh:
    """Boolean-union every solid into one manifold shell via manifold3d."""
    meshes = [to_trimesh(s) for s in solids]
    if len(meshes) == 1:
        return meshes[0]
    return trimesh.boolean.union(meshes, engine="manifold", check_volume=True)


def classify_undersides(
    vertices: np.ndarray, faces: np.ndarray, normals: np.ndarray, max_angle_deg: float = 45.0
) -> tuple[np.ndarray, np.ndarray]:
    """Masks of (sloped overhang, flat bridge) faces above the build plate.

    A sloped overhang faces down more steeply than ``max_angle_deg`` from vertical and needs
    support on FDM.  A flat underside (ceiling) is a bridge: fine over short spans.
    """
    down = -normals[:, 2]
    floor_z = float(vertices[:, 2].min())
    above = vertices[faces][:, :, 2].max(axis=1) > floor_z + 1e-6
    flat = (down > 0.999) & above
    steep = (down > math.sin(math.radians(max_angle_deg)) + 1e-6) & above & ~flat
    return steep, flat


def face_bodies(mesh: trimesh.Trimesh) -> np.ndarray:
    """Label every face with the smallest face index of the shell it belongs to.

    Connected components of the face-adjacency graph by min-label hooking with pointer
    jumping: every round hooks each edge's two labels to the smaller one and then
    compresses label chains, so it converges in O(log n) rounds of numpy work.  Written
    here because ``mesh.split()`` needs networkx or scipy, neither of which this project
    depends on, and a few dozen lines of numpy are cheaper than either.
    """
    n = len(mesh.faces)
    labels = np.arange(n)
    if n == 0:
        return labels
    adjacency = mesh.face_adjacency
    if len(adjacency) == 0:
        return labels
    a, b = adjacency[:, 0], adjacency[:, 1]
    while True:
        before = labels.copy()
        low = np.minimum(labels[a], labels[b])
        np.minimum.at(labels, labels[a], low)
        np.minimum.at(labels, labels[b], low)
        while True:
            jumped = labels[labels]
            if np.array_equal(jumped, labels):
                break
            labels = jumped
        if np.array_equal(before, labels):
            return labels


def body_count(mesh: trimesh.Trimesh) -> int:
    """Number of separate closed shells (a void inside a solid counts as one more)."""
    if len(mesh.faces) == 0:
        return 0
    return len(np.unique(face_bodies(mesh)))


def make_mesh(result: Build, union: bool = True) -> trimesh.Trimesh:
    """Scaled, optionally unioned mesh of a build."""
    scale = result.params.scale if result.params else 1.0
    solids = [s.scaled(scale) for s in result.solids()] if scale != 1.0 else result.solids()
    return union_solids(solids) if union else to_trimesh(merge(solids))


def inspect_mesh(mesh: trimesh.Trimesh, notes: list[str] | None = None, name: str = "") -> Report:
    if len(mesh.faces) == 0:
        zero = (0.0, 0.0, 0.0)
        return Report(False, 0, (zero, zero), 0.0, 0.0, 0.0, 0.0, list(notes or []), 0.0, 0, name)
    steep, flat = classify_undersides(mesh.vertices, mesh.faces, mesh.face_normals)
    areas = mesh.area_faces
    total = float(mesh.area)
    overhang = float(areas[steep].sum())
    lo, hi = mesh.bounds
    return Report(
        watertight=bool(mesh.is_watertight),
        faces=len(mesh.faces),
        bounds_mm=(tuple(map(float, lo)), tuple(map(float, hi))),
        volume_cm3=float(abs(mesh.volume)) / 1000.0,
        overhang_area_mm2=overhang,
        overhang_fraction=overhang / total if total > 0 else 0.0,
        bridge_area_mm2=float(areas[flat].sum()),
        notes=list(notes or []),
        area_mm2=total,
        bodies=body_count(mesh),
        name=name,
    )


def inspect_parts(parts: list[PartMesh]) -> list[Report]:
    """One report per part, carrying the part's name and notes."""
    return [inspect_mesh(part.mesh, part.notes, name=part.name) for part in parts]


def export_stl(params: MandapaParams, path: str | Path, union: bool = True) -> Report:
    """Build, union and write a binary STL; returns the print report."""
    result = build(params)
    mesh = make_mesh(result, union=union)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    mesh.export(path, file_type="stl")
    return inspect_mesh(mesh, result.notes)


# ---- part files -----------------------------------------------------------------------


def _slug(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "_", name).strip("_") or "part"


def export_parts(parts: list[PartMesh], path: str | Path, fmt: str | None = None) -> list[Path]:
    """Write the parts as STL or 3MF; returns the paths written.

    The suffix follows the format: ``fmt=None`` reads it from ``path`` (``.3mf`` means 3MF,
    anything else STL) and an explicit ``fmt`` replaces it.  STL is one solid per file, so
    several parts become ``stem_partname.stl`` next to each other; a single part keeps the
    exact path, which keeps ``mandapa --out out/mandapa.stl`` byte-identical to before.
    3MF always writes one package.
    """
    if not parts:
        raise ValueError("no parts to export")
    path = Path(path)
    if fmt is None:
        fmt = "3mf" if path.suffix.lower() == ".3mf" else "stl"
    fmt = fmt.lower()
    if fmt not in ("stl", "3mf"):
        raise ValueError(f"format must be 'stl' or '3mf', got {fmt!r}")
    path = path.with_suffix(f".{fmt}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "3mf":
        return [write_3mf(parts, path)]
    if len(parts) == 1:
        parts[0].mesh.export(path, file_type="stl")
        return [path]
    written = []
    for part in parts:
        target = path.with_name(f"{path.stem}_{_slug(part.name)}.stl")
        part.mesh.export(target, file_type="stl")
        written.append(target)
    return written


def _hex_colour(rgb: tuple[float, float, float]) -> str:
    r, g, b = (round(min(max(c, 0.0), 1.0) * 255) for c in rgb)
    return f"#{r:02X}{g:02X}{b:02X}FF"


def _rgb_from_hex(text: str | None) -> tuple[float, float, float] | None:
    if not text or not re.fullmatch(r"#[0-9A-Fa-f]{6}([0-9A-Fa-f]{2})?", text):
        return None
    return tuple(int(text[i : i + 2], 16) / 255.0 for i in (1, 3, 5))


def _xml_bytes(root: ET.Element) -> bytes:
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def write_3mf(parts: list[PartMesh], path: str | Path) -> Path:
    """Write a 3MF package: one ``<object>`` per part, every object placed by the build.

    Layout: a single part keeps its own coordinates (identity placement); several parts
    are laid in a row along +X, :data:`PART_GAP_MM` apart and starting at the origin, via
    the build items' transforms so the meshes themselves stay in print pose.  Slicers
    re-arrange anyway; the row just makes the file sensible when opened as is.

    Colour: parts with a ``colour`` share one ``<basematerials>`` resource and reference
    it with ``pid``/``pindex``; with no coloured part the element is omitted entirely, so a
    plain export stays the minimal valid package.
    """
    if not parts:
        raise ValueError("no parts to write")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    root = ET.Element("model", {"unit": "millimeter", "xmlns": _NS_MODEL})
    ET.SubElement(root, "metadata", name="Title").text = path.stem
    ET.SubElement(root, "metadata", name="Application").text = "proc_gen_temple"
    resources = ET.SubElement(root, "resources")

    material_index: dict[int, int] = {}  # part position -> pindex
    if any(p.colour is not None for p in parts):
        materials = ET.SubElement(resources, "basematerials", id="1")
        for k, part in enumerate(parts):
            if part.colour is None:
                continue
            material_index[k] = len(material_index)
            ET.SubElement(materials, "base", name=part.name, displaycolor=_hex_colour(part.colour))
    first_id = 2 if material_index else 1

    for k, part in enumerate(parts):
        attrs = {"id": str(first_id + k), "type": "model", "name": part.name}
        if k in material_index:
            attrs["pid"] = "1"
            attrs["pindex"] = str(material_index[k])
        mesh_el = ET.SubElement(ET.SubElement(resources, "object", attrs), "mesh")
        vertices = ET.SubElement(mesh_el, "vertices")
        for x, y, z in part.mesh.vertices.tolist():
            ET.SubElement(vertices, "vertex", x=f"{x:.4f}", y=f"{y:.4f}", z=f"{z:.4f}")
        triangles = ET.SubElement(mesh_el, "triangles")
        for a, b, c in part.mesh.faces.tolist():
            ET.SubElement(triangles, "triangle", v1=str(a), v2=str(b), v3=str(c))

    build_el = ET.SubElement(root, "build")
    if len(parts) == 1:
        ET.SubElement(build_el, "item", objectid=str(first_id))
    else:
        cursor = 0.0
        for k, part in enumerate(parts):
            lo, hi = part.mesh.bounds
            tx, ty = cursor - float(lo[0]), -float(lo[1])
            transform = f"1 0 0 0 1 0 0 0 1 {tx:.4f} {ty:.4f} 0"
            ET.SubElement(build_el, "item", objectid=str(first_id + k), transform=transform)
            cursor += float(hi[0] - lo[0]) + PART_GAP_MM

    types = ET.Element("Types", xmlns=_NS_CONTENT_TYPES)
    for ext, content_type in _CONTENT_TYPES.items():
        ET.SubElement(types, "Default", Extension=ext, ContentType=content_type)
    rels = ET.Element("Relationships", xmlns=_NS_RELATIONSHIPS)
    ET.SubElement(rels, "Relationship", Target=f"/{_MODEL_PATH}", Id="rel0", Type=_REL_MODEL)

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", _xml_bytes(types))
        zf.writestr("_rels/.rels", _xml_bytes(rels))
        zf.writestr(_MODEL_PATH, _xml_bytes(root))
    return path


def read_3mf(path: str | Path) -> list[PartMesh]:
    """Read back the subset of 3MF that :func:`write_3mf` produces: mesh objects placed by
    build items (transforms applied), names and base-material colours.  Component
    hierarchies and non-millimetre units are refused rather than guessed at.
    """
    with zipfile.ZipFile(path) as zf:
        rels = ET.fromstring(zf.read("_rels/.rels"))
        target = next(
            (r.get("Target") for r in rels if r.get("Type") == _REL_MODEL), f"/{_MODEL_PATH}"
        )
        root = ET.fromstring(zf.read(target.lstrip("/")))
    ns = {"m": _NS_MODEL}
    unit = root.get("unit", "millimeter")
    if unit != "millimeter":
        raise ValueError(f"{path}: unit is {unit!r}, expected millimeter")

    colours: dict[tuple[str | None, str | None], tuple[float, float, float] | None] = {}
    for materials in root.iterfind("m:resources/m:basematerials", ns):
        for k, base in enumerate(materials.iterfind("m:base", ns)):
            colours[(materials.get("id"), str(k))] = _rgb_from_hex(base.get("displaycolor"))

    objects: dict[str, tuple[str, np.ndarray, np.ndarray, tuple[float, float, float] | None]] = {}
    for obj in root.iterfind("m:resources/m:object", ns):
        mesh_el = obj.find("m:mesh", ns)
        if mesh_el is None:
            raise ValueError(f"{path}: object {obj.get('id')} is not a mesh object")
        vertices = np.array(
            [[float(v.get(k)) for k in "xyz"] for v in mesh_el.iterfind("m:vertices/m:vertex", ns)],
            dtype=np.float64,
        ).reshape(-1, 3)
        faces = np.array(
            [
                [int(t.get(k)) for k in ("v1", "v2", "v3")]
                for t in mesh_el.iterfind("m:triangles/m:triangle", ns)
            ],
            dtype=np.int64,
        ).reshape(-1, 3)
        colour = colours.get((obj.get("pid"), obj.get("pindex")))
        objects[obj.get("id")] = (obj.get("name", ""), vertices, faces, colour)

    parts = []
    for item in root.iterfind("m:build/m:item", ns):
        name, vertices, faces, colour = objects[item.get("objectid")]
        text = item.get("transform")
        if text:
            m = np.array(text.split(), dtype=np.float64).reshape(4, 3)
            vertices = vertices @ m[:3] + m[3]
        mesh = trimesh.Trimesh(vertices=vertices, faces=faces, process=False)
        parts.append(PartMesh(name, mesh, colour=colour))
    return parts
