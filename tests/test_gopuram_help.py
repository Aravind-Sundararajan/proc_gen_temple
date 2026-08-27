"""The gopuram's help is held to its panel, and its shared meanings to the mandapa's."""

from __future__ import annotations

import re
from pathlib import Path

from gopuram import __version__
from gopuram import help as about
from gopuram.params import GROUPS, GopuramParams
from mandapa import help as mandapa_about

PACKAGE = Path(about.__file__).parent

# Choice values that are plain English and need no glossary entry.
ENGLISH = {"plain", "fdm_0.4", "fdm_0.25", "resin", "none"}


def parenthesised(text: str) -> set[str]:
    terms: set[str] = set()
    for inner in re.findall(r"\(([^)]*)\)", text):
        terms |= {t.strip().lower() for t in inner.split(",") if t.strip()}
    return terms


def test_every_term_the_panel_states_has_a_meaning():
    terms: set[str] = set()
    for group in GROUPS:
        terms |= parenthesised(group)
    for _name, _kind, meta in GopuramParams.specs():
        terms |= parenthesised(meta["label"])
    assert terms, "the panel states its vocabulary in parentheses; none found"
    assert terms <= set(about.GLOSSARY), terms - set(about.GLOSSARY)


def test_every_choice_is_english_or_explained():
    for name, _kind, meta in GopuramParams.specs():
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


def test_shared_meanings_are_the_mandapas_never_a_retyping():
    """Where both glossaries carry a word for the same thing, it is one spelling; the
    entries this family respells (sikhara, kalasa, dvara) are the ones whose referent
    differs, and each of those must actually differ."""
    respelt = {"sikhara", "kalasa", "dvara"}
    for term, meaning in about.GLOSSARY.items():
        if term not in mandapa_about.GLOSSARY:
            continue
        if term in respelt:
            assert meaning != mandapa_about.GLOSSARY[term], term
        else:
            assert meaning == mandapa_about.GLOSSARY[term], term


def test_the_third_party_table_is_the_mandapas_verbatim():
    assert about.THIRD_PARTY is mandapa_about.THIRD_PARTY
    assert about.LICENCE_NOTE is mandapa_about.LICENCE_NOTE


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
    assert mandapa_about.APP_NAME not in info
    assert next(iter(info)) == about.APP_NAME
