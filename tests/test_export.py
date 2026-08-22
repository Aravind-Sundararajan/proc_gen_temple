"""Report arithmetic, the 3MF package, part file naming and the unchanged default STL."""

import xml.etree.ElementTree as ET
import zipfile

import numpy as np
import pytest
import trimesh

from mandapa.builder import build
from mandapa.export import (
    INFILL,
    PART_GAP_MM,
    PLA_DENSITY_G_CM3,
    SKIN_MM,
    PartMesh,
    body_count,
    classify_undersides,
    export_parts,
    export_stl,
    inspect_mesh,
    inspect_parts,
    read_3mf,
    to_trimesh,
    write_3mf,
)
from mandapa.meshlib import box_between, merge, ngon_sweep
from mandapa.params import MandapaParams
from mandapa.printprep import prepare_parts

NS = {"m": "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"}


def cube(size: float = 20.0, at=(0.0, 0.0, 0.0)) -> trimesh.Trimesh:
    x, y, z = at
    return to_trimesh(box_between((x, y, z), (x + size, y + size, z + size)))


# ---- report ---------------------------------------------------------------------------


def test_weight_estimate_formula_on_a_cube():
    report = inspect_mesh(cube(20.0))
    assert report.volume_cm3 == pytest.approx(8.0)
    assert report.area_mm2 == pytest.approx(2400.0)
    assert report.weight_g == pytest.approx(8.0 * PLA_DENSITY_G_CM3)
    skin = 2400.0 * SKIN_MM
    expected = (skin + INFILL * (8000.0 - skin)) / 1000.0 * PLA_DENSITY_G_CM3
    assert report.weight_estimate_g == pytest.approx(expected)
    assert report.weight_estimate_g < report.weight_g


def test_weight_estimate_never_exceeds_the_solid_figure():
    plate = to_trimesh(box_between((0, 0, 0), (50, 50, 1)))  # thinner than the skin: all skin
    report = inspect_mesh(plate)
    assert report.weight_estimate_g == pytest.approx(report.weight_g)


def test_summary_keeps_a_fixed_label_column():
    report = inspect_mesh(cube(), notes=["hello"], name="base")
    text = report.summary()
    lines = text.splitlines()
    assert lines[0] == "part       base"
    assert all(len(line) > 11 and line[10] == " " and line[11] != " " for line in lines)
    assert "100% infill" in text and "estimate" in text
    assert lines[-1] == "note       hello"
    assert not any(line.startswith("bodies") for line in lines)
    assert not inspect_mesh(cube()).summary().startswith("part")


def test_body_count_and_the_bodies_line():
    three = to_trimesh(
        merge(
            [
                box_between((0, 0, 0), (1, 1, 1)),
                box_between((5, 0, 0), (6, 1, 1)),
                box_between((0, 5, 0), (1, 6, 1)),
            ]
        )
    )
    assert body_count(cube()) == 1
    assert body_count(three) == 3
    report = inspect_mesh(three)
    assert report.bodies == 3
    assert "bodies     3 separate shells" in report.summary().splitlines()


def test_classify_undersides_flags_bridges_and_steep_overhangs():
    pedestal = box_between((0, 0, 0), (2, 2, 5))
    table = box_between((-5, -5, 5), (5, 5, 6))  # underside is a ceiling 5 mm up: a bridge
    cone = ngon_sweep([(0.0, 7.0), (5.0, 9.0), (5.0, 10.0)], 8).translated(20, 0, 0)  # apex down
    mesh = to_trimesh(merge([pedestal, table, cone]))
    steep, flat = classify_undersides(mesh.vertices, mesh.faces, mesh.face_normals)
    assert mesh.area_faces[flat].sum() == pytest.approx(100.0)
    lateral = mesh.area_faces[steep].sum()
    assert 0 < lateral and steep.sum() == 8
    assert not (steep & flat).any()
    report = inspect_mesh(mesh)
    assert report.bridge_area_mm2 == pytest.approx(100.0)
    assert report.overhang_area_mm2 == pytest.approx(lateral)


def test_inspect_parts_carries_names_and_notes():
    parts = [PartMesh("a", cube(), notes=["n1"]), PartMesh("b", cube())]
    reports = inspect_parts(parts)
    assert [r.name for r in reports] == ["a", "b"]
    assert reports[0].notes == ["n1"] and reports[1].notes == []


# ---- 3MF ------------------------------------------------------------------------------


def test_3mf_package_structure_and_read_back(tmp_path):
    a = PartMesh("base", cube(10.0), colour=(1.0, 0.5, 0.0))
    b = PartMesh("roof part", cube(5.0, at=(20.0, 0.0, 0.0)))
    path = write_3mf([a, b], tmp_path / "two.3mf")

    with zipfile.ZipFile(path) as zf:
        assert set(zf.namelist()) == {"[Content_Types].xml", "_rels/.rels", "3D/3dmodel.model"}
        types = ET.fromstring(zf.read("[Content_Types].xml"))
        assert {d.get("Extension") for d in types} == {"rels", "model"}
        rels = ET.fromstring(zf.read("_rels/.rels"))
        assert [r.get("Target") for r in rels] == ["/3D/3dmodel.model"]
        model = ET.fromstring(zf.read("3D/3dmodel.model"))

    assert model.tag == f"{{{NS['m']}}}model"
    assert model.get("unit") == "millimeter"
    objects = model.findall("m:resources/m:object", NS)
    assert [o.get("name") for o in objects] == ["base", "roof part"]
    for obj, part in zip(objects, (a, b)):
        assert obj.get("type") == "model"
        assert len(obj.findall("m:mesh/m:vertices/m:vertex", NS)) == len(part.mesh.vertices)
        assert len(obj.findall("m:mesh/m:triangles/m:triangle", NS)) == len(part.mesh.faces)
    materials = model.find("m:resources/m:basematerials", NS)
    assert [m.get("displaycolor") for m in materials] == ["#FF8000FF"]
    assert objects[0].get("pid") == materials.get("id") and objects[0].get("pindex") == "0"
    assert objects[1].get("pid") is None
    items = model.findall("m:build/m:item", NS)
    assert [i.get("objectid") for i in items] == [o.get("id") for o in objects]
    ids = [o.get("id") for o in objects] + [materials.get("id")]
    assert len(set(ids)) == 3

    back = read_3mf(path)
    assert [p.name for p in back] == ["base", "roof part"]
    assert back[0].colour == pytest.approx((1.0, 128 / 255, 0.0))
    assert back[1].colour is None
    for original, got in zip((a, b), back):
        assert len(got.mesh.faces) == len(original.mesh.faces)
        assert got.mesh.is_watertight
        assert got.mesh.volume == pytest.approx(original.mesh.volume)
    # placement: a row along +X from the origin, PART_GAP_MM apart; coordinates to 1e-4
    assert np.allclose(back[0].mesh.vertices, a.mesh.vertices, atol=1e-4)
    assert back[1].mesh.bounds[0] == pytest.approx([10.0 + PART_GAP_MM, 0.0, 0.0], abs=1e-4)


def test_3mf_single_part_is_placed_as_is_without_materials(tmp_path):
    original = cube(10.0, at=(3.0, 4.0, 0.0))
    path = write_3mf([PartMesh("mandapa", original)], tmp_path / "one.3mf")
    with zipfile.ZipFile(path) as zf:
        model = ET.fromstring(zf.read("3D/3dmodel.model"))
    assert model.find("m:resources/m:basematerials", NS) is None
    item = model.find("m:build/m:item", NS)
    assert item.get("transform") is None and item.get("objectid") == "1"
    back = read_3mf(path)
    assert len(back) == 1 and back[0].name == "mandapa"
    assert np.allclose(back[0].mesh.vertices, original.vertices, atol=1e-4)
    assert np.array_equal(back[0].mesh.faces, original.faces)


def test_3mf_through_trimesh_when_it_can_read_it(tmp_path):
    if "3mf" not in trimesh.available_formats():
        pytest.skip("trimesh cannot read 3MF here (needs lxml and networkx)")
    path = write_3mf([PartMesh("base", cube(10.0)), PartMesh("roof", cube(5.0))], tmp_path / "t.3mf")
    scene = trimesh.load(path)
    meshes = list(scene.geometry.values()) if hasattr(scene, "geometry") else [scene]
    assert sorted(round(m.volume) for m in meshes) == [125, 1000]


def test_3mf_refuses_what_it_cannot_read(tmp_path):
    with pytest.raises(ValueError):
        write_3mf([], tmp_path / "empty.3mf")
    bad = tmp_path / "inches.3mf"
    model = f'<?xml version="1.0"?><model unit="inch" xmlns="{NS["m"]}"><resources/><build/></model>'
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("_rels/.rels", "<Relationships/>")
        zf.writestr("3D/3dmodel.model", model)
    with pytest.raises(ValueError, match="millimeter"):
        read_3mf(bad)


# ---- part files -----------------------------------------------------------------------


def test_export_parts_naming_and_format_selection(tmp_path):
    parts = [PartMesh("base", cube()), PartMesh("roof part", cube())]
    written = export_parts(parts, tmp_path / "model.stl")
    assert [p.name for p in written] == ["model_base.stl", "model_roof_part.stl"]
    assert all(p.exists() for p in written)
    assert export_parts(parts[:1], tmp_path / "single.stl") == [tmp_path / "single.stl"]
    packaged = export_parts(parts, tmp_path / "model.stl", fmt="3mf")
    assert packaged == [tmp_path / "model.3mf"]
    assert [p.name for p in read_3mf(packaged[0])] == ["base", "roof part"]
    assert export_parts(parts, tmp_path / "by_suffix.3mf")[0].suffix == ".3mf"
    assert export_parts(parts[:1], tmp_path / "plain", fmt="stl") == [tmp_path / "plain.stl"]
    with pytest.raises(ValueError):
        export_parts(parts, tmp_path / "x.obj", fmt="obj")
    with pytest.raises(ValueError):
        export_parts([], tmp_path / "x.stl")


def test_default_stl_is_byte_identical_through_the_part_pipeline(tmp_path):
    params = MandapaParams()
    report = export_stl(params, tmp_path / "direct.stl")
    assert report.watertight and report.bodies == 1 and report.name == ""
    parts = prepare_parts(build(params))
    written = export_parts(parts, tmp_path / "via_parts.stl")
    assert written == [tmp_path / "via_parts.stl"]
    assert (tmp_path / "direct.stl").read_bytes() == written[0].read_bytes()
