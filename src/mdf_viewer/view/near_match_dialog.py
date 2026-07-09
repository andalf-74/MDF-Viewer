"""NearMatchDialog — confirm near-matched signals after a file/config load.

Shown once per operation (not once per signal) when one or more signals
couldn't be matched by exact name but a same-source-prefix candidate was
found — e.g. the same signal recorded under a different protocol
(REQ-FILE-032/033/036).
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


class NearMatchDialog(QDialog):
    """Lists near-matched signals with a per-row checkbox (checked by default)."""

    def __init__(
        self,
        pending: list[tuple[str, SignalMetadata]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._pending = pending
        self.setWindowTitle("Signals Measured Differently")
        self.setMinimumWidth(480)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        count = len(self._pending)
        noun = "signal" if count == 1 else "signals"
        layout.addWidget(
            QLabel(
                f"{count} {noun} weren't found by exact name, but a signal "
                "recorded under a different protocol or source looks like a "
                "match. Uncheck any you don't want replaced:"
            )
        )

        self._list = QListWidget()
        for original_name, candidate in self._pending:
            item = QListWidgetItem(f"{original_name}  →  {candidate.name}")
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked)
            item.setData(Qt.ItemDataRole.UserRole, (original_name, candidate))
            self._list.addItem(item)
        layout.addWidget(self._list)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accepted_matches(self) -> list[tuple[str, SignalMetadata]]:
        """(original_name, candidate) pairs whose row stayed checked."""
        return [
            self._list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._list.count())
            if self._list.item(i).checkState() == Qt.CheckState.Checked
        ]

    def declined_matches(self) -> list[tuple[str, SignalMetadata]]:
        """(original_name, candidate) pairs the user unchecked."""
        return [
            self._list.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self._list.count())
            if self._list.item(i).checkState() != Qt.CheckState.Checked
        ]

    def checked_mask(self) -> list[bool]:
        """Per-row checked state, in the same order as the *pending* list
        passed to __init__. Lets a caller re-associate each row with data
        that isn't stored on the dialog itself (e.g. which tab a near-match
        came from) without matching by name, which breaks if the same
        signal name appears in more than one pending row."""
        return [
            self._list.item(i).checkState() == Qt.CheckState.Checked
            for i in range(self._list.count())
        ]
