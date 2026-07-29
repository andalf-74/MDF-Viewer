"""LabelImportResultDialog — report the outcome of a .lab label list import (#143).

Shows two scrollable lists — names not found, and names already active and
skipped — with a "Copy to Clipboard" button covering both.
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


class LabelImportResultDialog(QDialog):
    """Lists candidate names not found, and candidates already active and
    skipped, after a label list import (REQ-LABEL-050)."""

    def __init__(
        self,
        not_found: list[str],
        already_active: list[str],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._not_found = not_found
        self._already_active = already_active
        self.setWindowTitle("Import Labels")
        self.setMinimumWidth(400)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        not_found_row = QHBoxLayout()
        not_found_row.addWidget(QLabel(f"Not found ({len(self._not_found)}):"))
        not_found_row.addStretch()
        copy_not_found_btn = QPushButton("Copy to Clipboard")
        copy_not_found_btn.clicked.connect(
            lambda: self._copy_to_clipboard(self._not_found)
        )
        not_found_row.addWidget(copy_not_found_btn)
        layout.addLayout(not_found_row)

        self._not_found_list = QListWidget()
        for name in self._not_found:
            self._not_found_list.addItem(name)
        layout.addWidget(self._not_found_list)

        already_active_row = QHBoxLayout()
        already_active_row.addWidget(
            QLabel(f"Already active, skipped ({len(self._already_active)}):")
        )
        already_active_row.addStretch()
        copy_already_active_btn = QPushButton("Copy to Clipboard")
        copy_already_active_btn.clicked.connect(
            lambda: self._copy_to_clipboard(self._already_active)
        )
        already_active_row.addWidget(copy_already_active_btn)
        layout.addLayout(already_active_row)

        self._already_active_list = QListWidget()
        for name in self._already_active:
            self._already_active_list.addItem(name)
        layout.addWidget(self._already_active_list)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _copy_to_clipboard(self, names: list[str]) -> None:
        QGuiApplication.clipboard().setText("\n".join(names))
