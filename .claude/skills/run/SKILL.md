---
name: run
description: Launch the mandapa editor, export an STL headlessly, run the tests, or render a screenshot with the correct environment (the poetry venv, not any PATH python). Trigger on run/launch/test/screenshot/export requests for this project.
---

# Running proc_gen_temple

## The environment — the only fact that matters cold

This is a poetry project pinned to pyenv's 3.13.1 (`.python-version`) with an
in-project venv (`poetry.toml`). The **only** Python with the dependencies is
`.venv`; the `python` on PATH is a bare 3.14 with numpy and nothing else, and a
cold shell that reaches for it gets `ModuleNotFoundError`. Always go through
`poetry run`, or rediscover the venv rather than trusting a remembered path:

```bash
poetry env info --path
```

The GUI stack is **PySide6** (LGPL; only the Essentials modules are imported) +
PyOpenGL + pyqtgraph; geometry is numpy + trimesh + manifold3d. Dev deps add
pytest and ruff. The package is installed editable, so imports resolve from the
working tree.

## Shell quirk on this machine

The Bash tool's wrapper mangles multi-line commands, commands over ~8 KB, and
multi-line `python -c` strings. Keep every invocation to one line; write files
with the Write/Edit tools, and put longer scripts in a file before running them.

## Tests and lint

```bash
poetry run pytest -q
```

```bash
poetry run ruff check mandapa tests
```

`pyproject.toml` scopes `testpaths` to `tests/`. GUI tests set
`QT_QPA_PLATFORM=offscreen` themselves; tests that need a real GL context skip
when none exists.

## Launch the editor

```bash
poetry run temple-gen
```

Optionally `poetry run temple-gen path/to/design.xml` via `--params`. This
blocks on the Qt event loop — run it in the background if the session needs to
keep working. Entry point: `mandapa.gui.app:main`.

## Screenshot / render check

The editor can render its first build to a PNG and quit, which is how renders
are verified without a human at the screen:

```bash
poetry run temple-gen --params examples/NAME.xml --screenshot out/NAME.png
```

`--screenshot-window out/window.png` grabs the whole main window instead of the
viewport. Read the PNG afterwards and look at it; do not trust a green test
suite to say the frame is right.

## Headless export

```bash
poetry run mandapa --out out/mandapa.stl
```

`--params FILE` (.xml or legacy .json), `--preset NAME` / `--list-presets`,
`--random [SEED]`, `--set name=value`, `--format stl|3mf`, `--split`,
`--hollow MM`, `--bed X,Y,Z`. It prints the print report (size, volume,
overhangs, bridges, watertightness) and exits non-zero if a part is not
watertight.
