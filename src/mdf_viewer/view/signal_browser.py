"""SignalBrowser — left panel TreeView of the full MDF channel hierarchy.

Emits add_signal_requested(group_index, channel_index) when the user wants to
add a signal (double-click a channel node, or select + "Add Signal" button).
Holds no model data itself; populated by the controller, reports intent out.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from mdf_viewer.model.mdf_loader import ChannelGroupInfo

# Stores (group_index, channel_index) tuple on channel items; None on group items.
_LOCATION_ROLE = Qt.ItemDataRole.UserRole + 1


class SignalBrowser(QWidget):
    """Channel-group / channel hierarchy tree with an Add Signal button."""

    add_signal_requested = pyqtSignal(int, int)  # (group_index, channel_index)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._tree = QTreeView()
        self._tree.setHeaderHidden(True)
        self._tree.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        self._tree.setSelectionMode(QTreeView.SelectionMode.SingleSelection)
        self._tree.setUniformRowHeights(True)
        layout.addWidget(self._tree)

        self._add_btn = QPushButton("Add Signal")
        self._add_btn.setEnabled(False)
        layout.addWidget(self._add_btn)

        self._model = QStandardItemModel(self)
        self._tree.setModel(self._model)

        self._tree.doubleClicked.connect(self._on_double_click)
        self._tree.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self._add_btn.clicked.connect(self._on_add_clicked)

    # ------------------------------------------------------------------
    # Public API (called by the controller)
    # ------------------------------------------------------------------

    def populate(self, groups: list[ChannelGroupInfo]) -> None:
        """Rebuild the tree from a channel hierarchy.

        Replaces any previously loaded content. Groups are expanded by default.
        """
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
        """Remove all tree items and disable the Add Signal button."""
        self._model.clear()
        self._add_btn.setEnabled(False)

    # ------------------------------------------------------------------
    # Slots (private)
    # ------------------------------------------------------------------

    def _on_selection_changed(self) -> None:
        self._add_btn.setEnabled(self._current_location() is not None)

    def _on_add_clicked(self) -> None:
        loc = self._current_location()
        if loc is not None:
            self.add_signal_requested.emit(loc[0], loc[1])

    def _on_double_click(self, index) -> None:
        item = self._model.itemFromIndex(index)
        if item is None:
            return
        loc = item.data(_LOCATION_ROLE)
        if loc is not None:
            self.add_signal_requested.emit(loc[0], loc[1])

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _current_location(self) -> tuple[int, int] | None:
        """Return (group_index, channel_index) for the selected channel, or None."""
        indexes = self._tree.selectedIndexes()
        if not indexes:
            return None
        item = self._model.itemFromIndex(indexes[0])
        if item is None:
            return None
        return item.data(_LOCATION_ROLE)


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
