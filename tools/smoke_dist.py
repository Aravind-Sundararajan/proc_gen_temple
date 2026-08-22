"""Prove that a PyInstaller folder works and keeps its promises, with nobody at the screen.

Run after ``pyinstaller proc_gen_temple.spec`` (``devtool build`` does).  It uses the two
executables the way a user would — the command exports a model, the editor renders a
screenshot — and then holds the folder to the README's licence note: only LGPL Qt modules (the
PySide6 Essentials wheel's own list), the third-party licence files, the LGPL and GPL texts.
Exit status is the verdict; the reasons are printed.  It runs under the development venv (it
reads the wheels' RECORDs and decodes the screenshot with Qt), never inside the bundle.

On a CI runner (``CI`` set) the editor is started only as far as its argument parser.  A
runner has no desktop for a window and no GL for the viewer, and a windowed program that
cannot render there does not fail — it waits, on a frame that never comes or a dialog nobody
can dismiss, with its stderr gone.  ``--help`` exits after every import and before any window,
which is the part of the editor a bundle can break; the screenshot is a desk-side check.
"""

from __future__ import annotations

import importlib.metadata
import os
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist" / "proc_gen_temple"
INTERNAL = DIST / "_internal"
EXE = ".exe" if sys.platform == "win32" else ""
TIMEOUT = 600

failures: list[str] = []


def fail(text: str) -> None:
    failures.append(text)
    print(f"FAIL  {text}")


def ok(text: str) -> None:
    print(f"ok    {text}")


def run(args: list[str], timeout: float = TIMEOUT) -> subprocess.CompletedProcess[str]:
    """Run a bundled executable; waits even for a windowed program, which a shell would not.

    Never set ``QT_OPENGL=software`` for the editor here: Qt would draw through
    ``opengl32sw.dll`` while PyOpenGL keeps calling the system ``opengl32.dll``, two GLs and no
    shared context, and the first call fails with GL_INVALID_OPERATION.
    """
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)


def wheel_files(dist: str) -> set[str]:
    """Relative paths (``PySide6/Qt6Charts.dll``) of everything a wheel installs under PySide6/."""
    files = importlib.metadata.distribution(dist).files or ()
    return {f.as_posix() for f in files if f.parts and f.parts[0] == "PySide6"}


# ---- the command ------------------------------------------------------------------------------


def check_cli(tmp: Path) -> None:
    exe = DIST / f"mandapa{EXE}"
    if not exe.is_file():
        fail(f"{exe} is missing")
        return
    out = tmp / "smoke.stl"
    result = run([str(exe), "--preset", "Desk mandapa", "--out", str(out)])
    if result.returncode != 0 or "watertight yes" not in result.stdout:
        fail(f"mandapa export failed ({result.returncode}):\n{result.stdout}\n{result.stderr}")
    elif out.stat().st_size < 10_000:
        fail(f"mandapa wrote a {out.stat().st_size}-byte STL")
    else:
        ok(f"mandapa exported a watertight STL ({out.stat().st_size // 1000} kB)")
    result = run([str(exe), "--glossary"])
    if "garbhagriha" not in result.stdout:
        fail("mandapa --glossary does not list the vocabulary")
    result = run([str(exe), "--about"])
    if "not installed" in result.stdout:
        fail("mandapa --about cannot read a dependency's version: metadata missing from the bundle")
    else:
        ok("mandapa --about reads every dependency's version")


# ---- the editor -------------------------------------------------------------------------------


def check_gui(tmp: Path) -> None:
    exe = DIST / f"temple-gen{EXE}"
    if not exe.is_file():
        fail(f"{exe} is missing")
        return
    if os.environ.get("CI"):
        result = run([str(exe), "--help"], timeout=120)
        if result.returncode != 0:
            fail(f"temple-gen --help exited {result.returncode}: the editor does not start\n{result.stderr}")
        else:
            ok("temple-gen starts as far as its argument parser (a CI runner has no desktop: no screenshot)")
        return
    png = tmp / "smoke.png"
    params = ROOT / "examples" / "small_shrine.xml"
    try:
        result = run([str(exe), "--params", str(params), "--screenshot", str(png)], timeout=180)
    except subprocess.TimeoutExpired:
        fail("temple-gen did not exit within 180 s: a dialog is probably waiting, or no frame was ever drawn")
        return
    if result.returncode != 0 or not png.is_file():
        fail(f"temple-gen screenshot failed ({result.returncode}):\n{result.stdout}\n{result.stderr}")
        return
    from PySide6.QtGui import QImage  # the development venv has Qt; the check needs no app

    image = QImage(str(png))
    if image.isNull() or image.width() < 200:
        fail(f"temple-gen wrote an unreadable screenshot ({png.stat().st_size} bytes)")
        return
    step = max(image.width() // 40, 1)
    colours = {
        image.pixel(x, y)
        for x in range(0, image.width(), step)
        for y in range(0, image.height(), step)
    }
    if len(colours) < 16:
        fail(f"temple-gen's screenshot is flat ({len(colours)} colours): no GL context, or nothing drawn")
    else:
        ok(f"temple-gen rendered {image.width()}x{image.height()} px with {len(colours)} sampled colours")


# ---- what the folder carries ------------------------------------------------------------------


def check_contents() -> None:
    examples = sorted(p.name for p in (ROOT / "examples").glob("*.xml"))
    bundled = sorted(p.name for p in (INTERNAL / "examples").glob("*.xml"))
    if bundled != examples:
        fail(f"examples in the bundle {bundled} differ from the repository's {examples}")
    else:
        ok(f"{len(bundled)} examples travel with the editor")

    licences = INTERNAL / "licenses"
    if not (licences / "THIRD_PARTY.md").is_file():
        fail("licenses/THIRD_PARTY.md is missing")
    for text in ("LGPL-3.0.txt", "GPL-3.0.txt"):
        if not (licences / text).is_file():
            fail(f"licenses/{text} is missing: run `devtool licenses` and commit licenses/")
    for package in ("numpy", "trimesh", "pyqtgraph", "manifold3d", "shiboken6", "PySide6"):
        if not any((licences / package).glob("*")):
            fail(f"licenses/{package}/ is empty")
    if not failures:
        ok("licence files and the LGPL/GPL texts are in licenses/")


def check_qt_is_essentials_only() -> None:
    essentials = wheel_files("PySide6_Essentials")
    addons = wheel_files("PySide6_Addons") - essentials
    qt_dir = INTERNAL / "PySide6"
    if not qt_dir.is_dir():
        fail("_internal/PySide6 is missing")
        return
    present = {("PySide6/" + p.relative_to(qt_dir).as_posix()) for p in qt_dir.rglob("*") if p.is_file()}
    stray = sorted(present & addons)
    if stray:
        fail(f"{len(stray)} file(s) from the PySide6 Addons wheel are in the bundle: {stray[:8]} ...")
    else:
        modules = sorted({Path(p).name.split(".")[0] for p in present if Path(p).name.startswith("Qt")})
        ok(f"Qt is Essentials only: {', '.join(m for m in modules if not m.startswith('Qt6'))}")


def report_size() -> None:
    total = sum(p.stat().st_size for p in DIST.rglob("*") if p.is_file())
    print(f"size  {total / 1e6:.0f} MB in {DIST}")


def main() -> int:
    if not DIST.is_dir():
        print(f"no bundle at {DIST}; run pyinstaller proc_gen_temple.spec first")
        return 2
    with tempfile.TemporaryDirectory() as tmp:
        check_cli(Path(tmp))
        check_gui(Path(tmp))
    check_contents()
    check_qt_is_essentials_only()
    report_size()
    if failures:
        print(f"\n{len(failures)} problem(s) with the bundle")
        return 1
    print("\nthe bundle works and keeps its promises")
    return 0


if __name__ == "__main__":
    sys.exit(main())
