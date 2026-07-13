"""SignalInfoBox — Info/Properties panel for the selected signal, hosted in the info drawer (#98).

Two sections stacked vertically in a resizable splitter (not tabs, so both
are visible at once in the drawer's narrow-but-tall shape):
  * Info — read-only metadata (name, unit, min/max, etc.)
  * Properties — per-signal display settings (display mode, marker shape)

Driven by the Active Signals Table selection.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QFrame,
    QLabel,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.view.measurement_info_box import _add_row, _add_wrapped_row, _clear_form
from mdf_viewer.view.widgets import make_splitter

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

_LINE_STYLES: list[tuple[str, str]] = [
    ("solid",    "Solid"),
    ("dashes",   "Dashes"),
    ("dots",     "Dots"),
    ("dash-dot", "Dash-Dot"),
]


_LINE_WIDTH_MIN = 1
_LINE_WIDTH_MAX = 8
_LINE_WIDTH_MIXED = 0  # sentinel: spinbox shows "—" for mismatched multi-select


class _SignalPropertiesWidget(QWidget):
    """Display-mode, marker-shape, line-width, and line-style controls for one or more selected signals."""

    display_mode_requested = pyqtSignal(str)
    marker_shape_requested = pyqtSignal(str)
    line_width_requested = pyqtSignal(int)
    line_style_requested = pyqtSignal(str)
    enum_table_requested = pyqtSignal(bool)
    enum_cursor_requested = pyqtSignal(bool)
    enum_yaxis_requested = pyqtSignal(bool)

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

        self._style_combo = QComboBox()
        for _, label in _LINE_STYLES:
            self._style_combo.addItem(label)
        form.addRow("Line style:", self._style_combo)

        # Enum label options — only shown when the selected signal has an enum map.
        self._enum_table_check = QCheckBox("Value table")
        self._enum_cursor_check = QCheckBox("Cursor label")
        self._enum_yaxis_check = QCheckBox("Y-axis")
        self._enum_container = QWidget()
        enum_layout = QVBoxLayout(self._enum_container)
        enum_layout.setContentsMargins(0, 0, 0, 0)
        enum_layout.setSpacing(2)
        enum_layout.addWidget(self._enum_table_check)
        enum_layout.addWidget(self._enum_cursor_check)
        enum_layout.addWidget(self._enum_yaxis_check)
        self._enum_label = QLabel("Enum labels:")
        form.addRow(self._enum_label, self._enum_container)
        self._enum_label.setVisible(False)
        self._enum_container.setVisible(False)

        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        self._shape_combo.currentIndexChanged.connect(self._on_shape_changed)
        self._width_spin.valueChanged.connect(self._on_width_changed)
        self._style_combo.currentIndexChanged.connect(self._on_style_changed)
        self._enum_table_check.toggled.connect(self.enum_table_requested)
        self._enum_cursor_check.toggled.connect(self.enum_cursor_requested)
        self._enum_yaxis_check.toggled.connect(self.enum_yaxis_requested)

    def set_enum_options(
        self,
        table: bool | None,
        cursor: bool | None,
        yaxis: bool | None,
    ) -> None:
        """Show or hide the enum-label checkboxes and set their states.

        Pass None for all three to hide the section (non-enum signal or multi-select).
        """
        visible = table is not None
        self._enum_label.setVisible(visible)
        self._enum_container.setVisible(visible)
        if not visible:
            return
        self._enum_table_check.blockSignals(True)
        self._enum_cursor_check.blockSignals(True)
        self._enum_yaxis_check.blockSignals(True)
        self._enum_table_check.setChecked(bool(table))
        self._enum_cursor_check.setChecked(bool(cursor))
        self._enum_yaxis_check.setChecked(bool(yaxis))
        self._enum_table_check.blockSignals(False)
        self._enum_cursor_check.blockSignals(False)
        self._enum_yaxis_check.blockSignals(False)

    def set_properties(self, mode: str | None, shape: str | None, width: int | None = None, style: str | None = None) -> None:
        """Populate the controls. Pass None for a field to show a blank (mismatched multi-select)."""
        self._mode_combo.blockSignals(True)
        self._shape_combo.blockSignals(True)
        self._width_spin.blockSignals(True)
        self._style_combo.blockSignals(True)
        mode_keys = [k for k, _ in _DISPLAY_MODES]
        self._mode_combo.setCurrentIndex(mode_keys.index(mode) if mode in mode_keys else -1)
        shape_keys = [k for k, _ in _MARKER_SHAPES]
        self._shape_combo.setCurrentIndex(shape_keys.index(shape) if shape in shape_keys else -1)
        self._width_spin.setValue(width if width is not None else _LINE_WIDTH_MIXED)
        style_keys = [k for k, _ in _LINE_STYLES]
        self._style_combo.setCurrentIndex(style_keys.index(style) if style in style_keys else -1)
        self._update_line_controls_enabled()
        self._mode_combo.blockSignals(False)
        self._shape_combo.blockSignals(False)
        self._width_spin.blockSignals(False)
        self._style_combo.blockSignals(False)

    def _on_mode_changed(self, index: int) -> None:
        self._update_line_controls_enabled()
        if 0 <= index < len(_DISPLAY_MODES):
            self.display_mode_requested.emit(_DISPLAY_MODES[index][0])

    def _on_shape_changed(self, index: int) -> None:
        if 0 <= index < len(_MARKER_SHAPES):
            self.marker_shape_requested.emit(_MARKER_SHAPES[index][0])

    def _on_width_changed(self, value: int) -> None:
        if value >= _LINE_WIDTH_MIN:
            self.line_width_requested.emit(value)

    def _on_style_changed(self, index: int) -> None:
        if 0 <= index < len(_LINE_STYLES):
            self.line_style_requested.emit(_LINE_STYLES[index][0])

    def _update_line_controls_enabled(self) -> None:
        marker_only = self._mode_combo.currentIndex() == 2  # "Marker Only"
        line_only = self._mode_combo.currentIndex() == 0    # "Line"
        self._shape_combo.setEnabled(not line_only)
        self._style_combo.setEnabled(not marker_only)
        self._width_spin.setEnabled(not marker_only)


class SignalInfoBox(QWidget):
    """Info and Properties sections, stacked vertically, for the selected signal(s)."""

    display_mode_requested = pyqtSignal(str)
    marker_shape_requested = pyqtSignal(str)
    line_width_requested = pyqtSignal(int)
    line_style_requested = pyqtSignal(str)
    enum_table_requested = pyqtSignal(bool)
    enum_cursor_requested = pyqtSignal(bool)
    enum_yaxis_requested = pyqtSignal(bool)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(80)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._splitter = make_splitter(Qt.Orientation.Vertical)
        layout.addWidget(self._splitter)

        # ── Info section ─────────────────────────────────────────────────
        info_section = QWidget()
        info_layout = QVBoxLayout(info_section)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(2)

        self._info_label = QLabel("Info")
        self._info_label.setStyleSheet("font-weight: bold;")
        info_layout.addWidget(self._info_label)

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

        # ── Properties section ───────────────────────────────────────────
        props_section = QWidget()
        props_layout = QVBoxLayout(props_section)
        props_layout.setContentsMargins(0, 0, 0, 0)
        props_layout.setSpacing(2)

        self._props_label = QLabel("Properties")
        self._props_label.setStyleSheet("font-weight: bold;")
        props_layout.addWidget(self._props_label)

        self._props_widget = _SignalPropertiesWidget()
        props_layout.addWidget(self._props_widget)

        # Properties (on top) is a short, fixed-row form; Info (below) is a
        # scrollable, variable-length metadata list. Bias both the initial
        # split and extra space on resize toward Info rather than the
        # QSplitter default of splitting newly-added panes evenly.
        self._splitter.addWidget(props_section)
        self._splitter.addWidget(info_section)
        self._splitter.setSizes([140, 300])
        self._splitter.setStretchFactor(0, 0)
        self._splitter.setStretchFactor(1, 1)

        self.enable_properties(False)

        self._props_widget.display_mode_requested.connect(self.display_mode_requested)
        self._props_widget.marker_shape_requested.connect(self.marker_shape_requested)
        self._props_widget.line_width_requested.connect(self.line_width_requested)
        self._props_widget.line_style_requested.connect(self.line_style_requested)
        self._props_widget.enum_table_requested.connect(self.enum_table_requested)
        self._props_widget.enum_cursor_requested.connect(self.enum_cursor_requested)
        self._props_widget.enum_yaxis_requested.connect(self.enum_yaxis_requested)

    # ------------------------------------------------------------------
    # Info tab API
    # ------------------------------------------------------------------

    def set_metadata(self, meta: SignalMetadata, display_name: str | None = None) -> None:
        """Populate the Info section from a SignalMetadata and show it.

        *display_name*, when given, overrides just the "Name" row's shown
        text (e.g. with a measurement-label prefix, REQ-PLOT-306) — every
        other row, and by-name resolution elsewhere, always uses meta.name
        directly (REQ-PLOT-307).
        """
        _clear_form(self._form)
        for label, value in _metadata_rows(meta):
            if label == "Name" and display_name is not None:
                value = display_name
            if label == "Comment":
                _add_wrapped_row(self._form, label, value)
            else:
                _add_row(self._form, label, value)
        self._stack.setCurrentIndex(1)

    def show_multi_selection(self) -> None:
        """Show the 'multiple signals selected' placeholder on the Info tab."""
        self._placeholder.setText("Multiple signals selected.")
        self._stack.setCurrentIndex(0)

    def clear(self) -> None:
        """Reset the Info section to its placeholder and disable Properties."""
        self._placeholder.setText("No signal selected.")
        _clear_form(self._form)
        self._stack.setCurrentIndex(0)
        self._props_widget.set_enum_options(None, None, None)
        self.enable_properties(False)

    # ------------------------------------------------------------------
    # Properties tab API
    # ------------------------------------------------------------------

    def set_properties(self, mode: str | None, shape: str | None, width: int | None = None, style: str | None = None) -> None:
        """Populate the Properties tab. None values show blank (mismatched multi-select)."""
        self._props_widget.set_properties(mode, shape, width, style)

    def set_enum_options(
        self,
        table: bool | None,
        cursor: bool | None,
        yaxis: bool | None,
    ) -> None:
        """Show/hide and populate the enum label checkboxes. Pass None to hide the section."""
        self._props_widget.set_enum_options(table, cursor, yaxis)

    def enable_properties(self, enabled: bool) -> None:
        """Enable or disable the Properties section."""
        self._props_widget.setEnabled(enabled)
        self._props_label.setEnabled(enabled)

    # ------------------------------------------------------------------
    # Layout persistence (.mvc session state)
    # ------------------------------------------------------------------

    def splitter_sizes(self) -> list[int]:
        """Current pixel sizes of the Info/Properties inner splitter."""
        return self._splitter.sizes()

    def set_splitter_sizes(self, sizes: list[int]) -> None:
        """Restore the Info/Properties inner splitter's pixel sizes."""
        self._splitter.setSizes(sizes)

    # ------------------------------------------------------------------
    # Plugin dock widgets (#73)
    # ------------------------------------------------------------------

    def add_plugin_section(self, title: str, widget: QWidget) -> None:
        """Add *widget* as another titled section, alongside Info/Properties
        (REQ-PLUGIN-220) — mirrors their own `[QLabel, content]` construction.

        Recomputes every pane's size/stretch factor afterward: `addWidget()`
        alone appends with a default (0) stretch factor and no explicit size
        entry, which — running before this splitter has ever been shown or
        laid out — tends to squeeze the new pane to a sliver rather than
        reasonably subdividing the available space. This deliberately
        flattens Info/Properties' original size bias into an equal split
        across every pane once a plugin section exists, rather than trying
        to preserve their original ratio around an arbitrary number of new
        plugin sections.
        """
        section = QWidget()
        section_layout = QVBoxLayout(section)
        section_layout.setContentsMargins(0, 0, 0, 0)
        section_layout.setSpacing(2)

        label = QLabel(title)
        label.setStyleSheet("font-weight: bold;")
        section_layout.addWidget(label)
        section_layout.addWidget(widget)

        self._splitter.addWidget(section)
        count = self._splitter.count()
        self._splitter.setSizes([200] * count)
        for i in range(count):
            self._splitter.setStretchFactor(i, 1)


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
