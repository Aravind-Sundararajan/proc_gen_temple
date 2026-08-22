"""The ``<temple>`` format: what round-trips, what is refused, what is ignored.

The decisions live here, not in prose.  Each test names a rule from the module
docstring of :mod:`mandapa.io.temple_xml`; if a rule changes, its test changes with it.
"""

import json
import math
import random
import xml.etree.ElementTree as ET
from dataclasses import fields
from pathlib import Path
from typing import get_type_hints

import pytest

from mandapa.io import (
    CAMERA_KEYS,
    FORMAT_VERSION,
    TempleFile,
    TempleFormatError,
    load_any,
    load_temple,
    save_temple,
)
from mandapa.look import COLOUR_FIELDS, Look
from mandapa.params import MandapaParams

DATA = Path(__file__).parent / "data"
CAMERA = {"azimuth": -30.0, "elevation": 20.0, "distance": 250.0, "cx": 1.0, "cy": 2.0, "cz": 3.0}


def every_field_changed() -> MandapaParams:
    """A parameter set with no field at its default, typed by declaration."""
    hints = get_type_hints(MandapaParams)
    changes = {}
    for f in fields(MandapaParams):
        default, kind, choices = f.default, hints[f.name], f.metadata.get("choices")
        if kind is bool:
            changes[f.name] = not default
        elif kind is int:
            changes[f.name] = default + 1
        elif kind is float:
            changes[f.name] = default + 0.1 + 1e-9  # a value with a long repr
        else:
            changes[f.name] = next(c for c in choices if c != default)
    return MandapaParams(**changes)


def write(tmp_path: Path, text: str, name: str = "doc.xml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def doc(body: str, version: object = FORMAT_VERSION, name: str = "") -> str:
    attrs = f'version="{version}"' if version is not None else ""
    if name:
        attrs += f' name="{name}"'
    return f"<temple {attrs}>{body}</temple>"


# ---- round trips ------------------------------------------------------------------------


def test_every_field_round_trips_exactly(tmp_path):
    params = every_field_changed()
    look = Look(light_azimuth=12.5, surface_colour=(0.5, 0.4, 0.3))
    path = tmp_path / "design.xml"
    save_temple(path, params, look, CAMERA, name="test")
    file = load_temple(path)
    assert file.params == params
    assert file.look == look
    assert file.camera == CAMERA
    assert file.name == "test"
    assert file.ignored == ()


def test_floats_survive_at_full_precision(tmp_path):
    value = 0.1 + 0.2  # 0.30000000000000004, the classic
    path = tmp_path / "p.xml"
    save_temple(path, MandapaParams(footprint_x=value), Look(light_azimuth=value))
    text = path.read_text(encoding="utf-8")
    assert 'value="0.30000000000000004"' in text
    assert 'light_azimuth="0.30000000000000004"' in text
    file = load_temple(path)
    assert file.params.footprint_x == value and file.look.light_azimuth == value


def written_values(path: Path) -> dict[str, str]:
    return {el.get("name"): el.get("value") for el in ET.parse(path).getroot().iterfind("./params/param")}


def test_an_int_given_to_a_float_field_is_written_as_a_float(tmp_path):
    path = tmp_path / "p.xml"
    save_temple(path, MandapaParams(footprint_x=100))
    assert written_values(path)["footprint_x"] == "100.0"
    assert load_temple(path).params.footprint_x == 100.0


def test_bools_are_written_as_true_and_false(tmp_path):
    path = tmp_path / "p.xml"
    save_temple(path, MandapaParams(steps=False, kudus=True))
    values = written_values(path)
    assert values["steps"] == "false" and values["kudus"] == "true"


def test_the_writer_states_every_field_once_in_declaration_order(tmp_path):
    """The file reads like the panel, and nothing derived is in it."""
    path = tmp_path / "p.xml"
    save_temple(path, MandapaParams())
    names = [el.get("name") for el in ET.parse(path).getroot().iterfind("./params/param")]
    assert names == [f.name for f in fields(MandapaParams)]
    assert "min_feature" not in names


def test_the_version_is_stamped_on_the_root(tmp_path):
    path = tmp_path / "p.xml"
    save_temple(path, MandapaParams())
    assert ET.parse(path).getroot().get("version") == str(FORMAT_VERSION)


def test_the_name_is_written_only_when_given(tmp_path):
    path = tmp_path / "p.xml"
    save_temple(path, MandapaParams())
    assert "name" not in ET.parse(path).getroot().attrib
    assert load_temple(path).name == ""


# ---- identity and additivity -----------------------------------------------------------


def test_param_identity_is_the_name_not_the_position(tmp_path):
    params = every_field_changed()
    path = tmp_path / "p.xml"
    save_temple(path, params)
    root = ET.parse(path).getroot()
    section = root.find("params")
    records = list(section)
    random.Random(1).shuffle(records)
    for el in list(section):
        section.remove(el)
    section.extend(records)
    shuffled = tmp_path / "shuffled.xml"
    ET.ElementTree(root).write(shuffled)
    assert load_temple(shuffled).params == params


def test_unknown_params_are_ignored_and_reported(tmp_path):
    path = write(
        tmp_path,
        doc(
            '<params><param name="pillars_x" value="3"/>'
            '<param name="from_the_future" value="1"/>'
            '<param name="from_the_future" value="2"/></params>'
        ),
    )
    file = load_temple(path)
    assert file.params == MandapaParams(pillars_x=3)
    assert file.ignored == ("from_the_future",)


def test_unknown_attributes_sections_and_children_are_ignored(tmp_path):
    path = write(
        tmp_path,
        doc(
            '<params><param name="tiers" value="2"/><note>free text</note></params>'
            '<annotations><a/></annotations>',
            name="x",
        ).replace("<temple ", '<temple flavour="spicy" '),
    )
    assert load_temple(path).params == MandapaParams(tiers=2)


def test_absent_sections_mean_defaults(tmp_path):
    path = write(tmp_path, doc('<params><param name="steps" value="false"/></params>'))
    file = load_temple(path)
    assert file.params == MandapaParams(steps=False)
    assert file.look == Look() and file.camera is None and file.name == ""


def test_an_empty_params_section_is_the_default_temple(tmp_path):
    assert load_temple(write(tmp_path, doc("<params/>"))).params == MandapaParams()


def test_a_missing_field_takes_its_default_not_the_writers_value(tmp_path):
    """How a field can be added without a version bump."""
    path = write(tmp_path, doc('<params><param name="pillars_y" value="2"/></params>'))
    assert load_temple(path).params.pillars_x == MandapaParams().pillars_x


def test_out_of_range_values_read_verbatim(tmp_path):
    """The slider range is the editor's; the builder clamps, the reader does not alter."""
    path = write(tmp_path, doc('<params><param name="pillars_x" value="50"/></params>'))
    assert load_temple(path).params.pillars_x == 50


# ---- refusals -------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text, reason",
    [
        ('<temple version="99"><params/></temple>', "version '99'"),
        ('<temple version=""><params/></temple>', "version ''"),
        ("<temple><params/></temple>", "no version"),
        ('<body version="1"/>', "<body>"),
        ('<temple version="1"/>', "no <params>"),
        ('<temple version="1"><params/><params/></temple>', "<params> is stated 2 times"),
        ('<temple version="1"><params/><look/><look/></temple>', "<look> is stated 2 times"),
        ('<temple version="1"><params/><camera/><camera/></temple>', "<camera> is stated"),
        ("<temple version='1'><params><param name='pillars_x' value='lots'/></params></temple>", "pillars_x"),
        ("<temple version='1'><params><param name='pillars_x' value='3.0'/></params></temple>", "integer"),
        ("<temple version='1'><params><param name='footprint_x' value='wide'/></params></temple>", "number"),
        ("<temple version='1'><params><param name='footprint_x' value='nan'/></params></temple>", "finite"),
        ("<temple version='1'><params><param name='footprint_x' value='inf'/></params></temple>", "finite"),
        ("<temple version='1'><params><param name='steps' value='1'/></params></temple>", "true or false"),
        ("<temple version='1'><params><param name='steps' value='yes'/></params></temple>", "true or false"),
        ("<temple version='1'><params><param name='roof_style' value='dome'/></params></temple>", "one of"),
        ("<temple version='1'><params><param name='pillars_x'/></params></temple>", "name and a value"),
        ("<temple version='1'><params><param value='3'/></params></temple>", "name and a value"),
        (
            (
                "<temple version='1'><params><param name='tiers' value='3'/>"
                "<param name='tiers' value='4'/></params></temple>"
            ),
            "stated twice",
        ),
        ("<temple version='1'><params></temple>", "well-formed"),
        ("not xml at all", "well-formed"),
        ("<temple version='1'><params/><look light_strength='-1'/></temple>", "look"),
        ("<temple version='1'><params/><look light_elevation='100'/></temple>", "look"),
        ("<temple version='1'><params/><look light_azimuth='nan'/></temple>", "finite"),
        ("<temple version='1'><params/><look light_azimuth='east'/></temple>", "number"),
        ("<temple version='1'><params/><look surface_colour='0.5 0.5'/></temple>", "three numbers"),
        ("<temple version='1'><params/><look surface_colour='0.5 0.5 -0.5'/></temple>", "look"),
        ("<temple version='1'><params/><look ambient_strength='0.1 0.2 0.3'/></temple>", "number"),
        ("<temple version='1'><params/><camera azimuth='1' elevation='2'/></temple>", "missing distance"),
        (
            (
                "<temple version='1'><params/><camera azimuth='1' elevation='2' distance='3' "
                "cx='0' cy='0' cz='nan'/></temple>"
            ),
            "finite",
        ),
    ],
)
def test_refuses_what_it_does_not_understand_naming_the_path(tmp_path, text, reason):
    path = write(tmp_path, text)
    with pytest.raises(TempleFormatError) as info:
        load_temple(path)
    assert str(path) in str(info.value)
    assert reason in str(info.value)


def test_the_format_error_is_a_value_error():
    assert issubclass(TempleFormatError, ValueError)


def test_bool_spellings_are_case_insensitive(tmp_path):
    path = write(
        tmp_path,
        doc('<params><param name="steps" value="False"/><param name="kudus" value="TRUE"/></params>'),
    )
    file = load_temple(path)
    assert file.params.steps is False and file.params.kudus is True


def test_a_missing_file_is_not_a_format_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_temple(tmp_path / "nope.xml")


# ---- the writer refuses what the reader refuses ----------------------------------------


@pytest.mark.parametrize(
    "params",
    [
        MandapaParams(roof_style="dome"),
        MandapaParams(pillars_x=3.5),
        MandapaParams(footprint_x=math.nan),
        MandapaParams(footprint_x=math.inf),
    ],
)
def test_the_writer_refuses_a_file_its_reader_would(tmp_path, params):
    path = tmp_path / "p.xml"
    with pytest.raises(ValueError):
        save_temple(path, params)
    assert not path.exists()


def test_the_writer_refuses_a_half_stated_camera(tmp_path):
    with pytest.raises(ValueError, match="missing cx, cy, cz"):
        save_temple(tmp_path / "p.xml", MandapaParams(), camera={"azimuth": 1, "elevation": 2, "distance": 3})


def test_the_writer_refuses_an_invalid_look(tmp_path):
    with pytest.raises(ValueError):
        save_temple(tmp_path / "p.xml", MandapaParams(), Look(light_strength=-1.0))


# ---- <look> -----------------------------------------------------------------------------


def test_the_look_is_written_in_full_even_at_the_defaults(tmp_path):
    """So the picture the author saw cannot depend on which build's defaults open it."""
    path = tmp_path / "p.xml"
    save_temple(path, MandapaParams(), Look())
    look_el = ET.parse(path).getroot().find("look")
    assert look_el is not None
    assert list(look_el.attrib) == [f.name for f in fields(Look)]
    assert look_el.get("surface_colour") == "0.84 0.72 0.54"
    assert look_el.get("light_azimuth") == "-40.0"


def test_no_look_given_writes_no_look_section(tmp_path):
    path = tmp_path / "p.xml"
    save_temple(path, MandapaParams())
    assert ET.parse(path).getroot().find("look") is None
    assert load_temple(path).look == Look()


def test_a_partial_look_reads_as_the_defaults_for_the_rest(tmp_path):
    path = write(tmp_path, doc('<params/><look light_elevation="10" rim_strength="0"/>'))
    assert load_temple(path).look == Look(light_elevation=10.0, rim_strength=0.0)


def test_an_empty_look_section_means_the_defaults(tmp_path):
    assert load_temple(write(tmp_path, doc("<params/><look/>"))).look == Look()


def test_unknown_look_attributes_are_ignored(tmp_path):
    path = write(tmp_path, doc('<params/><look glow="0.5" light_strength="2"/>'))
    assert load_temple(path).look == Look(light_strength=2.0)


def test_colour_fields_are_three_numbers_separated_by_whitespace(tmp_path):
    path = write(tmp_path, doc('<params/><look background_top="1\t0.5\n 0"/>'))
    assert load_temple(path).look.background_top == (1.0, 0.5, 0.0)


def test_colour_fields_are_exactly_the_three_component_fields():
    """Pins COLOUR_FIELDS against the dataclass: a new tuple field must be listed."""
    for f in fields(Look):
        is_tuple = isinstance(f.default, tuple)
        assert (f.name in COLOUR_FIELDS) == is_tuple, f.name


# ---- <camera> ---------------------------------------------------------------------------


def test_camera_keys_are_the_six_the_viewer_needs():
    assert CAMERA_KEYS == ("azimuth", "elevation", "distance", "cx", "cy", "cz")


def test_the_camera_is_written_in_full_at_full_precision(tmp_path):
    path = tmp_path / "p.xml"
    camera = dict(CAMERA, distance=0.1 + 0.2)
    save_temple(path, MandapaParams(), camera=camera)
    el = ET.parse(path).getroot().find("camera")
    assert list(el.attrib) == list(CAMERA_KEYS)
    assert el.get("distance") == "0.30000000000000004"
    assert load_temple(path).camera == camera


def test_an_empty_camera_dict_is_no_camera(tmp_path):
    path = tmp_path / "p.xml"
    save_temple(path, MandapaParams(), camera={})
    assert ET.parse(path).getroot().find("camera") is None


def test_extra_camera_attributes_are_ignored(tmp_path):
    attrs = " ".join(f'{k}="{v}"' for k, v in CAMERA.items())
    path = write(tmp_path, doc(f'<params/><camera {attrs} lens="50"/>'))
    assert load_temple(path).camera == CAMERA


# ---- the hand-written fixture -----------------------------------------------------------


def test_the_hand_written_fixture_reads_exactly():
    """A document the writer would never produce; see the comment in the file."""
    file = load_temple(DATA / "hand_written_v1.xml")
    assert file.params == MandapaParams(
        steps=False,
        pillars_x=3,
        footprint_x=123.45678901234567,
        roof_style="stepped",
        tiers=5,
        kudus=True,
        scale=0.1,
        pillar_height=40.0,
    )
    assert file.look == Look(
        light_elevation=35.5, surface_colour=(0.5, 0.4, 0.30000000000000004), light_azimuth=100.0
    )
    assert file.camera == {
        "azimuth": -55.0, "elevation": 22.0, "distance": 320.0, "cx": 0.0, "cy": 0.0, "cz": 30.0
    }
    assert file.name == "Hand-written fixture"
    assert file.ignored == ("not_yet_a_param",)


def test_the_fixture_survives_a_save_and_reload(tmp_path):
    file = load_temple(DATA / "hand_written_v1.xml")
    path = tmp_path / "again.xml"
    save_temple(path, file.params, file.look, file.camera, file.name)
    again = load_temple(path)
    assert (again.params, again.look, again.camera, again.name) == (
        file.params, file.look, file.camera, file.name
    )
    assert again.ignored == ()


# ---- load_any and the legacy JSON -------------------------------------------------------


def test_load_any_reads_xml(tmp_path):
    path = tmp_path / "p.xml"
    save_temple(path, MandapaParams(tiers=2), Look(rim_strength=0.0), CAMERA, "t")
    assert load_any(path) == load_temple(path)


def test_load_any_reads_the_legacy_json_fixture():
    file = load_any(DATA / "legacy_params.json")
    assert file == TempleFile(
        params=MandapaParams(pillars_x=3, pillars_y=2, footprint_x=90.5, roof_style="flat", steps=False),
        look=Look(),
        camera=None,
        name="",
        ignored=("bogus",),
    )


def test_load_any_reads_what_mandapa_params_save_writes(tmp_path):
    params = MandapaParams().randomized(5)
    path = tmp_path / "design.JSON"  # suffix case does not matter
    params.save(path)
    assert load_any(path).params == params


@pytest.mark.parametrize(
    "name, text, reason",
    [
        ("design.txt", "", ".xml"),
        ("design.json", "[1, 2]", "JSON object"),
        ("design.json", "{not json", "not a parameters JSON"),
        ("design.json", '<temple version="1"/>', "not a parameters JSON"),
    ],
)
def test_load_any_refuses_by_name(tmp_path, name, text, reason):
    path = write(tmp_path, text, name)
    with pytest.raises(TempleFormatError) as info:
        load_any(path)
    assert str(path) in str(info.value) and reason in str(info.value)


def test_the_legacy_reader_is_the_one_that_defined_the_format(tmp_path):
    """``MandapaParams.from_dict`` leniency, unchanged: a bad value keeps its default."""
    path = write(tmp_path, json.dumps({"pillars_x": "lots", "tiers": "2"}), "p.json")
    params = load_any(path).params
    assert params.pillars_x == MandapaParams().pillars_x and params.tiers == 2
