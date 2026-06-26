"""Standalone dialog for configuring the signal display name rule."""

from __future__ import annotations

from PyQt6.QtWidgets import (
    QButtonGroup,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)
from PyQt6.QtCore import Qt

from mdf_viewer.view._display_name_controls import DisplayNameRuleControls

_FALLBACK_PREVIEW = "ZF_DTI._.AutoDiagPosition.PosADP"


class SignalDisplayNameDialog(QDialog):
    """Small dialog opened from the Active Signals Table context menu."""

    def __init__(
        self,
        settings,
        preview_name: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self.setWindowTitle("Display Name Rule")
        self.setMinimumWidth(340)

        layout = QVBoxLayout(self)
        self._controls = DisplayNameRuleControls(
            settings,
            preview_name or _FALLBACK_PREVIEW,
        )
        layout.addWidget(self._controls)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._apply)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _apply(self) -> None:
        self._controls.apply_to_settings(self._settings)
        self.accept()
