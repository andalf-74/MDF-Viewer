from __future__ import annotations

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mdf_viewer.settings import (
    DEFAULT_CURSOR_COLOR_C1,
    DEFAULT_CURSOR_COLOR_C2,
    DEFAULT_CURSOR_COLOR_CL,
    DEFAULT_CURSOR_COLOR_CR,
    DEFAULT_DELTA_TIME_COLOR,
    Settings,
)


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

        reset_row = QHBoxLayout()
        reset_row.addStretch()
        reset_btn = QPushButton("Reset to defaults")
        reset_btn.clicked.connect(self._reset_cursor_colors)
        reset_row.addWidget(reset_btn)
        cursors_layout.addLayout(reset_row)

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
        self._settings.cursor_color_c1 = self._swatch_c1.rgb()
        self._settings.cursor_color_c2 = self._swatch_c2.rgb()
        self._settings.cursor_color_cl = self._swatch_cl.rgb()
        self._settings.cursor_color_cr = self._swatch_cr.rgb()
        self._settings.show_delta_time_in_plot = self._show_delta_time.isChecked()
        self._settings.delta_time_color = self._swatch_delta.rgb()
        self.accept()

    def _reset_cursor_colors(self) -> None:
        self._swatch_c1.set_color(QColor(*DEFAULT_CURSOR_COLOR_C1))
        self._swatch_c2.set_color(QColor(*DEFAULT_CURSOR_COLOR_C2))
        self._swatch_cl.set_color(QColor(*DEFAULT_CURSOR_COLOR_CL))
        self._swatch_cr.set_color(QColor(*DEFAULT_CURSOR_COLOR_CR))
        self._swatch_delta.set_color(QColor(*DEFAULT_DELTA_TIME_COLOR))
        self._show_delta_time.setChecked(True)


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
