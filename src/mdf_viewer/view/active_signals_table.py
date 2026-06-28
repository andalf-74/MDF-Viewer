"""ActiveSignalsTable — right panel table of signals currently on the plot.

Columns: color swatch | name | cursor 1 value | cursor 2 value | delta.
Cursor-value columns are hidden until cursors are activated.
Buttons: Remove Signal, Remove All.
Selection in this table drives the Signal Info Box via selection_changed.
Multi-select is supported (ExtendedSelection). Right-clicking a row that is
already part of the selection does not change the selection.
"""

from __future__ import annotations

import json
from typing import Callable

from PyQt6.QtCore import QEvent, Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
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
from mdf_viewer.view.widgets import ColorSwatch
from mdf_viewer.view_model.active_signal import ActiveSignal

_COL_COLOR = 0
_COL_NAME = 1
_COL_C1 = 2
_COL_C2 = 3
_COL_DELTA = 4
_NUM_COLS = 5

_CURSOR_COLS = (_COL_C1, _COL_C2, _COL_DELTA)
_HEADERS = ("", "Signal", "Cursor 1", "Cursor 2", "Δ")


class _ActiveTable(QTableWidget):
    """QTableWidget that keeps the selection intact on right-click when the
    clicked row is already selected (Finder/Explorer behaviour)."""

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.RightButton:
            idx = self.indexAt(event.position().toPoint())
            if idx.isValid():
                selected = {r.row() for r in self.selectionModel().selectedRows()}
                if idx.row() in selected:
                    return  # keep current selection; context menu fires separately
        super().mousePressEvent(event)


class ActiveSignalsTable(QWidget):
    """Table of active signals with color swatch, name, cursor values, and delta."""

    # active_signal (or None) — emitted when row selection changes to 0 or 1 rows
    selection_changed = pyqtSignal(object)
    # True when >1 rows are selected; False otherwise
    multi_selection_active = pyqtSignal(bool)
    # list[ActiveSignal] — emitted alongside multi_selection_active(True) with the full selection
    multi_selection_changed = pyqtSignal(list)
    # list[ActiveSignal] — emitted when Remove Signal is clicked / Del pressed / context menu
    remove_requested = pyqtSignal(list)
    # emitted when Remove All is clicked
    remove_all_requested = pyqtSignal()
    # list[ActiveSignal], new QColor — emitted when user picks a new color
    color_change_requested = pyqtSignal(list, QColor)
    # list[ActiveSignal], bool enabled — emitted from context menu step-mode actions
    step_mode_set_requested = pyqtSignal(list, bool)
    # list of (group_index, channel_index) — emitted when signals are dropped onto the table
    signals_dropped = pyqtSignal(list)
    # list[ActiveSignal] in new order — emitted after a row drag-and-drop reorder
    order_changed = pyqtSignal(list)
    # str (selected signal name) — emitted when "Display Name Rule…" is chosen from context menu
    configure_display_names_requested = pyqtSignal(str)
    # bool — emitted when the "Shorten Signal Names" toggle is clicked in the context menu
    shorten_names_toggled = pyqtSignal(bool)
    # list[ActiveSignal] — emitted when "Share Y-axis" is chosen from the context menu
    share_y_axis_requested = pyqtSignal(list)
    # list[ActiveSignal] — emitted when "Link Y-axes" is chosen from the context menu
    link_y_axes_requested = pyqtSignal(list)
    # list[ActiveSignal] — emitted when "Remove from shared/linked axis" is chosen
    ungroup_y_axis_requested = pyqtSignal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._signals: list[ActiveSignal] = []
        self._drag_src_rows: list[int] = []
        self._pending_reorder: tuple[list[int], int] | None = None
        self._name_formatter: Callable[[str], str] = lambda n: n
        self._shorten_names_enabled: bool = False
        self._grouped_signals: set = set()
        self._build_ui()

    # ------------------------------------------------------------------
    # Public API (called by AppController)
    # ------------------------------------------------------------------

    def add_row(self, active: ActiveSignal) -> None:
        """Append a row for the given ActiveSignal."""
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._signals.append(active)

        swatch = ColorSwatch(active.color)
        swatch.clicked.connect(
            lambda checked=False, a=active: self._on_color_swatch_clicked(a)
        )
        self._table.setCellWidget(row, _COL_COLOR, swatch)
        self._table.setItem(row, _COL_NAME, _ro_item(self._name_formatter(active.metadata.name)))
        for col in _CURSOR_COLS:
            self._table.setItem(row, col, _ro_item(""))

    def select_signal(self, active: "ActiveSignal | None") -> None:
        """Programmatically select (and scroll to) the row for *active*, or clear selection."""
        if active is None:
            self._table.clearSelection()
            return
        row = self._find_row(active)
        if row is None:
            return
        self._table.setCurrentCell(row, 0)
        self._table.scrollTo(self._table.model().index(row, 0))

    def set_shorten_names_enabled(self, enabled: bool) -> None:
        """Keep the context menu checkbox in sync with the current rule state."""
        self._shorten_names_enabled = enabled

    def set_grouped_signals(self, grouped: set) -> None:
        """Update the set of signals that are in any shared or linked group."""
        self._grouped_signals = set(grouped)

    def set_name_formatter(self, formatter: Callable[[str], str]) -> None:
        """Set a function that maps raw signal names to display names, then refresh all rows."""
        self._name_formatter = formatter
        for row, active in enumerate(self._signals):
            item = self._table.item(row, _COL_NAME)
            if item is not None:
                item.setText(formatter(active.metadata.name))

    def remove_row(self, active: ActiveSignal) -> None:
        """Remove the row for the given ActiveSignal. No-op if not present."""
        row = self._find_row(active)
        if row is None:
            return
        self._table.removeRow(row)
        self._signals.pop(row)

    def clear(self) -> None:
        """Remove all rows."""
        self._table.setRowCount(0)
        self._signals.clear()

    def show_cursor_columns(self, visible: bool) -> None:
        """Show or hide the three cursor-value columns."""
        for col in _CURSOR_COLS:
            self._table.setColumnHidden(col, not visible)

    def set_cursor_column_headers(self, c3_label: str, c4_label: str) -> None:
        """Update the header text for the two cursor value columns."""
        self._table.setHorizontalHeaderItem(_COL_C1, QTableWidgetItem(c3_label))
        self._table.setHorizontalHeaderItem(_COL_C2, QTableWidgetItem(c4_label))

    def set_delta_column_header(self, text: str) -> None:
        """Update the header text for the delta column."""
        self._table.setHorizontalHeaderItem(_COL_DELTA, QTableWidgetItem(text))

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

        self._table = _ActiveTable(0, _NUM_COLS)
        self._table.setHorizontalHeaderLabels(_HEADERS)
        self._table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
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

        self._table.setDragEnabled(True)
        self._table.setAcceptDrops(True)
        self._table.setDropIndicatorShown(True)
        self._table.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self._table.setDefaultDropAction(Qt.DropAction.MoveAction)

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
        valid = [r for r in rows if r.row() < len(self._signals)]
        count = len(valid)
        self._remove_btn.setEnabled(count > 0)
        if count == 0:
            self.selection_changed.emit(None)
            self.multi_selection_active.emit(False)
        elif count == 1:
            self.selection_changed.emit(self._signals[valid[0].row()])
            self.multi_selection_active.emit(False)
        else:
            selected = [self._signals[r.row()] for r in valid]
            self.selection_changed.emit(None)
            self.multi_selection_active.emit(True)
            self.multi_selection_changed.emit(selected)

    def _on_remove_clicked(self) -> None:
        signals = self._selected_signals()
        if signals:
            self.remove_requested.emit(signals)

    def _on_color_swatch_clicked(self, active: ActiveSignal) -> None:
        QColorDialog.setCustomColor(0, active.color)
        new_color = QColorDialog.getColor(active.color, self, "Choose Signal Color")
        if not new_color.isValid():
            return
        selected = self._selected_signals()
        targets = selected if len(selected) > 1 and active in selected else [active]
        for sig in targets:
            row = self._find_row(sig)
            if row is not None:
                swatch = self._table.cellWidget(row, _COL_COLOR)
                if isinstance(swatch, ColorSwatch):
                    swatch.set_color(new_color)
        self.color_change_requested.emit(targets, new_color)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self._on_remove_clicked()
        else:
            super().keyPressEvent(event)

    def _on_context_menu(self, pos) -> None:
        index = self._table.indexAt(pos)
        if not index.isValid() or index.row() >= len(self._signals):
            return
        selected = self._selected_signals()
        if not selected:
            selected = [self._signals[index.row()]]
        n = len(selected)
        menu = QMenu(self)

        remove_label = f"Remove {n} Signals" if n > 1 else "Remove Signal"
        remove_action = QAction(remove_label, self)
        remove_action.triggered.connect(lambda: self.remove_requested.emit(selected))
        menu.addAction(remove_action)

        menu.addSeparator()

        enable_label = "Enable Step Mode for all" if n > 1 else "Enable Step Mode"
        enable_action = QAction(enable_label, self)
        enable_action.triggered.connect(
            lambda: self.step_mode_set_requested.emit(selected, True)
        )
        menu.addAction(enable_action)

        disable_label = "Disable Step Mode for all" if n > 1 else "Disable Step Mode"
        disable_action = QAction(disable_label, self)
        disable_action.triggered.connect(
            lambda: self.step_mode_set_requested.emit(selected, False)
        )
        menu.addAction(disable_action)

        menu.addSeparator()

        shorten_action = QAction("Shorten Signal Names", self)
        shorten_action.setCheckable(True)
        shorten_action.setChecked(self._shorten_names_enabled)
        shorten_action.triggered.connect(
            lambda checked: self.shorten_names_toggled.emit(checked)
        )
        menu.addAction(shorten_action)

        display_name_action = QAction("Display Name Rule…", self)
        preview_name = selected[0].metadata.name if selected else ""
        display_name_action.triggered.connect(
            lambda: self.configure_display_names_requested.emit(preview_name)
        )
        menu.addAction(display_name_action)

        menu.addSeparator()

        if n >= 2:
            share_action = QAction("Share Y-axis", self)
            share_action.setToolTip(
                "All selected signals share one ViewBox and one Y-axis — same Y scale, zoomed together."
            )
            share_action.triggered.connect(lambda: self.share_y_axis_requested.emit(selected))
            menu.addAction(share_action)

            link_action = QAction("Link Y-axes", self)
            link_action.setToolTip(
                "Selected signals keep separate Y-axes but pan/zoom together to the same absolute Y range."
            )
            link_action.triggered.connect(lambda: self.link_y_axes_requested.emit(selected))
            menu.addAction(link_action)

        grouped_selected = [s for s in selected if s in self._grouped_signals]
        if grouped_selected:
            ungroup_action = QAction("Remove from shared/linked axis", self)
            ungroup_action.triggered.connect(
                lambda: self.ungroup_y_axis_requested.emit(grouped_selected)
            )
            menu.addAction(ungroup_action)

        menu.exec(self._table.viewport().mapToGlobal(pos))

    def eventFilter(self, watched, event):
        if watched is self._table.viewport():
            t = event.type()
            if t == QEvent.Type.DragEnter:
                mime = event.mimeData()
                if mime.hasFormat(SIGNAL_MIME_TYPE):
                    event.acceptProposedAction()
                    return True
                if mime.hasFormat("application/x-qabstractitemmodeldatalist"):
                    self._drag_src_rows = sorted(
                        r.row() for r in self._table.selectionModel().selectedRows()
                    )
                    event.setDropAction(Qt.DropAction.MoveAction)
                    event.accept()
                    return True
                event.ignore()
                return True
            elif t == QEvent.Type.DragMove:
                mime = event.mimeData()
                if mime.hasFormat(SIGNAL_MIME_TYPE):
                    event.acceptProposedAction()
                    return True
                if mime.hasFormat("application/x-qabstractitemmodeldatalist"):
                    event.setDropAction(Qt.DropAction.MoveAction)
                    event.accept()
                    return True
                event.ignore()
                return True
            elif t == QEvent.Type.Drop:
                mime = event.mimeData()
                if mime.hasFormat(SIGNAL_MIME_TYPE):
                    data = bytes(mime.data(SIGNAL_MIME_TYPE))
                    locs = [tuple(item) for item in json.loads(data)]
                    self.signals_dropped.emit(locs)
                    event.acceptProposedAction()
                    return True
                if mime.hasFormat("application/x-qabstractitemmodeldatalist"):
                    self._on_row_reorder(event)
                    return True
                return True
        return super().eventFilter(watched, event)

    def _on_row_reorder(self, event) -> None:
        src_rows = self._drag_src_rows
        target = self._table.indexAt(event.position().toPoint())
        dst_row = target.row() if target.isValid() else self._table.rowCount() - 1
        if not src_rows or dst_row < 0 or dst_row in src_rows:
            event.ignore()
            return
        self._pending_reorder = (src_rows, dst_row)
        event.setDropAction(Qt.DropAction.IgnoreAction)
        event.accept()
        QTimer.singleShot(0, self._apply_reorder)

    def _apply_reorder(self) -> None:
        if self._pending_reorder is None:
            return
        src_rows, dst_row = self._pending_reorder
        self._pending_reorder = None
        if not src_rows or any(r >= len(self._signals) for r in src_rows):
            return
        if dst_row >= len(self._signals):
            return
        moving = [self._signals[r] for r in src_rows]
        for r in reversed(src_rows):
            self._signals.pop(r)
        items_before = sum(1 for r in src_rows if r < dst_row)
        adjusted_dst = max(0, dst_row - items_before)
        self._signals[adjusted_dst:adjusted_dst] = moving
        select_rows = list(range(adjusted_dst, adjusted_dst + len(moving)))
        self._rebuild_rows(select_rows=select_rows)
        self.order_changed.emit(list(self._signals))

    def _rebuild_rows(self, select_rows: list[int] | None = None) -> None:
        """Rebuild the entire table from _signals (used after row reorder)."""
        self._table.blockSignals(True)
        self._table.setRowCount(0)
        for active in self._signals:
            row = self._table.rowCount()
            self._table.insertRow(row)
            swatch = ColorSwatch(active.color)
            swatch.clicked.connect(
                lambda checked=False, a=active: self._on_color_swatch_clicked(a)
            )
            self._table.setCellWidget(row, _COL_COLOR, swatch)
            self._table.setItem(row, _COL_NAME, _ro_item(self._name_formatter(active.metadata.name)))
            for col in _CURSOR_COLS:
                self._table.setItem(row, col, _ro_item(""))
        self._table.blockSignals(False)
        if select_rows:
            sm = self._table.selectionModel()
            sm.clearSelection()
            for row in select_rows:
                sm.select(
                    self._table.model().index(row, 0),
                    sm.SelectionFlag.Select | sm.SelectionFlag.Rows,
                )
        self._table.viewport().update()

    def _selected_signals(self) -> list[ActiveSignal]:
        """Return all currently selected ActiveSignals, in row order."""
        rows = sorted(r.row() for r in self._table.selectionModel().selectedRows())
        return [self._signals[r] for r in rows if r < len(self._signals)]

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
