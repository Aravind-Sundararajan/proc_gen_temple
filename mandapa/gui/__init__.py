"""The PySide6 editor.

One owner of state and views that submit commands: :mod:`~mandapa.gui.app` holds a
:class:`~mandapa.document.Document`; :mod:`~mandapa.gui.paramform` and
:mod:`~mandapa.gui.look_panel` submit ``SetParams`` and ``SetLook`` commands and refresh
from the document's events; :mod:`~mandapa.gui.viewer` renders the document's look;
:mod:`~mandapa.gui.workers` build and export off the GUI thread.  :mod:`~mandapa.gui.theme`
dresses the chrome in the viewport's own palette and is applied only by ``main()``;
:mod:`~mandapa.gui.icons` draws every glyph from that palette; :mod:`~mandapa.gui.prefs`
keeps what belongs to the person rather than the design.
"""
