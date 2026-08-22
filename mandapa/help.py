"""What the program says about itself: the glossary, the sources, the licences.

Why this is not in the GUI
--------------------------
The words in the parameter panel are Sanskrit and Tamil terms of art — *adhishthana*,
*potika*, *kapota* — and the one place a reader can ask what they mean must not be a
dialog only the editor can open.  The CLI prints the same glossary (``mandapa
--glossary``), the same credits (``mandapa --about``), and the tests read them without a
display.  So this module imports nothing but the standard library, like
:mod:`mandapa.look`, and the editor's Help dialog is a view of it.

Held to the panel, both ways
----------------------------
A glossary drifts in two directions: the panel grows a word the glossary does not explain,
or the glossary keeps a word nothing uses any more.  :mod:`tests.test_help` pins both —
every term the panel states in parentheses or offers as a choice has an entry here, and
every entry here is used somewhere in the package — so neither kind of rot can land
silently.  The meanings are kept to one line on purpose: a glossary is for the moment a
reader meets a word in a control, not for study.

The licences are stated from the installed packages' own metadata (a test compares them)
rather than from memory, because the only thing worse than no licence note is a wrong one.
"""

from __future__ import annotations

import importlib.metadata
import platform
import sys
from dataclasses import dataclass

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

APP_NAME = "Mandapa Generator"

DESCRIPTION = (
    "A parametric generator for a small Dravidian mandapa — the pillared pavilion of a "
    "South-Indian temple — that exports a 3D-printable STL or 3MF. Fifty-odd knobs describe "
    "the building in the vocabulary of the shilpa texts; the preview rebuilds as you turn "
    "them; every part is a closed solid and every export is one watertight body."
)

# (what, which proportions it gave us, where)
SOURCES: tuple[tuple[str, str, str], ...] = (
    (
        "Mayamata, chapters on the adhishthana and the pillar",
        "the padabandha base in 24 parts and the order kalasa, tadi, kumbha, padma, phalaka, potika",
        "https://www.wisdomlib.org/hinduism/essay/mayamata-and-building-construction-study/d/doc1598576.html",
    ),
    (
        "IGNCA survey of the Brihadishvara temple, Thanjavur",
        "the named members of a Chola adhishthana and prastara, with their relative heights",
        "https://ignca.gov.in/brhadisvaratemple/VIMAN/ARCHITECTURE/Components/pages/01_Adhisthana.htm",
    ),
    (
        "The Pallava period, Mamalla style",
        "the hara of kutas, salas and panjaras, the kapota with kudus, the taranga corbel",
        "https://www.wisdomlib.org/history/essay/pallava-period-study/d/doc1148407.html",
    ),
    (
        "Indian architectural terms",
        "the working glossary",
        "http://greatindiantemples.blogspot.com/2007/12/indian-architectural-terms.html",
    ),
)


@dataclass(frozen=True)
class ThirdParty:
    package: str  # the distribution name importlib.metadata knows
    licence: str  # as the package states it
    role: str  # what it does here
    url: str


THIRD_PARTY: tuple[ThirdParty, ...] = (
    ThirdParty("PySide6", "LGPL-3.0-only (or GPL, or Qt commercial)", "the editor: Qt for Python", "https://doc.qt.io/qtforpython-6/"),
    ThirdParty("shiboken6", "LGPL-3.0-only (or GPL, or Qt commercial)", "the binding generator's runtime", "https://doc.qt.io/qtforpython-6/"),
    ThirdParty("pyqtgraph", "MIT", "the OpenGL viewport", "https://www.pyqtgraph.org/"),
    ThirdParty("PyOpenGL", "BSD", "OpenGL bindings for the viewport", "https://pyopengl.sourceforge.net/"),
    ThirdParty("numpy", "BSD-3-Clause", "every vertex and face", "https://numpy.org/"),
    ThirdParty("trimesh", "MIT", "mesh I/O and the door to the boolean engine", "https://trimesh.org/"),
    ThirdParty("manifold3d", "Apache-2.0", "the boolean union that makes one body of the parts", "https://github.com/elalish/manifold"),
)

LICENCE_NOTE = (
    "Nothing here restricts what you do with the models you print. Distributing the "
    "application itself means the LGPL's terms for Qt: keep PySide6 dynamically loaded and "
    "replaceable (a folder install), ship the licence texts, and leave out the GPL-only "
    "modules the PySide6 Addons wheel bundles — this program imports only QtCore, QtGui, "
    "QtWidgets, QtOpenGL and QtOpenGLWidgets, which are LGPL."
)

# term -> one line, for the moment a reader meets the word in a control.
GLOSSARY: dict[str, str] = {
    "mandapa": "A pillared hall or pavilion of a temple; here a free-standing one.",
    "adhishthana": "The moulded base the whole building stands on.",
    "padabandha": "The standard base of the Mayamata: 24 parts from upana to prati.",
    "pratibandha": "A base whose kumuda is a round torus rather than a faceted one.",
    "kapotabandha": "A base that carries a small kapota, a dripstone, in its upper courses.",
    "upana": "The lowest course of the base, a plain projecting band.",
    "jagati": "The tall plain face of the base above the upana.",
    "kumuda": "The torus of the base — three-faceted (tripatta) or round.",
    "tripatta": "Three-faceted, said of a kumuda.",
    "kampa": "A thin fillet between two mouldings.",
    "kantha": "The recessed neck of the base, between the kumuda and the pattika.",
    "pattika": "The projecting band near the top of the base.",
    "prati": "The top fillet of the base, where the floor begins.",
    "galapada": "A small pilaster set in the kantha at intervals; a Pallava and Chola signature.",
    "padma": "Lotus: a band of petals on the upana, or the flared lotus member under the abacus.",
    "sopana": "The steps.",
    "hastihasta": "'Elephant trunk': the curled foot of a stair balustrade.",
    "stambha": "A pillar.",
    "chola": "Of the Chola dynasty; the shaft that goes square, octagonal, square.",
    "kattu": "A thin band where a shaft changes section.",
    "medallion": "A circular lotus boss carved on the square block of a shaft.",
    "kalasa": "The pot-shaped member at the top of the shaft.",
    "tadi": "The thin saucer above the kalasa.",
    "kumbha": "The cushion above the tadi; the widest part of the capital.",
    "phalaka": "The square abacus slab the corbel rests on.",
    "potika": "The corbel bracket between the abacus and the beam.",
    "taranga": "'Wave': a corbel whose underside rolls, Pallava and Chola.",
    "pushpa": "'Flower': a corbel ending in a pendant lotus bud, Vijayanagara.",
    "prastara": "The entablature: beams, frieze, cornice and slab.",
    "uttara": "The beam that spans the pillars.",
    "valabhi": "The frieze band above the beams.",
    "bhuta": "The dwarf figures (bhuta-gana) carved along the valabhi; here a row of bosses.",
    "dentil": "A small block in a row under the cornice.",
    "kapota": "The flexed cornice with its drip edge.",
    "kudu": "The horseshoe-arch ornament on the face of a kapota.",
    "nasi": "The horseshoe-arch dormer on the front of a miniature shrine.",
    "hara": "The parapet of miniature shrines along the edge of a roof.",
    "kuta": "A square miniature shrine with a domed roof; the corners of a hara.",
    "sala": "A rectangular miniature shrine with a barrel-vault roof; the middle of a side.",
    "panjara": "An apsidal miniature shrine, set between the kutas and salas.",
    "harantara": "The low wall that joins the shrines of a hara.",
    "griva": "The neck under a sikhara.",
    "sikhara": "The crowning dome of a tower: square (nagara), octagonal (dravida) or round (vesara).",
    "stupi": "The pot finial on a sikhara or a shrine.",
    "kerala": "The hipped, sloping roof of Kerala temples, here in the stone vocabulary.",
    "kakshasana": "The sloping seat-back parapet between the outer pillars of a hall.",
    "jali": "A perforated lattice screen.",
    "pitha": "A small moulded altar platform; an adhishthana in miniature.",
}


def build_info() -> dict[str, str]:
    """Versions worth quoting in a bug report."""
    info = {
        APP_NAME: __version__,
        "Python": platform.python_version(),
        "Platform": f"{platform.system()} {platform.release()}",
    }
    for package in ("PySide6", "pyqtgraph", "numpy", "trimesh", "manifold3d"):
        try:
            info[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            info[package] = "not installed"
    return info


def about_text() -> str:
    """The About tab as plain text, for ``mandapa --about``."""
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
