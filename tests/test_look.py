"""The look record: what it refuses, where the light points, how it round-trips."""

import math
from dataclasses import FrozenInstanceError, fields

import pytest

from mandapa.look import COLOUR_FIELDS, STRENGTH_FIELDS, Look

SQRT_HALF = math.sqrt(0.5)


def test_the_defaults_validate():
    assert Look().validate() == Look()


# ---- direction ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "azimuth, elevation, expected",
    [
        (0.0, 0.0, (1.0, 0.0, 0.0)),
        (90.0, 0.0, (0.0, 1.0, 0.0)),
        (-90.0, 0.0, (0.0, -1.0, 0.0)),
        (180.0, 0.0, (-1.0, 0.0, 0.0)),
        (0.0, 90.0, (0.0, 0.0, 1.0)),
        (0.0, -90.0, (0.0, 0.0, -1.0)),
        (45.0, 0.0, (SQRT_HALF, SQRT_HALF, 0.0)),
        (0.0, 45.0, (SQRT_HALF, 0.0, SQRT_HALF)),
        (360.0, 0.0, (1.0, 0.0, 0.0)),
    ],
)
def test_direction_is_world_space_z_up(azimuth, elevation, expected):
    got = Look(light_azimuth=azimuth, light_elevation=elevation).direction()
    assert got == pytest.approx(expected, abs=1e-12)


@pytest.mark.parametrize("azimuth, elevation", [(-40.0, 50.0), (200.0, 14.0), (-120.0, 22.0)])
def test_direction_is_a_unit_vector(azimuth, elevation):
    x, y, z = Look(light_azimuth=azimuth, light_elevation=elevation).direction()
    assert math.hypot(x, y, z) == pytest.approx(1.0)
    assert z > 0  # above the horizon


# ---- validate -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "changes, reason",
    [
        ({"light_azimuth": math.nan}, "finite"),
        ({"light_elevation": math.inf}, "finite"),
        ({"light_elevation": 90.5}, "-90..90"),
        ({"light_elevation": -91.0}, "-90..90"),
        ({"light_strength": -0.1}, "non-negative"),
        ({"ambient_strength": -1.0}, "non-negative"),
        ({"rim_strength": math.nan}, "finite"),
        ({"surface_colour": (0.5, 0.5)}, "three"),
        ({"surface_colour": (0.5, 0.5, 0.5, 1.0)}, "three"),
        ({"overhang_colour": (0.5, -0.1, 0.5)}, "non-negative"),
        ({"bridge_colour": (0.5, math.nan, 0.5)}, "finite"),
        ({"background_colour": 0.5}, "three numbers"),
        ({"background_top": ("r", "g", "b")}, "three numbers"),
        ({"light_strength": "bright"}, "number"),
    ],
)
def test_validate_refuses_what_breaks_downstream(changes, reason):
    with pytest.raises(ValueError, match=reason):
        Look(**changes).validate()


@pytest.mark.parametrize(
    "changes",
    [
        {"light_azimuth": 720.0},
        {"light_azimuth": -1e6},
        {"light_elevation": 90.0},
        {"light_elevation": -90.0},
        {"light_strength": 0.0, "ambient_strength": 0.0, "rim_strength": 0.0},
        {"light_strength": 50.0},
        {"surface_colour": (1.5, 2.0, 0.0)},
        {"surface_colour": [0.1, 0.2, 0.3]},
    ],
)
def test_validate_leaves_taste_to_the_author(changes):
    """Any finite azimuth, any strength, any colour component: no ceilings."""
    look = Look(**changes)
    assert look.validate() is look


def test_the_field_lists_cover_the_dataclass():
    """Every field is a colour or a number; strengths are the non-negative numbers."""
    names = {f.name for f in fields(Look)}
    assert set(COLOUR_FIELDS) <= names and set(STRENGTH_FIELDS) <= names
    assert names - set(COLOUR_FIELDS) - set(STRENGTH_FIELDS) == {"light_azimuth", "light_elevation"}


# ---- value semantics ------------------------------------------------------------------------


def test_with_returns_a_new_record_and_leaves_the_original():
    original = Look()
    changed = original.with_(light_azimuth=1.0)
    assert changed.light_azimuth == 1.0 and original.light_azimuth == -40.0
    assert changed != original


def test_the_record_is_frozen_and_hashable():
    look = Look()
    with pytest.raises(FrozenInstanceError):
        look.light_azimuth = 1.0  # type: ignore[misc]
    assert hash(look) == hash(Look())
    assert {look: 1}[Look()] == 1


# ---- dict round trip -------------------------------------------------------------------------


def test_dict_round_trip():
    look = Look(light_azimuth=12.5, surface_colour=(0.5, 0.4, 0.3), rim_strength=0.0)
    data = look.to_dict()
    assert data["surface_colour"] == (0.5, 0.4, 0.3)
    assert Look.from_dict(data) == look


def test_from_dict_ignores_unknown_keys_and_keeps_defaults_for_absent_ones():
    look = Look.from_dict({"light_elevation": 10, "glow": 1.0})
    assert look == Look(light_elevation=10.0)


def test_from_dict_coerces_to_floats_and_tuples():
    look = Look.from_dict({"light_strength": "2", "surface_colour": ["1", 0, 0.5]})
    assert look.light_strength == 2.0 and isinstance(look.light_strength, float)
    assert look.surface_colour == (1.0, 0.0, 0.5) and isinstance(look.surface_colour, tuple)


@pytest.mark.parametrize(
    "data",
    [
        {"light_strength": -1.0},
        {"light_strength": "bright"},
        {"surface_colour": 0.5},
        {"surface_colour": [0.5, 0.5]},
        {"surface_colour": None},
        {"light_elevation": 100.0},
    ],
)
def test_from_dict_raises_value_error_for_anything_malformed(data):
    with pytest.raises(ValueError):
        Look.from_dict(data)
