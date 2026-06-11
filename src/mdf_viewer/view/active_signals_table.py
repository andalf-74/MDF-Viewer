"""ActiveSignalsTable — right panel table of signals currently on the plot.

Columns: color swatch | name | cursor 1 value | cursor 2 value | delta.
Cursor-value columns are hidden until cursors are activated.
Buttons: Remove Signal, Remove All.
Selection in this table drives the Signal Info Box via selection_changed.
"""

from __future__ import annotations

import json

from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QKeyEvent
from PyQt6.QtWidgets import (
    QColorDialog,
    QHBoxLayout,
    QHeaderView,
    QMenu,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mdf_viewer.view._mime import SIGNAL_MIME_TYPE
from mdf_viewer.view_model.active_signal import ActiveSignal

_COL_COLOR = 0
_COL_NAME = 1
_COL_C1 = 2
_COL_C2 = 3
_COL_DELTA = 4
_NUM_COLS = 5

_CURSOR_COLS = (_COL_C1, _COL_C2, _COL_DELTA)
_HEADERS = ("", "Signal", "Cursor 1", "Cursor 2", "Δ")


class ActiveSignalsTable(QWidget):
    """Table of active signals with color swatch, name, cursor values, and delta."""

    # active_signal (or None) — emitted when row selection changes
    selection_changed = pyqtSignal(object)
    # active_signal — emitted when Remove Signal is clicked
    remove_requested = pyqtSignal(object)
    # emitted when Remove All is clicked
    remove_all_requested = pyqtSignal()
    # active_signal, new QColor — emitted when user picks a new color
    color_change_requested = pyqtSignal(object, QColor)
    # active_signal — emitted when user selects Toggle Step Mode from context menu
    step_mode_toggle_requested = pyqtSignal(object)
    # list of (group_index, channel_index) — emitted when signals are dropped onto the table
    signals_dropped = pyqtSignal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._signals: list[ActiveSignal] = []
        self._build_ui()

    # ------------------------------------------------------------------
    # Public API (called by AppController)
    # ------------------------------------------------------------------

    def add_row(self, active: ActiveSignal) -> None:
        """Append a row for the given ActiveSignal."""
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._signals.append(active)

        # Color swatch
        swatch = _ColorSwatch(active.color)
        swatch.clicked.connect(
            lambda checked=False, a=active: self._on_color_swatch_clicked(a)
        )
        self._table.setCellWidget(row, _COL_COLOR, swatch)

        # Signal name
        self._table.setItem(row, _COL_NAME, _ro_item(active.metadata.name))

        # Cursor value placeholders (hidden until cursors activated)
        for col in _CURSOR_COLS:
            self._table.setItem(row, col, _ro_item(""))

    def remove_row(self, active: ActiveSignal) -> None:
        """Remove the row for the given ActiveSignal. No-op if not present."""
        row = self._find_row(active)
        if row is None:
            return
        # Remove from the table first: removeRow() can synchronously emit
        # itemSelectionChanged, whose handler indexes into _signals.
        self._table.removeRow(row)
        self._signals.pop(row)

    def clear(self) -> None:
        """Remove all rows."""
        # Clear the table first: setRowCount(0) can synchronously emit
        # itemSelectionChanged, whose handler indexes into _signals.
        self._table.setRowCount(0)
        self._signals.clear()

    def show_cursor_columns(self, visible: bool) -> None:
        """Show or hide the three cursor-value columns."""
        for col in _CURSOR_COLS:
            self._table.setColumnHidden(col, not visible)

    def update_cursor_values(
        self,
        active: ActiveSignal,
        c1_text: str,
        c2_text: str,
        delta_text: str,
    ) -> None:
        """Update cursor value cells for one signal (called by CursorController)."""
        row = self._find_row(active)
        if row is None:
            return
        for col, text in zip(_CURSOR_COLS, (c1_text, c2_text, delta_text)):
            item = self._table.item(row, col)
            if item is not None:
                item.setText(text)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._table = QTableWidget(0, _NUM_COLS)
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)
        self._table.verticalHeader().setDefaultSectionSize(24)
        self._table.setShowGrid(True)
        self._table.setStyleSheet(
            "QTableWidget { gridline-color: #d0d0d0; outline: 0; }"
            "QTableWidget::item:selected { background-color: #e0e0e0; color: black; }"
        )

        hdr = self._table.horizontalHeader()
        hdr.setSectionResizeMode(_COL_COLOR, QHeaderView.ResizeMode.Fixed)
        self._table.setColumnWidth(_COL_COLOR, 28)
        hdr.setSectionResizeMode(_COL_NAME, QHeaderView.ResizeMode.Interactive)
        self._table.setColumnWidth(_COL_NAME, 120)
        for col in _CURSOR_COLS:
            hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
            self._table.setColumnWidth(col, 80)
        hdr.setStretchLastSection(False)

        # Cursor columns hidden until activated
        for col in _CURSOR_COLS:
            self._table.setColumnHidden(col, True)

        layout.addWidget(self._table)

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        self._remove_btn = QPushButton("Remove Signal")
        self._remove_btn.setEnabled(False)
        self._remove_all_btn = QPushButton("Remove All")
        btn_layout.addWidget(self._remove_btn)
        btn_layout.addWidget(self._remove_all_btn)
        layout.addLayout(btn_layout)

        self._table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._table.customContextMenuRequested.connect(self._on_context_menu)
        self._table.itemSelectionChanged.connect(self._on_selection_changed)
        self._remove_btn.clicked.connect(self._on_remove_clicked)
        self._remove_all_btn.clicked.connect(self.remove_all_requested)

        self._table.viewport().setAcceptDrops(True)
        self._table.viewport().installEventFilter(self)

    # ------------------------------------------------------------------
    # Slots (private)
    # ------------------------------------------------------------------

    def _on_selection_changed(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if rows and rows[0].row() < len(self._signals):
            row = rows[0].row()
            self._remove_btn.setEnabled(True)
            self.selection_changed.emit(self._signals[row])
        else:
            self._remove_btn.setEnabled(False)
            self.selection_changed.emit(None)

    def _on_remove_clicked(self) -> None:
        rows = self._table.selectionModel().selectedRows()
        if rows:
            self.remove_requested.emit(self._signals[rows[0].row()])

    def _on_color_swatch_clicked(self, active: ActiveSignal) -> None:
        QColorDialog.setCustomColor(0, active.color)
        new_color = QColorDialog.getColor(
            active.color, self, "Choose Signal Color"
        )
        if not new_color.isValid():
            return
        # Update swatch immediately; emit for controller/plot to react
        row = self._find_row(active)
        if row is not None:
            swatch = self._table.cellWidget(row, _COL_COLOR)
            if isinstance(swatch, _ColorSwatch):
                swatch.set_color(new_color)
        self.color_change_requested.emit(active, new_color)


    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self._on_remove_clicked()
        else:
            super().keyPressEvent(event)

    def _on_context_menu(self, pos) -> None:
        index = self._table.indexAt(pos)
        if not index.isValid() or index.row() >= len(self._signals):
            return
        active = self._signals[index.row()]
        menu = QMenu(self)
        label = "Disable Step Mode" if active.step_mode else "Enable Step Mode"
        action = QAction(label, self)
        action.triggered.connect(lambda: self.step_mode_toggle_requested.emit(active))
        menu.addAction(action)
        menu.exec(self._table.viewport().mapToGlobal(pos))

    def eventFilter(self, watched, event):
        if watched is self._table.viewport():
            t = event.type()
            if t == QEvent.Type.DragEnter:
                if event.mimeData().hasFormat(SIGNAL_MIME_TYPE):
                    event.acceptProposedAction()
                else:
                    event.ignore()
                return True
            elif t == QEvent.Type.DragMove:
                if event.mimeData().hasFormat(SIGNAL_MIME_TYPE):
                    event.acceptProposedAction()
                else:
                    event.ignore()
                return True
            elif t == QEvent.Type.Drop:
                if event.mimeData().hasFormat(SIGNAL_MIME_TYPE):
                    data = bytes(event.mimeData().data(SIGNAL_MIME_TYPE))
                    locs = [tuple(item) for item in json.loads(data)]
                    self.signals_dropped.emit(locs)
                    event.acceptProposedAction()
                return True
        return super().eventFilter(watched, event)

    def _find_row(self, active: ActiveSignal) -> int | None:
        """Return the row index of *active* using identity, or None."""
        for i, s in enumerate(self._signals):
            if s is active:
                return i
        return None


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _ro_item(text: str) -> QTableWidgetItem:
    """A non-editable QTableWidgetItem."""
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


class _ColorSwatch(QPushButton):
    """A flat, clickable colored rectangle used as a signal color indicator."""

    def __init__(self, color: QColor, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(20, 16)
        self.setFlat(True)
        self.set_color(color)

    def set_color(self, color: QColor) -> None:
        self._color = color
        self.setStyleSheet(
            f"background-color: {color.name()};"
            "border: 1px solid #666;"
            "border-radius: 2px;"
        )

    @property
    def color(self) -> QColor:
        return self._color
