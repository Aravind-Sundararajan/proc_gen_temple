"""Building and exporting off the GUI thread.

A build takes a few hundred milliseconds and a boolean union several seconds; neither may
stall a slider.  Each worker is a ``QThread`` that does one job and reports with a signal,
so the window only ever touches the result on its own thread.  Any exception is caught
and forwarded as text: a worker that dies silently leaves the busy indicator spinning
forever, which is worse than a traceback in the log.
"""

from __future__ import annotations

import traceback
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PySide6.QtCore import QThread, Signal

from .. import export as export_module
from ..builder import Build, build
from ..export import Report, classify_undersides, inspect_mesh, make_mesh
from ..meshlib import Solid, merge
from ..params import MandapaParams
from ..printprep import PartMesh, PrintOptions, prepare_parts
from .viewer import GroupMesh

__all__ = ["BuildPayload", "BuildWorker", "ExportOutcome", "ExportWorker", "analyse", "write_parts"]


@dataclass
class BuildPayload:
    """Everything the window shows after a build, computed where it is cheap to."""

    result: Build
    groups: dict[str, GroupMesh]
    bounds: tuple[np.ndarray, np.ndarray]
    faces: int
    overhang_fraction: float
    bridge_fraction: float
    report: Report | None
    union: bool


def _areas(solid: Solid) -> np.ndarray:
    v = solid.vertices[solid.faces]
    return 0.5 * np.linalg.norm(np.cross(v[:, 1] - v[:, 0], v[:, 2] - v[:, 0]), axis=1)


def analyse(result: Build, union: bool) -> BuildPayload:
    """Merge, classify and split back per group.

    Classification runs on the whole model because the build plate is the model's lowest
    point: a roof classified on its own would take its own underside for the floor and
    report no bridges at all.  The masks are then sliced back to the groups, whose faces
    sit in the merged mesh in the same order they were merged.
    """
    if union:
        mesh = make_mesh(result, union=True)
        scale = result.params.scale if result.params else 1.0
        solid = Solid(np.asarray(mesh.vertices) / (scale or 1.0), np.asarray(mesh.faces))
        steep, flat = classify_undersides(solid.vertices, solid.faces, solid.face_normals())
        groups = {"model": GroupMesh(solid, steep, flat)}
        merged = solid
        report = inspect_mesh(mesh, result.notes)
    else:
        per_group = {name: merge(solids) for name, solids in result.parts.items()}
        merged = merge(per_group.values())
        steep, flat = classify_undersides(merged.vertices, merged.faces, merged.face_normals())
        groups = {}
        offset = 0
        for name, solid in per_group.items():
            count = len(solid.faces)
            groups[name] = GroupMesh(solid, steep[offset : offset + count], flat[offset : offset + count])
            offset += count
        report = None
    if len(merged.faces):
        areas = _areas(merged)
        total = float(areas.sum()) or 1.0
        overhang = float(areas[steep].sum()) / total
        bridge = float(areas[flat].sum()) / total
        bounds = merged.bounds
    else:
        overhang = bridge = 0.0
        bounds = (np.zeros(3), np.zeros(3))
    return BuildPayload(
        result=result,
        groups=groups,
        bounds=bounds,
        faces=len(merged.faces),
        overhang_fraction=overhang,
        bridge_fraction=bridge,
        report=report,
        union=union,
    )


class BuildWorker(QThread):
    """Builds (and optionally unions) off the GUI thread.

    ``build`` is the family's builder — :func:`mandapa.builder.build` unless the window
    hands over the gopuram's — so the worker never has to know whose parameters it holds.
    """

    done = Signal(object)
    failed = Signal(str)

    def __init__(self, params: MandapaParams, union: bool, parent=None, build=build):
        super().__init__(parent)
        self.params, self.union, self.build = params, union, build

    def run(self) -> None:
        try:
            self.done.emit(analyse(self.build(self.params), self.union))
        except Exception:  # noqa: BLE001 - any failure must reach the GUI thread, not kill the worker
            self.failed.emit(traceback.format_exc())


@dataclass
class ExportOutcome:
    paths: list[Path]
    parts: list[PartMesh]
    reports: list[Report]

    def lines(self) -> list[str]:
        """The log's account: every file written, then every part's report.

        Files and parts are listed separately because they need not pair up — a 3MF
        carries several parts in one file, an STL export writes one file per part.
        """
        out = [f"wrote {path}" for path in self.paths]
        for part, report in zip(self.parts, self.reports):
            out.append(f"part {part.name}")
            out += [f"  {line}" for line in report.summary().splitlines()]
            out += [f"  note       {note}" for note in part.notes if note not in report.notes]
        return out


def write_parts(parts: list[PartMesh], path: Path, fmt: str) -> list[Path]:
    """Write the parts, through :func:`mandapa.export.export_parts` when it exists.

    Without it, one part goes to ``path`` and several go to ``<stem>_<part><suffix>``
    beside it, so a split model never overwrites itself.
    """
    export_parts = getattr(export_module, "export_parts", None)
    if export_parts is not None:
        written = export_parts(parts, path, fmt)
        if isinstance(written, (list, tuple)) and written:
            return [Path(p) for p in written]
        return [path] * len(parts)
    path.parent.mkdir(parents=True, exist_ok=True)
    if len(parts) == 1:
        parts[0].mesh.export(path, file_type=fmt)
        return [path]
    paths = []
    for part in parts:
        target = path.with_name(f"{path.stem}_{part.name}{path.suffix}")
        part.mesh.export(target, file_type=fmt)
        paths.append(target)
    return paths


class ExportWorker(QThread):
    """Prepares the print parts and writes them, reporting per part.

    ``prepare`` is the family's print-prep entry point, defaulting to the mandapa's
    :func:`~mandapa.printprep.prepare_parts`; the options object is whatever that
    function takes, which is also what the dialog was generated from.
    """

    done = Signal(object)
    failed = Signal(str)

    def __init__(
        self, result: Build, options: PrintOptions, path: Path, fmt: str, parent=None,
        prepare=prepare_parts,
    ):
        super().__init__(parent)
        self.result, self.options, self.path, self.fmt = result, options, Path(path), fmt
        self.prepare = prepare

    def run(self) -> None:
        try:
            parts = self.prepare(self.result, self.options)
            paths = write_parts(parts, self.path, self.fmt)
            inspect_parts = getattr(export_module, "inspect_parts", None)
            if inspect_parts is not None:
                reports = list(inspect_parts(parts))
            else:
                reports = [inspect_mesh(part.mesh, part.notes) for part in parts]
            self.done.emit(ExportOutcome(paths, parts, reports))
        except Exception:  # noqa: BLE001 - see BuildWorker
            self.failed.emit(traceback.format_exc())
