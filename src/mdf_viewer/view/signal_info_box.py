"""SignalInfoBox — bottom-right panel showing metadata and properties for the selected signal.

Two tabs:
  * Info — read-only metadata (name, unit, min/max, etc.)
  * Properties — per-signal display settings (display mode, marker shape)

Driven by the Active Signals Table selection.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFormLayout,
    QFrame,
    QLabel,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.view.measurement_info_box import _add_row, _clear_form

_DISPLAY_MODES: list[tuple[str, str]] = [
    ("line", "Line"),
    ("line_marker", "Line & Marker"),
    ("marker", "Marker Only"),
]

_MARKER_SHAPES: list[tuple[str, str]] = [
    ("circle", "Circle"),
    ("square", "Square"),
    ("diamond", "Diamond"),
    ("cross", "Cross"),
]


_LINE_WIDTH_MIN = 1
_LINE_WIDTH_MAX = 8
_LINE_WIDTH_MIXED = 0  # sentinel: spinbox shows "—" for mismatched multi-select


class _SignalPropertiesWidget(QWidget):
    """Display-mode, marker-shape, and line-width controls for one or more selected signals."""

    display_mode_requested = pyqtSignal(str)
    marker_shape_requested = pyqtSignal(str)
    line_width_requested = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        form = QFormLayout(self)
        form.setContentsMargins(4, 8, 4, 4)

        self._mode_combo = QComboBox()
        for _, label in _DISPLAY_MODES:
            self._mode_combo.addItem(label)
        form.addRow("Display:", self._mode_combo)

        self._shape_combo = QComboBox()
        for _, label in _MARKER_SHAPES:
            self._shape_combo.addItem(label)
        form.addRow("Marker:", self._shape_combo)

        self._width_spin = QSpinBox()
        self._width_spin.setMinimum(_LINE_WIDTH_MIXED)
        self._width_spin.setMaximum(_LINE_WIDTH_MAX)
        self._width_spin.setSpecialValueText("—")
        form.addRow("Line width:", self._width_spin)

        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self._shape_combo.currentIndexChanged.connect(self._on_shape_changed)
        self._width_spin.valueChanged.connect(self._on_width_changed)

    def set_properties(self, mode: str | None, shape: str | None, width: int | None = None) -> None:
        """Populate the controls. Pass None for a field to show a blank (mismatched multi-select)."""
        self._mode_combo.blockSignals(True)
        self._shape_combo.blockSignals(True)
        self._width_spin.blockSignals(True)
        mode_keys = [k for k, _ in _DISPLAY_MODES]
        self._mode_combo.setCurrentIndex(mode_keys.index(mode) if mode in mode_keys else -1)
        shape_keys = [k for k, _ in _MARKER_SHAPES]
        self._shape_combo.setCurrentIndex(shape_keys.index(shape) if shape in shape_keys else -1)
        self._width_spin.setValue(width if width is not None else _LINE_WIDTH_MIXED)
        self._update_shape_enabled()
        self._mode_combo.blockSignals(False)
        self._shape_combo.blockSignals(False)
        self._width_spin.blockSignals(False)

    def _on_mode_changed(self, index: int) -> None:
        self._update_shape_enabled()
        if 0 <= index < len(_DISPLAY_MODES):
            self.display_mode_requested.emit(_DISPLAY_MODES[index][0])

    def _on_shape_changed(self, index: int) -> None:
        if 0 <= index < len(_MARKER_SHAPES):
            self.marker_shape_requested.emit(_MARKER_SHAPES[index][0])

    def _on_width_changed(self, value: int) -> None:
        if value >= _LINE_WIDTH_MIN:
            self.line_width_requested.emit(value)

    def _update_shape_enabled(self) -> None:
        self._shape_combo.setEnabled(self._mode_combo.currentIndex() != 0)


class SignalInfoBox(QWidget):
    """Info and Properties tabs for the selected signal(s)."""

    display_mode_requested = pyqtSignal(str)
    marker_shape_requested = pyqtSignal(str)
    line_width_requested = pyqtSignal(int)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(80)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._tabs = QTabWidget()
        layout.addWidget(self._tabs)

        # ── Info tab ──────────────────────────────────────────────────────
        info_widget = QWidget()
        info_layout = QVBoxLayout(info_widget)
        info_layout.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget()
        info_layout.addWidget(self._stack)

        self._placeholder = QLabel("No signal selected.")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stack.addWidget(self._placeholder)  # index 0

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._content = QWidget()
        self._form = QFormLayout(self._content)
        self._form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        scroll.setWidget(self._content)
        self._stack.addWidget(scroll)  # index 1

        self._tabs.addTab(info_widget, "Info")

        # ── Properties tab ────────────────────────────────────────────────
        self._props_widget = _SignalPropertiesWidget()
        self._tabs.addTab(self._props_widget, "Properties")
        self._tabs.setTabEnabled(1, False)

        self._props_widget.display_mode_requested.connect(self.display_mode_requested)
        self._props_widget.marker_shape_requested.connect(self.marker_shape_requested)
        self._props_widget.line_width_requested.connect(self.line_width_requested)

    # ------------------------------------------------------------------
    # Info tab API
    # ------------------------------------------------------------------

    def set_metadata(self, meta: SignalMetadata) -> None:
        """Populate the Info tab from a SignalMetadata and show it."""
        _clear_form(self._form)
        for label, value in _metadata_rows(meta):
            _add_row(self._form, label, value)
        self._stack.setCurrentIndex(1)

    def show_multi_selection(self) -> None:
        """Show the 'multiple signals selected' placeholder on the Info tab."""
        self._placeholder.setText("Multiple signals selected.")
        self._stack.setCurrentIndex(0)

    def clear(self) -> None:
        """Reset Info tab to placeholder and disable the Properties tab."""
        self._placeholder.setText("No signal selected.")
        _clear_form(self._form)
        self._stack.setCurrentIndex(0)
        self._tabs.setTabEnabled(1, False)

    # ------------------------------------------------------------------
    # Properties tab API
    # ------------------------------------------------------------------

    def set_properties(self, mode: str | None, shape: str | None, width: int | None = None) -> None:
        """Populate the Properties tab. None values show blank (mismatched multi-select)."""
        self._props_widget.set_properties(mode, shape, width)

    def enable_properties(self, enabled: bool) -> None:
        """Enable or disable the Properties tab."""
        self._tabs.setTabEnabled(1, enabled)


# ---------------------------------------------------------------------------
# Row builder
# ---------------------------------------------------------------------------

def _metadata_rows(meta: SignalMetadata) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = [("Name", meta.name)]
    if meta.unit:
        rows.append(("Unit", meta.unit))
    if meta.data_type:
        rows.append(("Data type", meta.data_type))
    if meta.sample_count is not None:
        rows.append(("Samples", f"{meta.sample_count:,}"))
    if meta.sample_count is not None and meta.sample_count >= 2:
        if meta.raster_s is not None:
            rows.append(("Raster", _format_raster(meta.raster_s)))
        else:
            rows.append(("Raster", "variable"))
    if meta.min_value is not None:
        rows.append(("Min", _format_number(meta.min_value)))
    if meta.max_value is not None:
        rows.append(("Max", _format_number(meta.max_value)))
    if meta.comment:
        rows.append(("Comment", meta.comment))
    for key, value in meta.extra.items():
        rows.append((str(key), str(value)))
    return rows


def _format_raster(raster_s: float) -> str:
    ms = raster_s * 1000
    if ms <= 500:
        return f"{ms:.4g} ms"
    return f"{raster_s:.4g} s"


def _format_number(value: float) -> str:
    return f"{value:.6g}"
