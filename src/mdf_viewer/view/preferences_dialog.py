from __future__ import annotations

from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QRadioButton,
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

        cursors = QWidget()
        cursors_layout = QVBoxLayout(cursors)

        self._cursor_mode_group = QButtonGroup(self)
        self._cursor_12 = QRadioButton("Cursor 1 / 2")
        self._cursor_12.setToolTip(
            "Cursor 1 and Cursor 2 always stay the same cursor, regardless of their position.\n"
            "Delta is always Cursor 2 − Cursor 1."
        )
        self._cursor_lr = QRadioButton("Cursor L / R")
        self._cursor_lr.setToolTip(
            "Cursor L is always the cursor on the left, Cursor R is always the cursor on the right.\n"
            "Delta is always Cursor R − Cursor L."
        )
        self._cursor_mode_group.addButton(self._cursor_12, 0)
        self._cursor_mode_group.addButton(self._cursor_lr, 1)
        if self._settings.cursor_mode == "L/R":
            self._cursor_lr.setChecked(True)
        else:
            self._cursor_12.setChecked(True)
        mode_row = QHBoxLayout()
        mode_row.addWidget(self._cursor_12)
        mode_row.addWidget(self._cursor_lr)
        mode_row.addStretch()
        cursors_layout.addLayout(mode_row)

        self._cursor_persistent = QCheckBox("Persistent cursors")
        self._cursor_persistent.setChecked(self._settings.cursor_persistent)
        self._cursor_persistent.setToolTip(
            "If activated, cursors keep their last position when hidden and reshown.\n"
            "If deactivated, toggling the cursors makes them reappear in the current view."
        )
        cursors_layout.addWidget(self._cursor_persistent)
        cursors_layout.addStretch()
        tabs.addTab(cursors, "Cursors")

        layout.addWidget(tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._apply)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _apply(self) -> None:
        self._settings.check_for_updates = self._update_check.isChecked()
        self._settings.cursor_persistent = self._cursor_persistent.isChecked()
        self._settings.cursor_mode = "L/R" if self._cursor_lr.isChecked() else "1/2"
        self.accept()
