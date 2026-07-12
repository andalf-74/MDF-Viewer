"""MeasurementMappingDialog — map a saved config's measurement slots onto
already-loaded measurements (#105).

Shown by MainWindow._on_apply_config() before applying a .mvc workspace's
tabs/stripes/signals onto whichever measurement(s) are already loaded,
without opening any file the config itself records (REQ-FILE-110..119).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from mdf_viewer.model.loaded_measurement import LoadedMeasurement
    from mdf_viewer.model.viewer_config import MeasurementConfig

_NONE_LABEL = "None"


class MeasurementMappingDialog(QDialog):
    """One combo box per saved measurement slot, picking a live measurement or None.

    Every row always offers every live measurement (REQ-FILE-113) — picking
    one already assigned to another row reassigns it here and resets that
    other row to "None", rather than hiding it from this row's choices.
    """

    def __init__(
        self,
        measurement_configs: "list[MeasurementConfig]",
        live_measurements: "list[LoadedMeasurement]",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._configs = measurement_configs
        self._live = live_measurements
        self._combos: list[QComboBox] = []
        self.setWindowTitle("Map Measurements")
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        form = QFormLayout()
        for index, mc in enumerate(self._configs):
            combo = QComboBox()
            combo.addItem(_NONE_LABEL, None)
            for measurement in self._live:
                combo.addItem(measurement.label, measurement)
            default = self._live[index] if index < len(self._live) else None
            combo.setCurrentIndex(combo.findData(default) if default is not None else 0)
            combo.currentIndexChanged.connect(self._on_selection_changed)
            self._combos.append(combo)
            file_label = Path(mc.path).name if mc.path else "no file recorded"
            form.addRow(f'"{mc.label}" (was: {file_label})', combo)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _on_selection_changed(self, _index: int) -> None:
        """Enforce the 1:1 mapping by override, not exclusion (REQ-FILE-113):
        if the row that just changed picked a measurement another row
        already held, that other row is reset to "None" — the newer
        selection always wins."""
        sender = self.sender()
        selected = sender.currentData()
        if selected is None:
            return
        for other in self._combos:
            if other is sender or other.currentData() is not selected:
                continue
            other.blockSignals(True)
            other.setCurrentIndex(0)
            other.blockSignals(False)

    def mapping(self) -> "list[LoadedMeasurement | None]":
        """Index-aligned to the measurement_configs passed to __init__."""
        return [combo.currentData() for combo in self._combos]
