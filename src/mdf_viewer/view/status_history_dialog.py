"""StatusHistoryDialog — shows the in-session status bar message history (#125).

Non-modal (REQ-STATUS-021) and live-updating while open (REQ-STATUS-023).
The "Copy to Clipboard" button always copies the entire history
(REQ-STATUS-032), regardless of any active text selection.
"""

from __future__ import annotations

from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from mdf_viewer.view.status_message_history import StatusMessageEntry, StatusMessageHistory


class StatusHistoryDialog(QDialog):
    """Read-only view of every status bar message shown this session."""

    def __init__(self, history: StatusMessageHistory, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Status Message History")
        self.setMinimumSize(500, 300)

        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setPlainText(history.as_text())

        layout = QVBoxLayout(self)
        layout.addWidget(self._text)

        btn_row = QHBoxLayout()
        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.clicked.connect(self._copy_to_clipboard)
        btn_row.addWidget(copy_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)

    def append_entry(self, entry: StatusMessageEntry) -> None:
        """Add one new line for a message recorded after the dialog was built."""
        self._text.appendPlainText(entry.formatted())

    def _copy_to_clipboard(self) -> None:
        QGuiApplication.clipboard().setText(self._text.toPlainText())
