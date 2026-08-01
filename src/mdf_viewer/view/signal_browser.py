"""SignalBrowser — left panel: Flat or Tree channel browser (#141).

Emits add_signals_requested(list) when the user wants to add one or more
signals (double-click a channel, select + "Add Signal" button, or drag).
Holds no model data itself; populated by the controller, reports intent out.

Two view modes, chosen via set_view_mode() (REQ-BROWSER-060):

Flat mode (default, REQ-BROWSER-062): every channel from every loaded
measurement is one flat, alphabetically sorted row (#103,
REQ-BROWSER-010/011) — there is no channel-group tree. When more than one
measurement is loaded, each row is prefixed with its measurement's short
name (e.g. "[M1] Drehzahl", REQ-BROWSER-050) and a measurement filter
above the list narrows it to one measurement or "All" (REQ-BROWSER-052);
with exactly one measurement loaded, no prefix and no filter are shown.
Each row's original channel-group name is preserved as a hover tooltip
rather than as list structure (REQ-BROWSER-013).

Tree mode (#141, REQ-BROWSER-070+): each loaded measurement is a
top-level node (labeled with its short name and virtual marker,
REQ-BROWSER-073), its channel groups are child nodes, and channels are
leaves — reflecting the file's own hierarchy and order rather than
Flat mode's alphabetical resort (REQ-BROWSER-071). Only channel nodes
carry a _LOCATION_ROLE and are selectable/addable/draggable
(REQ-BROWSER-074); measurement/group nodes exist purely to organize.
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
from PyQt6.QtGui import QDrag, QGuiApplication, QStandardItem, QStandardItemModel
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
from mdf_viewer.view import theme
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

    def __init__(self, get_locations, on_copy=None, parent=None):
        super().__init__(parent)
        self._get_locations = get_locations
        self._on_copy = on_copy

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

    def keyPressEvent(self, event) -> None:
        if (
            self._on_copy is not None
            and event.key() == Qt.Key.Key_C
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self._on_copy()
        else:
            super().keyPressEvent(event)


class _FlatSignalProxy(QSortFilterProxyModel):
    """Text filter (inherited) ANDed with a measurement filter.

    In Flat mode, sorted on the bare channel name with measurement index
    as a tiebreak (#103). In Tree mode, sorting is disabled (sort(-1),
    see set_view_mode()) so the model's insertion order — the file's own
    channel-group/channel order — is preserved (REQ-BROWSER-071).
    Recursive filtering is always on: it's how a Tree-mode match keeps its
    ancestor Channel Group/Measurement rows visible (REQ-BROWSER-023), and
    it's a no-op in Flat mode since there's no hierarchy to recurse into.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._measurement_filter: int = _ALL_MEASUREMENTS
        self.setRecursiveFilteringEnabled(True)

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
    """Flat or Tree channel browser (see set_view_mode()) with a filter field
    and Add Signal button."""

    # Emits a list of (measurement_index, group_index, channel_index) triples.
    add_signals_requested = pyqtSignal(list)
    # int — how many names were copied via Ctrl+C (#163); MainWindow shows a
    # status message with it (REQ-BROWSER-082).
    names_copied = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._labels: list[str] = []
        self._view_mode: str = "flat"
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._measurement_filter_combo = QComboBox()
        self._measurement_filter_combo.setVisible(False)
        self._measurement_filter_combo.setToolTip(
            "Filter the channel list to one measurement, or show all"
        )
        layout.addWidget(self._measurement_filter_combo)

        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("Filter signals… (* and ? wildcards)")
        self._filter_edit.setClearButtonEnabled(True)
        layout.addWidget(self._filter_edit)

        self._tree = _DragTreeView(self._selected_locations, on_copy=self._on_copy_names)
        self._tree.setHeaderHidden(True)
        self._tree.setRootIsDecorated(False)
        self._tree.setEditTriggers(QTreeView.EditTrigger.NoEditTriggers)
        self._tree.setSelectionMode(QTreeView.SelectionMode.ExtendedSelection)
        self._tree.setUniformRowHeights(True)
        self._tree.setDragEnabled(True)
        self._tree.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self._tree.setStyleSheet(
            f"QTreeView::item:selected {{ background-color: {theme.ACCENT}; color: {theme.ACCENT_TEXT}; }}"
        )
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

    def set_view_mode(self, mode: str) -> None:
        """Switch between "flat" and "tree" display (REQ-BROWSER-060).

        Toggles rootIsDecorated so top-level (Measurement) nodes get an
        expand/collapse arrow in Tree mode — _build_ui() sets it False,
        correct only for Flat mode's single-level list. Does not itself
        repopulate; the caller re-calls populate_all() with the same
        measurement data (REQ-BROWSER-063).
        """
        self._view_mode = mode if mode in ("flat", "tree") else "flat"
        self._tree.setRootIsDecorated(self._view_mode == "tree")

    def populate_all(self, measurements: list[tuple[str, list[ChannelGroupInfo], bool]]) -> None:
        """Rebuild the browser from every loaded measurement's channels, in
        the current view mode (REQ-BROWSER-010 for Flat, REQ-BROWSER-070
        for Tree).

        *measurements* is a (short_name, channel_groups, is_virtual) triple
        per loaded measurement, in load order (REQ-BROWSER-010/011/071;
        is_virtual added #147/REQ-VMEAS-210). Clears the text filter
        (REQ-BROWSER-012).
        """
        previous_filter_label = self._current_filter_label()
        self._clear_filter()
        self._model.clear()
        self._labels = [label for label, _, _ in measurements]

        if self._view_mode == "tree":
            self._populate_tree(measurements)
            self._hide_measurement_filter_combo()
        else:
            self._populate_flat(measurements)
            self._rebuild_measurement_filter_combo(previous_filter_label)
        self._add_btn.setEnabled(False)

    def _populate_flat(self, measurements: list[tuple[str, list[ChannelGroupInfo], bool]]) -> None:
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

    def _populate_tree(self, measurements: list[tuple[str, list[ChannelGroupInfo], bool]]) -> None:
        # Must run before any appendRow below: the proxy's sort column is
        # sticky across populates, so a prior Flat populate (sort(0), the
        # common case since Flat is the default mode) would otherwise
        # trigger an incremental re-sort — and lessThan() — on every insert
        # here, crashing on measurement/group items that carry no
        # _LOCATION_ROLE by design (leaf-only selection, REQ-BROWSER-074).
        self._proxy.sort(-1)
        for mi, (label, groups, is_virtual) in enumerate(measurements):
            measurement_item = _make_measurement_item(label, is_virtual)
            for group in groups:
                group_item = _make_group_item(group.name)
                for ch in group.channels:
                    group_item.appendRow(_make_channel_item(ch, mi, None, group.name, False))
                measurement_item.appendRow(group_item)
            self._model.appendRow(measurement_item)
        # REQ-BROWSER-072: measurement nodes (depth 0) start expanded,
        # channel-group nodes (depth 1) start collapsed.
        self._tree.expandToDepth(0)

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
        if self._view_mode == "tree":
            # Recursive filtering (set on the proxy) only controls which
            # rows are *accepted* — it doesn't expand collapsed ancestors,
            # so a deep match would otherwise stay invisible on screen
            # (REQ-BROWSER-023). Clearing the filter restores the default
            # expand state rather than leaving branches expanded from the
            # search (REQ-BROWSER-025).
            if text:
                self._tree.expandAll()
            else:
                self._tree.expandToDepth(0)

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

    def _on_copy_names(self) -> None:
        """Copy each selected channel's raw name (not its on-screen display
        text) to the clipboard, one per line (#163, REQ-BROWSER-080)."""
        names = self._selected_names()
        if not names:
            return
        QGuiApplication.clipboard().setText("\n".join(names))
        self.names_copied.emit(len(names))

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

    def _selected_names(self) -> list[str]:
        """Return the raw channel name (no measurement prefix, no unit) for
        each selected row, in _SORT_ROLE (#163)."""
        names = []
        for idx in self._tree.selectedIndexes():
            src = self._proxy.mapToSource(idx)
            item = self._model.itemFromIndex(src)
            if item is not None:
                name = item.data(_SORT_ROLE)
                if name is not None:
                    names.append(name)
        return names

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

    def _hide_measurement_filter_combo(self) -> None:
        """Tree mode has no measurement filter (REQ-BROWSER-075) — a
        measurement's own node is already collapsible. Unconditionally
        resets the proxy's measurement filter rather than restoring it by
        label (as Flat mode's combo does): leaving a Flat-mode filter
        active here would silently hide every other measurement's whole
        subtree, with no visible control left to explain or undo it.
        """
        self._measurement_filter_combo.blockSignals(True)
        self._measurement_filter_combo.clear()
        self._measurement_filter_combo.blockSignals(False)
        self._measurement_filter_combo.setVisible(False)
        self._proxy.set_measurement_filter(_ALL_MEASUREMENTS)

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


def _make_measurement_item(label: str, is_virtual: bool) -> QStandardItem:
    """Tree-mode top-level node — carries the identity (short name, virtual
    marker) that Flat mode instead puts on every channel row
    (REQ-BROWSER-073). No _LOCATION_ROLE and not selectable, so it can
    never be added/dragged, only expanded/collapsed (REQ-BROWSER-074).
    """
    text = f"(virtual) {label}" if is_virtual else label
    item = QStandardItem(text)
    item.setEditable(False)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
    return item


def _make_group_item(name: str) -> QStandardItem:
    """Tree-mode Channel Group node — organizational only, same
    not-selectable treatment as a measurement node (REQ-BROWSER-074)."""
    item = QStandardItem(name)
    item.setEditable(False)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsSelectable)
    return item
