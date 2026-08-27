"""The on-disk design format: ``<temple version="1">``, flat records, explicitly versioned.

Layout::

    <?xml version='1.0' encoding='utf-8'?>
    <temple version="1" name="Chola hall at noon">
      <params>
        <param name="footprint_x" value="110.0"/>
        <param name="pillars_x" value="4"/>
        <param name="kudus" value="true"/>
        <param name="roof_style" value="hara"/>
        ...one record per field, in declaration order...
      </params>
      <look light_azimuth="-35.0" light_elevation="68.0" ... background_top="0.26 0.24 0.22"/>
      <camera azimuth="-55.0" elevation="22.0" distance="330.0" cx="0.0" cy="0.0" cz="30.0"/>
    </temple>

Why the version stamp
---------------------
A reader that does not recognise the version refuses the document instead of quietly
misinterpreting it.  There is exactly one version today, so the stamp buys nothing yet —
which is the point: it has to be there *before* the first semantic change, because a
change made without one leaves no byte in the file to tell the eras apart, and from then
on only a heuristic can.  Any future change to what an attribute *means* bumps the
version rather than reusing the name; adding a section or an attribute whose absence
keeps the old meaning does not (see ``<look>`` and ``<camera>`` below).  The JSON files
:meth:`~mandapa.params.MandapaParams.save` wrote before this format are read by
:func:`load_any` on their own terms and never written again; they carry no stamp, and
they get away with it only because they hold nothing but parameters whose meaning has
not changed.

Why ``<param name= value=>`` records
------------------------------------
Identity is the ``name`` attribute, never the position: a document with its records
shuffled is the same document (a test proves it).  The reader walks the dataclass's
fields, not the file, so a name it does not know is ignored — an older build opens a
newer file and keeps what it understands — and a field the file does not state takes
its default, which is how a field can be added without a version bump.  Ignored names
are reported in :attr:`TempleFile.ignored` rather than swallowed, so a caller can say
so: refusing them would make every newer file unopenable, saying nothing would make
every typo invisible.  Two rejected spellings: forty attributes on one ``<params>``
element, which ``ElementTree`` writes on one line so a diff can only say "the
parameters changed"; and one element per field (``<footprint_x>110</footprint_x>``),
which makes the vocabulary of the format the vocabulary of the dataclass and a schema
impossible to state.  One record per line diffs per parameter.

The writer states every field, always, in declaration order, so the file reads like the
panel and a default that later changes cannot reshape a saved design.  Floats are
written with ``repr``: the shortest string that reads back to the same double, so
``0.1`` stays ``0.1`` and ``0.30000000000000004`` stays itself, where a ``%g``
shortening would move a value a little on every save.

What the reader refuses and what it passes through
--------------------------------------------------
The rule: refuse what has no meaning to this build, pass through what has one even when
the builder cannot fully honour it, never alter silently.

* Refused, naming the path: a root that is not ``<temple>``; a missing or unknown
  version; no ``<params>`` section (an explicit empty ``<params/>`` is the default
  temple, but a misspelt section name must not open as one); a parameter or a section
  stated twice (two statements of one value is a contradiction, and picking one is
  guessing); a value that is not a number for a number, not integral for an integer,
  not finite, not ``true``/``false`` for a flag, or a word outside a choice's vocabulary
  (``roof_style="dome"`` is a temple this build cannot make, and building ``hara`` in
  its place would report a different design as the file's).
* Passed through: a number outside the panel's slider range reads verbatim.  The range
  is the editor's; :func:`mandapa.builder.build` clamps at build time and that is the
  one place the limit is enforced.  A reader that clamped too would be a second copy of
  the rule, the copy that turns a 320 mm footprint into 300 on open with nothing in the
  file to show it happened — and the JSON reader never clamped either.
* Ignored: parameter names, attributes, child elements and sections this build does not
  know.  That is what lets the format grow without a version bump.

The writer refuses what its reader would refuse (a non-integral integer, an unknown
choice, a non-finite number, a half-stated camera) so a file this module writes is one
it can read.

``<look>``: always written, in full
-----------------------------------
Every :class:`~mandapa.look.Look` field, in field order, at full precision, whenever a
look is given — even when it equals the defaults.  The alternative, writing the section
only when the look differs from the defaults, was rejected: "default" would then mean
*the reader's* default, and a design saved under one build's defaults and opened under
another's would render differently with nothing in the file to say which picture the
author saw.  That is the meaning-outside-the-file failure the version stamp exists to
prevent, arriving by another door.  ``save_temple(look=None)`` writes no section, for
a caller with no opinion about the look (a script converting parameters); an absent
section reads as the shipped defaults, which is the truth about every document written
before a look could be stated, and an absent attribute inside a present section reads as
that field's default, because every look default is a plain value.  Neither needed a
version bump.  Validation is the record's own :meth:`~mandapa.look.Look.validate`,
wrapped into this module's error.

``<camera>``: optional, all or nothing
--------------------------------------
A viewer pose — orbit azimuth and elevation in degrees, distance in mm, the point orbited
— not a design: the document never undoes it and never counts it as an edit.  It is the
six numbers or nothing; a half-stated pose is not a pose, so a section missing one is
refused rather than filled in.  Absent means the viewer keeps whatever pose it has.

``name``
--------
An authored title, shown in menus.  Not the file name: that is derived from the path,
and derived data is not persisted, because a copy of it can only ever be stale.

One engine, two formats
-----------------------
The reader and writer take the root tag, the parameter dataclass and the format version
as arguments, defaulting to this module's own ``<temple>``/:class:`MandapaParams`/1, and
:mod:`gopuram.io` calls the same functions with ``<gopuram>`` and its own class.  The
two formats share every rule above but version independently — a semantic change to a
gopuram attribute must not force every mandapa file to a new number — which is why the
version is a parameter rather than the one constant.  The root tag is what keeps the
families apart: a gopuram's parameter names would all be "unknown" to a mandapa reader,
so without the distinct root a gopuram file would open as the default mandapa — the
silent-misreading failure this format exists to refuse.

Deliberately not persisted
--------------------------
``min_feature`` (a function of ``printer_profile``), the layout, the mesh, the undo
history, the window geometry.  Everything in the file is an input.
"""

from __future__ import annotations

import json
import math
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, get_type_hints

from ..look import COLOUR_FIELDS, Look
from ..params import MandapaParams

__all__ = [
    "CAMERA_KEYS",
    "FORMAT_VERSION",
    "TempleFile",
    "TempleFormatError",
    "load_any",
    "load_temple",
    "save_temple",
]

FORMAT_VERSION = 1

CAMERA_KEYS = ("azimuth", "elevation", "distance", "cx", "cy", "cz")
"""A viewer pose: orbit angles in degrees, distance in mm, and the point orbited."""


class TempleFormatError(ValueError):
    """The file is not a temple document this reader understands.  The message names the path."""


@dataclass(frozen=True)
class TempleFile:
    """What a document states, with the defaults filled in for what it does not.

    ``look`` is the shipped defaults for a document without a ``<look>``; ``camera`` is
    ``None`` for one without a ``<camera>``; ``name`` is ``""`` for one with no authored
    title; ``ignored`` lists the parameter names the reader did not recognise.

    ``params`` is an instance of the class the loader was given — :class:`MandapaParams`
    for a ``<temple>``, ``GopuramParams`` for a ``<gopuram>`` — and the annotation states
    the default family rather than a union, because naming the sister class here would
    point the dependency arrow backwards.
    """

    params: MandapaParams
    look: Look = field(default_factory=Look)
    camera: dict[str, float] | None = None
    name: str = ""
    ignored: tuple[str, ...] = ()


# ---- the parameter vocabulary -----------------------------------------------------------


def _param_specs(params_cls: type = MandapaParams) -> dict[str, tuple[type, list[str] | None]]:
    """Field name -> (declared type, choices), resolved from the string annotations."""
    hints = get_type_hints(params_cls)
    return {f.name: (hints[f.name], f.metadata.get("choices")) for f in fields(params_cls)}


def _write_value(name: str, kind: type, choices: list[str] | None, value: Any) -> str:
    """The one spelling of a value; refuses what :func:`_read_value` would refuse."""
    if kind is bool:
        return "true" if value else "false"
    if kind is int:
        if int(value) != value:
            raise ValueError(f"{name} must be an integer, got {value!r}")
        return str(int(value))
    if kind is float:
        return _write_float(name, value)
    text = str(value)
    if choices is not None and text not in choices:
        raise ValueError(f"{name} must be one of {', '.join(choices)}; got {value!r}")
    return text


def _write_float(name: str, value: Any) -> str:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{name} must be finite, got {value!r}")
    return repr(number)


def _read_value(path: Path, name: str, kind: type, choices: list[str] | None, text: str) -> Any:
    if kind is bool:
        lowered = text.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
        raise TempleFormatError(f"{path}: {name} must be true or false, got {text!r}")
    if kind is int:
        try:
            return int(text.strip())
        except ValueError as exc:
            raise TempleFormatError(f"{path}: {name} must be an integer, got {text!r}") from exc
    if kind is float:
        return _read_float(path, name, text)
    if choices is not None and text not in choices:
        raise TempleFormatError(
            f"{path}: {name} must be one of {', '.join(choices)}; got {text!r}"
        )
    return text


def _read_float(path: Path, name: str, text: str) -> float:
    try:
        number = float(text)
    except ValueError as exc:
        raise TempleFormatError(f"{path}: {name} must be a number, got {text!r}") from exc
    if not math.isfinite(number):
        raise TempleFormatError(f"{path}: {name} must be finite, got {text!r}")
    return number


# ---- writing --------------------------------------------------------------------------


def save_temple(
    path: str | Path,
    params: MandapaParams,
    look: Look | None = None,
    camera: dict[str, float] | None = None,
    name: str = "",
    *,
    root_tag: str = "temple",
    version: int = FORMAT_VERSION,
) -> None:
    """Write a version-``version`` document.  Every parameter; the look in full if given;
    the camera in full if given; the title if non-empty.  Raises ``ValueError`` for a
    value the reader would refuse, before anything is written.  The fields written are
    ``type(params)``'s, so the one writer serves the ``<gopuram>`` format too."""
    root = ET.Element(root_tag, {"version": str(version)})
    if name:
        root.set("name", name)

    section = ET.SubElement(root, "params")
    for pname, (kind, choices) in _param_specs(type(params)).items():
        value = _write_value(pname, kind, choices, getattr(params, pname))
        ET.SubElement(section, "param", {"name": pname, "value": value})

    if look is not None:
        look.validate()
        attrs = {}
        for f in fields(Look):
            value = getattr(look, f.name)
            if f.name in COLOUR_FIELDS:
                attrs[f.name] = " ".join(_write_float(f.name, c) for c in value)
            else:
                attrs[f.name] = _write_float(f.name, value)
        ET.SubElement(root, "look", attrs)

    if camera:
        missing = [k for k in CAMERA_KEYS if k not in camera]
        if missing:
            raise ValueError(
                f"camera must state all of {', '.join(CAMERA_KEYS)}; missing {', '.join(missing)}"
            )
        ET.SubElement(root, "camera", {k: _write_float(f"camera {k}", camera[k]) for k in CAMERA_KEYS})

    tree = ET.ElementTree(root)
    ET.indent(tree, space="  ")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tree.write(path, encoding="utf-8", xml_declaration=True)


# ---- reading --------------------------------------------------------------------------


def _single(path: Path, root: ET.Element, tag: str, required: bool = False) -> ET.Element | None:
    found = root.findall(tag)
    if len(found) > 1:
        raise TempleFormatError(f"{path}: <{tag}> is stated {len(found)} times; once is the most")
    if not found:
        if required:
            raise TempleFormatError(f"{path}: no <{tag}> section")
        return None
    return found[0]


def load_temple(
    path: str | Path,
    *,
    root_tag: str = "temple",
    params_cls: type = MandapaParams,
    version: int = FORMAT_VERSION,
) -> TempleFile:
    """Read a ``<temple>`` document — or, given another root tag and parameter class, its
    sister format.  Raises :class:`TempleFormatError` naming the path for anything this
    build cannot read; the module docstring lists what that is."""
    path = Path(path)
    try:
        root = ET.parse(path).getroot()
    except ET.ParseError as exc:
        raise TempleFormatError(f"{path}: not well-formed XML ({exc})") from exc
    if root.tag != root_tag:
        raise TempleFormatError(f"{path}: root element is <{root.tag}>, expected <{root_tag}>")
    stated = root.get("version")
    if stated is None:
        raise TempleFormatError(
            f"{path}: <{root_tag}> has no version attribute (this build writes version {version})"
        )
    if stated.strip() != str(version):
        raise TempleFormatError(
            f"{path}: {root_tag} version {stated!r} is not one this build reads (it reads {version})"
        )

    params_el = _single(path, root, "params", required=True)
    look_el = _single(path, root, "look")
    camera_el = _single(path, root, "camera")

    specs = _param_specs(params_cls)
    data: dict[str, Any] = {}
    ignored: list[str] = []
    for el in params_el.findall("param"):
        pname, text = el.get("name"), el.get("value")
        if pname is None or text is None:
            raise TempleFormatError(f"{path}: every <param> needs a name and a value")
        if pname not in specs:
            if pname not in ignored:
                ignored.append(pname)
            continue
        if pname in data:
            raise TempleFormatError(f"{path}: parameter {pname!r} is stated twice")
        kind, choices = specs[pname]
        data[pname] = _read_value(path, pname, kind, choices, text)
    params = params_cls(**data)

    look = Look()
    if look_el is not None:
        raw: dict[str, Any] = {}
        for f in fields(Look):
            text = look_el.get(f.name)
            if text is None:
                continue
            if f.name in COLOUR_FIELDS:
                parts = text.split()
                if len(parts) != 3:
                    raise TempleFormatError(
                        f"{path}: look {f.name} must be three numbers, got {text!r}"
                    )
                raw[f.name] = tuple(_read_float(path, f"look {f.name}", p) for p in parts)
            else:
                raw[f.name] = _read_float(path, f"look {f.name}", text)
        try:
            look = Look.from_dict(raw)
        except ValueError as exc:
            raise TempleFormatError(f"{path}: bad look: {exc}") from exc

    camera = None
    if camera_el is not None:
        camera = {}
        for key in CAMERA_KEYS:
            text = camera_el.get(key)
            if text is None:
                raise TempleFormatError(
                    f"{path}: <camera> must state all of {', '.join(CAMERA_KEYS)}; missing {key}"
                )
            camera[key] = _read_float(path, f"camera {key}", text)

    return TempleFile(
        params=params, look=look, camera=camera, name=root.get("name", ""), ignored=tuple(ignored)
    )


def load_any(path: str | Path) -> TempleFile:
    """Read a ``<temple>`` document (``.xml``) or a legacy parameters file (``.json``).

    Dispatch is by suffix, case-insensitively, and anything else is refused by name: a
    content sniff would accept ``design.txt`` today and have to keep accepting it for
    ever.  The JSON era is read by the reader that defined it,
    :meth:`~mandapa.params.MandapaParams.from_dict`, with only the wrapping added — a
    :class:`TempleFormatError` naming the path for a file that is not a JSON object at
    all, and the unknown keys reported in :attr:`TempleFile.ignored`.  A JSON file
    states no look and no camera, so it reads with the defaults and ``None``, which is
    the truth about it.
    """
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".xml":
        return load_temple(path)
    if suffix == ".json":
        return _load_legacy_json(path)
    raise TempleFormatError(
        f"{path}: not a temple document (.xml) or a legacy parameters file (.json)"
    )


def _load_legacy_json(path: Path) -> TempleFile:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise TempleFormatError(f"{path}: not a parameters JSON file ({exc})") from exc
    if not isinstance(data, dict):
        raise TempleFormatError(
            f"{path}: a parameters file is a JSON object, got {type(data).__name__}"
        )
    known = {f.name for f in fields(MandapaParams)}
    ignored = tuple(key for key in data if key not in known)
    return TempleFile(params=MandapaParams.from_dict(data), ignored=ignored)
