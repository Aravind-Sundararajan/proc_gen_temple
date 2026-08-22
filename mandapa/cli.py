"""Headless entry point: ``mandapa --out model.stl``.

The default invocation builds, unions and writes one binary STL exactly as it always has.
The print-preparation flags hand the build to :mod:`mandapa.printprep` first, so
``--split`` yields three parts (``stem_base.stl`` and friends, or one ``.3mf``), and the
per-part report follows.  The exit status is 1 if any written part is not watertight,
which is the one thing a slicer cannot fix.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from .builder import build
from .export import export_parts, export_stl, inspect_parts
from .help import about_text, glossary_text
from .io import TempleFormatError, load_any, save_temple
from .params import MandapaParams
from .presets import PRESETS
from .printprep import PrintOptions, prepare_parts


def save_params(params: MandapaParams, path: str | Path) -> None:
    """``.xml`` writes a parameters-only ``<temple>`` document; anything else the JSON dump."""
    path = Path(path)
    if path.suffix.lower() == ".xml":
        save_temple(path, params)
    else:
        params.save(path)


def find_preset(name: str) -> MandapaParams:
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


def parse_bed(text: str) -> tuple[float, float, float]:
    parts = [t for t in text.replace("x", ",").replace("X", ",").split(",") if t.strip()]
    try:
        values = tuple(float(t) for t in parts)
    except ValueError:
        values = ()
    if len(values) != 3 or any(v <= 0 for v in values):
        raise ValueError(f"--bed expects three positive sizes X,Y,Z in mm, got {text!r}")
    return values


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="mandapa", description="Generate a 3D-printable mandapa.")
    ap.add_argument("--out", "-o", default="out/mandapa.stl",
                    help="output path; the suffix follows --format (default out/mandapa.stl)")
    ap.add_argument("--format", "-f", choices=["stl", "3mf"],
                    help="stl (one file per part) or 3mf (one package); default from the --out suffix")
    source = ap.add_mutually_exclusive_group()
    source.add_argument("--params", "-p", metavar="FILE",
                        help="design to build: a <temple> .xml document or a legacy .json parameters file")
    source.add_argument("--preset", metavar="NAME", help="start from a named preset (see --list-presets)")
    ap.add_argument("--list-presets", action="store_true", help="print the preset names and exit")
    ap.add_argument("--about", action="store_true", help="print the version, sources and licences and exit")
    ap.add_argument("--glossary", action="store_true", help="print the glossary of the terms in the panel and exit")
    ap.add_argument("--random", "-r", nargs="?", const=-1, type=int, metavar="SEED",
                    help="randomise the design (optionally from a fixed seed)")
    ap.add_argument("--set", "-s", action="append", default=[], metavar="NAME=VALUE",
                    help="override one parameter, e.g. --set pillars_x=3")
    ap.add_argument("--save-params", metavar="FILE",
                    help="write the effective parameters: a <temple> document for .xml, else JSON")
    ap.add_argument("--no-union", action="store_true",
                    help="skip the boolean union (fast, overlapping shells; STL only, no print prep)")
    prep = ap.add_argument_group("print preparation")
    prep.add_argument("--split", action="store_true",
                      help="cut into base / colonnade / roof parts with alignment pegs")
    prep.add_argument("--flip-roof", action="store_true",
                      help="print the roof part upside down on its flat top (flat roofs, with --split)")
    prep.add_argument("--hollow", type=float, default=0.0, metavar="MM",
                      help="shell the plinth to this wall thickness with drain holes (resin)")
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
            params = MandapaParams()
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
        params = MandapaParams.from_dict({**params.to_dict(), **overrides})
    if args.save_params:
        save_params(params, args.save_params)

    bed = None
    if args.bed:
        try:
            bed = parse_bed(args.bed)
        except ValueError as exc:
            ap.error(str(exc))
    options = PrintOptions(
        split=args.split, hollow_wall_mm=args.hollow, bed_mm=bed, fit_to_bed=args.fit_bed,
        flip_roof=args.flip_roof,
    )

    t0 = time.perf_counter()
    if args.no_union:
        if options != PrintOptions() or args.format == "3mf":
            ap.error("--no-union writes raw overlapping shells: no print preparation, STL only")
        report = export_stl(params, args.out, union=False)
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
    for report in reports:
        print()
        print(report.summary())
    return 0 if all(r.watertight for r in reports) else 1


if __name__ == "__main__":
    sys.exit(main())
