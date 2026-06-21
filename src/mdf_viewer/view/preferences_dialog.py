from __future__ import annotations

from PyQt6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mdf_viewer.settings import Settings


class PreferencesDialog(QDialog):
    def __init__(self, settings: Settings, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._settings = settings
        self.setWindowTitle("Preferences")
        self.setMinimumWidth(380)
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        tabs = QTabWidget()

        general = QWidget()
        general_layout = QVBoxLayout(general)
        self._update_check = QCheckBox("Check for updates on startup")
        self._update_check.setChecked(self._settings.check_for_updates)
        general_layout.addWidget(self._update_check)
        general_layout.addStretch()
        tabs.addTab(general, "General")

        layout.addWidget(tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._apply)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _apply(self) -> None:
        self._settings.check_for_updates = self._update_check.isChecked()
        self.accept()
