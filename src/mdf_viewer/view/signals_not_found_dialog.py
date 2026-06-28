"""SignalsNotFoundDialog — report signals that could not be matched after a file load.

Shows a scrollable list of signal names and offers a "Copy to Clipboard" button
so the user can paste the list elsewhere.
"""

from __future__ import annotations

from PyQt6.QtGui import QGuiApplication
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class SignalsNotFoundDialog(QDialog):
    """Lists signal names that could not be found in the newly loaded file."""

    def __init__(
        self,
        signal_names: list[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._names = signal_names
        self.setWindowTitle("Signals Not Found")
        self.setMinimumWidth(400)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        count = len(self._names)
        noun = "signal" if count == 1 else "signals"
        layout.addWidget(
            QLabel(
                f"{count} {noun} could not be matched in the new measurement:"
            )
        )

        self._list = QListWidget()
        for name in self._names:
            self._list.addItem(name)
        layout.addWidget(self._list)

        btn_row = QHBoxLayout()
        copy_btn = QPushButton("Copy to Clipboard")
        copy_btn.clicked.connect(self._copy_to_clipboard)
        btn_row.addWidget(copy_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _copy_to_clipboard(self) -> None:
        text = "\n".join(self._names)
        QGuiApplication.clipboard().setText(text)
