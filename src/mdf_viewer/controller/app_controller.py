"""AppController — central coordinator between Model and View.

Owns application state that is not specific to a single widget:
  * the loaded MeasurementInfo and channel hierarchy
  * the list of ActiveSignal objects currently on the plot
  * the current selection in the Active Signals Table

It calls into the model (MdfLoader) to load data and tells the view what to
display, without either layer importing the other.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

from mdf_viewer.model.mdf_loader import MdfLoader
from mdf_viewer.view_model.active_signal import ActiveSignal

if TYPE_CHECKING:
    from PyQt6.QtGui import QColor
    from mdf_viewer.controller.interfaces import (
        MeasurementInfoProtocol,
        PlotAreaProtocol,
        SignalBrowserProtocol,
        SignalInfoProtocol,
        SignalTableProtocol,
    )
    from mdf_viewer.settings import Settings

# Ordered color palette for new signals; cycles on overflow.
_COLOR_PALETTE: tuple[tuple[int, int, int], ...] = (
    (255, 85, 85),    # red
    (85, 170, 255),   # blue
    (100, 220, 100),  # green
    (255, 170, 50),   # orange
    (200, 100, 200),  # purple
    (100, 220, 220),  # cyan
    (255, 230, 85),   # yellow
    (200, 150, 100),  # brown
)


class AppController:
    """Coordinates loading, active-signal management, and selection state."""

    def __init__(
        self,
        loader: MdfLoader,
        signal_browser: SignalBrowserProtocol,
        plot_area: PlotAreaProtocol,
        active_signals_table: SignalTableProtocol,
        measurement_info_box: MeasurementInfoProtocol,
        signal_info_box: SignalInfoProtocol,
        settings: Settings | None = None,
    ) -> None:
        self._loader = loader
        self._browser = signal_browser
        self._plot = plot_area
        self._table = active_signals_table
        self._info_box = measurement_info_box
        self._signal_info = signal_info_box
        self._settings = settings

        self._active: list[ActiveSignal] = []
        self._selected: ActiveSignal | None = None
        self._color_index: int = 0
        self._cursor_ctrl = None  # set by set_cursor_controller()
        self._y_grid_enabled: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_cursor_controller(self, cursor_ctrl) -> None:
        """Wire in the CursorController after construction."""
        self._cursor_ctrl = cursor_ctrl

    # ------------------------------------------------------------------
    # Cursor proxy — MainWindow calls these instead of CursorController
    # directly, so the view has a single controller contact point.
    # ------------------------------------------------------------------

    def toggle_cursor(self) -> None:
        if self._cursor_ctrl is not None:
            self._cursor_ctrl.toggle()

    def press_cursor1(self) -> None:
        if self._cursor_ctrl is not None:
            self._cursor_ctrl.press_cursor1()

    def press_cursor2(self) -> None:
        if self._cursor_ctrl is not None:
            self._cursor_ctrl.press_cursor2()

    def zoom_to_cursors(self) -> tuple[float, float] | None:
        if self._cursor_ctrl is not None:
            return self._cursor_ctrl.zoom_to_cursors()
        return None

    def press_left(self) -> None:
        if self._cursor_ctrl is not None:
            self._cursor_ctrl.press_left()

    def press_right(self) -> None:
        if self._cursor_ctrl is not None:
            self._cursor_ctrl.press_right()

    def set_cursor_mode_callback(self, cb) -> None:
        if self._cursor_ctrl is not None:
            self._cursor_ctrl.set_mode_changed_callback(cb)

    def refresh_cursors(self) -> None:
        """Refresh cursor display after preference changes."""
        if self._cursor_ctrl is not None:
            self._cursor_ctrl.refresh()

    def load_file(self, path: str | os.PathLike) -> None:
        """Open an MDF file and populate the Signal Browser.

        Clears all existing active signals and resets the color counter.
        Raises MdfLoadError if the file cannot be opened or read — the
        caller is responsible for showing an error dialog.
        """
        # Clear existing state; loader.open() closes the old file regardless
        # of whether the new one succeeds, so the UI must clear first.
        self.remove_all()
        self._browser.clear()
        self._info_box.clear()
        self._color_index = 0

        self._loader.open(path)  # raises MdfLoadError on failure

        groups = self._loader.channel_tree()
        info = self._loader.measurement_info()
        self._browser.populate(groups)
        self._info_box.set_info(info)
        if self._cursor_ctrl is not None:
            self._cursor_ctrl.reset()
        if self._settings is not None:
            self._settings.add_recent(path)

    def add_signal(self, group_index: int, channel_index: int) -> bool:
        """Load a channel and add it to the plot and the Active Signals Table.

        Returns True if added, False if the channel was already active.
        Raises MdfLoadError if the channel cannot be read or its samples are
        not numeric.
        """
        if any(
            s.metadata.group_index == group_index
            and s.metadata.channel_index == channel_index
            for s in self._active
        ):
            return False
        data, meta = self._loader.load_signal(group_index, channel_index)
        rgb = _COLOR_PALETTE[self._color_index % len(_COLOR_PALETTE)]
        self._color_index += 1
        active = ActiveSignal(data=data, metadata=meta, color=rgb, step_mode=meta.is_integer)
        self._active.append(active)
        self._plot.add_signal(active)
        self._table.add_row(active)
        if self._cursor_ctrl is not None:
            self._cursor_ctrl.refresh()
        return True

    def toggle_step_mode(self, active_signal: ActiveSignal) -> None:
        """Flip the step-mode flag for a signal and update the plot."""
        if active_signal not in self._active:
            return
        active_signal.step_mode = not active_signal.step_mode
        self._plot.set_step_mode(active_signal, active_signal.step_mode)

    def recolor_signal(self, active_signal: ActiveSignal, color: QColor) -> None:
        """Update the color of an active signal's curve, axis, and cursor labels."""
        self._plot.recolor_signal(active_signal, color)
        if self._cursor_ctrl is not None:
            self._cursor_ctrl.recolor_signal(active_signal, color)

    def remove_signal(self, active_signal: ActiveSignal) -> None:
        """Remove one signal from the plot and the table.

        No-op if the signal is not currently active.
        """
        if active_signal not in self._active:
            return
        # Cursor labels must be removed before the plot destroys the ViewBox.
        if self._cursor_ctrl is not None:
            self._cursor_ctrl.on_signal_removed(active_signal)
        self._plot.remove_signal(active_signal)
        self._active.remove(active_signal)
        self._table.remove_row(active_signal)
        if self._cursor_ctrl is not None:
            self._cursor_ctrl.refresh()
        if self._selected is active_signal:
            self.set_selected_signal(None)

    def remove_all(self) -> None:
        """Remove all active signals from the plot and the table."""
        # Clear cursor labels before ViewBoxes are destroyed.
        if self._cursor_ctrl is not None:
            self._cursor_ctrl.on_all_signals_cleared()
        for sig in list(self._active):
            self._plot.remove_signal(sig)
        self._active.clear()
        self._table.clear()
        self.set_selected_signal(None)

    def swimlanes(self) -> bool:
        """Arrange active signals in horizontal swimlanes.

        Returns True if applied, False when no signals are active.
        """
        return self._plot.swimlanes(self._active)

    def reorder_signals(self, ordered: list) -> None:
        """Update the active signal order to match the table's new row order."""
        self._active = list(ordered)
        if self._cursor_ctrl is not None:
            self._cursor_ctrl.refresh()

    def on_y_grid_toggled(self, enabled: bool) -> None:
        """Called when the user toggles Y-grid in the plot context menu."""
        self._y_grid_enabled = enabled
        if self._selected is not None:
            self._plot.set_y_grid(self._selected, enabled)

    def set_selected_signal(self, active_signal: ActiveSignal | None) -> None:
        """Update the selection and drive the Signal Info Box."""
        if self._y_grid_enabled:
            if self._selected is not None:
                self._plot.set_y_grid(self._selected, False)
            if active_signal is not None:
                self._plot.set_y_grid(active_signal, True)
        self._selected = active_signal
        if active_signal is None:
            self._signal_info.clear()
        else:
            self._signal_info.set_metadata(active_signal.metadata)

    # ------------------------------------------------------------------
    # Read-only state accessors
    # ------------------------------------------------------------------

    @property
    def is_file_loaded(self) -> bool:
        return self._loader.is_open

    @property
    def active_signals(self) -> list[ActiveSignal]:
        return list(self._active)

    @property
    def selected_signal(self) -> ActiveSignal | None:
        return self._selected
