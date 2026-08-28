"""The dependency rule, enforced rather than described.

Two packages, one direction: ``meshlib`` stands on numpy and the standard library
alone; everything in ``mandapa/`` may stand on it; ``gopuram/`` stands on ``mandapa/``
and never the reverse — the mandapa must not know it has a sister; and in both
packages only ``gui/`` may import Qt, pyqtgraph or OpenGL.  The CLIs, the tests and
the file formats rely on that — a machine with no display builds, exports and reads
designs of either family — and a docstring is not an enforcement mechanism, so the
imports are read off the parsed source of every module, and a fresh interpreter is
asked to import the headless half of both packages with the GUI stack blocked.
"""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PACKAGES = {name: ROOT / name for name in ("mandapa", "gopuram")}
GUI_ONLY = {"PySide6", "pyqtgraph", "OpenGL", "shiboken6"}


def headless_modules(package: Path) -> list[Path]:
    return sorted(p for p in package.rglob("*.py") if "gui" not in p.relative_to(package).parts)


def all_modules(package: Path) -> list[Path]:
    return sorted(package.rglob("*.py"))


def top_level_imports(source: Path) -> set[str]:
    """Every package name imported anywhere in the module, nested scopes included."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"), filename=str(source))):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def _headless_ids():
    return [
        (name, path)
        for name, package in PACKAGES.items()
        for path in headless_modules(package)
    ]


def test_the_headless_halves_are_what_we_think_they_are():
    names = {p.relative_to(PACKAGES["mandapa"]).as_posix() for p in headless_modules(PACKAGES["mandapa"])}
    assert {"document.py", "look.py", "io/temple_xml.py", "meshlib.py", "builder.py"} <= names
    sister = {p.relative_to(PACKAGES["gopuram"]).as_posix() for p in headless_modules(PACKAGES["gopuram"])}
    assert {"document.py", "io/gopuram_xml.py", "builder.py", "params.py", "printprep.py"} <= sister
    for modules in (names, sister):
        assert not any(name.startswith("gui/") for name in modules)


@pytest.mark.parametrize(
    ("package", "module"), _headless_ids(), ids=lambda v: v.name if isinstance(v, Path) else v
)
def test_nothing_outside_gui_imports_the_gui_stack(package, module):
    assert not (top_level_imports(module) & GUI_ONLY), module


@pytest.mark.parametrize("module", all_modules(PACKAGES["mandapa"]), ids=lambda p: p.stem)
def test_the_mandapa_never_imports_its_sister(module):
    """gopuram → mandapa is the one direction; the elder package must build, test and
    ship exactly as it did before the sister existed."""
    assert "gopuram" not in top_level_imports(module), module


def test_meshlib_imports_only_numpy_and_the_standard_library():
    imported = top_level_imports(PACKAGES["mandapa"] / "meshlib.py")
    assert "numpy" in imported
    assert "mandapa" not in imported
    assert imported - {"numpy"} <= sys.stdlib_module_names


def test_the_formats_and_documents_import_neither_qt_nor_a_mesh_library():
    """Reading a design needs no numpy and no trimesh, let alone a window."""
    for package, name in (
        ("mandapa", "io/temple_xml.py"),
        ("mandapa", "io/__init__.py"),
        ("mandapa", "look.py"),
        ("mandapa", "document.py"),
        ("gopuram", "io/gopuram_xml.py"),
        ("gopuram", "io/__init__.py"),
        ("gopuram", "params.py"),
        ("gopuram", "document.py"),
        ("gopuram", "help.py"),
    ):
        imported = top_level_imports(PACKAGES[package] / name)
        assert not (imported & (GUI_ONLY | {"numpy", "trimesh", "manifold3d"})), (package, name)


def test_the_headless_halves_import_with_the_gui_stack_blocked():
    """A fresh interpreter is the only honest witness: in-process, any earlier test may
    have loaded Qt already.  ``sys.modules[name] = None`` makes the import raise."""
    modules = [
        f"{name}." + p.relative_to(package).with_suffix("").as_posix().replace("/", ".")
        for name, package in PACKAGES.items()
        for p in headless_modules(package)
        if p.name != "__init__.py"
    ]
    probe = (
        "import sys\n"
        f"for name in {sorted(GUI_ONLY)!r}:\n"
        "    sys.modules[name] = None\n"
        "import importlib\n"
        f"for name in {modules!r}:\n"
        "    importlib.import_module(name)\n"
        "loaded = [m for m in sys.modules if m.split('.')[0] in "
        f"{sorted(GUI_ONLY)!r} and sys.modules[m] is not None]\n"
        "assert not loaded, loaded\n"
    )
    subprocess.run([sys.executable, "-c", probe], check=True, cwd=ROOT)
