"""Named starting points.  ``PRESETS`` maps a display name to a full parameter set.

The rules are :mod:`mandapa.presets`'s: each preset is a period type someone who knows
the buildings recognises, written with explicit keyword arguments so a default changing
under it cannot change its character, pinned by :mod:`tests.test_gopuram_presets`, and
sized for a desktop printer bed.  Gopurams are tall before they are wide, so the sizes
run to height: the Rayagopuram preset is the bed-height case the way the kalyana
mandapa is the bed-area one.
"""

from __future__ import annotations

from .params import GopuramParams

PRESETS: dict[str, GopuramParams] = {
    "Default (five-tala gateway)": GopuramParams(),
    # Early Chola: the modest two-storey gateway of the enclosure wall — three talas,
    # single salas, no panjaras, the whole thing stone-coloured restraint.
    "Early Chola gateway": GopuramParams(
        base_width=80.0, base_depth=56.0, plinth_height=10.0, plinth_style="padabandha",
        plinth_galapadas=True, dvara_width=0.12, dvara_height=0.7,
        wall_height=24.0, wall_storeys=2, pilasters=True, niches=True,
        kapota_height=3.0, kapota_projection=2.4, kudus=True,
        talas=3, tala_ratio=0.82, tala_height=11.0,
        hara=True, salas_per_tala=1, panjaras=False, nasi=False, finial=True, tala_openings=True,
        crown_height=10.0, kalasas=3, mahanasi=True,
    ),
    # Vijayanagara: the rayagopuram — the tall imperial gateway, seven talas on a high
    # two-storey base, panjaras between the salas, the full hara on every terrace.
    "Rayagopuram (Vijayanagara)": GopuramParams(
        base_width=120.0, base_depth=72.0, plinth_height=13.0, plinth_style="kapotabandha",
        plinth_galapadas=True, plinth_padma=True, dvara_width=0.11, dvara_height=0.75,
        wall_height=42.0, wall_storeys=2, pilasters=True, niches=True,
        kapota_height=3.5, kapota_projection=2.8, kudus=True,
        talas=7, tala_ratio=0.87, tala_height=13.0,
        hara=True, salas_per_tala=2, panjaras=True, nasi=False, finial=True, tala_openings=True,
        crown_height=14.0, kalasas=7, mahanasi=True, printer_profile="fdm_0.25",
    ),
    # Madurai: the Nayaka tower — nine talas, the steep sweep, salas everywhere; at this
    # count the finer profile keeps the top storeys' shrines above the nozzle.
    "Madurai Nayaka tower": GopuramParams(
        base_width=110.0, base_depth=64.0, plinth_height=11.0, plinth_style="padabandha",
        plinth_galapadas=True, dvara_width=0.1, dvara_height=0.78,
        wall_height=36.0, wall_storeys=2, pilasters=True, niches=True,
        kapota_height=3.0, kapota_projection=2.4, kudus=True,
        talas=9, tala_ratio=0.88, tala_height=12.0,
        hara=True, salas_per_tala=2, panjaras=False, nasi=False, finial=True, tala_openings=True,
        crown_height=13.0, kalasas=9, mahanasi=True, printer_profile="fdm_0.25",
    ),
    # Sixty millimetres wide on a 0.4 mm nozzle: what would blur is off, the rest obeys
    # the 45° rule; three talas so each storey still reads at desk scale.
    "Desk gopuram": GopuramParams(
        base_width=60.0, base_depth=42.0, plinth_height=8.0, plinth_style="padabandha",
        plinth_galapadas=False, plinth_padma=False, dvara_width=0.12, dvara_height=0.7,
        wall_height=20.0, wall_storeys=1, pilasters=True, niches=False,
        kapota_height=2.5, kapota_projection=2.0, kudus=False,
        talas=3, tala_ratio=0.8, tala_height=9.0,
        hara=True, salas_per_tala=1, panjaras=False, nasi=False, finial=False, tala_openings=True,
        crown_height=8.0, kalasas=3, mahanasi=True,
        printer_profile="fdm_0.4", printable_overhangs=True,
    ),
}
