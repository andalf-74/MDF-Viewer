"""SignalBrowser — left panel TreeView of the full MDF channel hierarchy.

Emits add_signals_requested(list) when the user wants to add one or more
signals (double-click a channel node, select + "Add Signal" button, or drag).
Holds no model data itself; populated by the controller, reports intent out.
"""

from __future__ import annotations

import json

from PyQt6.QtCore import (
    QByteArray,
    QMimeData,
    QSortFilterProxyModel,
    Qt,
    QTimer,
    pyqtSignal,
)
from PyQt6.QtGui import QDrag, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QLineEdit,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from mdf_viewer.model.mdf_loader import ChannelGroupInfo
from mdf_viewer.view._mime import SIGNAL_MIME_TYPE

# Stores (group_index, channel_index) tuple on channel items; None on group items.
_LOCATION_ROLE = Qt.ItemDataRole.UserRole + 1

# Delay before applying the filter after the user stops typing. Recursive
# filtering over a large channel tree is expensive, so re-filtering on every
# keystroke makes typing feel sluggish.
_FILTER_DELAY_MS = 250


class _DragTreeView(QTreeView):
    """QTreeView that encodes selected signal locations as MIME data on drag."""

    def __init__(self, get_locations, parent=None):
        super().__init__(parent)
        self._get_locations = get_locations

    def startDrag(self, supported_actions):
        locations = self._get_locations()
        if not locations:
            return
        data = json.dumps([[gi, ci] for gi, ci in locations]).encode()
        mime = QMimeData()
        mime.setData(SIGNAL_MIME_TYPE, QByteArray(data))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)


class SignalBrowser(QWidget):
    """Channel-group / channel hierarchy tree with a filter field and Add Signal button."""

    # Emits a list of (group_index, channel_index) tuples — one or many.
    add_signals_requested = pyqtSignal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("Filter signals…")
        self._filter_edit.setClearButtonEnabled(True)
        layout.addWidget(self._filter_edit)

        self._tree = _DragTreeView(self._selected_locations)
        self._tree.setHeaderHidden(True)
        self._tree.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        self._tree.setSelectionMode(QTreeView.SelectionMode.ExtendedSelection)
        self._tree.setUniformRowHeights(True)
        self._tree.setDragEnabled(True)
        self._tree.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        layout.addWidget(self._tree)

        self._add_btn = QPushButton("Add Signal")
        self._add_btn.setEnabled(False)
        layout.addWidget(self._add_btn)

        self._model = QStandardItemModel(self)

        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._proxy.setRecursiveFilteringEnabled(True)
        self._proxy.setFilterKeyColumn(0)
        self._tree.setModel(self._proxy)

        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(_FILTER_DELAY_MS)
        self._filter_timer.timeout.connect(self._apply_filter)
        self._filter_edit.textChanged.connect(lambda: self._filter_timer.start())
        self._tree.doubleClicked.connect(self._on_double_click)
        self._tree.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self._add_btn.clicked.connect(self._on_add_clicked)

    # ------------------------------------------------------------------
    # Public API (called by the controller)
    # ------------------------------------------------------------------

    def populate(self, groups: list[ChannelGroupInfo]) -> None:
        """Rebuild the tree from a channel hierarchy.

        Clears the filter so all signals in the new file are immediately visible.
        Groups are expanded by default.
        """
        self._clear_filter()
        self._model.clear()
        for group in groups:
            group_item = _make_group_item(group.name)
            for ch in group.channels:
                label = f"{ch.name} [{ch.unit}]" if ch.unit else ch.name
                ch_item = _make_channel_item(label, ch.group_index, ch.channel_index)
                group_item.appendRow(ch_item)
            self._model.appendRow(group_item)
        self._tree.expandAll()
        self._add_btn.setEnabled(False)

    def clear(self) -> None:
        """Remove all tree items, clear the filter, and disable the Add Signal button."""
        self._clear_filter()
        self._model.clear()
        self._add_btn.setEnabled(False)

    # ------------------------------------------------------------------
    # Slots (private)
    # ------------------------------------------------------------------

    def _apply_filter(self) -> None:
        self._proxy.setFilterFixedString(self._filter_edit.text())

    def _clear_filter(self) -> None:
        """Clear the filter field and apply the empty filter immediately."""
        self._filter_timer.stop()
        self._filter_edit.clear()
        self._proxy.setFilterFixedString("")

    def _on_selection_changed(self) -> None:
        self._add_btn.setEnabled(bool(self._selected_locations()))

    def _on_add_clicked(self) -> None:
        locs = self._selected_locations()
        if locs:
            self.add_signals_requested.emit(locs)

    def _on_double_click(self, proxy_index) -> None:
        source_index = self._proxy.mapToSource(proxy_index)
        item = self._model.itemFromIndex(source_index)
        if item is None:
            return
        loc = item.data(_LOCATION_ROLE)
        if loc is not None:
            self.add_signals_requested.emit([loc])

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _selected_locations(self) -> list[tuple[int, int]]:
        """Return [(group_index, channel_index), ...] for all selected channel items."""
        locations = []
        for idx in self._tree.selectedIndexes():
            src = self._proxy.mapToSource(idx)
            item = self._model.itemFromIndex(src)
            if item is not None:
                loc = item.data(_LOCATION_ROLE)
                if loc is not None:
                    locations.append(loc)
        return locations


# ---------------------------------------------------------------------------
# Item factories
# ---------------------------------------------------------------------------

def _make_group_item(name: str) -> QStandardItem:
    item = QStandardItem(name)
    item.setEditable(False)
    item.setData(None, _LOCATION_ROLE)
    return item


def _make_channel_item(label: str, group_index: int, channel_index: int) -> QStandardItem:
    item = QStandardItem(label)
    item.setEditable(False)
    item.setData((group_index, channel_index), _LOCATION_ROLE)
    return item
