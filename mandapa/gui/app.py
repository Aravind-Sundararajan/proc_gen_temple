"""The application: one window that owns a :class:`Document` and wires views to it.

Assembly only.  The window holds the document, builds the docks, the toolbar and the
menus, and forwards document events to the views: parameters to a debounced rebuild,
the look to the viewer, the history to the Undo/Redo labels and the title.  Anything with
behaviour worth testing lives in :mod:`mandapa.document`, :mod:`~mandapa.gui.paramform`,
:mod:`~mandapa.gui.viewer` or :mod:`~mandapa.gui.export_dialog`, because a main window
is the one part of a Qt app that is awkward to test and therefore the worst place for
logic.

The views never write to each other.  The parameter form submits a command, the document
announces it, and the viewer rebuilds; the look panel submits, the document announces,
and the viewer relights.  Undo goes through the same door, so the panels cannot drift
from the preview.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QAction, QFontDatabase, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QDockWidget,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from ..document import Document, ReplaceDesign
from ..params import MandapaParams
from ..presets import PRESETS
from . import icons, theme
from .export_dialog import ExportDialog
from .look_panel import LookPanel
from .paramform import ParamForm
from .prefs import Preferences
from .viewer import Viewer
from .workers import BuildPayload, BuildWorker

__all__ = ["APP_NAME", "EXAMPLES", "MainWindow", "Readout", "main"]

APP_NAME = "Mandapa Generator"
EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
DEBOUNCE_MS = 250
FILE_FILTER = "Temple documents (*.xml);;Legacy parameters (*.json);;All files (*)"


class Readout(QLabel):
    """One fact on the status bar: faces, size, watertightness, a risk percentage.

    A readout that turns red is the only alarm the window raises.  It uses the render's
    own overhang red (:data:`theme.WARN`) for "exceeds the bed" and "not watertight" —
    the same colour that means "this will fail on the printer" on a face.
    """

    def __init__(self, tip: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("readout")
        self.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.setToolTip(tip)
        self.setContentsMargins(8, 0, 8, 0)
        self.warned = False

    def set(self, text: str, warn: bool = False) -> None:
        self.setText(text)
        self.warned = warn
        self.setStyleSheet(f"color: {theme.WARN};" if warn else "")


class BedDialog(QDialog):
    """Three numbers: the plate and the height the status bar checks the model against."""

    def __init__(self, size: tuple[float, float, float], parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Print bed")
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.spins: list[QDoubleSpinBox] = []
        for label, value in zip(("Width (X)", "Depth (Y)", "Height (Z)"), size):
            spin = QDoubleSpinBox()
            spin.setRange(10.0, 2000.0)
            spin.setDecimals(0)
            spin.setSuffix(" mm")
            spin.setValue(float(value))
            form.addRow(label, spin)
            self.spins.append(spin)
        layout.addLayout(form)
        note = QLabel("Drawn around the origin in the viewport; the status bar warns when the export exceeds it.")
        note.setObjectName("note")
        note.setWordWrap(True)
        layout.addWidget(note)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def size_mm(self) -> tuple[float, float, float]:
        return tuple(float(s.value()) for s in self.spins)


class MainWindow(QMainWindow):
    def __init__(
        self,
        document: Document | None = None,
        prefs: Preferences | None = None,
        autobuild: bool = True,
    ):
        super().__init__()
        self.prefs = prefs if prefs is not None else Preferences()
        self.document = document if document is not None else Document()
        self._unsubscribe: Callable[[], None] | None = None
        self._worker: BuildWorker | None = None
        self._pending = False
        self._payload: BuildPayload | None = None
        self._first_frame = self.document.camera is None
        self._export_dialog: ExportDialog | None = None
        self._group_actions: dict[str, QAction] = {}
        self._bed_warned = False
        #: Off, the window builds only when asked (tests drive it without worker threads).
        self._autobuild = autobuild
        #: Whether closing writes the dock layout back to the preferences.  A headless
        #: screenshot run opens at the default layout and must not make that the saved one.
        self.remember_layout = True
        self.actions: dict[str, QAction] = {}
        self.menus: dict[str, QMenu] = {}

        self.viewer = Viewer(self.document.look)
        self.setCentralWidget(self.viewer)
        self._build_docks()
        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        self._build_status()

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(DEBOUNCE_MS)
        self._timer.timeout.connect(self.start_build)

        self._subscribe(self.document)
        if self.document.camera:
            self.viewer.set_camera(self.document.camera)
        self.viewer.set_bed(self.prefs.bed(), self.document.params.scale)
        self.viewer.set_bed_visible(self.actions["bed"].isChecked())
        self.viewer.set_grid_visible(self.actions["grid"].isChecked())
        self.viewer.set_highlight(self.actions["highlight"].isChecked())

        app = QApplication.instance()
        if app is not None:
            # Moving focus ends any gesture: tabbing from one field to the next starts a
            # new undo step even when neither field reported a release.
            app.focusChanged.connect(self._focus_changed)

        # The viewport owns the keyboard at start, so F, 1/3/7 and Space reach it instead
        # of being typed into the first field; Esc in the filter hands focus back.
        self.form.filter.escaped.connect(self.viewer.setFocus)
        self.viewer.setFocus()

        self.resize(1500, 940)
        self._refresh_title()
        self._refresh_history()
        if autobuild:
            self.start_build()

    # ---- assembly -------------------------------------------------------------------------
    def _build_docks(self) -> None:
        self.form = ParamForm(self.document, self.prefs)
        self.params_dock = self._dock("Parameters", self.form, "dock_parameters", Qt.DockWidgetArea.LeftDockWidgetArea)

        self.look_panel = LookPanel(self.document)
        self.look_dock = self._dock("Look", self.look_panel, "dock_look", Qt.DockWidgetArea.RightDockWidgetArea)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(600)
        self.log.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.log_dock = self._dock("Build log", self.log, "dock_log", Qt.DockWidgetArea.BottomDockWidgetArea)

        # The render is the product, so it gets the room: these are the floors the docks
        # stay legible at, not their share of the window.
        self.resizeDocks([self.params_dock, self.look_dock], [390, 290], Qt.Orientation.Horizontal)
        self.resizeDocks([self.log_dock], [120], Qt.Orientation.Vertical)

    def _dock(self, title: str, widget: QWidget, name: str, area: Qt.DockWidgetArea) -> QDockWidget:
        dock = QDockWidget(title.upper(), self)
        dock.setObjectName(name)
        dock.setWidget(widget)
        dock.setFeatures(
            QDockWidget.DockWidgetFeature.DockWidgetMovable | QDockWidget.DockWidgetFeature.DockWidgetClosable
        )
        self.addDockWidget(area, dock)
        return dock

    def _action(
        self,
        key: str,
        text: str,
        slot: Callable[..., object] | None,
        shortcut: str | QKeySequence | list | None = None,
        icon: str | None = None,
        tip: str = "",
        checkable: bool = False,
        checked: bool = False,
        owner: QWidget | None = None,
    ) -> QAction:
        action = QAction(text, self)
        if icon:
            action.setIcon(icons.icon(icon))
        if shortcut is not None:
            if isinstance(shortcut, list):
                action.setShortcuts([QKeySequence(s) for s in shortcut])
            else:
                action.setShortcut(QKeySequence(shortcut))
        action.setCheckable(checkable)
        action.setChecked(checked)
        if tip:
            action.setToolTip(tip)
            action.setStatusTip(tip)
        if slot is not None:
            if checkable:
                action.toggled.connect(slot)
            else:
                action.triggered.connect(lambda checked=False: slot())
        # Registered on a widget so the shortcut fires while focus is in the viewport,
        # which is where it lives most of the time.
        if owner is not None:
            action.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            owner.addAction(action)
        else:
            self.addAction(action)
        self.actions[key] = action
        return action

    def _build_actions(self) -> None:
        prefs = self.prefs
        self._action("new", "&New", self.new, QKeySequence.StandardKey.New, "new", "Start an untitled design")
        self._action("open", "&Open…", self.open, QKeySequence.StandardKey.Open, "open", "Open a temple document (.xml) or legacy parameters (.json)")
        self._action("save", "&Save", self.save, QKeySequence.StandardKey.Save, "save", "Save the design, its look and the camera")
        self._action("save_as", "Save &As…", self.save_as, QKeySequence.StandardKey.SaveAs, None, "Save under a new name")
        self._action("export", "&Export…", self.export, "Ctrl+E", "export", "Union the model and write print parts (Ctrl+E)")
        self._action("screenshot", "Screens&hot…", self.screenshot, "Ctrl+P", "screenshot", "Save the viewport as a PNG (Ctrl+P)")
        self._action("quit", "&Quit", self.close, QKeySequence.StandardKey.Quit)

        self._action("undo", "&Undo", self._undo, QKeySequence.StandardKey.Undo, "undo")
        self._action("redo", "&Redo", self._redo, ["Ctrl+Y", "Ctrl+Shift+Z"], "redo")
        self._action("randomise", "&Randomise", self.randomise, "Ctrl+R", "randomise", "A plausible variant: same vocabulary, new proportions (Ctrl+R)")
        self._action("reset", "Reset to &defaults", self.reset_defaults, None, "reset", "Every parameter back to its default")
        self._action("find", "&Find parameter", self.form.focus_filter, "Ctrl+F", "search", "Jump to the parameter filter (Ctrl+F)")

        self._action("build", "&Build", self.start_build, "F5", "build", "Rebuild the preview now (F5)")
        self._action("fit", "&Fit", self.viewer.fit_current, "F", "fit", "Frame the model (F)")
        self._action("front", "&Front", lambda: self.viewer.snap("front"), "1", "front", "Look at the steps' side (1)")
        self._action("back", "Back", lambda: self.viewer.snap("back"), "Ctrl+1", None, "Look at the back (Ctrl+1)")
        self._action("side", "&Side", lambda: self.viewer.snap("right"), "3", "side", "Look from +X (3)")
        self._action("left", "Left", lambda: self.viewer.snap("left"), "Ctrl+3", None, "Look from -X (Ctrl+3)")
        self._action("top", "&Top", lambda: self.viewer.snap("top"), "7", "top", "The plan (7)")
        self._action("bottom", "Bottom", lambda: self.viewer.snap("bottom"), "Ctrl+7", None, "The undersides (Ctrl+7)")
        self._action("ortho", "&Orthographic", self.viewer.set_orthographic, "O", "ortho", "Parallel projection (O)", checkable=True)
        self._action(
            "turntable", "Turn&table", self.viewer.set_turntable, "Space", "turntable",
            "Slow auto-orbit; Space toggles it while the viewport has focus", checkable=True, owner=self.viewer,
        )
        self.viewer.turntable_changed.connect(self._sync_turntable)

        self._action(
            "highlight", "Highlight &print risks", self._set_highlight, "H", "risks",
            "Colour overhangs steeper than 45° and flat undersides (H)", checkable=True, checked=prefs.flag("highlight", True),
        )
        self._action(
            "union", "&Union preview", self._set_union, "U", "union",
            "Preview the boolean union — slower, but the exact export geometry (U)", checkable=True,
        )
        self._action("wireframe", "&Wireframe", self.viewer.set_wireframe, "W", "wireframe", "Draw edges over the faces (W)", checkable=True)
        self._action("grid", "&Grid", self._set_grid, "G", "grid", "The 10 mm floor grid (G)", checkable=True, checked=prefs.flag("grid", True))
        self._action("bed", "Print &bed", self._set_bed_visible, "B", "bed", "Outline the printer's plate (B)", checkable=True, checked=prefs.flag("bed", True))
        self._action("bed_size", "Print bed si&ze…", self.edit_bed, None, None, "The plate and height the model is checked against")

    def _build_menus(self) -> None:
        a = self.actions
        file_menu = self.menuBar().addMenu("&File")
        self.menus["file"] = file_menu
        file_menu.addAction(a["new"])
        file_menu.addAction(a["open"])
        self.recent_menu = file_menu.addMenu("Open &Recent")
        self.recent_menu.aboutToShow.connect(self._fill_recent_menu)
        self.examples_menu: QMenu | None = None
        if EXAMPLES.is_dir():
            self.examples_menu = file_menu.addMenu("Open E&xample")
            self.examples_menu.aboutToShow.connect(self._fill_examples_menu)
        file_menu.addSeparator()
        file_menu.addAction(a["save"])
        file_menu.addAction(a["save_as"])
        file_menu.addSeparator()
        file_menu.addAction(a["export"])
        file_menu.addAction(a["screenshot"])
        file_menu.addSeparator()
        file_menu.addAction(a["quit"])

        edit_menu = self.menuBar().addMenu("&Edit")
        self.menus["edit"] = edit_menu
        edit_menu.addAction(a["undo"])
        edit_menu.addAction(a["redo"])
        edit_menu.addSeparator()
        edit_menu.addAction(a["randomise"])
        edit_menu.addAction(a["reset"])
        presets = edit_menu.addMenu("&Presets")
        for name, params in PRESETS.items():
            action = QAction(name, self)
            action.triggered.connect(lambda checked=False, n=name, p=params: self.apply_preset(n, p))
            presets.addAction(action)
        self.menus["presets"] = presets
        edit_menu.addSeparator()
        edit_menu.addAction(a["find"])

        view_menu = self.menuBar().addMenu("&View")
        self.menus["view"] = view_menu
        for key in ("fit", "front", "back", "side", "left", "top", "bottom"):
            view_menu.addAction(a[key])
        view_menu.addSeparator()
        view_menu.addAction(a["ortho"])
        view_menu.addAction(a["turntable"])
        view_menu.addSeparator()
        for key in ("highlight", "union", "wireframe", "grid", "bed", "bed_size"):
            view_menu.addAction(a[key])
        view_menu.addSeparator()
        self.parts_menu = view_menu.addMenu("&Parts")
        self.parts_menu.setToolTip("Show or hide each build group — hide the roof to look inside")
        self.menus["parts"] = self.parts_menu
        self._refresh_group_menu([])
        view_menu.addSeparator()
        for dock in (self.params_dock, self.look_dock, self.log_dock):
            toggle = dock.toggleViewAction()
            toggle.setText(dock.windowTitle().capitalize())
            view_menu.addAction(toggle)

        build_menu = self.menuBar().addMenu("&Build")
        self.menus["build"] = build_menu
        build_menu.addAction(a["build"])
        build_menu.addAction(a["union"])
        build_menu.addSeparator()
        build_menu.addAction(a["export"])

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Verbs", self)
        toolbar.setObjectName("toolbar_main")
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        # Icon beside text: these are verbs an author reads, and the glyph makes the row
        # scannable while the word keeps it unambiguous.
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toolbar.setIconSize(QSize(16, 16))
        a = self.actions
        toolbar.addAction(a["build"])
        toolbar.addSeparator()
        for key in ("fit", "front", "side", "top", "ortho"):
            toolbar.addAction(a[key])
        toolbar.addSeparator()
        for key in ("highlight", "union", "turntable"):
            toolbar.addAction(a[key])
        toolbar.addSeparator()
        for key in ("screenshot", "randomise", "export"):
            toolbar.addAction(a[key])
        self.addToolBar(toolbar)
        self.toolbar = toolbar

    def _build_status(self) -> None:
        bar = self.statusBar()
        self.message = QLabel("Ready")
        self.message.setObjectName("readout")
        bar.addWidget(self.message, 1)
        self.busy = QProgressBar()
        self.busy.setRange(0, 0)
        self.busy.setTextVisible(False)
        self.busy.setFixedWidth(90)
        self.busy.hide()
        bar.addWidget(self.busy)
        self.readouts = {
            "faces": Readout("Triangles in the preview"),
            "size": Readout("Export size, width × depth × height, after the export scale"),
            "watertight": Readout("Whether the unioned mesh is a closed shell (union preview only)"),
            "overhang": Readout("Share of the surface sloping down steeper than 45° — needs support"),
            "bridge": Readout("Share of the surface that is a flat underside — bridges between beams"),
        }
        for readout in self.readouts.values():
            bar.addPermanentWidget(readout)

    # ---- the document ---------------------------------------------------------------------
    def _subscribe(self, document: Document) -> None:
        if self._unsubscribe is not None:
            self._unsubscribe()
        self._unsubscribe = document.subscribe(self._on_document_event)

    def _on_document_event(self, event: str) -> None:
        if event == "params":
            if self._autobuild:
                self._timer.start()
        elif event == "look":
            self.viewer.set_look(self.document.look)
        elif event == "history":
            self._refresh_history()
        elif event == "path":
            self._refresh_title()

    def set_document(self, document: Document) -> None:
        """Swap in another document — a fresh history, its own look and camera."""
        self._timer.stop()
        self.document = document
        self._subscribe(document)
        self.form.set_document(document)
        self.look_panel.set_document(document)
        self.viewer.set_look(document.look)
        self.viewer.set_turntable(False)
        if document.camera:
            self.viewer.set_camera(document.camera)
            self._first_frame = False
        else:
            self._first_frame = True
        self._refresh_title()
        self._refresh_history()
        if self._autobuild:
            self.start_build()

    def _focus_changed(self, old: QWidget | None, new: QWidget | None) -> None:
        self.document.seal()

    def _refresh_title(self) -> None:
        mark = "*" if self.document.dirty else ""
        self.setWindowTitle(f"{self.document.name}{mark} — {APP_NAME}")

    def _refresh_history(self) -> None:
        document = self.document
        undo, redo = self.actions["undo"], self.actions["redo"]
        undo.setEnabled(document.can_undo)
        redo.setEnabled(document.can_redo)
        undo.setText(f"&Undo {document.undo_text}".rstrip())
        redo.setText(f"&Redo {document.redo_text}".rstrip())
        self._refresh_title()

    def _undo(self) -> None:
        self.document.undo()

    def _redo(self) -> None:
        self.document.redo()

    # ---- building -------------------------------------------------------------------------
    def start_build(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            self._pending = True
            return
        self._pending = False
        self._set_busy(True, "Building…" if not self.actions["union"].isChecked() else "Building and unioning…")
        worker = BuildWorker(self.document.params, self.actions["union"].isChecked())
        worker.done.connect(self._build_done)
        worker.failed.connect(self._build_failed)
        # The pending rebuild waits for *finished*, not for the result: the result arrives
        # while the thread may still be winding down, and a restart attempted then would
        # see it running, mark itself pending again, and never be retried.
        worker.finished.connect(lambda w=worker: self._worker_finished(w))
        self._worker = worker
        worker.start()

    def _worker_finished(self, worker: BuildWorker) -> None:
        if self._worker is worker:
            self._worker = None
        worker.deleteLater()
        if self._pending and not self.is_building():
            self.start_build()

    def is_building(self) -> bool:
        return self._worker is not None and self._worker.isRunning()

    def wait_idle(self, timeout_ms: int = 30000) -> bool:
        """Spin the event loop until no build is running or pending; for scripts and tests."""
        app = QApplication.instance()
        from time import monotonic

        deadline = monotonic() + timeout_ms / 1000.0
        while monotonic() < deadline:
            if app is not None:
                app.processEvents()
            if not self.is_building() and not self._pending and not self._timer.isActive():
                return True
            if self._worker is not None:
                self._worker.wait(20)
        return False

    def _set_busy(self, busy: bool, message: str) -> None:
        self.busy.setVisible(busy)
        self.message.setText(message)

    def _build_done(self, payload: BuildPayload) -> None:
        self._payload = payload
        scale = payload.result.params.scale if payload.result.params else 1.0
        self.viewer.set_build(payload.groups)
        self.viewer.set_bed(self.prefs.bed(), scale)
        # Only groups that drew something: the viewer skips empty ones (no steps, flat roof),
        # and a toggle for a group that is not there would be a lie.
        self._refresh_group_menu([n for n, g in payload.groups.items() if len(g.solid.faces)])
        if self._first_frame:
            self.viewer.fit_current()
            self._first_frame = False
        self._refresh_readouts(payload)
        for note in payload.result.notes:
            self.log.appendPlainText(f"note: {note}")
        self._set_busy(False, "Ready")

    def _build_failed(self, message: str) -> None:
        self._set_busy(False, "Build failed — see the log")
        self.log.appendPlainText(message)

    def _refresh_readouts(self, payload: BuildPayload) -> None:
        scale = payload.result.params.scale if payload.result.params else 1.0
        lo, hi = payload.bounds
        size = tuple(float(v) * scale for v in (hi - lo))
        bed = self.prefs.bed()
        exceeds = any(s > b + 1e-6 for s, b in zip(size, bed))
        self.readouts["faces"].set(f"{payload.faces:,} faces")
        size_text = "{:.1f} × {:.1f} × {:.1f} mm".format(*size)
        if exceeds:
            size_text += "  exceeds bed {:g} × {:g} × {:g}".format(*bed)
        self.readouts["size"].set(size_text, warn=exceeds)
        if exceeds and not self._bed_warned:
            self.log.appendPlainText(
                "warning: the model exceeds the print bed ({:g} × {:g} × {:g} mm); lower the export scale "
                "or enlarge the bed under View".format(*bed)
            )
        self._bed_warned = exceeds
        if payload.report is not None:
            watertight = payload.report.watertight
            text = "watertight" if watertight else "NOT watertight"
            text += f"  {payload.report.volume_cm3:.1f} cm³"
            self.readouts["watertight"].set(text, warn=not watertight)
        else:
            self.readouts["watertight"].set("shells (no union)")
        self.readouts["overhang"].set(f"overhang {100 * payload.overhang_fraction:.1f}%")
        self.readouts["bridge"].set(f"bridge {100 * payload.bridge_fraction:.1f}%")

    def _refresh_group_menu(self, names: list[str]) -> None:
        """One toggle per build group, regenerated from the keys the builder reports."""
        menu = self.parts_menu
        for name in list(self._group_actions):
            if name not in names:
                menu.removeAction(self._group_actions.pop(name))
        for name in names:
            if name in self._group_actions:
                continue
            action = QAction(name.capitalize(), self)
            action.setCheckable(True)
            action.setChecked(self.viewer.is_group_visible(name))
            action.toggled.connect(lambda on, n=name: self.viewer.set_group_visible(n, on))
            menu.addAction(action)
            self._group_actions[name] = action
        menu.setEnabled(bool(names))

    # ---- view toggles ---------------------------------------------------------------------
    def _set_highlight(self, on: bool) -> None:
        self.viewer.set_highlight(on)
        self.prefs.set_flag("highlight", on)

    def _set_union(self, on: bool) -> None:
        self.start_build()

    def _set_grid(self, on: bool) -> None:
        self.viewer.set_grid_visible(on)
        self.prefs.set_flag("grid", on)

    def _set_bed_visible(self, on: bool) -> None:
        self.viewer.set_bed_visible(on)
        self.prefs.set_flag("bed", on)

    def _sync_turntable(self, on: bool) -> None:
        action = self.actions["turntable"]
        if action.isChecked() != on:
            action.blockSignals(True)
            action.setChecked(on)
            action.blockSignals(False)

    def edit_bed(self) -> None:
        dialog = BedDialog(self.prefs.bed(), self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.set_bed(dialog.size_mm())

    def set_bed(self, size: tuple[float, float, float]) -> None:
        self.prefs.set_bed(size)
        scale = self.document.params.scale
        self.viewer.set_bed(size, scale)
        if self._payload is not None:
            self._refresh_readouts(self._payload)

    # ---- design verbs ---------------------------------------------------------------------
    def randomise(self) -> None:
        self.document.seal()
        self.document.submit(ReplaceDesign(self.document.params.randomized(), text="Randomise"))
        self.document.seal()

    def reset_defaults(self) -> None:
        self.document.seal()
        self.document.submit(ReplaceDesign(MandapaParams(), text="Reset to defaults"))
        self.document.seal()

    def apply_preset(self, name: str, params: MandapaParams) -> None:
        self.document.seal()
        self.document.submit(ReplaceDesign(params, text=f"Preset {name}"))
        self.document.seal()

    # ---- files ----------------------------------------------------------------------------
    def new(self) -> None:
        if self._confirm_discard():
            self.set_document(Document())
            self.log.appendPlainText("new design")

    def open(self) -> None:
        start = str(self.document.path.parent if self.document.path else Path.cwd())
        path, _ = QFileDialog.getOpenFileName(self, "Open design", start, FILE_FILTER)
        if path:
            self.open_path(Path(path))

    def open_path(self, path: Path, confirm: bool = True) -> bool:
        if confirm and not self._confirm_discard():
            return False
        try:
            document = Document.open(path)
        except Exception as exc:  # noqa: BLE001 - any reader failure is the user's news
            QMessageBox.critical(self, "Open failed", f"{Path(path).name}\n\n{exc}")
            self.prefs.remove_recent(path)
            return False
        self.set_document(document)
        self.prefs.add_recent(path)
        title = f" — {document.title!r}" if document.title else ""
        self.log.appendPlainText(f"opened {path}{title}")
        if document.ignored:
            self.log.appendPlainText(
                "note: the file names parameters this build does not know, ignored: "
                + ", ".join(document.ignored)
            )
        return True

    def save(self) -> bool:
        if self.document.path is None or self.document.path.suffix.lower() != ".xml":
            return self.save_as()
        return self._save_to(self.document.path)

    def save_as(self) -> bool:
        current = self.document.path
        suggested = current.with_suffix(".xml") if current else Path.cwd() / f"{self.document.name}.xml"
        path, _ = QFileDialog.getSaveFileName(self, "Save design", str(suggested), "Temple documents (*.xml)")
        if not path:
            return False
        return self._save_to(Path(path).with_suffix(".xml"))

    def _save_to(self, path: Path) -> bool:
        try:
            self.document.save(path, camera=self.viewer.camera())
        except Exception as exc:  # noqa: BLE001 - report, do not crash
            QMessageBox.critical(self, "Save failed", f"{path.name}\n\n{exc}")
            return False
        self.prefs.add_recent(path)
        self.log.appendPlainText(f"saved {path}")
        self._refresh_title()
        return True

    def _confirm_discard(self) -> bool:
        """Ask before losing edits; Save answers the question by saving."""
        if not self.document.dirty:
            return True
        box = QMessageBox(self)
        box.setWindowTitle("Unsaved changes")
        box.setText(f"{self.document.name} has unsaved changes.")
        box.setInformativeText("Save them before continuing?")
        box.setStandardButtons(
            QMessageBox.StandardButton.Save | QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel
        )
        box.setDefaultButton(QMessageBox.StandardButton.Save)
        answer = box.exec()
        if answer == QMessageBox.StandardButton.Save:
            return self.save()
        return answer == QMessageBox.StandardButton.Discard

    def _fill_recent_menu(self) -> None:
        menu = self.recent_menu
        menu.clear()
        paths = self.prefs.recent()
        for path in paths:
            action = QAction(path.name, self)
            action.setToolTip(str(path))
            action.setStatusTip(str(path))
            action.triggered.connect(lambda checked=False, p=path: self.open_path(p))
            menu.addAction(action)
        if paths:
            menu.addSeparator()
            clear = QAction("Clear list", self)
            clear.triggered.connect(self.prefs.clear_recent)
            menu.addAction(clear)
        else:
            empty = QAction("No recent files", self)
            empty.setEnabled(False)
            menu.addAction(empty)

    def _fill_examples_menu(self) -> None:
        menu = self.examples_menu
        if menu is None:
            return
        menu.clear()
        paths = sorted(EXAMPLES.glob("*.xml")) if EXAMPLES.is_dir() else []
        for path in paths:
            action = QAction(path.stem.replace("_", " "), self)
            action.triggered.connect(lambda checked=False, p=path: self.open_path(p))
            menu.addAction(action)
        if not paths:
            empty = QAction("No examples found", self)
            empty.setEnabled(False)
            menu.addAction(empty)

    def export(self) -> None:
        if self._payload is None:
            self.message.setText("Nothing built yet — wait for the preview")
            return
        if self._export_dialog is not None and self._export_dialog.is_running():
            self._export_dialog.show()
            self._export_dialog.raise_()
            return
        stem = self.document.path.stem if self.document.path else self.document.name
        folder = self.document.path.parent if self.document.path else Path.cwd()
        dialog = ExportDialog(self._payload.result, self, suggested=folder / f"{stem}.stl", bed=self.prefs.bed())
        dialog.logged.connect(self.log.appendPlainText)
        dialog.exported.connect(self._exported)
        self._export_dialog = dialog
        dialog.show()

    def _exported(self, paths: list[str]) -> None:
        names = ", ".join(Path(p).name for p in paths)
        self.message.setText(f"Exported {names}")

    def screenshot(self) -> None:
        suggested = Path.cwd() / f"{self.document.name}.png"
        path, _ = QFileDialog.getSaveFileName(self, "Save screenshot", str(suggested), "PNG images (*.png)")
        if not path:
            return
        if self.save_screenshot(Path(path)):
            self.log.appendPlainText(f"screenshot {path}")
            self.message.setText(f"Saved {Path(path).name}")

    def save_screenshot(self, path: Path, whole_window: bool = False) -> bool:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        if whole_window:
            return bool(self.grab().save(str(path)))
        return bool(self.viewer.grabFramebuffer().save(str(path)))

    def closeEvent(self, event) -> None:
        if not self._confirm_discard():
            event.ignore()
            return
        if self.remember_layout:
            self.prefs.save_window(self)
        self.viewer.set_turntable(False)
        if self._worker is not None and self._worker.isRunning():
            self._worker.wait(10000)
        if self._export_dialog is not None and self._export_dialog.is_running():
            self._export_dialog._worker.wait(30000)
        event.accept()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="temple-gen", description="Mandapa generator GUI.")
    ap.add_argument("file", nargs="?", help="temple document (.xml) or legacy parameters (.json) to open")
    ap.add_argument("--params", "-p", help="document or parameters file to load at start-up")
    ap.add_argument("--screenshot", metavar="PNG", help="render the first build to a PNG and quit")
    ap.add_argument("--screenshot-window", metavar="PNG", help="grab the whole window to a PNG and quit")
    args, qt_args = ap.parse_known_args(argv)

    app = QApplication([sys.argv[0], *qt_args])
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("mandapa")
    # The entrypoint dresses the app; the library never does, so tests meet stock widgets.
    theme.apply(app)
    app.setWindowIcon(icons.icon("temple", theme.ACCENT))

    path = args.params or args.file
    # A window given a file builds that file, not the default design first.
    window = MainWindow(autobuild=path is None)
    headless = bool(args.screenshot or args.screenshot_window)
    window.remember_layout = not headless
    if not headless:
        window.prefs.restore_window(window)
    if path:
        window._autobuild = True
        if not window.open_path(Path(path), confirm=False):
            window.start_build()
    window.show()

    if headless:

        def grab() -> None:
            if window.is_building() or window._pending or window._timer.isActive():
                QTimer.singleShot(100, grab)
                return
            # One more turn of the loop so the frame the build produced is the one grabbed.
            QTimer.singleShot(400, finish)

        def finish() -> None:
            if args.screenshot:
                window.save_screenshot(Path(args.screenshot))
            if args.screenshot_window:
                window.save_screenshot(Path(args.screenshot_window), whole_window=True)
            window.document.mark_saved()
            app.quit()

        QTimer.singleShot(300, grab)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
