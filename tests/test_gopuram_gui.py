"""The gopuram's window is the mandapa's shell wearing this family's facts.

Everything behavioural is pinned by :mod:`tests.test_gui` against the shared window;
this file pins the binding — the panel is generated from :class:`GopuramParams`, the
presets menu lists gateways, the export dialog grows from the gopuram's options, the
help shows the gopuram's glossary — and one undo pass to prove the machinery runs.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from dataclasses import fields

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from gopuram import help as about
from gopuram.gui.app import APP_NAME, EXAMPLES, GopuramWindow
from gopuram.params import GROUPS, GopuramParams
from gopuram.presets import PRESETS
from gopuram.printprep import GopuramPrintOptions
from mandapa.gui.prefs import Preferences


@pytest.fixture(scope="module")
def qapp() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp, tmp_path):
    win = GopuramWindow(prefs=Preferences(QSettings(str(tmp_path / "prefs.ini"), QSettings.Format.IniFormat)),
                        autobuild=False)
    yield win
    win.wait_idle(60000)
    win.deleteLater()
    qapp.processEvents()


def test_the_panel_is_generated_from_the_gopuram_params(window):
    assert set(window.form.controls) == {name for name, _, _ in GopuramParams.specs()}
    assert list(window.form.sections) == GROUPS
    assert window.windowTitle() == f"untitled — {APP_NAME}"


def test_the_presets_menu_lists_the_gateways(window):
    names = [a.text() for a in window.menus["presets"].actions()]
    assert names == list(PRESETS)


def test_undo_runs_through_the_shared_machinery(window):
    control = window.form.controls["talas"]
    control.spin.setValue(7)
    assert window.document.params.talas == 7
    assert window.actions["undo"].text() == "&Undo Set Talas"
    window.actions["undo"].trigger()
    assert window.document.params.talas == 5 and control.value() == 5


def test_new_and_reset_stay_in_the_family(window):
    window.form.controls["talas"].spin.setValue(7)
    window.reset_defaults()
    assert type(window.document.params) is GopuramParams
    assert window.document.params == GopuramParams()


def test_open_reads_gopuram_documents(window, tmp_path):
    from gopuram.document import GopuramDocument

    path = tmp_path / "gate.xml"
    GopuramDocument(GopuramParams(talas=7)).save(path)
    assert window.open_path(path, confirm=False)
    assert window.document.params.talas == 7
    assert type(window.document) is GopuramDocument


def test_a_mandapa_file_is_refused_with_both_tags_named(window, tmp_path, monkeypatch):
    from mandapa.document import Document
    from mandapa.gui import app as app_module

    said = []
    monkeypatch.setattr(app_module.QMessageBox, "critical", lambda *a, **k: said.append(a[2]))
    path = tmp_path / "hall.xml"
    Document().save(path)
    assert not window.open_path(path, confirm=False)
    assert said and "<temple>" in said[0] and "<gopuram>" in said[0]


def test_the_export_dialog_grows_from_the_gopuram_options(window):
    from gopuram.builder import build
    from mandapa.gui.export_dialog import ExportDialog

    dialog = ExportDialog(build(GopuramParams()), options_cls=GopuramPrintOptions,
                          bed=(220.0, 220.0, 250.0))
    assert set(dialog.widgets) == {f.name for f in fields(GopuramPrintOptions)}
    assert isinstance(dialog.options(), GopuramPrintOptions)


def test_the_help_dialog_shows_this_familys_glossary(window):
    window.show_help("Glossary")
    dialog = window._help
    assert dialog.glossary_table.rowCount() == len(about.GLOSSARY)
    assert APP_NAME in dialog.windowTitle()
    dialog.set_filter("mahanasi")
    assert dialog.visible_terms() == ["mahanasi"]
    dialog.close()


def test_the_examples_menu_points_at_the_gopuram_directory(window):
    assert EXAMPLES.name == "gopuram" and EXAMPLES.parent.name == "examples"
    assert window.EXAMPLES == EXAMPLES
    assert EXAMPLES.is_dir(), "the sister app ships examples too"
