"""The dependency rule, enforced rather than described.

``mandapa/`` is one-directional: ``meshlib`` stands on numpy and the standard library
alone; everything else may stand on it; only ``mandapa/gui/`` may import Qt, pyqtgraph
or OpenGL.  The CLI, the tests and the file format rely on that — a machine with no
display builds, exports and reads designs — and a docstring is not an enforcement
mechanism, so the imports are read off the parsed source of every module, and a fresh
interpreter is asked to import the headless half with the GUI stack blocked.
"""

import ast
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
PACKAGE = ROOT / "mandapa"
GUI_ONLY = {"PySide6", "pyqtgraph", "OpenGL", "shiboken6"}


def headless_modules() -> list[Path]:
    return sorted(p for p in PACKAGE.rglob("*.py") if "gui" not in p.relative_to(PACKAGE).parts)


def top_level_imports(source: Path) -> set[str]:
    """Every package name imported anywhere in the module, nested scopes included."""
    names: set[str] = set()
    for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"), filename=str(source))):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def test_the_headless_half_is_what_we_think_it_is():
    names = {p.relative_to(PACKAGE).as_posix() for p in headless_modules()}
    assert {"document.py", "look.py", "io/temple_xml.py", "meshlib.py", "builder.py"} <= names
    assert not any(name.startswith("gui/") for name in names)


@pytest.mark.parametrize("module", headless_modules(), ids=lambda p: p.relative_to(PACKAGE).as_posix())
def test_nothing_outside_gui_imports_the_gui_stack(module):
    assert not (top_level_imports(module) & GUI_ONLY), module


def test_meshlib_imports_only_numpy_and_the_standard_library():
    imported = top_level_imports(PACKAGE / "meshlib.py")
    assert "numpy" in imported
    assert "mandapa" not in imported
    assert imported - {"numpy"} <= sys.stdlib_module_names


def test_the_format_and_document_import_neither_qt_nor_a_mesh_library():
    """Reading a design needs no numpy and no trimesh, let alone a window."""
    for name in ("io/temple_xml.py", "io/__init__.py", "look.py", "document.py"):
        imported = top_level_imports(PACKAGE / name)
        assert not (imported & (GUI_ONLY | {"numpy", "trimesh", "manifold3d"})), name


def test_the_headless_half_imports_with_the_gui_stack_blocked():
    """A fresh interpreter is the only honest witness: in-process, any earlier test may
    have loaded Qt already.  ``sys.modules[name] = None`` makes the import raise."""
    modules = [
        "mandapa." + p.relative_to(PACKAGE).with_suffix("").as_posix().replace("/", ".")
        for p in headless_modules()
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
