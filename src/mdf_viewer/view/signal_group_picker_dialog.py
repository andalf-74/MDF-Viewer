"""SignalGroupPickerDialog — let the user pick which channel group to restore.

Shown when a snapshot signal name matches channels in more than one channel
group in the newly loaded file.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mdf_viewer.model.signal_metadata import SignalMetadata


class SignalGroupPickerDialog(QDialog):
    """Asks the user which channel group to use when a signal name is ambiguous."""

    def __init__(
        self,
        signal_name: str,
        candidates: list[SignalMetadata],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._candidates = candidates
        self._selected: SignalMetadata | None = None
        self.setWindowTitle("Select Channel Group")
        self.setMinimumWidth(420)
        self._build_ui(signal_name)

    def _build_ui(self, signal_name: str) -> None:
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                f'Signal "<b>{signal_name}</b>" was found in multiple channel groups.\n'
                "Select which one to restore:"
            )
        )
        self._list = QListWidget()
        for meta in self._candidates:
            item = QListWidgetItem(f"Channel group {meta.group_index}")
            item.setData(Qt.ItemDataRole.UserRole, meta)
            self._list.addItem(item)
        self._list.setCurrentRow(0)
        self._list.itemDoubleClicked.connect(self._on_double_click)
        layout.addWidget(self._list)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_accept(self) -> None:
        item = self._list.currentItem()
        if item is None:
            return
        self._selected = item.data(Qt.ItemDataRole.UserRole)
        self.accept()

    def _on_double_click(self, item: QListWidgetItem) -> None:
        self._selected = item.data(Qt.ItemDataRole.UserRole)
        self.accept()

    def selected(self) -> SignalMetadata | None:
        """Return the metadata chosen by the user, or None if dialog was cancelled."""
        return self._selected
