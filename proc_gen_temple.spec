# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for proc_gen_temple: one folder, two executables.

Run ``pyinstaller proc_gen_temple.spec --noconfirm`` (or ``devtool build``, which also draws
the icons first and smoke-tests the result).  The output is ``dist/proc_gen_temple/`` holding
``temple-gen`` (the editor, a windowed program) and ``mandapa`` (the headless command, a
console program) over one shared ``_internal/``; on macOS the same folder is also wrapped as
``Mandapa Generator.app``.

Why one folder, never onefile
-----------------------------
The README's licence note promises Qt "dynamically loaded and replaceable (a folder install)":
that is the LGPL's condition for shipping it, and a onefile build — which unpacks a private
copy into a temp directory on every start — breaks it, and the start-up time with it.  The two
executables are two ``Analysis`` objects collected into the same ``COLLECT``: PyInstaller drops
the duplicate libraries, so the second program costs a few hundred kilobytes.  ``MERGE`` is
deliberately not used; in PyInstaller 6 it gives every executable onefile semantics.

Why the Qt modules are an allow-list
------------------------------------
PySide6's Addons wheel carries modules that are GPL-only (Charts, DataVisualization, Graphs,
VirtualKeyboard, Quick3D, HttpServer, ...).  PyInstaller collects only what is imported, so they
would stay out anyway — but "would" is not a contract.  The Essentials wheel's RECORD is the
list of LGPL modules; every module the Addons wheel adds is excluded by name here, and
``tools/smoke_dist.py`` reads the finished folder and fails the build if one landed in it.

Licences
--------
Each third-party package's licence files are copied from its dist-info into
``licenses/<package>/``, under a generated ``THIRD_PARTY.md`` naming versions and roles from
``mandapa.help.THIRD_PARTY``.  The PySide6 wheels ship only the Qt commercial licence reference,
not the LGPL text, so the repository's ``licenses/`` directory (LGPL-3.0 and the GPL-3.0 it
incorporates; ``devtool licenses`` fetches them) is copied in, and its absence is reported by
the smoke test rather than papered over.
"""

import importlib.metadata
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules, copy_metadata

ROOT = Path(SPECPATH).resolve()  # noqa: F821 — a spec global
sys.path.insert(0, str(ROOT))

from mandapa import __version__  # noqa: E402
from mandapa.help import LICENCE_NOTE, THIRD_PARTY  # noqa: E402

BUNDLE_NAME = "proc_gen_temple"
GUI_NAME, CLI_NAME = "temple-gen", "mandapa"
APP_NAME = "Mandapa Generator"
BUNDLE_ID = "io.github.aravind-sundararajan.mandapa"
ICON_DIR = ROOT / "build" / "icons"  # drawn by tools/make_icons.py; optional
LICENCE_DIR = ROOT / "licenses"  # LGPL-3.0.txt and GPL-3.0.txt; optional, see above
BUILD_DIR = ROOT / "build" / "licenses"

# Modules no part of this program wants; excluding them keeps a stray import in a dependency
# from dragging a toolkit in.
COMMON_EXCLUDES = [
    "tkinter", "PyQt5", "PyQt6", "PySide2", "matplotlib", "scipy", "IPython", "jupyter",
    "pytest", "ruff", "setuptools", "pip", "wheel", "_pytest",
]


# ---- Qt: the Essentials wheel is the allow-list ---------------------------------------------


def qt_modules(dist: str) -> set[str]:
    """Stems (``QtCharts``) of the extension modules a PySide6 wheel ships, from its RECORD."""
    stems = set()
    for file in importlib.metadata.distribution(dist).files or ():
        if len(file.parts) == 2 and file.parts[0] == "PySide6" and file.name.startswith("Qt"):
            if file.suffix in (".pyd", ".so"):
                stems.add(file.name.split(".")[0])
    return stems


def wheel_files(dist: str) -> set[str]:
    """Relative paths (``PySide6/Qt6Charts.dll``) of everything a wheel installs under PySide6/."""
    files = importlib.metadata.distribution(dist).files or ()
    return {f.as_posix() for f in files if f.parts and f.parts[0] == "PySide6"}


ESSENTIALS = qt_modules("PySide6_Essentials")
ADDONS = qt_modules("PySide6_Addons") - ESSENTIALS
if not ESSENTIALS or not ADDONS:
    raise SystemExit("could not read the PySide6 wheels' RECORDs; is the venv complete?")
QT_EXCLUDES = [f"PySide6.{stem}" for stem in sorted(ADDONS)]
ADDON_FILES = wheel_files("PySide6_Addons") - wheel_files("PySide6_Essentials")


# Essentials the program never uses but the Qt hook's plugin sweep brings in: the TUIO touch
# plugin (plugins/generic) links Qt6Network, whose own plugin folders follow it, and the
# virtual-keyboard plugin — gone with the Addons — had linked Qml and Quick.  Nothing left
# references them; the smoke test's screenshot is what says so after every build.
UNUSED_QT = ("Network", "Qml", "QmlMeta", "QmlModels", "QmlWorkerScript", "Quick")
UNUSED_PLUGIN_DIRS = ("generic", "networkinformation", "tls")


def unused_qt(dest: str) -> bool:
    """Whether a destination path is one of the Qt libraries, modules or plugin folders above,
    in the naming of any platform: ``Qt6Network.dll``, ``libQt6Network.so.6``,
    ``QtNetwork.framework/…``, ``QtNetwork.pyd``, ``plugins/tls/…``."""
    parts = Path(dest).parts
    if "plugins" in parts:
        after = parts[parts.index("plugins") + 1 :]
        if after and after[0] in UNUSED_PLUGIN_DIRS:
            return True
    stem = Path(dest).name.split(".")[0]
    for module in UNUSED_QT:
        if stem in (f"Qt6{module}", f"libQt6{module}", f"Qt{module}") or f"Qt{module}.framework" in parts:
            return True
    return False


def without_addons(toc: list) -> list:
    """The TOC minus every file the Addons wheel installed, and minus the unused Qt above.

    Excluding the modules is not enough: the Qt hook collects whole plugin folders for QtGui,
    and the PDF image-format and virtual-keyboard plugins drag Qt6Pdf and Qt6VirtualKeyboard
    in behind them.  Qt loads plugins on demand, so dropping a plugin and the library only
    it needed leaves nothing dangling.
    """
    kept, dropped = [], []
    for entry in toc:
        dest = Path(entry[0]).as_posix()
        if dest in ADDON_FILES:
            dropped.append((entry[0], "PySide6 Addons"))
        elif unused_qt(dest):
            dropped.append((entry[0], "unused Qt"))
        else:
            kept.append(entry)
    for name, why in dropped:
        print(f"proc_gen_temple.spec: leaving out {Path(name).as_posix()} ({why})")
    return kept


# ---- licences ---------------------------------------------------------------------------------


def licence_files(package: str) -> list[tuple[str, str]]:
    """``(source, destination dir)`` for every licence-looking file in a package's dist-info."""
    dist = importlib.metadata.distribution(package)
    out = []
    for file in dist.files or ():
        if ".dist-info" not in str(file):
            continue
        name = file.name.lower()
        if "licen" in name or name.startswith("copying") or name in ("authors", "notice"):
            out.append((str(dist.locate_file(file)), f"licenses/{package}"))
    return out


def third_party_notice() -> Path:
    """Write THIRD_PARTY.md for the bundle: the table the About tab shows, with versions."""
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Third-party software in this folder",
        "",
        f"proc_gen_temple {__version__}. Every package below is redistributed under its own "
        "licence; the files in the subfolders are the licence files its wheel carries, and "
        "LGPL-3.0.txt and GPL-3.0.txt beside this file are the texts Qt is shipped under.",
        "",
        "| Package | Version | Licence | Role | Home |",
        "|---|---|---|---|---|",
    ]
    for t in THIRD_PARTY:
        version = importlib.metadata.version(t.package)
        lines.append(f"| {t.package} | {version} | {t.licence} | {t.role} | {t.url} |")
    lines += [
        "",
        "## Qt",
        "",
        LICENCE_NOTE,
        "",
        "Only modules of the PySide6 Essentials wheel — all LGPL — can be present: "
        + ", ".join(sorted(ESSENTIALS)) + ".",
        "",
    ]
    path = BUILD_DIR / "THIRD_PARTY.md"
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


datas = [(str(ROOT / "examples" / "*.xml"), "examples")]
datas += collect_data_files("trimesh")  # its resources folder; the hook does this too, harmlessly
datas += [(str(third_party_notice()), "licenses")]
for t in THIRD_PARTY:
    datas += copy_metadata(t.package)  # Help → About reads the versions from the metadata
    datas += licence_files(t.package)
if LICENCE_DIR.is_dir():
    datas += [(str(p), "licenses") for p in sorted(LICENCE_DIR.glob("*.txt"))]
else:
    print(f"WARNING: {LICENCE_DIR} is missing: the LGPL/GPL texts will not ship (devtool licenses)")

# PyOpenGL loads its platform and array-format plugins by name at run time.
hidden_gui = ["manifold3d", *collect_submodules("OpenGL.platform"), *collect_submodules("OpenGL.arrays")]
hidden_cli = ["manifold3d"]


def icon(suffix: str) -> str | None:
    path = ICON_DIR / f"mandapa.{suffix}"
    return str(path) if path.is_file() else None


# ---- the two programs -------------------------------------------------------------------------

gui = Analysis(  # noqa: F821
    [str(ROOT / "tools" / "launch_gui.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_gui,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=COMMON_EXCLUDES + QT_EXCLUDES,
    noarchive=False,
)
cli = Analysis(  # noqa: F821
    [str(ROOT / "tools" / "launch_cli.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_cli,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # the dependency rule (tests/test_dependency_rule.py) says the command is Qt-free; hold it to that
    excludes=COMMON_EXCLUDES + ["PySide6", "shiboken6", "pyqtgraph", "OpenGL", "mandapa.gui"],
    noarchive=False,
)

gui.binaries = without_addons(gui.binaries)
gui.datas = without_addons(gui.datas)

gui_exe = EXE(  # noqa: F821
    PYZ(gui.pure),  # noqa: F821
    gui.scripts,
    [],
    exclude_binaries=True,
    name=GUI_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,  # UPX and Qt do not mix
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon("ico") if sys.platform == "win32" else None,
)
cli_exe = EXE(  # noqa: F821
    PYZ(cli.pure),  # noqa: F821
    cli.scripts,
    [],
    exclude_binaries=True,
    name=CLI_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon("ico") if sys.platform == "win32" else None,
)

# The editor goes first: BUNDLE takes the first executable as the app's own.
coll = COLLECT(  # noqa: F821
    gui_exe,
    gui.binaries,
    gui.datas,
    cli_exe,
    cli.binaries,
    cli.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=BUNDLE_NAME,
)

if sys.platform == "darwin":
    app = BUNDLE(  # noqa: F821
        coll,
        name=f"{APP_NAME}.app",
        icon=icon("icns"),
        bundle_identifier=BUNDLE_ID,
        version=__version__,
        info_plist={
            # A console executable in the COLLECT would otherwise make the app background-only.
            "LSBackgroundOnly": False,
            "NSHighResolutionCapable": True,
            "CFBundleDisplayName": APP_NAME,
            "CFBundleShortVersionString": __version__,
        },
    )
