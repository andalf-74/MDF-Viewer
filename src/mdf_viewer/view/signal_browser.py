"""SignalBrowser — left panel: flat, cross-measurement channel list.

Emits add_signals_requested(list) when the user wants to add one or more
signals (double-click a channel, select + "Add Signal" button, or drag).
Holds no model data itself; populated by the controller, reports intent out.

Every channel from every loaded measurement is one flat, alphabetically
sorted row (#103, REQ-BROWSER-010/011) — there is no channel-group tree.
When more than one measurement is loaded, each row is prefixed with its
measurement's short name (e.g. "[M1] Drehzahl", REQ-BROWSER-050) and a
measurement filter above the list narrows it to one measurement or "All"
(REQ-BROWSER-052); with exactly one measurement loaded, no prefix and no
filter are shown, identical to today. Each row's original channel-group
name is preserved as a hover tooltip rather than as list structure
(REQ-BROWSER-013).
"""

from __future__ import annotations

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
    QComboBox,
    QLineEdit,
    QPushButton,
    QTreeView,
    QVBoxLayout,
    QWidget,
)

from mdf_viewer.model.mdf_loader import ChannelGroupInfo
from mdf_viewer.view._mime import SIGNAL_MIME_TYPE, encode_signal_payload

# Stores (measurement_index, group_index, channel_index) on every row.
_LOCATION_ROLE = Qt.ItemDataRole.UserRole + 1
# Bare channel name (no measurement prefix) — the primary sort key, so
# identically-named channels from different measurements sort adjacent to
# each other rather than grouped by measurement (REQ-BROWSER-051).
_SORT_ROLE = Qt.ItemDataRole.UserRole + 2

# Index into the measurement filter combo meaning "show every measurement".
_ALL_MEASUREMENTS = -1

# Delay before applying the filter after the user stops typing. Recursive
# filtering over a large channel list is expensive, so re-filtering on every
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
        data = encode_signal_payload(locations)
        mime = QMimeData()
        mime.setData(SIGNAL_MIME_TYPE, QByteArray(data))
        drag = QDrag(self)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.CopyAction)


class _FlatSignalProxy(QSortFilterProxyModel):
    """Text filter (inherited) ANDed with a measurement filter, sorted on
    the bare channel name with measurement index as a tiebreak (#103).
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._measurement_filter: int = _ALL_MEASUREMENTS

    def set_measurement_filter(self, measurement_index: int) -> None:
        self._measurement_filter = measurement_index
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row, source_parent) -> bool:
        if not super().filterAcceptsRow(source_row, source_parent):
            return False
        if self._measurement_filter == _ALL_MEASUREMENTS:
            return True
        index = self.sourceModel().index(source_row, 0, source_parent)
        location = index.data(_LOCATION_ROLE)
        return location is not None and location[0] == self._measurement_filter

    def lessThan(self, left, right) -> bool:
        left_key = (left.data(_SORT_ROLE), left.data(_LOCATION_ROLE)[0])
        right_key = (right.data(_SORT_ROLE), right.data(_LOCATION_ROLE)[0])
        return left_key < right_key


class SignalBrowser(QWidget):
    """Flat, cross-measurement channel list with a filter field and Add Signal button."""

    # Emits a list of (measurement_index, group_index, channel_index) triples.
    add_signals_requested = pyqtSignal(list)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._labels: list[str] = []
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._measurement_filter_combo = QComboBox()
        self._measurement_filter_combo.setVisible(False)
        layout.addWidget(self._measurement_filter_combo)

        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("Filter signals… (* and ? wildcards)")
        self._filter_edit.setClearButtonEnabled(True)
        layout.addWidget(self._filter_edit)

        self._tree = _DragTreeView(self._selected_locations)
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(False)
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

        self._proxy = _FlatSignalProxy(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self._proxy.setFilterKeyColumn(0)
        self._proxy.setSortRole(_SORT_ROLE)
        self._tree.setModel(self._proxy)

        self._filter_timer = QTimer(self)
        self._filter_timer.setSingleShot(True)
        self._filter_timer.setInterval(_FILTER_DELAY_MS)
        self._filter_timer.timeout.connect(self._apply_filter)
        self._filter_edit.textChanged.connect(lambda: self._filter_timer.start())
        self._tree.doubleClicked.connect(self._on_double_click)
        self._tree.selectionModel().selectionChanged.connect(self._on_selection_changed)
        self._add_btn.clicked.connect(self._on_add_clicked)
        self._measurement_filter_combo.currentIndexChanged.connect(
            self._on_measurement_filter_changed
        )

    # ------------------------------------------------------------------
    # Public API (called by the controller)
    # ------------------------------------------------------------------

    def populate_all(self, measurements: list[tuple[str, list[ChannelGroupInfo], bool]]) -> None:
        """Rebuild the flat list from every loaded measurement's channels.

        *measurements* is a (short_name, channel_groups, is_virtual) triple
        per loaded measurement, in load order (REQ-BROWSER-010/011;
        is_virtual added #147/REQ-VMEAS-210). Clears the text filter
        (REQ-BROWSER-012); the measurement filter is preserved by short
        name across the rebuild, resetting to "All" only if the
        measurement it was set to is no longer present.
        """
        previous_filter_label = self._current_filter_label()
        self._clear_filter()
        self._model.clear()
        self._labels = [label for label, _, _ in measurements]
        show_prefix = len(self._labels) > 1

        for mi, (label, groups, is_virtual) in enumerate(measurements):
            for group in groups:
                for ch in group.channels:
                    self._model.appendRow(
                        _make_channel_item(
                            ch, mi, label if show_prefix else None, group.name, is_virtual,
                        )
                    )
        self._proxy.sort(0)
        self._rebuild_measurement_filter_combo(previous_filter_label)
        self._add_btn.setEnabled(False)

    def clear(self) -> None:
        """Remove all rows, clear both filters, and disable the Add Signal button."""
        self._clear_filter()
        self._model.clear()
        self._labels = []
        self._add_btn.setEnabled(False)
        self._measurement_filter_combo.blockSignals(True)
        self._measurement_filter_combo.clear()
        self._measurement_filter_combo.blockSignals(False)
        self._measurement_filter_combo.setVisible(False)
        self._proxy.set_measurement_filter(_ALL_MEASUREMENTS)

    # ------------------------------------------------------------------
    # Slots (private)
    # ------------------------------------------------------------------

    def _apply_filter(self) -> None:
        text = self._filter_edit.text()
        if '*' in text or '?' in text:
            self._proxy.setFilterWildcard(text)
        else:
            self._proxy.setFilterFixedString(text)

    def _clear_filter(self) -> None:
        """Clear the text filter field and apply the empty filter immediately."""
        self._filter_timer.stop()
        self._filter_edit.clear()
        self._proxy.setFilterFixedString("")

    def _on_selection_changed(self) -> None:
        self._add_btn.setEnabled(bool(self._selected_locations()))

    def _on_measurement_filter_changed(self, index: int) -> None:
        if index < 0:
            return
        measurement_index = index - 1  # index 0 is "All"
        self._proxy.set_measurement_filter(measurement_index)

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

    def _selected_locations(self) -> list[tuple[int, int, int]]:
        """Return [(measurement_index, group_index, channel_index), ...] for the selection."""
        locations = []
        for idx in self._tree.selectedIndexes():
            src = self._proxy.mapToSource(idx)
            item = self._model.itemFromIndex(src)
            if item is not None:
                loc = item.data(_LOCATION_ROLE)
                if loc is not None:
                    locations.append(loc)
        return locations

    def _current_filter_label(self) -> str | None:
        """The short name the measurement filter is currently set to, or None for "All"."""
        index = self._measurement_filter_combo.currentIndex()
        if index <= 0:
            return None
        return self._measurement_filter_combo.itemText(index)

    def _rebuild_measurement_filter_combo(self, previous_filter_label: str | None) -> None:
        self._measurement_filter_combo.blockSignals(True)
        self._measurement_filter_combo.clear()
        self._measurement_filter_combo.addItem("All")
        self._measurement_filter_combo.addItems(self._labels)
        self._measurement_filter_combo.setVisible(len(self._labels) > 1)
        if previous_filter_label is not None and previous_filter_label in self._labels:
            new_index = 1 + self._labels.index(previous_filter_label)
            self._measurement_filter_combo.setCurrentIndex(new_index)
            self._proxy.set_measurement_filter(new_index - 1)
        else:
            self._measurement_filter_combo.setCurrentIndex(0)
            self._proxy.set_measurement_filter(_ALL_MEASUREMENTS)
        self._measurement_filter_combo.blockSignals(False)


# ---------------------------------------------------------------------------
# Item factory
# ---------------------------------------------------------------------------

def _make_channel_item(
    ch, measurement_index: int, prefix: str | None, group_name: str, is_virtual: bool = False,
) -> QStandardItem:
    base = f"{ch.name} [{ch.unit}]" if ch.unit else ch.name
    # Marked regardless of whether the [label] prefix itself is shown
    # (single-measurement sessions have no prefix at all) — REQ-VMEAS-210.
    if is_virtual:
        base = f"(virtual) {base}"
    text = f"[{prefix}] {base}" if prefix else base
    item = QStandardItem(text)
    item.setEditable(False)
    item.setData((measurement_index, ch.group_index, ch.channel_index), _LOCATION_ROLE)
    item.setData(ch.name, _SORT_ROLE)
    if group_name:
        item.setToolTip(group_name)
    return item
