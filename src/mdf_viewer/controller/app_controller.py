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
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from mdf_viewer.model.mdf_loader import MdfLoader
from mdf_viewer.view_model.active_signal import ActiveSignal


@dataclass
class ActiveSignalSnapshot:
    """A lightweight copy of all display-state fields of one active signal.

    Used to preserve signal appearance across file loads when the
    "keep signals" feature is active.  Immutable once created.
    """
    name: str
    color: tuple[int, int, int]   # (r, g, b)
    line_width: int
    line_style: str
    display_mode: str
    marker_shape: str
    step_mode: bool
    enum_display_table: bool
    enum_display_cursor: bool
    enum_display_yaxis: bool
    group_name: str = ""

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
        self._selected_signals: list[ActiveSignal] = []
        self._color_index: int = 0
        self._cursor_ctrl = None  # set by set_cursor_controller()
        self._zoom_ctrl = None    # set by set_zoom_controller()
        self._y_grid_enabled: bool = False
        self._current_config_path: Path | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_cursor_controller(self, cursor_ctrl) -> None:
        """Wire in the CursorController after construction."""
        self._cursor_ctrl = cursor_ctrl

    def set_zoom_controller(self, zoom_ctrl) -> None:
        """Wire in the ZoomController after construction."""
        self._zoom_ctrl = zoom_ctrl

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

    def zoom_to_cursors(self) -> bool:
        """Zoom X to the cursor span in TWO mode. Returns True if applied."""
        if self._cursor_ctrl is None:
            return False
        span = self._cursor_ctrl.zoom_to_cursors()
        if span is None:
            return False
        if self._zoom_ctrl is not None:
            self._zoom_ctrl.before_discrete_action()
        self._plot.zoom_to_x_range(*span)
        if self._zoom_ctrl is not None:
            self._zoom_ctrl.after_discrete_action()
        return True

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

    # ------------------------------------------------------------------
    # Zoom proxy — MainWindow calls these for all zoom actions so the
    # ZoomController can wrap each one with before/after_discrete_action.
    # ------------------------------------------------------------------

    def zoom_to_fit(self) -> None:
        if self._zoom_ctrl is not None:
            self._zoom_ctrl.before_discrete_action()
        self._plot.zoom_to_fit()
        if self._zoom_ctrl is not None:
            self._zoom_ctrl.after_discrete_action()

    def zoom_y_to_view(self) -> bool:
        if self._zoom_ctrl is not None:
            self._zoom_ctrl.before_discrete_action()
        result = self._plot.zoom_y_to_view()
        if self._zoom_ctrl is not None:
            self._zoom_ctrl.after_discrete_action()
        return result

    # ------------------------------------------------------------------
    # Undo/redo proxy
    # ------------------------------------------------------------------

    def undo(self) -> None:
        if self._zoom_ctrl is not None:
            self._zoom_ctrl.undo()

    def redo(self) -> None:
        if self._zoom_ctrl is not None:
            self._zoom_ctrl.redo()

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
        if self._zoom_ctrl is not None:
            self._zoom_ctrl.clear()
        if self._settings is not None:
            self._settings.add_recent(path)
        self._current_config_path = None

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
        self.refresh_z_order()
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

    def recolor_signals(self, actives: list, color: QColor) -> None:
        """Recolor multiple signals to the same color."""
        for active in actives:
            self.recolor_signal(active, color)

    def on_share_y_axis_requested(self, signals: list) -> None:
        """Share a single Y-axis (ViewBox) across all given signals."""
        actives = [s for s in signals if s in self._active]
        if len(actives) < 2:
            return
        self._plot.share_signals(actives)
        self._refresh_table_group_state()

    def on_link_y_axes_requested(self, signals: list) -> None:
        """Link the Y-axes of all given signals so they pan/zoom together."""
        actives = [s for s in signals if s in self._active]
        if len(actives) < 2:
            return
        self._plot.link_signals(actives)
        self._refresh_table_group_state()

    def on_ungroup_y_axis_requested(self, signals: list) -> None:
        """Remove each given signal from its shared or linked group."""
        for active in signals:
            if active in self._active:
                self._plot.ungroup_signal(active)
        self._refresh_table_group_state()

    def _refresh_table_group_state(self) -> None:
        """Push the current grouped-signal set to the Active Signals Table."""
        self._table.set_grouped_signals(self._plot.get_grouped_signals())

    def remove_signals(self, actives: list) -> None:
        """Remove multiple signals from the plot and the table."""
        for active in list(actives):
            if active not in self._active:
                continue
            if self._cursor_ctrl is not None:
                self._cursor_ctrl.on_signal_removed(active)
            self._plot.remove_signal(active)
            self._active.remove(active)
            self._table.remove_row(active)
        if self._cursor_ctrl is not None:
            self._cursor_ctrl.refresh()
        self._refresh_table_group_state()

    def set_step_modes(self, actives: list, enabled: bool) -> None:
        """Set step mode to a specific state for each signal in *actives*."""
        for active in actives:
            if active not in self._active:
                continue
            active.step_mode = enabled
            self._plot.set_step_mode(active, enabled)

    def on_enum_table_requested(self, enabled: bool) -> None:
        """Toggle enum label display in the cursor-value table columns."""
        for active in self._selected_signals:
            if active not in self._active:
                continue
            active.enum_display_table = enabled
        if self._cursor_ctrl is not None:
            self._cursor_ctrl.refresh()

    def on_enum_cursor_requested(self, enabled: bool) -> None:
        """Toggle enum label display on the floating cursor plot label."""
        for active in self._selected_signals:
            if active not in self._active:
                continue
            active.enum_display_cursor = enabled
        if self._cursor_ctrl is not None:
            self._cursor_ctrl.refresh()

    def on_enum_yaxis_requested(self, enabled: bool) -> None:
        """Toggle enum label display on the Y-axis tick labels."""
        for active in self._selected_signals:
            if active not in self._active:
                continue
            active.enum_display_yaxis = enabled
            self._plot.set_enum_display_yaxis(active, enabled)

    def on_multi_selection(self, multi: bool) -> None:
        """Called when the table switches between single and multi-row selection."""
        if multi:
            self._signal_info.show_multi_selection()

    def set_multi_selected(self, actives: list) -> None:
        """Update the full multi-selection list and populate the Properties tab."""
        self._selected_signals = list(actives)
        if not actives:
            return
        modes = {a.display_mode for a in actives}
        shapes = {a.marker_shape for a in actives}
        widths = {a.line_width for a in actives}
        styles = {a.line_style for a in actives}
        mode = next(iter(modes)) if len(modes) == 1 else None
        shape = next(iter(shapes)) if len(shapes) == 1 else None
        width = next(iter(widths)) if len(widths) == 1 else None
        style = next(iter(styles)) if len(styles) == 1 else None
        ordered = [a for a in self._active if a in set(actives)]
        self._plot.set_selected_signals(ordered, all_signals=self._active, top_first=self._top_first)
        self._signal_info.set_properties(mode, shape, width, style)
        self._signal_info.set_enum_options(None, None, None)
        self._signal_info.enable_properties(True)

    def on_display_mode_requested(self, mode: str) -> None:
        """Apply a display mode change to all currently selected signals."""
        for active in self._selected_signals:
            if active not in self._active:
                continue
            active.display_mode = mode
            self._plot.set_display_mode(active, mode, active.marker_shape)

    def on_marker_shape_requested(self, shape: str) -> None:
        """Apply a marker shape change to all currently selected signals."""
        for active in self._selected_signals:
            if active not in self._active:
                continue
            active.marker_shape = shape
            if active.display_mode != "line":
                self._plot.set_display_mode(active, active.display_mode, shape)

    def on_line_width_requested(self, width: int) -> None:
        """Apply a line width change to all currently selected signals."""
        for active in self._selected_signals:
            if active not in self._active:
                continue
            self._plot.set_line_width(active, width)

    def on_line_style_requested(self, style: str) -> None:
        """Apply a line style change to all currently selected signals."""
        for active in self._selected_signals:
            if active not in self._active:
                continue
            self._plot.set_line_style(active, style)

    def refresh_display_names(self) -> None:
        """Reapply the display name formatter to the Active Signals Table."""
        if self._settings is not None:
            from mdf_viewer.settings import apply_display_name_rule
            formatter = lambda n: apply_display_name_rule(n, self._settings)
        else:
            formatter = lambda n: n
        self._table.set_name_formatter(formatter)

    def refresh_z_order(self) -> None:
        """Reapply Z-order, selection boost, and Y-axis visibility after a preference change."""
        self._plot.set_selected_line_boost(self._line_boost)
        self._plot.set_show_only_selected_y_axis(self._show_only_selected_y_axis)
        self._plot.set_selected_signals(
            self._selected_signals,
            all_signals=self._active,
            top_first=self._top_first,
        )

    @property
    def _top_first(self) -> bool:
        if self._settings is None:
            return True
        return self._settings.signal_z_order == "top_first"

    @property
    def _line_boost(self) -> int:
        if self._settings is None:
            return 1
        return self._settings.selected_line_boost

    @property
    def _show_only_selected_y_axis(self) -> bool:
        if self._settings is None:
            return False
        return self._settings.show_only_selected_y_axis

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
        self._refresh_table_group_state()

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
        self._refresh_table_group_state()

    def swimlanes(self) -> bool:
        """Arrange active signals in horizontal swimlanes.

        Returns True if applied, False when no signals are active.
        """
        if self._zoom_ctrl is not None:
            self._zoom_ctrl.before_discrete_action()
        result = self._plot.swimlanes(self._active)
        if self._zoom_ctrl is not None:
            self._zoom_ctrl.after_discrete_action()
        return result

    def reorder_signals(self, ordered: list) -> None:
        """Update the active signal order to match the table's new row order."""
        self._active = list(ordered)
        self.refresh_z_order()
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
        self._selected_signals = [active_signal] if active_signal is not None else []
        self._plot.set_selected_signals(self._selected_signals, all_signals=self._active, top_first=self._top_first)
        if active_signal is None:
            self._signal_info.clear()
        else:
            self._signal_info.set_metadata(active_signal.metadata)
            self._signal_info.set_properties(active_signal.display_mode, active_signal.marker_shape, active_signal.line_width, active_signal.line_style)
            if active_signal.metadata.enum_map:
                self._signal_info.set_enum_options(
                    active_signal.enum_display_table,
                    active_signal.enum_display_cursor,
                    active_signal.enum_display_yaxis,
                )
            else:
                self._signal_info.set_enum_options(None, None, None)
            self._signal_info.enable_properties(True)

    def snapshot_active_signals(self) -> list[ActiveSignalSnapshot]:
        """Capture the display state of all active signals, in table order."""
        snapshots = []
        for active in self._active:
            c = active.color
            snapshots.append(ActiveSignalSnapshot(
                name=active.metadata.name,
                color=(c.red(), c.green(), c.blue()),
                line_width=active.line_width,
                line_style=active.line_style,
                display_mode=active.display_mode,
                marker_shape=active.marker_shape,
                step_mode=active.step_mode,
                enum_display_table=active.enum_display_table,
                enum_display_cursor=active.enum_display_cursor,
                enum_display_yaxis=active.enum_display_yaxis,
                group_name=active.metadata.group_name,
            ))
        return snapshots

    def find_signal_by_name(self, name: str) -> list:
        """Return all SignalMetadata entries in the loaded file that match *name*."""
        return self._loader.find_signal_by_name(name)

    def restore_signals(
        self, resolved: list[tuple[ActiveSignalSnapshot, int, int]]
    ) -> None:
        """Re-add signals from (snapshot, group_index, channel_index) tuples.

        Each signal is added via the normal path (palette color), then all
        display attributes from the snapshot are applied immediately.
        """
        from PyQt6.QtGui import QColor
        for snap, gi, ci in resolved:
            try:
                added = self.add_signal(gi, ci)
            except Exception:
                continue
            if not added:
                continue
            active = self._active[-1]
            new_color = QColor(*snap.color)
            # Set color on the active signal first, then propagate to the plot.
            active.color = new_color
            self._plot.recolor_signal(active, new_color)
            self._table.set_row_color(active, new_color)
            # Restore other display properties.
            if snap.line_width != active.line_width:
                self._plot.set_line_width(active, snap.line_width)
                active.line_width = snap.line_width
            if snap.line_style != active.line_style:
                self._plot.set_line_style(active, snap.line_style)
                active.line_style = snap.line_style
            if snap.display_mode != active.display_mode or snap.marker_shape != active.marker_shape:
                self._plot.set_display_mode(active, snap.display_mode, snap.marker_shape)
                active.display_mode = snap.display_mode
                active.marker_shape = snap.marker_shape
            if snap.step_mode != active.step_mode:
                self._plot.set_step_mode(active, snap.step_mode)
                active.step_mode = snap.step_mode
            active.enum_display_table = snap.enum_display_table
            active.enum_display_cursor = snap.enum_display_cursor
            if snap.enum_display_yaxis != active.enum_display_yaxis:
                self._plot.set_enum_display_yaxis(active, snap.enum_display_yaxis)
                active.enum_display_yaxis = snap.enum_display_yaxis
        if self._cursor_ctrl is not None:
            self._cursor_ctrl.refresh()

    def capture_config(self, config_path: Path) -> "ViewerConfig":
        """Capture the current viewer state as a ViewerConfig.

        *config_path* is the intended save location — needed to compute
        relative measurement paths later in ConfigManager.save().
        """
        from mdf_viewer.model.viewer_config import SignalConfig, ViewerConfig

        snapshots = self.snapshot_active_signals()
        signal_configs = tuple(
            SignalConfig(
                name=s.name,
                group_name=s.group_name,
                color=s.color,
                line_width=s.line_width,
                line_style=s.line_style,
                display_mode=s.display_mode,
                marker_shape=s.marker_shape,
                step_mode=s.step_mode,
                enum_display_table=s.enum_display_table,
                enum_display_cursor=s.enum_display_cursor,
                enum_display_yaxis=s.enum_display_yaxis,
            )
            for s in snapshots
        )

        zoom = self._plot.get_zoom_state(self._active)
        x_range = tuple(zoom.x_range)  # type: ignore[arg-type]
        y_ranges: dict[str, tuple[float, float]] = {}
        for active, yr in zoom.y_ranges.items():
            y_ranges[active.metadata.name] = tuple(yr)  # type: ignore[assignment]

        shared_raw, linked_raw = self._plot.get_axis_grouping()
        shared_groups = tuple(tuple(g) for g in shared_raw)
        linked_groups = tuple(tuple(g) for g in linked_raw)

        cursor_snap: dict = {}
        if self._cursor_ctrl is not None:
            cursor_snap = self._cursor_ctrl.snapshot()
        cursor_mode = cursor_snap.get("mode", "HIDDEN")
        cursor_pos_raw = cursor_snap.get("positions", [0.0, 0.0])
        cursor_positions: tuple[float, float] = (
            float(cursor_pos_raw[0]),
            float(cursor_pos_raw[1]),
        )

        selected_name = (
            self._selected.metadata.name if self._selected is not None else None
        )

        meas_path = ""
        if self._loader.is_open and self._loader._path is not None:
            meas_path = str(self._loader._path)

        from mdf_viewer.config_manager import CONFIG_FORMAT_VERSION
        return ViewerConfig(
            format_version=CONFIG_FORMAT_VERSION,
            measurement_path=meas_path,
            signals=signal_configs,
            x_range=x_range,  # type: ignore[arg-type]
            y_ranges=y_ranges,
            shared_groups=shared_groups,
            linked_groups=linked_groups,
            cursor_mode=cursor_mode,
            cursor_positions=cursor_positions,
            selected_signal=selected_name,
        )

    def restore_config(
        self,
        config: "ViewerConfig",
        resolved_signals: "list[tuple[ActiveSignalSnapshot, int, int]]",
    ) -> None:
        """Restore a saved viewer session after the measurement file is loaded.

        *resolved_signals* is a list of (snapshot, group_index, channel_index)
        tuples — the caller is responsible for resolving name → indices.
        """
        from PyQt6.QtGui import QColor
        from mdf_viewer.view_model.zoom_state import ZoomState

        self.restore_signals(resolved_signals)

        # Restore axis grouping — must happen after signals are added
        shared = [list(g) for g in config.shared_groups]
        linked = [list(g) for g in config.linked_groups]
        self._plot.restore_axis_grouping(shared, linked, self._active)
        self._refresh_table_group_state()

        # Restore zoom — must happen after grouping (ViewBoxes may have changed)
        y_ranges: dict = {}
        for active in self._active:
            name = active.metadata.name
            if name in config.y_ranges:
                y_ranges[active] = config.y_ranges[name]
        zoom_state = ZoomState(x_range=config.x_range, y_ranges=y_ranges)
        self._plot.set_zoom_state(zoom_state, self._active)

        # Restore cursor state
        if self._cursor_ctrl is not None:
            self._cursor_ctrl.restore({
                "mode": config.cursor_mode,
                "positions": list(config.cursor_positions),
            })

        # Restore selection
        if config.selected_signal is not None:
            for active in self._active:
                if active.metadata.name == config.selected_signal:
                    self.set_selected_signal(active)
                    break

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

    @property
    def current_config_path(self) -> Path | None:
        return self._current_config_path

    @current_config_path.setter
    def current_config_path(self, value: Path | None) -> None:
        self._current_config_path = value
