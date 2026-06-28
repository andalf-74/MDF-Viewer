from __future__ import annotations

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mdf_viewer.settings import (
    DEFAULT_CURSOR_COLOR_C1,
    DEFAULT_CURSOR_COLOR_C2,
    DEFAULT_CURSOR_COLOR_CL,
    DEFAULT_CURSOR_COLOR_CR,
    DEFAULT_CURSOR_STEP_PIXELS,
    DEFAULT_CURSOR_STEP_SAMPLES,
    DEFAULT_CURSOR_STEP_TIME_MS,
    DEFAULT_DELTA_TIME_COLOR,
    DEFAULT_KEEP_SIGNALS_ON_LOAD,
    DEFAULT_SELECTED_LINE_BOOST,
    DEFAULT_SHOW_ONLY_SELECTED_Y_AXIS,
    Settings,
)

_Z_ORDER_OPTIONS: list[tuple[str, str]] = [
    ("top_first",    "Top row on top"),
    ("bottom_first", "Bottom row on top"),
]


_FALLBACK_PREVIEW = "ZF_DTI._.AutoDiagPosition.PosADP"


class PreferencesDialog(QDialog):
    def __init__(
        self,
        settings: Settings,
        parent: QWidget | None = None,
        preview_name: str | None = None,
    ) -> None:
        super().__init__(parent)
        self._settings = settings
        self._preview_name = preview_name or _FALLBACK_PREVIEW
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

        undo_row = QHBoxLayout()
        undo_row.addWidget(QLabel("Undo steps:"))
        self._undo_steps = QSpinBox()
        self._undo_steps.setMinimum(1)
        self._undo_steps.setMaximum(100)
        self._undo_steps.setValue(self._settings.max_undo_steps)
        self._undo_steps.setToolTip(
            "Number of zoom steps that can be undone (Ctrl+Z).\n"
            "Higher values use more memory."
        )
        undo_row.addWidget(self._undo_steps)
        undo_row.addStretch()
        general_layout.addLayout(undo_row)

        general_layout.addSpacing(8)
        general_layout.addWidget(QLabel("When loading a new file while signals are active:"))
        self._keep_signals_group = QButtonGroup(self)
        self._keep_always = QRadioButton("Always keep active signals")
        self._keep_ask = QRadioButton("Ask each time")
        self._keep_never = QRadioButton("Always discard active signals")
        self._keep_signals_group.addButton(self._keep_always, 0)
        self._keep_signals_group.addButton(self._keep_ask, 1)
        self._keep_signals_group.addButton(self._keep_never, 2)
        setting = self._settings.keep_signals_on_load
        if setting == "ask":
            self._keep_ask.setChecked(True)
        elif setting == "never":
            self._keep_never.setChecked(True)
        else:
            self._keep_always.setChecked(True)
        general_layout.addWidget(self._keep_always)
        general_layout.addWidget(self._keep_ask)
        general_layout.addWidget(self._keep_never)

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

        cursors_layout.addSpacing(8)

        def _make_swatch(rgb: tuple[int, int, int]) -> _CursorColorSwatch:
            return _CursorColorSwatch(QColor(*rgb))

        self._swatch_c1 = _make_swatch(self._settings.cursor_color_c1)
        self._swatch_c2 = _make_swatch(self._settings.cursor_color_c2)
        self._swatch_cl = _make_swatch(self._settings.cursor_color_cl)
        self._swatch_cr = _make_swatch(self._settings.cursor_color_cr)

        color_grid = QGridLayout()
        color_grid.setHorizontalSpacing(6)
        color_grid.setColumnStretch(2, 1)  # gap column between the two pairs
        color_grid.setColumnStretch(5, 1)  # trailing stretch
        color_grid.addWidget(self._swatch_c1, 0, 0)
        color_grid.addWidget(QLabel("Cursor 1"), 0, 1)
        color_grid.addWidget(self._swatch_c2, 0, 3)
        color_grid.addWidget(QLabel("Cursor 2"), 0, 4)
        color_grid.addWidget(self._swatch_cl, 1, 0)
        color_grid.addWidget(QLabel("Cursor L"), 1, 1)
        color_grid.addWidget(self._swatch_cr, 1, 3)
        color_grid.addWidget(QLabel("Cursor R"), 1, 4)
        cursors_layout.addLayout(color_grid)

        cursors_layout.addSpacing(8)

        delta_row = QHBoxLayout()
        self._show_delta_time = QCheckBox("Show ∆-Time in Plot")
        self._show_delta_time.setChecked(self._settings.show_delta_time_in_plot)
        self._swatch_delta = _make_swatch(self._settings.delta_time_color)
        delta_row.addWidget(self._show_delta_time)
        delta_row.addStretch()
        delta_row.addWidget(self._swatch_delta)
        delta_row.addWidget(QLabel("∆-Time color"))
        cursors_layout.addLayout(delta_row)

        cursors_layout.addSpacing(8)

        # Arrow-key step
        step_row = QHBoxLayout()
        step_row.addWidget(QLabel("Arrow key step:"))
        self._step_unit = QComboBox()
        self._step_unit.addItems(["Samples", "Pixels", "Time"])
        unit_index = {"samples": 0, "pixels": 1, "time": 2}.get(
            self._settings.cursor_step_unit, 0
        )
        self._step_unit.setCurrentIndex(unit_index)
        step_row.addWidget(self._step_unit)

        self._step_amount = QDoubleSpinBox()
        self._step_amount.setMinimum(0.1)
        self._step_amount.setMaximum(99999.0)
        self._step_amount.setFixedWidth(80)
        step_row.addWidget(self._step_amount)

        self._step_unit_label = QLabel()
        step_row.addWidget(self._step_unit_label)
        step_row.addStretch()
        cursors_layout.addLayout(step_row)

        # Per-unit cached amounts (so switching units doesn't lose the value)
        self._step_values = {
            "samples": float(self._settings.cursor_step_samples),
            "pixels": float(self._settings.cursor_step_pixels),
            "time": self._settings.cursor_step_time_ms,
        }
        self._step_unit.currentIndexChanged.connect(self._on_step_unit_changed)
        self._on_step_unit_changed(unit_index)  # configure spinbox for current unit

        reset_row = QHBoxLayout()
        reset_row.addStretch()
        reset_btn = QPushButton("Reset to defaults")
        reset_btn.clicked.connect(self._reset_cursor_colors)
        reset_row.addWidget(reset_btn)
        cursors_layout.addLayout(reset_row)

        cursors_layout.addStretch()
        tabs.addTab(cursors, "Cursors")

        signals = QWidget()
        signals_layout = QVBoxLayout(signals)

        z_row = QHBoxLayout()
        z_row.addWidget(QLabel("Z-Order:"))
        self._z_order_combo = QComboBox()
        for _, label in _Z_ORDER_OPTIONS:
            self._z_order_combo.addItem(label)
        z_keys = [k for k, _ in _Z_ORDER_OPTIONS]
        self._z_order_combo.setCurrentIndex(
            z_keys.index(self._settings.signal_z_order)
            if self._settings.signal_z_order in z_keys else 0
        )
        self._z_order_combo.setToolTip(
            "Which row of the Active Signals Table appears in the foreground of the plot."
        )
        z_row.addWidget(self._z_order_combo)
        z_row.addStretch()
        signals_layout.addLayout(z_row)

        boost_row = QHBoxLayout()
        boost_row.addWidget(QLabel("Selected signal line boost:"))
        self._line_boost = QSpinBox()
        self._line_boost.setMinimum(0)
        self._line_boost.setMaximum(5)
        self._line_boost.setSuffix(" px")
        self._line_boost.setValue(self._settings.selected_line_boost)
        self._line_boost.setToolTip(
            "Extra line width applied to the selected signal.\n"
            "Set to 0 to disable the boost."
        )
        boost_row.addWidget(self._line_boost)
        boost_row.addStretch()
        signals_layout.addLayout(boost_row)

        self._show_only_selected_y_axis = QCheckBox("Show only selected signal's Y-axis")
        self._show_only_selected_y_axis.setChecked(self._settings.show_only_selected_y_axis)
        self._show_only_selected_y_axis.setToolTip(
            "When checked, only the Y-axis of the currently selected signal is shown.\n"
            "All other Y-axes are hidden to give the plot more horizontal space.\n"
            "When no signal is selected, all Y-axes are shown."
        )
        signals_layout.addWidget(self._show_only_selected_y_axis)

        signals_layout.addSpacing(8)

        from mdf_viewer.view._display_name_controls import DisplayNameRuleControls
        self._display_name_controls = DisplayNameRuleControls(
            self._settings, self._preview_name
        )
        signals_layout.addWidget(self._display_name_controls)

        signals_layout.addStretch()
        tabs.addTab(signals, "Signals")

        layout.addWidget(tabs)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._apply)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _apply(self) -> None:
        self._settings.check_for_updates = self._update_check.isChecked()
        self._settings.max_undo_steps = self._undo_steps.value()
        bid = self._keep_signals_group.checkedId()
        self._settings.keep_signals_on_load = ("always", "ask", "never")[bid] if bid >= 0 else DEFAULT_KEEP_SIGNALS_ON_LOAD
        self._settings.signal_z_order = _Z_ORDER_OPTIONS[self._z_order_combo.currentIndex()][0]
        self._settings.selected_line_boost = self._line_boost.value()
        self._settings.show_only_selected_y_axis = self._show_only_selected_y_axis.isChecked()
        self._display_name_controls.apply_to_settings(self._settings)
        self._settings.cursor_persistent = self._cursor_persistent.isChecked()
        self._settings.cursor_mode = "L/R" if self._cursor_lr.isChecked() else "1/2"
        self._settings.cursor_color_c1 = self._swatch_c1.rgb()
        self._settings.cursor_color_c2 = self._swatch_c2.rgb()
        self._settings.cursor_color_cl = self._swatch_cl.rgb()
        self._settings.cursor_color_cr = self._swatch_cr.rgb()
        self._settings.show_delta_time_in_plot = self._show_delta_time.isChecked()
        self._settings.delta_time_color = self._swatch_delta.rgb()
        # Flush the current spinbox value back to the cache before saving
        self._flush_step_amount()
        unit_key = ["samples", "pixels", "time"][self._step_unit.currentIndex()]
        self._settings.cursor_step_unit = unit_key
        self._settings.cursor_step_samples = max(1, int(self._step_values["samples"]))
        self._settings.cursor_step_pixels = max(1, int(self._step_values["pixels"]))
        self._settings.cursor_step_time_ms = max(0.1, self._step_values["time"])
        self.accept()

    def _on_step_unit_changed(self, index: int) -> None:
        self._flush_step_amount()
        unit_key = ["samples", "pixels", "time"][index]
        if unit_key == "time":
            self._step_amount.setDecimals(1)
            self._step_amount.setSingleStep(1.0)
            self._step_unit_label.setText("ms")
        else:
            self._step_amount.setDecimals(0)
            self._step_amount.setSingleStep(1.0)
            self._step_unit_label.setText("samples" if unit_key == "samples" else "px")
        self._step_amount.setValue(self._step_values[unit_key])
        self._current_step_unit_key = unit_key

    def _flush_step_amount(self) -> None:
        key = getattr(self, "_current_step_unit_key", None)
        if key is not None:
            self._step_values[key] = self._step_amount.value()

    def _reset_cursor_colors(self) -> None:
        self._swatch_c1.set_color(QColor(*DEFAULT_CURSOR_COLOR_C1))
        self._swatch_c2.set_color(QColor(*DEFAULT_CURSOR_COLOR_C2))
        self._swatch_cl.set_color(QColor(*DEFAULT_CURSOR_COLOR_CL))
        self._swatch_cr.set_color(QColor(*DEFAULT_CURSOR_COLOR_CR))
        self._swatch_delta.set_color(QColor(*DEFAULT_DELTA_TIME_COLOR))
        self._show_delta_time.setChecked(True)
        self._step_values = {
            "samples": float(DEFAULT_CURSOR_STEP_SAMPLES),
            "pixels": float(DEFAULT_CURSOR_STEP_PIXELS),
            "time": DEFAULT_CURSOR_STEP_TIME_MS,
        }
        self._on_step_unit_changed(0)
        self._step_unit.setCurrentIndex(0)


class _CursorColorSwatch(QPushButton):
    """Flat colored button that opens a color picker on click."""

    def __init__(self, color: QColor, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(20, 16)
        self.setFlat(True)
        self.set_color(color)
        self.clicked.connect(self._pick_color)

    def set_color(self, color: QColor) -> None:
        self._color = color
        self.setStyleSheet(
            f"background-color: {color.name()};"
            "border: 1px solid #666;"
            "border-radius: 2px;"
        )

    @property
    def color(self) -> QColor:
        return self._color

    def rgb(self) -> tuple[int, int, int]:
        return (self._color.red(), self._color.green(), self._color.blue())

    def _pick_color(self) -> None:
        color = QColorDialog.getColor(self._color, self)
        if color.isValid():
            self.set_color(color)
