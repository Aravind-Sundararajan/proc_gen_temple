"""Every tunable of the mandapa, with the metadata the GUI needs to build its controls.

Why one dataclass carries both the value and its control
--------------------------------------------------------
The parameter panel, the JSON/XML files, ``--set`` on the command line and
:meth:`MandapaParams.randomized` all need the same list of knobs.  Keeping the
range, step, group and help text next to the default (the :func:`P` metadata)
means a field added here appears everywhere at once, and nothing else in the
project has to be told.  A field without complete metadata would surface as a
broken control, so :mod:`tests.test_builder` pins that every field has it.

Field types are deliberately limited to ``int``, ``float``, ``bool`` and a
``str`` drawn from ``choices``.  The GUI, the clamping logic and the file
formats all understand exactly those four; a richer type (a list of sides, a
nested dataclass) would need bespoke handling in every one of them.

Why sides are a choice rather than four flags
---------------------------------------------
Kakshasana seats, jali screens and steps are all "on some sides of the hall".
Four booleans per feature would be twelve checkboxes that allow combinations no
hall uses (a seat on the front only, steps on three sides); the named sets in
:data:`SIDE_SETS` are the arrangements that occur, with the front (-Y, where the
steps are) left open by default because that is the entrance.

Why ``clamped`` exists
----------------------
Files written by older versions, hand-edited JSON and ``--set`` can all carry
values outside the declared ranges.  The builder would still produce *something*
for most of them, but the something is rarely a building, and a few (zero pillars,
negative heights) crash.  Clamping at the start of :func:`mandapa.builder.build`
turns every such input into a nearby legal design instead.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field, fields, replace
from pathlib import Path
from typing import Any, Self

# Smallest feature a printer can reproduce reliably, in mm.
PRINTER_PROFILES: dict[str, float] = {
    "fdm_0.4": 0.8,
    "fdm_0.25": 0.5,
    "resin": 0.3,
    "none": 0.0,
}

GROUPS = [
    "Plan",
    "Plinth (adhishthana)",
    "Pillars (stambha)",
    "Entablature (prastara)",
    "Roof",
    "Steps (sopana)",
    "Printing",
    "Procedural",
    "Enclosure (kakshasana, jali)",
    "Sanctum (garbhagriha)",
]

# Named side arrangements.  Compass letters: S is the front (-Y, where the steps are),
# N the back (+Y), E is +X and W is -X.
SIDE_SETS: dict[str, tuple[str, ...]] = {
    "none": (),
    "front": ("S",),
    "back": ("N",),
    "sides": ("E", "W"),
    "front+back": ("S", "N"),
    "back+sides": ("N", "E", "W"),
    "all": ("S", "N", "E", "W"),
}
_ENCLOSURE_SIDES = ["none", "back", "sides", "back+sides", "all"]
_STEP_SIDES = ["front", "front+back", "sides", "all"]


def P(
    default: Any,
    label: str,
    *,
    lo: float | None = None,
    hi: float | None = None,
    step: float | None = None,
    group: str = "Plan",
    choices: list[str] | None = None,
    help: str = "",
) -> Any:
    meta = {"label": label, "lo": lo, "hi": hi, "step": step, "group": group, "choices": choices, "help": help}
    return field(default=default, metadata=meta)


class ParamRecord:
    """The machinery every parameter family shares; the fields are the family.

    :class:`MandapaParams` and the gopuram's ``GopuramParams`` are both dataclasses of
    :func:`P` fields over this mixin, which is what lets the parameter panel, the XML
    format, ``--set`` and the clamping rule serve both buildings from one spelling.
    The mixin assumes only what :func:`P` guarantees: four field types and complete
    metadata.  Family taste — ``randomized``, the side sets — stays on the subclass.
    """

    @property
    def min_feature(self) -> float:
        return PRINTER_PROFILES.get(self.printer_profile, 0.0)

    @classmethod
    def specs(cls) -> list[tuple[str, type, dict[str, Any]]]:
        """Field name, declared type and GUI metadata, in declaration order."""
        return [(f.name, f.type, dict(f.metadata)) for f in fields(cls)]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Self:
        """Build from a dict, ignoring unknown keys and coercing types of known ones."""
        kwargs: dict[str, Any] = {}
        for f in fields(cls):
            if f.name not in data:
                continue
            value = data[f.name]
            kind = _resolve_type(f.type)
            if kind is bool and isinstance(value, str):
                # ``bool("false")`` is True; files and ``--set`` hand us words, not truth values.
                value = value.strip().lower() in ("1", "true", "yes", "on")
            try:
                kwargs[f.name] = kind(value)
            except (TypeError, ValueError):
                continue
        return cls(**kwargs)

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: str | Path) -> Self:
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    def with_(self, **changes: Any) -> Self:
        return replace(self, **changes)

    def clamped(self) -> Self:
        """Copy with every numeric field pulled inside its declared range."""
        changes: dict[str, Any] = {}
        for name, kind, meta in self.specs():
            value = getattr(self, name)
            if meta["choices"] is not None:
                if value not in meta["choices"]:
                    changes[name] = meta["choices"][0]
                continue
            if meta["lo"] is None or isinstance(value, bool):
                continue
            clamped = min(max(value, meta["lo"]), meta["hi"])
            if clamped != value:
                changes[name] = _resolve_type(kind)(clamped)
        return replace(self, **changes) if changes else self


@dataclass
class MandapaParams(ParamRecord):
    """All dimensions are millimetres unless the help text says otherwise.

    Defaults describe a 100 mm, sixteen-pillar Chola hall: the size that prints in
    an evening on a desktop FDM machine and still has room for the full moulding
    vocabulary.  Proportions that come from the texts are named where they are
    used in :mod:`mandapa.builder`; the ones here (pillar 35 mm on a 12 mm plinth,
    beam 3.5 mm) are tuned for the model to read as a building at arm's length.
    """

    # ---- Plan ---------------------------------------------------------------------------
    footprint_x: float = P(100.0, "Footprint X", lo=40, hi=300, step=1, help="Overall plinth width.")
    footprint_y: float = P(100.0, "Footprint Y", lo=40, hi=300, step=1, help="Overall plinth depth.")
    pillars_x: int = P(4, "Pillars along X", lo=2, hi=8, step=1)
    pillars_y: int = P(4, "Pillars along Y", lo=2, hi=8, step=1)
    pillar_inset: float = P(
        1.0, "Pillar inset", lo=0.5, hi=3.0, step=0.1,
        help="Distance from the plinth top edge to the outer pillar centres, in pillar widths.",
    )

    # ---- Plinth -------------------------------------------------------------------------
    plinth_height: float = P(12.0, "Plinth height", lo=2, hi=60, step=0.5, group=GROUPS[1])
    plinth_style: str = P(
        "padabandha", "Moulding style", group=GROUPS[1],
        choices=["padabandha", "pratibandha", "kapotabandha", "plain"],
        help="padabandha: Mayamata 24-part base with faceted torus. pratibandha: round torus. "
        "kapotabandha: adds a dripstone cornice. plain: simple chamfers.",
    )
    plinth_projection: float = P(
        0.12, "Torus projection", lo=0.0, hi=0.3, step=0.01, group=GROUPS[1],
        help="How far the kumuda (torus) bulges, as a fraction of plinth height.",
    )
    plinth_galapadas: bool = P(
        True, "Galapadas", group=GROUPS[1],
        help="Small pilasters bridging the kantha recess at regular intervals (Pallava/Chola signature).",
    )
    plinth_padma: bool = P(
        False, "Padma band", group=GROUPS[1],
        help="Lotus-petal (saw-tooth) band on the upana, the lowest moulding.",
    )

    # ---- Pillars ------------------------------------------------------------------------
    pillar_width: float = P(6.0, "Pillar width", lo=2, hi=30, step=0.5, group=GROUPS[2])
    pillar_height: float = P(
        35.0, "Pillar height", lo=5, hi=200, step=1, group=GROUPS[2],
        help="Plinth top to underside of the beams, including capital and corbel.",
    )
    shaft_style: str = P(
        "chola", "Shaft style", group=GROUPS[2],
        choices=["chola", "square", "octagonal", "sixteen", "round", "fluted", "varied"],
        help="chola: square-octagon-square. fluted: sixteen concave flutes. "
        "varied: two styles alternating by row or column, driven by the seed.",
    )
    capital_ratio: float = P(
        0.25, "Capital ratio", lo=0.1, hi=0.5, step=0.01, group=GROUPS[2],
        help="Share of pillar height taken by kalasa, tadi, kumbha, padma and phalaka.",
    )
    corbel_reach: float = P(
        1.2, "Corbel reach", lo=0.6, hi=2.5, step=0.05, group=GROUPS[2],
        help="Tip of the potika bracket from the pillar centre, in pillar widths.",
    )
    corbel_height: float = P(
        0.7, "Corbel height", lo=0.3, hi=1.5, step=0.05, group=GROUPS[2], help="In pillar widths."
    )
    corbel_style: str = P(
        "taranga", "Corbel style", group=GROUPS[2], choices=["taranga", "bevel", "pushpa"],
        help="taranga: rolled wave underside. bevel: plain angled cut. "
        "pushpa: bevel with a pendant lotus bud under each arm tip.",
    )
    medallions: bool = P(
        True, "Lotus medallions", group=GROUPS[2],
        help="Circular bosses on the faces of the square shaft blocks; dropped below the printer's minimum feature.",
    )
    kattu_bands: bool = P(
        True, "Kattu bands", group=GROUPS[2], help="Thin raised bands where the shaft changes section."
    )

    # ---- Entablature --------------------------------------------------------------------
    beam_height: float = P(3.5, "Beam (uttara) height", lo=1, hi=20, step=0.5, group=GROUPS[3])
    beam_width: float = P(0.8, "Beam width", lo=0.4, hi=1.5, step=0.05, group=GROUPS[3], help="In pillar widths.")
    frieze_height: float = P(2.5, "Frieze (valabhi) height", lo=0, hi=15, step=0.5, group=GROUPS[3])
    bhuta_frieze: bool = P(
        False, "Bhuta-gana frieze", group=GROUPS[3],
        help="Row of rounded bosses on the valabhi; reads as the dwarf-figure frieze at this scale.",
    )
    dentils: bool = P(False, "Dentil course", group=GROUPS[3], help="Row of small blocks directly under the kapota.")
    kapota_height: float = P(4.0, "Kapota height", lo=0, hi=20, step=0.5, group=GROUPS[3])
    kapota_projection: float = P(4.0, "Kapota projection", lo=0, hi=20, step=0.5, group=GROUPS[3])
    kapota_scoop: float = P(
        0.5, "Kapota scoop", lo=0.0, hi=1.0, step=0.05, group=GROUPS[3],
        help="Concavity of the cornice underside; 0 is a straight chamfer.",
    )
    kudus: bool = P(
        True, "Kudu arches", group=GROUPS[3],
        help="Horseshoe-arch ornaments along the kapota face; they get tiny finials when the printer can make them.",
    )
    roof_slab: float = P(3.0, "Roof slab", lo=1, hi=20, step=0.5, group=GROUPS[3])

    # ---- Roof ---------------------------------------------------------------------------
    roof_style: str = P(
        "hara", "Roof style", group=GROUPS[4], choices=["hara", "flat", "stepped", "kerala"],
        help="hara: flat roof with a parapet of miniature shrines. stepped: tiered pyramid. "
        "kerala: hipped sloping roof with overhanging eaves.",
    )
    parapet_height: float = P(8.0, "Parapet / tier height", lo=1, hi=30, step=0.5, group=GROUPS[4])
    parapet_inset: float = P(1.5, "Parapet inset", lo=0, hi=20, step=0.5, group=GROUPS[4])
    salas_per_side: int = P(
        1, "Salas per side", lo=0, hi=4, step=1, group=GROUPS[4],
        help="Barrel-roofed shrines between the corner kutas of the hara parapet.",
    )
    panjaras: bool = P(
        False, "Panjaras", group=GROUPS[4],
        help="Apsidal shrines between the kutas and salas of the hara (kuta-panjara-sala-panjara-kuta) when there is room.",
    )
    nasi: bool = P(False, "Nasi arches", group=GROUPS[4], help="Small horseshoe dormers on the fronts of kutas and salas.")
    tiers: int = P(3, "Tiers", lo=1, hi=6, step=1, group=GROUPS[4], help="Stepped roof only.")
    tier_ratio: float = P(0.78, "Tier ratio", lo=0.5, hi=0.95, step=0.01, group=GROUPS[4])
    sikhara_shape: str = P(
        "octagonal", "Sikhara shape", group=GROUPS[4], choices=["square", "octagonal", "round"],
        help="Plan of the crowning dome on the stepped roof: square (nagara), octagonal (dravida), round (vesara).",
    )
    roof_pitch: float = P(
        30.0, "Roof pitch", lo=15, hi=50, step=1, group=GROUPS[4],
        help="Kerala roof only: slope of the planes in degrees from horizontal.",
    )
    eave_overhang: float = P(
        6.0, "Eave overhang", lo=0, hi=30, step=0.5, group=GROUPS[4],
        help="Kerala roof only: how far the eaves hang past the roof slab.",
    )
    finial: bool = P(True, "Finials (stupi)", group=GROUPS[4])

    # ---- Steps --------------------------------------------------------------------------
    steps: bool = P(True, "Steps", group=GROUPS[5])
    steps_sides: str = P(
        "front", "Steps on", group=GROUPS[5], choices=_STEP_SIDES,
        help="Which sides get a flight of steps; the front is -Y.",
    )
    step_count: int = P(4, "Step count", lo=1, hi=12, step=1, group=GROUPS[5])
    steps_width: float = P(0.35, "Steps width", lo=0.1, hi=1.0, step=0.05, group=GROUPS[5], help="Fraction of footprint X.")
    balustrades: bool = P(True, "Balustrades", group=GROUPS[5])
    hastihasta: bool = P(
        True, "Hastihasta curl", group=GROUPS[5],
        help="Elephant-trunk curl at the foot of each balustrade.",
    )

    # ---- Printing -----------------------------------------------------------------------
    printer_profile: str = P(
        "fdm_0.4", "Printer", group=GROUPS[6], choices=list(PRINTER_PROFILES),
        help="Sets the minimum feature size that thin parts are clamped to.",
    )
    printable_overhangs: bool = P(
        True, "Limit overhangs to 45°", group=GROUPS[6],
        help="Flattens the kapota scoop and corbel roll so they print without supports.",
    )
    scale: float = P(1.0, "Export scale", lo=0.1, hi=10.0, step=0.05, group=GROUPS[6])

    # ---- Procedural ---------------------------------------------------------------------
    seed: int = P(0, "Seed", lo=0, hi=99999, step=1, group=GROUPS[7], help="Drives per-pillar variation.")

    # ---- Enclosure ----------------------------------------------------------------------
    kakshasana: str = P(
        "none", "Kakshasana seats", group=GROUPS[8], choices=_ENCLOSURE_SIDES,
        help="Seat-back parapets between the outer pillars, with a sloping back-rest.",
    )
    jali: str = P(
        "none", "Jali screens", group=GROUPS[8], choices=_ENCLOSURE_SIDES,
        help="Lattice screens between the outer pillars; bays with steps stay open.",
    )
    centre_feature: str = P(
        "none", "Centre feature", group=GROUPS[8], choices=["none", "pitha", "pedestal"],
        help="pitha: a miniature moulded altar platform. pedestal: a shaft with a lotus top.",
    )

    # ---- Sanctum ------------------------------------------------------------------------
    sanctum: str = P(
        "none", "Garbhagriha", group=GROUPS[9], choices=["none", "centre", "back"],
        help="The walled cell a vigraham stands in. centre: free-standing in the middle of the "
        "hall with an ambulatory round it. back: against the back row, the hall in front of it "
        "as a porch. Its walls run on the pillar lines, so the pillars in them become pilasters.",
    )
    sanctum_bays: int = P(
        1, "Cell bays", lo=1, hi=3, step=1, group=GROUPS[9],
        help="Bays of the pillar grid the cell spans, centred on the hall; rounded to what the grid can centre.",
    )
    sanctum_wall: float = P(
        1.15, "Wall thickness", lo=0.8, hi=2.5, step=0.05, group=GROUPS[9],
        help="In pillar widths. Just over one width hides the shafts and lets the capitals and "
        "corbels show as pilasters.",
    )
    dvara_width: float = P(
        0.5, "Doorway (dvara) width", lo=0.3, hi=0.8, step=0.05, group=GROUPS[9],
        help="Fraction of the clear cell width, capped so the opening stays twice as high as it is wide.",
    )
    sanctum_floor: float = P(
        0.08, "Raised floor", lo=0.0, hi=0.3, step=0.01, group=GROUPS[9],
        help="Height of the cell floor and its threshold above the hall floor, in pillar heights.",
    )
    sanctum_niches: bool = P(
        True, "Devakoshtha niches", group=GROUPS[9],
        help="A framed niche on every blind wall bay, between the pilasters.",
    )
    vimana: bool = P(
        True, "Vimana tower", group=GROUPS[9],
        help="A tower over the cell: the Roof group's tiers and sikhara, or a second hipped roof "
        "under a Kerala roof. The stepped roof is already the tower.",
    )

    # ---- helpers ------------------------------------------------------------------------
    def sides(self, name: str) -> tuple[str, ...]:
        """Compass letters for a side-set field (``kakshasana``, ``jali``, ``steps_sides``)."""
        return SIDE_SETS.get(getattr(self, name), ())

    def randomized(self, seed: int | None = None) -> MandapaParams:
        """A plausible variant: same vocabulary, different proportions and ornament choices.

        The draws are weighted towards what real halls do (most are open, most have
        a hara, few have a Kerala roof), not uniform over the parameter space; the
        uniform sweep is the job of the fuzz test, not of the "Randomise" button.
        """
        if seed is None:
            seed = random.randrange(100000)
        rng = random.Random(seed)
        size = rng.uniform(70, 140)
        pillar_w = rng.uniform(4.5, 8.0)
        roof = rng.choice(["hara", "hara", "hara", "stepped", "stepped", "flat", "kerala"])
        return replace(
            self,
            seed=seed,
            footprint_x=round(size, 1),
            footprint_y=round(size * rng.choice([1.0, 1.0, 1.25, 1.5]), 1),
            pillars_x=rng.randint(2, 5),
            pillars_y=rng.randint(2, 5),
            plinth_height=round(size * rng.uniform(0.09, 0.15), 1),
            plinth_style=rng.choice(["padabandha", "padabandha", "pratibandha", "kapotabandha"]),
            plinth_projection=round(rng.uniform(0.08, 0.16), 2),
            plinth_galapadas=rng.random() < 0.7,
            plinth_padma=rng.random() < 0.3,
            pillar_width=round(pillar_w, 1),
            pillar_height=round(pillar_w * rng.uniform(4.5, 7.0), 1),
            shaft_style=rng.choice(["chola", "chola", "octagonal", "sixteen", "fluted", "varied"]),
            capital_ratio=round(rng.uniform(0.2, 0.32), 2),
            corbel_reach=round(rng.uniform(1.0, 1.6), 2),
            corbel_style=rng.choice(["taranga", "taranga", "bevel", "pushpa"]),
            medallions=rng.random() < 0.6,
            kattu_bands=rng.random() < 0.7,
            bhuta_frieze=rng.random() < 0.3,
            dentils=rng.random() < 0.3,
            kapota_projection=round(rng.uniform(3.0, 6.0), 1),
            kapota_height=round(rng.uniform(3.0, 5.5), 1),
            kudus=rng.random() < 0.8,
            roof_style=roof,
            salas_per_side=rng.randint(0, 2),
            panjaras=rng.random() < 0.4,
            nasi=rng.random() < 0.4,
            tiers=rng.randint(2, 4),
            tier_ratio=round(rng.uniform(0.7, 0.85), 2),
            sikhara_shape=rng.choice(["square", "octagonal", "octagonal", "round"]),
            roof_pitch=round(rng.uniform(25, 40), 0),
            eave_overhang=round(rng.uniform(4, 9), 1),
            steps=rng.random() < 0.8,
            steps_sides=rng.choice(["front", "front", "front", "front+back", "all"]),
            step_count=rng.randint(3, 6),
            balustrades=rng.random() < 0.7,
            hastihasta=rng.random() < 0.7,
            kakshasana=rng.choice(["none", "none", "back", "back+sides", "sides"]),
            jali=rng.choice(["none", "none", "none", "back", "back+sides"]),
            centre_feature=rng.choice(["none", "none", "pitha", "pedestal"]),
            # drawn last so every seed's hall is the one it was before sanctums existed
            sanctum=rng.choice(["none", "none", "back", "centre"]),
            sanctum_bays=rng.choice([1, 1, 2]),
            sanctum_wall=round(rng.uniform(1.0, 1.6), 2),
            dvara_width=round(rng.uniform(0.4, 0.6), 2),
            sanctum_floor=round(rng.uniform(0.05, 0.12), 2),
            sanctum_niches=rng.random() < 0.7,
            vimana=rng.random() < 0.8,
        ).clamped()


def _resolve_type(kind: Any) -> type:
    """Field annotations are strings under ``from __future__ import annotations``."""
    if isinstance(kind, type):
        return kind
    return {"int": int, "float": float, "str": str, "bool": bool}[str(kind)]
