"""The help is held to the panel: it explains every word the panel uses, keeps no word the
package forgot, and states licences the installed packages agree with."""

from __future__ import annotations

import importlib.metadata
import os
import re
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from mandapa import __version__
from mandapa import help as about
from mandapa.params import GROUPS, MandapaParams

PACKAGE = Path(about.__file__).parent

# Choice values that are plain English and need no glossary entry.
ENGLISH = {
    "plain", "square", "octagonal", "sixteen", "round", "fluted", "varied", "bevel", "flat",
    "stepped", "none", "pedestal", "front", "back", "centre", "sides", "front+back", "back+sides", "all",
    "fdm_0.4", "fdm_0.25", "resin",
}


def parenthesised(text: str) -> set[str]:
    terms: set[str] = set()
    for inner in re.findall(r"\(([^)]*)\)", text):
        terms |= {t.strip().lower() for t in inner.split(",") if t.strip()}
    return terms


def test_every_term_the_panel_states_has_a_meaning():
    terms: set[str] = set()
    for group in GROUPS:
        terms |= parenthesised(group)
    for _name, _kind, meta in MandapaParams.specs():
        terms |= parenthesised(meta["label"])
    assert terms, "the panel states its vocabulary in parentheses; none found"
    assert terms <= set(about.GLOSSARY), terms - set(about.GLOSSARY)


def test_every_choice_is_english_or_explained():
    for name, _kind, meta in MandapaParams.specs():
        for choice in meta["choices"] or ():
            assert choice in ENGLISH or choice in about.GLOSSARY, (name, choice)


def test_every_glossary_entry_is_used_somewhere_in_the_package():
    sources = "\n".join(
        p.read_text(encoding="utf-8").lower()
        for p in PACKAGE.rglob("*.py")
        if p.name != "help.py"
    )
    unused = [term for term in about.GLOSSARY if term not in sources]
    assert unused == []


def test_meanings_are_one_line_each():
    for term, meaning in about.GLOSSARY.items():
        assert "\n" not in meaning and meaning.endswith(".") and len(meaning) <= 110, term
        assert term == term.lower() and " " not in term, term


def test_third_party_licences_agree_with_the_installed_metadata():
    for t in about.THIRD_PARTY:
        meta = importlib.metadata.metadata(t.package)
        stated = " ".join(
            s for s in [meta.get("License-Expression"), meta.get("License"), *(meta.get_all("Classifier") or [])] if s
        ).lower()
        key = re.split(r"[- ]", t.licence)[0].lower()
        assert key in stated, (t.package, t.licence, stated[:120])


def test_about_and_glossary_text_are_complete():
    text = about.about_text()
    assert __version__ in text and about.DESCRIPTION in text
    assert all(t.package in text for t in about.THIRD_PARTY)
    assert all(url in text for _, _, url in about.SOURCES)
    glossary = about.glossary_text()
    assert all(term in glossary for term in about.GLOSSARY)
    assert len(glossary.splitlines()) == len(about.GLOSSARY)


def test_build_info_names_the_app_and_python():
    info = about.build_info()
    assert info[about.APP_NAME] == __version__ and "Python" in info


# ---- the dialog -------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def qapp():
    from PySide6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


@pytest.fixture
def window(qapp, tmp_path):
    from PySide6.QtCore import QSettings

    from mandapa.gui.app import MainWindow
    from mandapa.gui.prefs import Preferences

    prefs = Preferences(QSettings(str(tmp_path / "prefs.ini"), QSettings.Format.IniFormat))
    win = MainWindow(prefs=prefs, autobuild=False)
    yield win
    win.wait_idle(60000)
    win.deleteLater()
    qapp.processEvents()


def test_the_dialog_lists_every_key_every_term_and_every_licence(window):
    from PySide6.QtGui import QKeySequence

    from mandapa.gui.help import TABS, HelpDialog

    dialog = HelpDialog(window.actions, window)
    rows = dialog.verb_rows()
    keys_column = " | ".join(keys for _, keys, _ in rows)
    for action in window.actions.values():
        for shortcut in action.shortcuts():
            assert shortcut.toString(QKeySequence.SequenceFormat.NativeText) in keys_column, action.text()
    assert any(verb == "Fit" and keys == "F" for verb, keys, _ in rows)
    assert dialog.glossary_table.rowCount() == len(about.GLOSSARY)
    assert __version__ in dialog.about_html
    assert all(t.package in dialog.licences_html for t in about.THIRD_PARTY)
    dialog.set_filter("kapota")
    assert set(dialog.visible_terms()) == {
        t for t, m in about.GLOSSARY.items() if "kapota" in t or "kapota" in m.lower()
    }
    dialog.set_filter("")
    assert len(dialog.visible_terms()) == len(about.GLOSSARY)
    assert len(TABS) == dialog.tabs.count()


def test_the_help_menu_opens_the_dialog_on_the_asked_tab(window):
    from mandapa.gui.help import TABS

    assert "help" in window.menus
    window.show_help("Glossary")
    assert window._help is not None and window._help.tabs.currentIndex() == TABS.index("Glossary")
    window.actions["about"].trigger()
    assert window._help.tabs.currentIndex() == TABS.index("About")
    assert window.actions["help"].shortcuts(), "F1 is the help key"
    window._help.close()
