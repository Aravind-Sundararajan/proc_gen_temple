"""Every tunable of the gopuram, with the metadata the GUI needs to build its controls.

The record is a :class:`~mandapa.params.ParamRecord` like :class:`MandapaParams`, and
for the same reasons (that module's docstring carries them): one dataclass is the panel,
the file, ``--set`` and the randomiser at once.  The fields are the gopuram's own.

Why the passage is stated as fractions
--------------------------------------
The dvara of a gopuram is not a doorway in a wall, it is the reason the building
exists — the axis processions pass along — so its width follows the base and its
height follows the wall rather than being millimetres that go stale when the massing
changes.  The builder resolves them, keeps the texts' minimum of a dvara twice as
high as it is wide by narrowing an opening the wall cannot honour, and reports the
clear width, which is less than the stated one because the adhishthana's mouldings
run through the passage.

Why the talas share one ratio
-----------------------------
Real gopurams diminish in plan faster than in height, which is what gives the profile
its concave lean.  One ``tala_ratio`` drives the plan directly and the heights at a
gentler derived rate (see :func:`gopuram.builder.compute_layout`); a second knob for
the height ratio was tried on paper and rejected — every pairing that read as a
building kept the two within a few percent of that rule, so the knob would mostly
offer ways to be wrong.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, replace

from mandapa.params import PRINTER_PROFILES, P, ParamRecord

GROUPS = [
    "Plan",
    "Plinth (adhishthana)",
    "Passage (dvara)",
    "Wall (pada)",
    "Talas",
    "Crown (sikhara)",
    "Printing",
    "Procedural",
]


@dataclass
class GopuramParams(ParamRecord):
    """All dimensions are millimetres unless the help text says otherwise.

    Defaults describe a 90 mm, five-tala gateway: tall enough that the taper reads,
    small enough to print upright in an evening.  Proportions that come from the
    buildings are named where they are used in :mod:`gopuram.builder`.
    """

    # ---- Plan ---------------------------------------------------------------------------
    base_width: float = P(
        90.0, "Base width", lo=40, hi=300, step=1,
        help="Along the enclosure wall (X): the long axis, and the axis the crown's vault runs.",
    )
    base_depth: float = P(
        60.0, "Base depth", lo=30, hi=200, step=1,
        help="The way through (Y): the length of the passage.",
    )

    # ---- Plinth -------------------------------------------------------------------------
    plinth_height: float = P(10.0, "Plinth height", lo=2, hi=40, step=0.5, group=GROUPS[1])
    plinth_style: str = P(
        "padabandha", "Moulding style", group=GROUPS[1],
        choices=["padabandha", "pratibandha", "kapotabandha", "plain"],
        help="The same vocabulary as the mandapa's base; the mouldings run through the passage, "
        "as they do in the built gateways.",
    )
    plinth_projection: float = P(
        0.12, "Torus projection", lo=0.0, hi=0.3, step=0.01, group=GROUPS[1],
        help="How far the kumuda (torus) bulges, as a fraction of plinth height.",
    )
    plinth_galapadas: bool = P(
        True, "Galapadas", group=GROUPS[1],
        help="Small pilasters bridging the kantha recess at regular intervals.",
    )
    plinth_padma: bool = P(
        False, "Padma band", group=GROUPS[1],
        help="Lotus-petal band on the upana, the lowest moulding.",
    )

    # ---- Passage ------------------------------------------------------------------------
    dvara_width: float = P(
        0.11, "Doorway (dvara) width", lo=0.08, hi=0.3, step=0.01, group=GROUPS[2],
        help="Fraction of the base width; narrowed by the builder when the wall is too low "
        "to keep the opening twice as high as it is wide.",
    )
    dvara_height: float = P(
        0.72, "Doorway height", lo=0.4, hi=0.85, step=0.01, group=GROUPS[2],
        help="Fraction of the wall height; a lintel of at least 0.15 of the wall stays above.",
    )

    # ---- Wall ---------------------------------------------------------------------------
    wall_height: float = P(
        30.0, "Wall height", lo=8, hi=120, step=1, group=GROUPS[3],
        help="Plinth top to the base prastara: the plumb masonry the talas stand on.",
    )
    wall_storeys: int = P(
        2, "Storeys", lo=1, hi=2, step=1, group=GROUPS[3],
        help="The built gateways read as one or two storeys of wall; two adds a kapota "
        "course at the storey line.",
    )
    pilasters: bool = P(
        True, "Pilasters", group=GROUPS[3],
        help="Flat wall pilasters on the outer faces; dropped below the printer's minimum feature.",
    )
    niches: bool = P(
        True, "Devakoshtha niches", group=GROUPS[3],
        help="A framed niche on each flank of the lower storey, and one over the dvara.",
    )
    kapota_height: float = P(3.0, "Kapota height", lo=0, hi=12, step=0.5, group=GROUPS[3])
    kapota_projection: float = P(
        2.4, "Kapota projection", lo=0, hi=12, step=0.5, group=GROUPS[3],
        help="Of the base prastara and the storey course; capped at 0.8 x height under the 45 deg rule.",
    )
    kudus: bool = P(True, "Kudu arches", group=GROUPS[3], help="Along the base prastara's kapota face.")

    # ---- Talas --------------------------------------------------------------------------
    talas: int = P(
        5, "Talas", lo=1, hi=9, step=1, group=GROUPS[4],
        help="Storeys of the superstructure; fewer are built, with a note, when the taper "
        "runs out of footprint.",
    )
    tala_ratio: float = P(
        0.85, "Tala ratio", lo=0.7, hi=0.95, step=0.01, group=GROUPS[4],
        help="Plan of each tala as a fraction of the one below; heights shrink at a gentler "
        "derived rate, which is what leans the profile inward.",
    )
    tala_height: float = P(10.0, "First tala height", lo=3, hi=30, step=0.5, group=GROUPS[4])
    hara: bool = P(
        True, "Hara", group=GROUPS[4],
        help="A parapet of miniature shrines — corner kutas, salas between — on every tala's terrace.",
    )
    salas_per_tala: int = P(
        1, "Salas per side", lo=0, hi=3, step=1, group=GROUPS[4],
        help="Barrel-roofed shrines between the corner kutas along each tala's long sides.",
    )
    panjaras: bool = P(
        False, "Panjaras", group=GROUPS[4],
        help="Apsidal shrines between the kutas and salas when there is room.",
    )
    nasi: bool = P(False, "Nasi arches", group=GROUPS[4], help="Small horseshoe dormers on the hara shrines.")
    finial: bool = P(
        True, "Stupis on the shrines", group=GROUPS[4],
        help="Pot finials on the hara's kutas and salas; dropped below the printer's minimum feature.",
    )
    tala_openings: bool = P(
        True, "Tala openings", group=GROUPS[4],
        help="The framed opening over the passage on each tala, front and back: the vertical "
        "line the dvara starts.",
    )

    # ---- Crown --------------------------------------------------------------------------
    crown_height: float = P(
        11.0, "Crown height", lo=3, hi=30, step=0.5, group=GROUPS[5],
        help="Griva and vault together, above the top tala.",
    )
    kalasas: int = P(
        5, "Kalasas", lo=1, hi=13, step=1, group=GROUPS[5],
        help="Pot finials along the vault's ridge. The row is odd in every built gopuram, "
        "so an even count is lowered by one, with a note.",
    )
    mahanasi: bool = P(
        True, "Mahanasi", group=GROUPS[5],
        help="The great horseshoe arch on each end face of the vault.",
    )

    # ---- Printing -----------------------------------------------------------------------
    printer_profile: str = P(
        "fdm_0.4", "Printer", group=GROUPS[6], choices=list(PRINTER_PROFILES),
        help="Sets the minimum feature size that thin parts are clamped to.",
    )
    printable_overhangs: bool = P(
        True, "Limit overhangs to 45°", group=GROUPS[6],
        help="Flattens the kapota curves and eaves so the tower prints without supports.",
    )
    scale: float = P(1.0, "Export scale", lo=0.1, hi=10.0, step=0.05, group=GROUPS[6])

    # ---- Procedural ---------------------------------------------------------------------
    seed: int = P(0, "Seed", lo=0, hi=99999, step=1, group=GROUPS[7], help="Drives the Randomise button.")

    def randomized(self, seed: int | None = None) -> GopuramParams:
        """A plausible variant: same vocabulary, different massing and ornament choices.

        Weighted towards what the built gateways do — most are two-storeyed and
        five-to-seven-tala'd, few are squat — not uniform over the parameter space;
        the uniform sweep is the fuzz test's job.
        """
        if seed is None:
            seed = random.randrange(100000)
        rng = random.Random(seed)
        width = rng.uniform(65, 140)
        return replace(
            self,
            seed=seed,
            base_width=round(width, 1),
            base_depth=round(width * rng.uniform(0.55, 0.75), 1),
            plinth_height=round(width * rng.uniform(0.09, 0.13), 1),
            plinth_style=rng.choice(["padabandha", "padabandha", "pratibandha", "kapotabandha"]),
            plinth_projection=round(rng.uniform(0.08, 0.16), 2),
            plinth_galapadas=rng.random() < 0.7,
            plinth_padma=rng.random() < 0.3,
            dvara_width=round(rng.uniform(0.09, 0.14), 2),
            dvara_height=round(rng.uniform(0.62, 0.8), 2),
            wall_height=round(width * rng.uniform(0.28, 0.4), 1),
            wall_storeys=rng.choice([1, 2, 2]),
            pilasters=rng.random() < 0.8,
            niches=rng.random() < 0.8,
            kapota_height=round(rng.uniform(2.2, 4.0), 1),
            kapota_projection=round(rng.uniform(2.2, 4.0), 1),
            kudus=rng.random() < 0.7,
            talas=rng.choice([3, 4, 5, 5, 6, 7, 7, 9]),
            tala_ratio=round(rng.uniform(0.8, 0.92), 2),
            tala_height=round(width * rng.uniform(0.09, 0.14), 1),
            hara=rng.random() < 0.85,
            salas_per_tala=rng.randint(0, 2),
            panjaras=rng.random() < 0.3,
            nasi=rng.random() < 0.4,
            finial=rng.random() < 0.85,
            tala_openings=rng.random() < 0.85,
            crown_height=round(width * rng.uniform(0.1, 0.16), 1),
            kalasas=rng.choice([3, 5, 5, 7, 9]),
            mahanasi=rng.random() < 0.8,
        ).clamped()
