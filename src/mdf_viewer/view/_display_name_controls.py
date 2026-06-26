"""Shared widget for the display name rule controls.

Embedded in both PreferencesDialog (Signals tab) and SignalDisplayNameDialog.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QRadioButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from mdf_viewer.settings import apply_display_name_rule


class DisplayNameRuleControls(QWidget):
    """Controls for the signal display name rule: checkbox, separator, direction, count, preview."""

    def __init__(self, settings, preview_name: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._preview_name = preview_name
        self._build_ui(settings)

    def _build_ui(self, settings) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._enabled = QCheckBox("Shorten signal names")
        self._enabled.setChecked(settings.display_name_rule_enabled)
        layout.addWidget(self._enabled)

        form = QFormLayout()
        form.setContentsMargins(16, 4, 0, 4)

        self._separator = QLineEdit(settings.display_name_separator)
        self._separator.setMaximumWidth(60)
        self._separator.setToolTip("Character(s) used to split the signal name.")
        form.addRow("Separator:", self._separator)

        dir_row = QHBoxLayout()
        self._dir_group = QButtonGroup(self)
        self._dir_left = QRadioButton("Left")
        self._dir_right = QRadioButton("Right")
        self._dir_group.addButton(self._dir_left, 0)
        self._dir_group.addButton(self._dir_right, 1)
        if settings.display_name_direction == "left":
            self._dir_left.setChecked(True)
        else:
            self._dir_right.setChecked(True)
        dir_row.addWidget(self._dir_left)
        dir_row.addWidget(self._dir_right)
        dir_row.addStretch()
        dir_widget = QWidget()
        dir_widget.setLayout(dir_row)
        form.addRow("Direction:", dir_widget)

        self._segments = QSpinBox()
        self._segments.setMinimum(1)
        self._segments.setMaximum(10)
        self._segments.setValue(settings.display_name_segments)
        self._segments.setToolTip("Number of segments to show from the chosen direction.")
        form.addRow("Segments:", self._segments)

        layout.addLayout(form)

        preview_row = QHBoxLayout()
        preview_row.addWidget(QLabel("Preview:"))
        self._preview = QLabel()
        self._preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        preview_row.addWidget(self._preview)
        preview_row.addStretch()
        layout.addLayout(preview_row)

        self._controls_widgets = [
            self._separator, self._dir_left, self._dir_right, self._segments,
        ]

        self._enabled.toggled.connect(self._on_enabled_toggled)
        self._separator.textChanged.connect(self._update_preview)
        self._dir_left.toggled.connect(self._update_preview)
        self._segments.valueChanged.connect(self._update_preview)

        self._on_enabled_toggled(settings.display_name_rule_enabled)

    def _on_enabled_toggled(self, enabled: bool) -> None:
        for w in self._controls_widgets:
            w.setEnabled(enabled)
        self._update_preview()

    def _update_preview(self) -> None:
        if not self._enabled.isChecked():
            self._preview.setText(self._preview_name)
            return
        sep = self._separator.text()
        direction = "left" if self._dir_left.isChecked() else "right"
        n = self._segments.value()
        if not sep or sep not in self._preview_name:
            self._preview.setText(self._preview_name)
            return
        parts = self._preview_name.split(sep)
        segments = parts[-n:] if direction == "right" else parts[:n]
        self._preview.setText(sep.join(segments))

    def apply_to_settings(self, settings) -> None:
        settings.display_name_rule_enabled = self._enabled.isChecked()
        settings.display_name_separator = self._separator.text()
        settings.display_name_direction = "left" if self._dir_left.isChecked() else "right"
        settings.display_name_segments = self._segments.value()
