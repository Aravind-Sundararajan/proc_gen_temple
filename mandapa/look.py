"""The authored look of the preview: one key light, the fill it stands in, the palette.

Why the record lives here and not in ``mandapa.gui``
----------------------------------------------------
The document format reads and writes a look, and the format has to work on a machine
with no OpenGL and no Qt: the CLI, the tests, a script converting files.  So the record
sits beside :mod:`mandapa.params`, imports nothing beyond the standard library, and
``tests/test_dependency_rule.py`` parses the package's imports to hold that line rather
than trusting this paragraph.  The viewer *consumes* a :class:`Look`; it never owns one.
That is what keeps the record a file round-trips and the record a frame renders the same
object, so they cannot drift: one spelling per value, never two.  The alternative — a
viewer with its own light and palette constants, mirrored into the file by hand — is what
the first viewer had (``SANDSTONE``, a key light baked into the shader), and it is why
nothing about the picture could be saved.

Why the light is in world space
-------------------------------
The key light is stated as an azimuth around +Z from +X and an elevation above the
horizon, in the temple's frame, not the camera's.  The first viewer lit from over the
camera's shoulder; no face ever dropped to black, and no face was ever in shade either,
because orbiting the model orbits the light with it — a kapota never shades the wall it
projects over, so the overhang reads as flat.  A world-space key stays put on the
building while the viewer orbits, the way sunlight does, and "noon" or "dusk" become
something an author can state and a file can keep.  Elevation is bounded to ±90° because
beyond that the same direction is reachable with the azimuth flipped: two spellings of
one light.

What ``validate`` refuses
-------------------------
The house rule every reader follows: refuse what breaks downstream, leave taste to the
author.  Every number finite (a NaN here poisons every pixel), strengths non-negative
(negative light is not a tuning, it is a typo), colours exactly three finite non-negative
components.  No ceilings anywhere: a component above 1 overdrives on purpose.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, fields, replace
from typing import Any

__all__ = ["COLOUR_FIELDS", "STRENGTH_FIELDS", "Colour", "Look"]

Colour = tuple[float, float, float]

COLOUR_FIELDS = (
    "surface_colour",
    "overhang_colour",
    "bridge_colour",
    "background_colour",
    "background_top",
)
"""The fields that are three components; every other field is one number.

The format reader needs this to know how to parse an attribute, and the validator needs
it to know what to check, so it is stated once here and a test pins it against the
dataclass rather than letting a new field quietly land in neither category.
"""

STRENGTH_FIELDS = ("light_strength", "ambient_strength", "rim_strength")
"""Levels that must be non-negative; the angles may take any finite value."""


@dataclass(frozen=True)
class Look:
    """Every default is the frame the screenshots in ``docs/`` were made with.

    Frozen, like :class:`~mandapa.params.MandapaParams`: the document keeps the look by
    value, compares it to the saved one to know when it is dirty, and snapshots it for
    undo, all of which need a record that nothing can change behind its back.
    """

    light_azimuth: float = -40.0
    light_elevation: float = 50.0
    light_strength: float = 1.0
    ambient_strength: float = 0.35
    rim_strength: float = 0.25
    surface_colour: Colour = (0.84, 0.72, 0.54)
    overhang_colour: Colour = (0.92, 0.25, 0.20)
    bridge_colour: Colour = (0.95, 0.60, 0.15)
    background_colour: Colour = (0.13, 0.145, 0.165)
    background_top: Colour = (0.19, 0.21, 0.25)

    def direction(self) -> tuple[float, float, float]:
        """Unit vector *towards* the light, world space, Z up.

        Azimuth 0 and elevation 0 is +X; azimuth 90 is +Y; elevation 90 is straight up.
        """
        az, el = math.radians(self.light_azimuth), math.radians(self.light_elevation)
        return (math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), math.sin(el))

    def validate(self) -> Look:
        """Refuse what breaks downstream; leave taste to the author.

        Raises ``ValueError`` for every malformed value, whatever Python type it arrived
        as, so callers with their own error vocabulary (the format reader) wrap one
        exception type.  Returns the record so a read can validate in one breath.
        """
        for name in ("light_azimuth", "light_elevation", *STRENGTH_FIELDS):
            value = _number(name, getattr(self, name))
            if not math.isfinite(value):
                raise ValueError(f"{name} must be finite, got {value!r}")
        if not -90.0 <= self.light_elevation <= 90.0:
            raise ValueError(f"light_elevation must be within -90..90, got {self.light_elevation}")
        for name in STRENGTH_FIELDS:
            if getattr(self, name) < 0.0:
                raise ValueError(f"{name} must be non-negative, got {getattr(self, name)}")
        for name in COLOUR_FIELDS:
            value = getattr(self, name)
            try:
                components = tuple(float(c) for c in value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be three numbers, got {value!r}") from exc
            if len(components) != 3 or any(not math.isfinite(c) or c < 0.0 for c in components):
                raise ValueError(
                    f"{name} must be three finite non-negative components, got {value!r}"
                )
        return self

    def with_(self, **changes: Any) -> Look:
        """A copy with ``changes`` applied; the original is untouched (it is frozen)."""
        return replace(self, **changes)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Look:
        """Build from a dict: unknown keys are ignored, absent keys keep their defaults.

        Validates, so the only way out is a record the viewer can draw or a
        ``ValueError`` naming the field — including for a colour that is not a sequence
        of three, which would otherwise surface as a ``TypeError`` from deep inside.
        """
        kwargs: dict[str, Any] = {}
        for f in fields(cls):
            if f.name not in data:
                continue
            value = data[f.name]
            try:
                if f.name in COLOUR_FIELDS:
                    kwargs[f.name] = tuple(float(c) for c in value)
                else:
                    kwargs[f.name] = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{f.name}: not a usable value: {value!r}") from exc
        return cls(**kwargs).validate()


def _number(name: str, value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a number, got {value!r}") from exc
