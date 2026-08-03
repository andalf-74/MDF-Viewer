"""SearchDialog — Signal Value Search UI (#110).

Non-modal (REQ-SEARCH-015): the table lists one row per signal handed to
set_rows(), with an operator/value pair per row. Only the row-building and
Search-button semantics live here; the actual scan (model.signal_search)
and the cursor/plot side effects (AppController.search_execute) live
elsewhere — this dialog only ever emits the current non-blank rows.
"""

from __future__ import annotations

from typing import Callable

from PyQt6.QtGui import QDoubleValidator
from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import Qt, pyqtSignal

from mdf_viewer.model.signal_search import SearchOperator, SearchRow
from mdf_viewer.view_model.active_signal import ActiveSignal

_COL_NAME = 0
_COL_OPERATOR = 1
_COL_VALUE = 2


def _ro_item(text: str) -> QTableWidgetItem:
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


class SearchDialog(QDialog):
    """Signal Value Search dialog: one editable operator/value row per signal."""

    search_clicked = pyqtSignal(list)  # list[SearchRow]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Search")
        self.setMinimumSize(420, 300)

        self._signals: list[ActiveSignal] = []

        self._tab_label = QLabel()

        self._table = QTableWidget(0, 3, self)
        self._table.setHorizontalHeaderLabels(["Signal", "Operator", "Value"])
        self._table.verticalHeader().setVisible(False)
        header = self._table.horizontalHeader()
        header.setSectionResizeMode(_COL_NAME, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(_COL_OPERATOR, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(_COL_VALUE, QHeaderView.ResizeMode.ResizeToContents)

        self._search_button = QPushButton("Search")
        self._search_button.setEnabled(False)
        self._search_button.clicked.connect(self._on_search_clicked)

        self._no_match_label = QLabel("No match found")
        self._no_match_label.setVisible(False)

        button_row = QHBoxLayout()
        button_row.addWidget(self._search_button)
        button_row.addWidget(self._no_match_label)
        button_row.addStretch()

        layout = QVBoxLayout(self)
        layout.addWidget(self._tab_label)
        layout.addWidget(self._table)
        layout.addLayout(button_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)

    def set_rows(
        self,
        signals: list[ActiveSignal],
        prefill: dict[ActiveSignal, float | tuple[SearchOperator, float]] | None = None,
        tab_name: str | None = None,
        name_for: Callable[[ActiveSignal], str] | None = None,
    ) -> None:
        """Rebuild the table for *signals* (REQ-SEARCH-020), one row each.

        *prefill* (keyed by identity) sets a row's initial operator/value.
        A plain float defaults the operator to equals (REQ-SEARCH-013, the
        AST context-menu pre-fill); a `(SearchOperator, float)` tuple sets
        both explicitly (REQ-SEARCH-018, carrying a value forward across a
        tab switch). *tab_name*, if given, updates the "Searching in: …"
        label (REQ-SEARCH-016). *name_for*, if given, builds each row's
        displayed name (REQ-SEARCH-021) — MainWindow passes
        AppController.format_display_name so a row shows the same
        shortened + measurement-prefixed name the Active Signals Table
        shows, rather than the raw (possibly very long) channel name;
        defaults to the raw channel name when omitted, for callers with no
        controller to format against.
        """
        prefill = prefill or {}
        name_for = name_for or (lambda signal: signal.metadata.name)
        self._signals = list(signals)
        self._table.setRowCount(0)
        self._no_match_label.setVisible(False)
        if tab_name is not None:
            self._tab_label.setText(f"Searching in: {tab_name}")
        for signal in signals:
            row = self._table.rowCount()
            self._table.insertRow(row)
            self._table.setItem(row, _COL_NAME, _ro_item(name_for(signal)))

            combo = QComboBox()
            for op in SearchOperator:
                combo.addItem(op.value, op)
            self._table.setCellWidget(row, _COL_OPERATOR, combo)

            value_edit = QLineEdit()
            value_edit.setValidator(QDoubleValidator())
            if signal in prefill:
                entry = prefill[signal]
                if isinstance(entry, tuple):
                    operator, value = entry
                    combo.setCurrentIndex(list(SearchOperator).index(operator))
                else:
                    value = entry
                value_edit.setText(_format_value(value))
            value_edit.textChanged.connect(self._update_search_enabled)
            self._table.setCellWidget(row, _COL_VALUE, value_edit)
        self._update_search_enabled()

    def current_criteria_by_name(self) -> dict[str, tuple[SearchOperator, float]]:
        """Every row with a non-blank value, keyed by raw channel name.

        Used to carry a search forward across a tab switch (REQ-SEARCH-018)
        — matching by name since a different tab's ActiveSignal instances
        are never the same objects even for "the same" channel.
        """
        result: dict[str, tuple[SearchOperator, float]] = {}
        for i, signal in enumerate(self._signals):
            text = self._table.cellWidget(i, _COL_VALUE).text().strip()
            if not text:
                continue
            try:
                value = float(text)
            except ValueError:
                continue
            operator = self._table.cellWidget(i, _COL_OPERATOR).currentData()
            result[signal.metadata.name] = (operator, value)
        return result

    def show_no_match(self) -> None:
        """Show the inline "No match found" message (REQ-SEARCH-043)."""
        self._no_match_label.setVisible(True)

    def _update_search_enabled(self) -> None:
        """Search is enabled only while at least one row has a value (REQ-SEARCH-025)."""
        self._search_button.setEnabled(any(
            self._table.cellWidget(row, _COL_VALUE).text().strip()
            for row in range(self._table.rowCount())
        ))

    def _on_search_clicked(self) -> None:
        rows: list[SearchRow] = []
        for i, signal in enumerate(self._signals):
            text = self._table.cellWidget(i, _COL_VALUE).text().strip()
            if not text:
                continue
            try:
                value = float(text)
            except ValueError:
                continue
            operator = self._table.cellWidget(i, _COL_OPERATOR).currentData()
            rows.append(SearchRow(signal=signal, operator=operator, value=value))
        self._no_match_label.setVisible(False)
        self.search_clicked.emit(rows)


def _format_value(value: float) -> str:
    if value == int(value):
        return str(int(value))
    return repr(value)
