"""The editor's single source of truth, with no Qt in it.

Why one owner, and commands rather than setters
-----------------------------------------------
The first window kept its state in the widgets: the parameter form *was* the parameters,
and the main window asked it for values when it wanted to build.  That shape has one copy
of the state too, but it is the wrong copy — a form cannot be opened headlessly, cannot
be told to undo, and cannot be saved without a second record being assembled from it.
So there is exactly one owner here, a :class:`Document`, and views never write to it:
they submit :class:`Command` objects that know how to apply and revert themselves, the
document applies them, records them, and tells its subscribers what changed.  Commands
are what make undo possible at all — with setters there is nothing central to record —
and they are what lets a preset apply parameters and look together as one step
(:class:`Macro`) rather than two the author has to undo twice.

Why no Qt
---------
The CLI, the tests and the file format all need the document, and none of them has a
display.  This module therefore imports nothing from ``mandapa.gui`` and nothing from
PySide6; subscribers are plain callables, not signals, and ``tests/test_dependency_rule``
parses every module's imports to hold that line rather than trusting this paragraph.
The GUI adapts — a Qt view subscribes a bound method, one line — where the reverse, a
Qt-bound document, would cost every headless caller an import of Qt.

Why coalescing, and why sealing is explicit
-------------------------------------------
A slider drag is one edit to the author, not two hundred.  A command may carry a
``coalesce`` key; consecutive commands with the same key fold into the step at the top
of the undo stack until :meth:`Document.seal` is called (the GUI calls it when the slider
is released) or something else intervenes: an undo, a command with another key.  The
alternative, timing-based coalescing ("edits within 300 ms merge"), was rejected because
it makes undo granularity depend on how fast the author moves — two deliberate clicks on
a spinbox would merge while a slow drag would split.

Why listeners hear each event once per step
-------------------------------------------
A step may touch the design more than once — a macro of three commands, a replace of
params and look — but a view wants to rebuild once, after it.  Emission is therefore
batched per :meth:`Document.submit`, :meth:`Document.undo` and :meth:`Document.redo`:
each distinct event is delivered once, after the step is recorded and in a fixed order
(``params``, ``look``, ``history``), so a listener that asks ``can_undo`` or ``dirty``
from inside a ``"params"`` callback sees the finished state, and an undo that reverts
the look before the params still announces them the same way round.

What is not design state
------------------------
:attr:`Document.camera` and :attr:`Document.title` ride with the file but are not the
design: moving the view is not an edit, so neither is undoable and neither makes the
document dirty.  :attr:`Document.revision` counts design changes only, for the same
reason — it exists so a view that renders from the design can ask "anything since I last
looked?" without comparing records.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from .io import load_any, save_temple
from .look import Look
from .params import MandapaParams

__all__ = ["Command", "Document", "Macro", "ReplaceDesign", "SetLook", "SetParams"]

Listener = Callable[[str], None]

#: Events a :class:`Document` emits, in the order a step delivers them.
EVENTS = ("params", "look", "history", "path")


@runtime_checkable
class Command(Protocol):
    """A reversible edit.  ``text`` is what the Undo menu item says."""

    text: str

    def apply(self, document: Document) -> None: ...

    def revert(self, document: Document) -> None: ...

    def merge(self, other: Command) -> bool:
        """Absorb ``other`` (already applied) into this step; return False to keep it separate."""
        ...


@dataclass
class SetParams:
    """Change some parameters.  ``before`` is captured on first apply, so a coalesced run
    reverts to the value from before the drag, not before its last tick."""

    changes: dict[str, Any]
    text: str = "Edit parameters"
    coalesce: str | None = None
    before: dict[str, Any] = field(default_factory=dict)

    def apply(self, document: Document) -> None:
        after = document.params.with_(**self.changes)  # raises TypeError for an unknown field
        if not self.before:
            self.before = {k: getattr(document.params, k) for k in self.changes}
        document._set_params(after)

    def revert(self, document: Document) -> None:
        document._set_params(document.params.with_(**self.before))

    def merge(self, other: Command) -> bool:
        if not isinstance(other, SetParams) or self.coalesce is None or other.coalesce != self.coalesce:
            return False
        for key, value in other.before.items():
            self.before.setdefault(key, value)
        self.changes = {**self.changes, **other.changes}
        return True


@dataclass
class SetLook:
    """Change some look fields.  Validates before touching the document, so a bad value
    raises ``ValueError`` and leaves nothing behind."""

    changes: dict[str, Any]
    text: str = "Edit look"
    coalesce: str | None = None
    before: dict[str, Any] = field(default_factory=dict)

    def apply(self, document: Document) -> None:
        after = document.look.with_(**self.changes).validate()
        if not self.before:
            self.before = {k: getattr(document.look, k) for k in self.changes}
        document._set_look(after)

    def revert(self, document: Document) -> None:
        document._set_look(document.look.with_(**self.before))

    def merge(self, other: Command) -> bool:
        if not isinstance(other, SetLook) or self.coalesce is None or other.coalesce != self.coalesce:
            return False
        for key, value in other.before.items():
            self.before.setdefault(key, value)
        self.changes = {**self.changes, **other.changes}
        return True


@dataclass
class ReplaceDesign:
    """Swap the whole design: presets, examples, randomise, reset.

    ``look=None`` keeps the current look and leaves it alone on revert too, so a
    parameters-only replace never emits ``"look"``.
    """

    params: MandapaParams
    look: Look | None = None
    text: str = "Replace design"
    before: tuple[MandapaParams, Look] | None = None

    def apply(self, document: Document) -> None:
        look = self.look.validate() if self.look is not None else None  # before touching anything
        if self.before is None:
            self.before = (document.params, document.look)
        document._set_params(self.params)
        if look is not None:
            document._set_look(look)

    def revert(self, document: Document) -> None:
        assert self.before is not None
        document._set_params(self.before[0])
        if self.look is not None:
            document._set_look(self.before[1])

    def merge(self, other: Command) -> bool:
        return False


@dataclass
class Macro:
    """Several commands as one undo step: a preset that applies params and look together.

    Applies in order and reverts in reverse, so a later command that read state written
    by an earlier one is undone before it.  All or nothing: if a command fails to apply,
    the ones before it are reverted and the error propagates, so the document is never
    left half way through a step with nothing on the undo stack to take it back.  Never
    coalesces — a macro is one deliberate act, not a drag.
    """

    commands: Sequence[Command]
    text: str = "Edit"

    def apply(self, document: Document) -> None:
        applied: list[Command] = []
        try:
            for command in self.commands:
                command.apply(document)
                applied.append(command)
        except Exception:
            for command in reversed(applied):
                command.revert(document)
            raise

    def revert(self, document: Document) -> None:
        for command in reversed(self.commands):
            command.revert(document)

    def merge(self, other: Command) -> bool:
        return False


class Document:
    """One design, its undo history, and where it lives on disk.

    Events emitted to subscribers: ``"params"``, ``"look"``, ``"history"`` (anything
    about undo, redo or dirtiness), ``"path"``.
    """

    def __init__(
        self, params: MandapaParams | None = None, look: Look | None = None, path: Path | None = None
    ):
        self._params = params or MandapaParams()
        self._look = look or Look()
        self._path = Path(path) if path else None
        self._undo: list[Command] = []
        self._redo: list[Command] = []
        self._sealed = True
        self._listeners: list[Listener] = []
        self._saved = (self._params, self._look)
        self._revision = 0
        self._pending: list[str] | None = None
        self._import_name = ""
        #: Viewer pose saved with the file; not part of the design, so never undoable.
        self.camera: dict[str, float] | None = None
        #: Authored title, written as the file's ``name``; not the file name.
        self.title = ""
        #: Parameter names the file stated that this build does not know.
        self.ignored: tuple[str, ...] = ()

    # ---- files ------------------------------------------------------------------------
    @classmethod
    def open(cls, path: str | Path) -> Document:
        """Open a ``<temple>`` XML document, or a legacy parameters JSON file.

        A legacy file opens *untitled*, keeping its stem as :attr:`name`: the document
        is XML, and a path ending in ``.json`` is not somewhere :meth:`save` may write
        it, so the first save asks for a path instead of quietly writing beside the old
        file under a name nobody chose.
        """
        path = Path(path)
        file = load_any(path)
        legacy = path.suffix.lower() != ".xml"
        document = cls(file.params, file.look, None if legacy else path)
        document.camera = file.camera
        document.title = file.name
        document.ignored = file.ignored
        if legacy:
            document._import_name = path.stem
        return document

    def save(self, path: str | Path | None = None, camera: dict[str, float] | None = None) -> Path:
        """Write the document as XML; ``path`` defaults to where it was opened from.

        Refuses a path that :func:`~mandapa.io.load_any` would not open as XML, so
        what this writes is what :meth:`open` reads.
        """
        target = Path(path) if path else self._path
        if target is None:
            raise ValueError("document has no path; pass one")
        if target.suffix.lower() != ".xml":
            raise ValueError(f"a temple document is XML; {target} does not end in .xml")
        if camera is not None:
            self.camera = camera
        save_temple(target, self._params, self._look, self.camera, name=self.title)
        self.path = target
        self.mark_saved()
        return target

    # ---- state ------------------------------------------------------------------------
    @property
    def params(self) -> MandapaParams:
        return self._params

    @property
    def look(self) -> Look:
        return self._look

    @property
    def path(self) -> Path | None:
        return self._path

    @path.setter
    def path(self, value: Path | str | None) -> None:
        self._path = Path(value) if value else None
        self._emit("path")

    @property
    def name(self) -> str:
        """What the title bar says: the file's stem, or the imported file's, or untitled."""
        if self._path is not None:
            return self._path.stem
        return self._import_name or "untitled"

    @property
    def dirty(self) -> bool:
        """Whether the design differs from the last saved (or opened) one — by value, so
        an edit undone, or undone by hand, is not an unsaved change."""
        return (self._params, self._look) != self._saved

    @property
    def revision(self) -> int:
        """Increments on every design change: each command, undo or redo that alters the
        parameters or the look.  Monotonic, never reset, cheap to compare."""
        return self._revision

    def mark_saved(self) -> None:
        self._saved = (self._params, self._look)
        self._emit("history")

    # ---- commands ---------------------------------------------------------------------
    def submit(self, command: Command) -> None:
        """Apply ``command`` and record it as the next undo step — or fold it into the
        current one if it coalesces.  A command that raises leaves no trace."""
        with self._batched():
            command.apply(self)
            if not (self._undo and not self._sealed and self._undo[-1].merge(command)):
                self._undo.append(command)
            self._sealed = False
            self._redo.clear()
            self._emit("history")

    def seal(self) -> None:
        """End a coalescing run: the next command starts a new undo step."""
        self._sealed = True

    def undo(self) -> bool:
        if not self._undo:
            return False
        with self._batched():
            command = self._undo.pop()
            command.revert(self)
            self._redo.append(command)
            self._sealed = True
            self._emit("history")
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        with self._batched():
            command = self._redo.pop()
            command.apply(self)
            self._undo.append(command)
            self._sealed = True
            self._emit("history")
        return True

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    @property
    def undo_text(self) -> str:
        return self._undo[-1].text if self._undo else ""

    @property
    def redo_text(self) -> str:
        return self._redo[-1].text if self._redo else ""

    # ---- subscriptions ----------------------------------------------------------------
    def subscribe(self, listener: Listener) -> Callable[[], None]:
        """Register a listener; returns a function that unsubscribes it (idempotent)."""
        self._listeners.append(listener)

        def unsubscribe() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return unsubscribe

    # ---- internals used by commands ---------------------------------------------------
    def _set_params(self, params: MandapaParams) -> None:
        self._params = params
        self._revision += 1
        self._emit("params")

    def _set_look(self, look: Look) -> None:
        self._look = look
        self._revision += 1
        self._emit("look")

    @contextmanager
    def _batched(self) -> Iterator[None]:
        """Collect emissions until the step is done, then deliver each event once, in
        :data:`EVENTS` order whatever order the step touched them in."""
        if self._pending is not None:
            yield
            return
        self._pending = []
        try:
            yield
        finally:
            pending, self._pending = self._pending, None
            ordered = [e for e in EVENTS if e in pending] + [e for e in pending if e not in EVENTS]
            for event in ordered:
                self._emit(event)

    def _emit(self, event: str) -> None:
        if self._pending is not None:
            if event not in self._pending:
                self._pending.append(event)
            return
        for listener in list(self._listeners):
            listener(event)
