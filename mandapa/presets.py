"""Named starting points.  ``PRESETS`` maps a display name to a full parameter set.

Each preset is a regional type rather than a random sample of the parameter space:
the point of a preset is that someone who knows the buildings recognises it, and
someone who does not learns which knobs make a Pallava pavilion differ from a
Vijayanagara hall.  They are written as ``MandapaParams(...)`` with explicit keyword
arguments so that a default changing under them (the defaults are tuned separately)
cannot silently change a preset's character; :mod:`tests.test_presets` pins the
distinguishing choices of each one, and that every one unions watertight in under
three seconds.

Sizes stay between 60 and 150 mm: small enough for a desktop printer bed, large
enough that the ornament the preset is showing off is bigger than the nozzle.
"""

from __future__ import annotations

from .params import MandapaParams

PRESETS: dict[str, MandapaParams] = {
    "Default (Chola 16-pillar)": MandapaParams(),
    # Pallava: four plain pillars under a tiered dravida roof, the Shore Temple's little
    # pavilions and the Mahabalipuram rathas.  Octagonal shafts, curved taranga corbels,
    # no medallions (a Chola habit), nasi dormers on the crowning tiers' kudus.
    "Mahabalipuram shore pavilion": MandapaParams(
        footprint_x=70.0, footprint_y=70.0, pillars_x=2, pillars_y=2, pillar_inset=1.1,
        plinth_height=10.0, plinth_style="pratibandha", plinth_galapadas=True, plinth_padma=False,
        pillar_width=6.0, pillar_height=32.0, shaft_style="octagonal", capital_ratio=0.26,
        corbel_style="taranga", corbel_reach=1.3, medallions=False, kattu_bands=False,
        frieze_height=2.5, bhuta_frieze=False, dentils=False, kapota_height=4.0, kapota_projection=4.0,
        kudus=True, roof_style="stepped", tiers=3, tier_ratio=0.76, parapet_height=7.0,
        sikhara_shape="octagonal", nasi=True, finial=True,
        steps=True, steps_sides="front", step_count=4, balustrades=True, hastihasta=True,
    ),
    # Chola: the sixteen-pillar hall with the full hara parapet — corner kutas, salas,
    # panjaras between — over a bhuta-gana frieze, on a padabandha base with galapadas.
    "Chola sixteen-pillar hall": MandapaParams(
        footprint_x=110.0, footprint_y=110.0, pillars_x=4, pillars_y=4,
        plinth_height=13.0, plinth_style="padabandha", plinth_galapadas=True,
        pillar_width=6.0, pillar_height=36.0, shaft_style="chola", corbel_style="taranga",
        medallions=True, kattu_bands=True, frieze_height=3.0, bhuta_frieze=True, dentils=False,
        kudus=True, roof_style="hara", salas_per_side=1, panjaras=True, nasi=True, parapet_height=8.5,
        steps=True, steps_sides="front", hastihasta=True, printer_profile="fdm_0.25",
    ),
    # Vijayanagara: the big kalyana mandapa — fluted shafts, pushpa-potika corbels,
    # kakshasana seats round three sides, dentils and a bhuta row under the cornice,
    # a pedestal in the middle for the image.
    "Vijayanagara kalyana mandapa": MandapaParams(
        footprint_x=150.0, footprint_y=130.0, pillars_x=5, pillars_y=4, pillar_inset=1.1,
        plinth_height=15.0, plinth_style="kapotabandha", plinth_galapadas=True, plinth_padma=True,
        pillar_width=7.0, pillar_height=45.0, shaft_style="fluted", capital_ratio=0.24,
        corbel_style="pushpa", corbel_reach=1.4, corbel_height=0.8, medallions=True, kattu_bands=True,
        beam_height=4.0, frieze_height=4.0, bhuta_frieze=True, dentils=True,
        kapota_height=5.0, kapota_projection=5.0, kudus=True,
        roof_style="hara", salas_per_side=2, panjaras=True, nasi=True, parapet_height=9.0,
        steps=True, steps_sides="front", step_count=5, steps_width=0.3, hastihasta=True,
        kakshasana="back+sides", centre_feature="pedestal", printer_profile="fdm_0.25",
    ),
    # Kerala: a hipped sloping roof with deep eaves over square timber-style pillars;
    # the stone vocabulary of the cornice steps back to a thin band under the eaves.
    "Kerala sloping roof": MandapaParams(
        footprint_x=100.0, footprint_y=80.0, pillars_x=3, pillars_y=3,
        plinth_height=10.0, plinth_style="padabandha", plinth_galapadas=False,
        pillar_width=6.0, pillar_height=34.0, shaft_style="square", capital_ratio=0.2,
        corbel_style="bevel", corbel_reach=1.1, medallions=True, kattu_bands=False,
        beam_height=3.0, frieze_height=1.5, kapota_height=2.0, kapota_projection=2.0, kudus=False,
        roof_slab=2.5, roof_style="kerala", roof_pitch=35.0, eave_overhang=8.0, parapet_height=8.0, finial=True,
        steps=True, steps_sides="front", step_count=4, hastihasta=True,
    ),
    # A screened pavilion: jali lattices round the back and sides over seat-backs,
    # the front left open to the steps.  Resin profile so the bars stay delicate.
    "Jali pavilion": MandapaParams(
        footprint_x=100.0, footprint_y=64.0, pillars_x=4, pillars_y=2,
        plinth_height=11.0, plinth_style="padabandha", plinth_galapadas=True,
        pillar_width=5.5, pillar_height=34.0, shaft_style="octagonal", corbel_style="taranga",
        medallions=True, kattu_bands=True, frieze_height=2.5, dentils=True,
        kudus=True, roof_style="hara", salas_per_side=1, nasi=True, parapet_height=7.0,
        steps=True, steps_sides="front", steps_width=0.3, hastihasta=True,
        jali="back+sides", kakshasana="sides", printer_profile="resin",
    ),
    # Sixty millimetres on a 0.4 mm nozzle: everything that would blur is off, what is
    # left is sized to the nozzle, and every underside obeys the 45° rule.
    "Desk mandapa": MandapaParams(
        footprint_x=60.0, footprint_y=60.0, pillars_x=3, pillars_y=3, pillar_inset=0.9,
        plinth_height=8.0, plinth_style="padabandha", plinth_galapadas=False, plinth_padma=False,
        pillar_width=5.0, pillar_height=24.0, shaft_style="chola", corbel_style="bevel", corbel_reach=1.1,
        medallions=False, kattu_bands=False, beam_height=3.0, frieze_height=2.0, bhuta_frieze=False,
        dentils=False, kapota_height=3.0, kapota_projection=2.5, kudus=False, roof_slab=2.5,
        roof_style="stepped", tiers=2, tier_ratio=0.75, parapet_height=6.0, sikhara_shape="octagonal",
        steps=True, steps_sides="front", step_count=3, balustrades=True, hastihasta=False,
        printer_profile="fdm_0.4", printable_overhangs=True,
    ),
}
