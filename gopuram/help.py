"""What the program says about itself: the glossary, the sources, the licences.

The rules are :mod:`mandapa.help`'s — Qt-free, printed by the CLI, viewed by the Help
dialog, held to the panel by tests — and the shared vocabulary is *taken* from that
module rather than retyped, so a meaning corrected there is corrected here.  A few
entries are this family's own spelling of a shared word (``sikhara`` is a barrel here,
a dome there; ``kalasa`` a ridge row here, a capital member there), because a glossary
serves the panel in front of the reader, not a union of all panels.  The third-party
table and the licence note are the mandapa's verbatim: the dependencies are identical.
"""

from __future__ import annotations

import sys

from mandapa import help as _mandapa_help
from mandapa.help import LICENCE_NOTE, THIRD_PARTY, ThirdParty

from . import __version__

__all__ = [
    "APP_NAME",
    "DESCRIPTION",
    "GLOSSARY",
    "LICENCE_NOTE",
    "SOURCES",
    "THIRD_PARTY",
    "ThirdParty",
    "about_text",
    "build_info",
    "glossary_text",
]

APP_NAME = "Gopuram Generator"

DESCRIPTION = (
    "A parametric generator for a Dravidian gopuram — the gateway tower of a South-Indian "
    "temple enclosure, with the processional passage through its base — that exports a "
    "3D-printable STL or 3MF. The knobs describe the building in the vocabulary of the "
    "shilpa texts; the preview rebuilds as you turn them; every part is a closed solid "
    "and every export is one watertight body. The mandapa's sister application."
)

# (what, which proportions it gave us, where)
SOURCES: tuple[tuple[str, str, str], ...] = (
    (
        "Gopura, across the shilpa and agama texts",
        "the oblong gateway on the enclosure wall: storeyed elevation, the passage on the axis",
        "https://www.wisdomlib.org/definition/gopura",
    ),
    (
        "Mayamata, chapters on the adhishthana and the pillar",
        "the padabandha base in 24 parts, run through the passage as built",
        "https://www.wisdomlib.org/hinduism/essay/mayamata-and-building-construction-study/d/doc1598576.html",
    ),
    (
        "The Pallava period, Mamalla style",
        "the hara of kutas, salas and panjaras that rings every tala, the kapota with kudus",
        "https://www.wisdomlib.org/history/essay/pallava-period-study/d/doc1148407.html",
    ),
    (
        "Indian architectural terms",
        "the working glossary",
        "http://greatindiantemples.blogspot.com/2007/12/indian-architectural-terms.html",
    ),
)

_SHARED_TERMS = (
    "adhishthana", "padabandha", "pratibandha", "kapotabandha", "upana", "kumuda",
    "kantha", "galapada", "padma", "prastara", "kapota", "kudu", "hara", "kuta",
    "sala", "panjara", "nasi", "griva", "stupi", "devakoshtha",
)

# term -> one line, for the moment a reader meets the word in a control.
GLOSSARY: dict[str, str] = {
    **{term: _mandapa_help.GLOSSARY[term] for term in _SHARED_TERMS},
    "gopuram": "The gateway tower of a temple enclosure: a passage through a masonry base "
    "under diminishing brick talas.",
    "dvara": "The doorway; here the processional passage through the gateway, kept at least "
    "twice as high as it is wide.",
    "pada": "The wall zone between the base and the entablature: one of the six members "
    "the texts divide an elevation into.",
    "tala": "One storey of a tower's superstructure; gopurams are counted by them.",
    "sikhara": "The crowning member of a tower; on a gopuram, the barrel-vaulted sala form "
    "along the ridge.",
    "kalasa": "The pot finial; a gopuram carries an odd row of them along its ridge.",
    "mahanasi": "The great horseshoe arch filling each end face of the vault.",
}


def build_info() -> dict[str, str]:
    """Versions worth quoting in a bug report; the platform half is the mandapa's."""
    info = _mandapa_help.build_info()
    del info[_mandapa_help.APP_NAME]
    return {APP_NAME: __version__, **info}


def about_text() -> str:
    """The About tab as plain text, for ``gopuram --about``."""
    lines = [f"{APP_NAME} {__version__}", "", DESCRIPTION, "", "Proportions and vocabulary:"]
    lines += [f"  {what} — {gave}\n    {url}" for what, gave, url in SOURCES]
    lines += ["", "Built on:"]
    lines += [f"  {t.package:11} {t.licence:40} {t.role}" for t in THIRD_PARTY]
    lines += ["", LICENCE_NOTE, "", "Versions:"]
    lines += [f"  {k}: {v}" for k, v in build_info().items()]
    return "\n".join(lines)


def glossary_text() -> str:
    width = max(len(term) for term in GLOSSARY)
    return "\n".join(f"{term:{width}}  {meaning}" for term, meaning in sorted(GLOSSARY.items()))


if __name__ == "__main__":
    sys.stdout.write(about_text() + "\n\n" + glossary_text() + "\n")
