"""The Help dialog: a view of :mod:`mandapa.help`, plus the verbs the window actually has.

The Verbs tab is generated from the window's own actions — their text, their shortcuts,
their status tips — so it cannot fall behind the toolbar: a key that is not in this dialog
is a key the program does not have.  The other three tabs render the Qt-free record
(description, sources, glossary, licences) that the CLI prints as text; nothing is
authored here twice.
"""

from __future__ import annotations

import importlib.metadata
from html import escape

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QHeaderView,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from .. import help as about

__all__ = ["TABS", "HelpDialog"]

TABS = ("About", "Verbs", "Glossary", "Licences")


def _plain(text: str) -> str:
    """Menu text without its mnemonic ampersand or trailing ellipsis."""
    return text.replace("&", "").rstrip("…").strip()


def _table(columns: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(columns))
    table.setHorizontalHeaderLabels(columns)
    table.verticalHeader().hide()
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setShowGrid(False)
    table.setWordWrap(True)
    header = table.horizontalHeader()
    for i in range(len(columns) - 1):
        header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
    header.setSectionResizeMode(len(columns) - 1, QHeaderView.ResizeMode.Stretch)
    return table


class HelpDialog(QDialog):
    def __init__(self, actions: dict[str, QAction], parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"Help — {about.APP_NAME}")
        self.resize(760, 580)
        self.tabs = QTabWidget()
        self.about_html = self._about_html()
        self.licences_html = self._licences_html()
        self.tabs.addTab(self._browser(self.about_html), TABS[0])
        self.verbs_table = self._verbs(actions)
        self.tabs.addTab(self.verbs_table, TABS[1])
        self.tabs.addTab(self._glossary_page(), TABS[2])
        self.tabs.addTab(self._browser(self.licences_html), TABS[3])
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ---- pages --------------------------------------------------------------------------
    @staticmethod
    def _browser(html: str) -> QTextBrowser:
        browser = QTextBrowser()
        browser.setOpenExternalLinks(True)
        browser.setHtml(html)
        return browser

    @staticmethod
    def _about_html() -> str:
        sources = "".join(
            f"<li><a href='{escape(url)}'>{escape(what)}</a> — {escape(gave)}</li>"
            for what, gave, url in about.SOURCES
        )
        versions = "".join(
            f"<tr><td>{escape(k)}</td><td style='padding-left:1em'>{escape(v)}</td></tr>"
            for k, v in about.build_info().items()
        )
        return (
            f"<h2>{escape(about.APP_NAME)} <small>{escape(about.__version__)}</small></h2>"
            f"<p>{escape(about.DESCRIPTION)}</p>"
            f"<h3>Proportions and vocabulary</h3><ul>{sources}</ul>"
            f"<h3>Versions</h3><table>{versions}</table>"
        )

    @staticmethod
    def _licences_html() -> str:
        rows = []
        for t in about.THIRD_PARTY:
            try:
                version = importlib.metadata.version(t.package)
            except importlib.metadata.PackageNotFoundError:
                version = "—"
            rows.append(
                f"<tr><td><a href='{escape(t.url)}'>{escape(t.package)}</a></td>"
                f"<td style='padding:0 1em'>{escape(version)}</td>"
                f"<td style='padding-right:1em'>{escape(t.licence)}</td><td>{escape(t.role)}</td></tr>"
            )
        return (
            "<h3>Built on</h3><table>"
            "<tr><th align='left'>package</th><th align='left' style='padding:0 1em'>version</th>"
            "<th align='left'>licence</th><th align='left'>role</th></tr>"
            f"{''.join(rows)}</table>"
            f"<p>{escape(about.LICENCE_NOTE)}</p>"
            "<p>Each package ships its own licence text inside the environment's "
            "<code>site-packages</code>.</p>"
        )

    def _verbs(self, actions: dict[str, QAction]) -> QTableWidget:
        table = _table(["Verb", "Keys", "What it does"])
        for action in actions.values():
            keys = ", ".join(s.toString(QKeySequence.SequenceFormat.NativeText) for s in action.shortcuts())
            tip = action.statusTip() or action.toolTip()
            if not keys and not tip:
                continue
            row = table.rowCount()
            table.insertRow(row)
            for column, text in enumerate((_plain(action.text()), keys, tip)):
                item = QTableWidgetItem(text)
                if column == 1:
                    item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                table.setItem(row, column, item)
        return table

    def _glossary_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 6, 0, 0)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Filter terms")
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(self.set_filter)
        layout.addWidget(self.filter)
        self.glossary_table = _table(["Term", "Meaning"])
        for term, meaning in sorted(about.GLOSSARY.items()):
            row = self.glossary_table.rowCount()
            self.glossary_table.insertRow(row)
            self.glossary_table.setItem(row, 0, QTableWidgetItem(term))
            self.glossary_table.setItem(row, 1, QTableWidgetItem(meaning))
        layout.addWidget(self.glossary_table)
        return page

    # ---- queries and verbs ----------------------------------------------------------------
    def verb_rows(self) -> list[tuple[str, str, str]]:
        table = self.verbs_table
        return [
            tuple(table.item(r, c).text() for c in range(3))  # type: ignore[misc]
            for r in range(table.rowCount())
        ]

    def set_filter(self, text: str) -> None:
        needle = text.strip().lower()
        table = self.glossary_table
        for row in range(table.rowCount()):
            haystack = f"{table.item(row, 0).text()} {table.item(row, 1).text()}".lower()
            table.setRowHidden(row, bool(needle) and needle not in haystack)

    def visible_terms(self) -> list[str]:
        table = self.glossary_table
        return [table.item(r, 0).text() for r in range(table.rowCount()) if not table.isRowHidden(r)]

    def show_tab(self, name: str) -> None:
        self.tabs.setCurrentIndex(TABS.index(name))
        self.show()
        self.raise_()
        self.activateWindow()
