"""The window as an editor: the views and the document agree, and undo goes through both.

Everything here runs on the offscreen platform, which on Windows has no OpenGL: the
viewer widget is constructed but never shown, so nothing below asks it to draw.  The one
test that would need a frame is skipped with that reason rather than faked.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dataclasses import fields

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QCheckBox, QComboBox

from mandapa.builder import build
from mandapa.document import Document, SetParams
from mandapa.gui import app as app_module
from mandapa.gui.app import APP_NAME, MainWindow
from mandapa.gui.controls import NumberControl
from mandapa.gui.export_dialog import ExportDialog, option_kind
from mandapa.gui.look_panel import LookPanel
from mandapa.gui.paramform import ParamForm
from mandapa.gui.prefs import RECENT_LIMIT, Preferences
from mandapa.look import Look
from mandapa.params import MandapaParams
from mandapa.printprep import PrintOptions


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def prefs(tmp_path) -> Preferences:
    """An ini file in the temp dir, so no test touches the registry."""
    return Preferences(QSettings(str(tmp_path / "prefs.ini"), QSettings.Format.IniFormat))


@pytest.fixture
def window(qapp, prefs):
    win = MainWindow(prefs=prefs, autobuild=False)
    yield win
    win.wait_idle(60000)
    win.deleteLater()
    qapp.processEvents()


# ---- the number control -------------------------------------------------------------------


def test_a_number_control_reports_the_gesture_and_its_end(qapp):
    control = NumberControl(float, 0.5, 3.0, 0.1)
    seen: list[object] = []
    control.edited.connect(seen.append)
    control.committed.connect(lambda: seen.append("commit"))
    control.spin.setValue(1.2)
    control.spin.editingFinished.emit()
    control.slider.setValue(control.slider.maximum())
    control.slider.sliderReleased.emit()
    assert seen == [1.2, "commit", 3.0, "commit"]
    control.setValue(2.0)  # the document talking: shown, never reported
    assert control.value() == 2.0 and seen[-1] == "commit"


# ---- form <-> document ----------------------------------------------------------------------


def test_the_form_shows_what_the_document_says(qapp):
    document = Document()
    form = ParamForm(document)
    revision = document.revision
    document.submit(SetParams({"pillars_x": 3, "roof_style": "stepped", "steps": False}))
    assert form.controls["pillars_x"].value() == 3
    assert form.controls["roof_style"].currentText() == "stepped"
    assert form.controls["steps"].isChecked() is False
    # Refreshing submitted nothing back: one step on the stack, one revision.
    assert len(document._undo) == 1 and document.revision == revision + 1


def test_editing_a_number_submits_a_coalesced_command(qapp):
    document = Document()
    form = ParamForm(document)
    control = form.controls["pillar_width"]
    control.spin.setValue(7.5)
    control.spin.setValue(8.0)
    assert document.params.pillar_width == 8.0
    assert len(document._undo) == 1, "a gesture is one undo step"
    assert document._undo[-1].coalesce == "pillar_width"
    assert document.undo_text == "Set Pillar width"
    control.spin.editingFinished.emit()  # the gesture ends
    control.spin.setValue(9.0)
    assert len(document._undo) == 2
    document.undo()
    assert document.params.pillar_width == 8.0 and control.value() == 8.0
    document.undo()
    assert document.params.pillar_width == 6.0 and control.value() == 6.0


def test_discrete_controls_seal_their_own_step(qapp):
    document = Document()
    form = ParamForm(document)
    combo: QComboBox = form.controls["roof_style"]
    combo.setCurrentText("flat")
    check: QCheckBox = form.controls["kudus"]
    check.setChecked(False)
    assert document.params.roof_style == "flat" and document.params.kudus is False
    assert [c.coalesce for c in document._undo] == [None, None]
    assert len(document._undo) == 2


def test_a_group_reset_is_one_command(qapp):
    document = Document()
    form = ParamForm(document)
    document.submit(SetParams({"pillars_x": 3, "footprint_x": 120.0}))
    assert form.sections["Plan"].reset_button.isEnabled()
    form.reset_group("Plan")
    assert document.params.pillars_x == 4 and document.params.footprint_x == 100.0
    assert document.undo_text == "Reset Plan"
    assert not form.sections["Plan"].reset_button.isEnabled()
    document.undo()
    assert document.params.pillars_x == 3 and document.params.footprint_x == 120.0


def test_the_filter_hides_rows_that_do_not_match(qapp):
    form = ParamForm(Document())
    form.filter.setText("kapota")
    plan = form.sections["Plan"]
    entablature = form.sections["Entablature (prastara)"]
    assert plan.isHidden() and not entablature.isHidden()
    _, row = form._rows["kapota_height"]
    assert entablature.form.isRowVisible(row)
    _, beam_row = form._rows["beam_height"]
    assert not entablature.form.isRowVisible(beam_row)
    form.filter.setText("")
    assert not plan.isHidden() and entablature.form.isRowVisible(beam_row)


def test_folded_sections_are_remembered(qapp, prefs):
    form = ParamForm(Document(), prefs)
    form.sections["Roof"].header.setChecked(False)
    assert prefs.section_expanded("Roof") is False
    again = ParamForm(Document(), prefs)
    assert again.sections["Roof"].expanded is False and again.sections["Plan"].expanded is True


# ---- the look panel ---------------------------------------------------------------------------


def test_the_look_panel_submits_setlook(qapp):
    document = Document()
    panel = LookPanel(document)
    panel.numbers["light_azimuth"].spin.setValue(10.0)
    panel.numbers["light_azimuth"].spin.setValue(12.0)
    assert document.look.light_azimuth == 12.0
    assert len(document._undo) == 1 and document._undo[-1].coalesce == "light_azimuth"
    swatch = panel.swatches["surface_colour"]
    swatch._dialog = lambda initial: QColor.fromRgbF(0.5, 0.25, 0.125)
    swatch.click()
    assert document.look.surface_colour == pytest.approx((0.5, 0.25, 0.125), abs=1e-4)
    assert document.undo_text == "Set Surface colour"
    document.undo()
    assert document.look.surface_colour == Look().surface_colour
    assert swatch.colour() == pytest.approx(Look().surface_colour)


# ---- the window ---------------------------------------------------------------------------------


def test_undo_through_the_window_restores_the_control(window):
    control = window.form.controls["pillars_x"]
    control.spin.setValue(3)
    assert window.document.params.pillars_x == 3
    assert window.actions["undo"].isEnabled()
    assert window.actions["undo"].text() == "&Undo Set Pillars along X"
    window.actions["undo"].trigger()
    assert window.document.params.pillars_x == 4 and control.value() == 4
    assert window.actions["redo"].text() == "&Redo Set Pillars along X"
    window.actions["redo"].trigger()
    assert window.document.params.pillars_x == 3 and control.value() == 3


def test_the_title_tracks_the_name_and_dirtiness(window, tmp_path):
    assert window.windowTitle() == f"untitled — {APP_NAME}"
    window.form.controls["tiers"].spin.setValue(2)
    assert window.windowTitle() == f"untitled* — {APP_NAME}"
    window.actions["undo"].trigger()
    assert window.windowTitle() == f"untitled — {APP_NAME}"
    window.form.controls["tiers"].spin.setValue(5)
    assert window._save_to(tmp_path / "hall.xml")
    assert window.windowTitle() == f"hall — {APP_NAME}"
    assert window.prefs.recent()[0] == (tmp_path / "hall.xml").resolve()


def test_moving_focus_seals_the_gesture(window):
    control = window.form.controls["pillar_height"]
    control.spin.setValue(40.0)
    window._focus_changed(None, None)
    control.spin.setValue(41.0)
    assert len(window.document._undo) == 2


def test_the_verbs_carry_their_shortcuts(window):
    expected = {
        "fit": "F", "front": "1", "side": "3", "top": "7", "ortho": "O", "highlight": "H",
        "union": "U", "turntable": "Space", "screenshot": "Ctrl+P", "randomise": "Ctrl+R",
        "export": "Ctrl+E", "undo": "Ctrl+Z", "build": "F5",
    }
    for key, shortcut in expected.items():
        assert window.actions[key].shortcut().toString() == shortcut, key
    assert [s.toString() for s in window.actions["redo"].shortcuts()] == ["Ctrl+Y", "Ctrl+Shift+Z"]
    toolbar = {a.text() for a in window.toolbar.actions() if a.text()}
    for key in ("build", "fit", "front", "side", "top", "ortho", "highlight", "union", "turntable", "screenshot", "randomise", "export"):
        assert window.actions[key].text() in toolbar, key


def test_open_restores_look_camera_and_clears_history(window, tmp_path):
    look = Look(light_azimuth=33.0, surface_colour=(0.5, 0.5, 0.5))
    camera = {"azimuth": -30.0, "elevation": 20.0, "distance": 250.0, "cx": 1.0, "cy": 2.0, "cz": 3.0}
    path = tmp_path / "authored.xml"
    Document(MandapaParams(pillars_x=2), look).save(path, camera=camera)
    window.form.controls["pillars_y"].spin.setValue(3)  # history that must not survive
    assert window.open_path(path, confirm=False)
    assert window.document.path == path and window.document.params.pillars_x == 2
    assert window.document.look == look
    assert not window.actions["undo"].isEnabled()
    assert window.viewer.camera() == pytest.approx(camera)
    assert window.look_panel.numbers["light_azimuth"].value() == 33.0
    assert window.form.controls["pillars_x"].value() == 2
    assert window.prefs.recent()[0] == path.resolve()
    assert window.windowTitle() == f"authored — {APP_NAME}"


def test_a_legacy_json_opens_untitled_and_save_asks_for_a_path(window, tmp_path, monkeypatch):
    path = tmp_path / "old.json"
    MandapaParams(pillars_x=5).save(path)
    assert window.open_path(path, confirm=False)
    assert window.document.path is None and window.document.name == "old"
    assert window.document.params.pillars_x == 5
    asked = []
    monkeypatch.setattr(window, "save_as", lambda: asked.append(True) or True)
    window.save()
    assert asked == [True]


def test_a_bad_file_is_refused_and_dropped_from_recent(window, tmp_path, monkeypatch):
    path = tmp_path / "broken.xml"
    path.write_text("<body/>", encoding="utf-8")
    window.prefs.add_recent(path)
    monkeypatch.setattr(app_module.QMessageBox, "critical", lambda *a, **k: None)
    assert not window.open_path(path, confirm=False)
    assert path.resolve() not in window.prefs.recent()


def test_the_recent_menu_lists_what_the_preferences_hold(window, tmp_path):
    for name in ("a.xml", "b.xml"):
        (tmp_path / name).write_text("<temple/>", encoding="utf-8")
        window.prefs.add_recent(tmp_path / name)
    window._fill_recent_menu()
    texts = [a.text() for a in window.recent_menu.actions() if not a.isSeparator()]
    assert texts == ["b.xml", "a.xml", "Clear list"]
    window.prefs.clear_recent()
    window._fill_recent_menu()
    assert [a.text() for a in window.recent_menu.actions()] == ["No recent files"]


def test_the_examples_menu_lists_the_directory(qapp, prefs, tmp_path, monkeypatch):
    examples = tmp_path / "examples"
    examples.mkdir()
    for name in ("small_shrine.xml", "long_hall.xml"):
        Document(MandapaParams()).save(examples / name)
    monkeypatch.setattr(app_module, "EXAMPLES", examples)
    window = MainWindow(prefs=prefs, autobuild=False)
    try:
        assert window.examples_menu is not None
        window._fill_examples_menu()
        assert [a.text() for a in window.examples_menu.actions()] == ["long hall", "small shrine"]
    finally:
        window.deleteLater()
        qapp.processEvents()


def test_a_build_fills_the_readouts_and_the_parts_menu(window):
    window.start_build()
    assert window.wait_idle(120000), "the build did not finish"
    assert window._payload is not None
    assert "faces" in window.readouts["faces"].text()
    assert "mm" in window.readouts["size"].text()
    assert window.readouts["watertight"].text() == "shells (no union)"
    assert "overhang" in window.readouts["overhang"].text()
    names = [a.text().lower() for a in window.parts_menu.actions()]
    assert names == [name for name in build(window.document.params).parts if name in window.viewer.group_names()]
    assert "roof" in window.viewer.group_names()
    window._group_actions["roof"].setChecked(False)
    assert not window.viewer.is_group_visible("roof")


def test_exceeding_the_bed_warns_on_the_status_bar(window):
    window.start_build()
    assert window.wait_idle(120000)
    window.set_bed((50.0, 50.0, 50.0))
    assert window.readouts["size"].warned
    assert "exceeds bed" in window.readouts["size"].text()
    assert "exceeds the print bed" in window.log.toPlainText()
    window.set_bed((220.0, 220.0, 250.0))
    assert not window.readouts["size"].warned


# ---- preferences --------------------------------------------------------------------------------


def test_recent_files_are_ordered_deduplicated_and_capped(prefs, tmp_path):
    paths = []
    for i in range(RECENT_LIMIT + 2):
        path = tmp_path / f"design{i}.xml"
        path.write_text("<temple/>", encoding="utf-8")
        paths.append(path.resolve())
        prefs.add_recent(path)
    recent = prefs.recent()
    assert len(recent) == RECENT_LIMIT and recent[0] == paths[-1]
    prefs.add_recent(paths[-3])
    assert prefs.recent()[0] == paths[-3] and prefs.recent().count(paths[-3]) == 1
    paths[-1].unlink()
    assert paths[-1] not in prefs.recent(), "a file that is gone is not offered"
    prefs.remove_recent(paths[-3])
    assert paths[-3] not in prefs.recent()
    prefs.clear_recent()
    assert prefs.recent() == []


def test_the_bed_round_trips_and_defaults(prefs):
    assert prefs.bed() == (220.0, 220.0, 250.0)
    prefs.set_bed((256, 256, 256))
    assert prefs.bed() == (256.0, 256.0, 256.0)
    prefs.settings.setValue("bed/size", "nonsense")
    assert prefs.bed() == (220.0, 220.0, 250.0)


# ---- the export dialog --------------------------------------------------------------------------


def test_the_export_dialog_is_built_from_print_options(qapp):
    dialog = ExportDialog(build(MandapaParams()), bed=(220.0, 220.0, 250.0))
    assert set(dialog.widgets) == {f.name for f in fields(PrintOptions)}
    options = dialog.options()
    assert isinstance(options, PrintOptions)
    for name, kind in dialog.kinds.items():
        if kind == "xyz":
            assert getattr(options, name) == (220.0, 220.0, 250.0)
            dialog.widgets[name].setText("")
            assert getattr(dialog.options(), name) is None
            dialog.widgets[name].setText("1 2")
            with pytest.raises(ValueError):
                dialog.options()
            dialog.widgets[name].setText("200, 200, 200")
            assert getattr(dialog.options(), name) == (200.0, 200.0, 200.0)
    assert dialog.format() == "stl" and dialog.path().suffix == ".stl"


@pytest.mark.parametrize(
    ("annotation", "kind"),
    [
        ("bool", "bool"),
        ("int", "int"),
        ("float", "float"),
        ("str", "str"),
        ("tuple[float, float, float] | None", "xyz"),
        (bool, "bool"),
        (float, "float"),
        (tuple[float, float, float] | None, "xyz"),
    ],
)
def test_option_kinds(annotation, kind):
    assert option_kind(annotation) == kind


@pytest.mark.skip(reason="needs a real OpenGL context; the offscreen platform has none on Windows")
def test_the_viewer_renders_the_documents_look():
    """Covered by `temple-gen --screenshot`, which the orchestrator runs on every example."""
