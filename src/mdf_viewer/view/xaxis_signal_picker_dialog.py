"""XAxisSignalPickerDialog — pick which signal becomes a new tab's X-axis (#86).

Shown by choosing "X-Axis Signal…" from the New Tab chooser (REQ-XAXIS-012).
The candidate list can be long across several measurements, so it's filterable
the same way the Signal Browser's Flat-mode list is (plain substring or
`*`/`?` wildcards, same debounce timing) — reusing
`view/widgets/text_filter.py`'s shared helpers rather than re-deriving that
matching logic, without pulling in the Signal Browser's own unrelated
machinery (Tree mode, drag-and-drop, measurement filter combo).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import QSortFilterProxyModel, Qt
from PyQt6.QtGui import QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QListView,
    QVBoxLayout,
    QWidget,
)

from mdf_viewer.view.widgets import apply_text_filter, wire_debounced_filter

if TYPE_CHECKING:
    from mdf_viewer.model.loaded_measurement import LoadedMeasurement
    from mdf_viewer.model.signal_metadata import SignalMetadata

# Stores the (measurement, SignalMetadata) candidate tuple on each row.
_CANDIDATE_ROLE = Qt.ItemDataRole.UserRole + 1


class XAxisSignalPickerDialog(QDialog):
    """Asks the user which loaded signal to use as a new tab's X-axis."""

    def __init__(
        self,
        candidates: "list[tuple[LoadedMeasurement, SignalMetadata]]",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._multi_measurement = len({m.label for m, _ in candidates}) > 1
        self._selected: "tuple[LoadedMeasurement, SignalMetadata] | None" = None
        self.setWindowTitle("Select X-Axis Signal")
        self.setMinimumWidth(420)
        self.resize(420, 480)
        self._build_ui(candidates)

    def _build_ui(self, candidates: "list[tuple[LoadedMeasurement, SignalMetadata]]") -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel(
            "Select a signal to use as this tab's X-axis, instead of time:"
        ))

        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("Filter signals… (* and ? wildcards)")
        self._filter_edit.setClearButtonEnabled(True)
        layout.addWidget(self._filter_edit)

        self._model = QStandardItemModel(self)
        for measurement, meta in candidates:
            label = f"[{measurement.label}] {meta.name}" if self._multi_measurement else meta.name
            item = QStandardItem(label)
            item.setEditable(False)
            item.setData((measurement, meta), _CANDIDATE_ROLE)
            self._model.appendRow(item)

        self._proxy = QSortFilterProxyModel(self)
        self._proxy.setSourceModel(self._model)
        self._proxy.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)

        self._list = QListView()
        self._list.setModel(self._proxy)
        self._list.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
        self._list.doubleClicked.connect(self._on_double_click)
        if self._model.rowCount():
            self._list.setCurrentIndex(self._proxy.index(0, 0))
        layout.addWidget(self._list)

        self._filter_timer = wire_debounced_filter(
            self._filter_edit, self._apply_filter, parent=self,
        )

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _apply_filter(self) -> None:
        apply_text_filter(self._proxy, self._filter_edit.text())
        if self._proxy.rowCount():
            self._list.setCurrentIndex(self._proxy.index(0, 0))

    def _on_accept(self) -> None:
        index = self._list.currentIndex()
        if not index.isValid():
            return
        self._selected = index.data(_CANDIDATE_ROLE)
        self.accept()

    def _on_double_click(self, index) -> None:
        if not index.isValid():
            return
        self._selected = index.data(_CANDIDATE_ROLE)
        self.accept()

    def selected(self) -> "tuple[LoadedMeasurement, SignalMetadata] | None":
        """Return the (measurement, SignalMetadata) chosen by the user, or
        None if the dialog was cancelled."""
        return self._selected
