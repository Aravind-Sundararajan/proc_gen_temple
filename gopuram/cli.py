"""Headless entry point: ``gopuram --out model.stl``.

The mandapa's CLI shape with this family's verbs: the default invocation builds, unions
and writes one binary STL; ``--split`` parts the building at its one seam; the per-part
report follows and the exit status is 1 if any written part is not watertight.  Where
the mandapa sizes itself to what stands inside (``--vigraham``), the gopuram sizes
itself to what passes through: ``--procession W,H`` sets the export scale so the dvara
clears an object that big.  There is no ``--hollow`` and no ``--flip-roof`` because
:mod:`gopuram.printprep` has no honest way to do either; a flag that would only ever
print an apology is not offered.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from mandapa.cli import parse_bed
from mandapa.export import export_parts, export_stl, inspect_parts
from mandapa.io import TempleFormatError

from .builder import Build, build, scale_for_passage
from .help import about_text, glossary_text
from .io import load_any, save_gopuram
from .params import GopuramParams
from .presets import PRESETS
from .printprep import GopuramPrintOptions, prepare_parts


def find_preset(name: str) -> GopuramParams:
    """Exact, then case-insensitive, then unique-prefix match against ``PRESETS``."""
    if name in PRESETS:
        return PRESETS[name]
    folded = name.casefold()
    matches = [k for k in PRESETS if k.casefold() == folded]
    if not matches:
        matches = [k for k in PRESETS if k.casefold().startswith(folded)]
    if len(matches) != 1:
        options = ", ".join(repr(k) for k in PRESETS)
        kind = "ambiguous" if matches else "unknown"
        raise KeyError(f"{kind} preset {name!r}; choose from {options}")
    return PRESETS[matches[0]]


def parse_pair(text: str, flag: str, names: str) -> tuple[float, float]:
    parts = [t for t in text.replace("x", ",").replace("X", ",").split(",") if t.strip()]
    try:
        values = tuple(float(t) for t in parts)
    except ValueError:
        values = ()
    if len(values) != 2 or any(v <= 0 for v in values):
        raise ValueError(f"{flag} expects two positive sizes {names} in mm, got {text!r}")
    return values


def procession_note(result: Build, size: tuple[float, float]) -> str:
    """What the export does for the procession: the scale applied and the clear passage."""
    s, L = result.params.scale, result.layout
    w, h = size
    return (
        f"scaled by {s:.3f} so a {w:g} x {h:g} mm object passes: the dvara clears "
        f"{L.clear_w * s:.1f} x {L.door_h * s:.1f} mm between the mouldings"
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="gopuram", description="Generate a 3D-printable gopuram.")
    ap.add_argument("--out", "-o", default="out/gopuram.stl",
                    help="output path; the suffix follows --format (default out/gopuram.stl)")
    ap.add_argument("--format", "-f", choices=["stl", "3mf"],
                    help="stl (one file per part) or 3mf (one package); default from the --out suffix")
    source = ap.add_mutually_exclusive_group()
    source.add_argument("--params", "-p", metavar="FILE", help="design to build: a <gopuram> .xml document")
    source.add_argument("--preset", metavar="NAME", help="start from a named preset (see --list-presets)")
    ap.add_argument("--list-presets", action="store_true", help="print the preset names and exit")
    ap.add_argument("--about", action="store_true", help="print the version, sources and licences and exit")
    ap.add_argument("--glossary", action="store_true", help="print the glossary of the terms in the panel and exit")
    ap.add_argument("--random", "-r", nargs="?", const=-1, type=int, metavar="SEED",
                    help="randomise the design (optionally from a fixed seed)")
    ap.add_argument("--set", "-s", action="append", default=[], metavar="NAME=VALUE",
                    help="override one parameter, e.g. --set talas=7")
    ap.add_argument("--procession", metavar="W,H",
                    help="set the export scale so the dvara passes an object this big (mm, "
                    "with 1 mm clearance)")
    ap.add_argument("--save-params", metavar="FILE", help="write the effective parameters as a <gopuram> document")
    ap.add_argument("--no-union", action="store_true",
                    help="skip the boolean union (fast, overlapping shells; STL only, no print prep)")
    prep = ap.add_argument_group("print preparation")
    prep.add_argument("--split", action="store_true",
                      help="cut into base / superstructure at the base prastara, with alignment pegs")
    prep.add_argument("--bed", metavar="X,Y,Z", help="printer volume in mm to check every part against")
    prep.add_argument("--fit-bed", action="store_true", help="scale everything uniformly to fit --bed")
    args = ap.parse_args(argv)

    if args.about:
        print(about_text())
        return 0
    if args.glossary:
        print(glossary_text())
        return 0
    if args.list_presets:
        for name in PRESETS:
            print(name)
        return 0

    try:
        if args.preset:
            params = find_preset(args.preset)
        elif args.params:
            document = load_any(args.params)
            params = document.params
            if document.ignored:
                print(f"ignored unknown parameters: {', '.join(document.ignored)}", file=sys.stderr)
        else:
            params = GopuramParams()
    except (KeyError, OSError, TempleFormatError, ValueError) as exc:
        ap.error(str(exc))
    if args.random is not None:
        params = params.randomized(None if args.random < 0 else args.random)
    overrides = {}
    for item in args.set:
        name, _, value = item.partition("=")
        if not value:
            ap.error(f"--set expects NAME=VALUE, got {item!r}")
        overrides[name.strip()] = value.strip()
    if overrides:
        params = GopuramParams.from_dict({**params.to_dict(), **overrides})
    procession = None
    if args.procession:
        try:
            procession = parse_pair(args.procession, "--procession", "W,H")
            params = scale_for_passage(params, procession)
        except ValueError as exc:
            ap.error(str(exc))
        if params.scale > 10.0:
            print(f"the procession needs scale {params.scale:.2f}; the panel stops at 10", file=sys.stderr)
            params = params.clamped()
    if args.save_params:
        save_gopuram(args.save_params, params)

    bed = None
    if args.bed:
        try:
            bed = parse_bed(args.bed)
        except ValueError as exc:
            ap.error(str(exc))
    options = GopuramPrintOptions(split=args.split, bed_mm=bed, fit_to_bed=args.fit_bed)

    t0 = time.perf_counter()
    if args.no_union:
        if options != GopuramPrintOptions() or args.format == "3mf":
            ap.error("--no-union writes raw overlapping shells: no print preparation, STL only")
        report = export_stl(params, args.out, union=False, build=build)
        print(f"wrote {Path(args.out)} in {time.perf_counter() - t0:.1f}s")
        print(report.summary())
        return 0 if report.watertight else 1

    result = build(params)
    parts = prepare_parts(result, options)
    paths = export_parts(parts, args.out, fmt=args.format)
    reports = inspect_parts(parts)
    print(f"wrote {', '.join(str(p) for p in paths)} in {time.perf_counter() - t0:.1f}s")
    for note in result.notes:
        print(f"note       {note}")
    if procession is not None:
        print(f"note       {procession_note(result, procession)}")
    for report in reports:
        print()
        print(report.summary())
    return 0 if all(r.watertight for r in reports) else 1


if __name__ == "__main__":
    sys.exit(main())
