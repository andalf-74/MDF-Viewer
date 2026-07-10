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
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from mdf_viewer.controller.events import (
    CursorMovedEvent,
    EventBus,
    FileLoadedEvent,
    SelectionChangedEvent,
    SignalAddedEvent,
    SignalRemovedEvent,
)
from mdf_viewer.errors import MdfLoadError
from mdf_viewer.model.loaded_measurement import LoadedMeasurement, make_label
from mdf_viewer.model.mdf_loader import MdfLoader
from mdf_viewer.view_model.active_signal import ActiveSignal


@dataclass
class LoadResult:
    """Per-file outcome of replace_measurements()/add_measurements() (#101).

    Files that fail to open are collected here rather than aborting the
    whole operation (REQ-FILE-023) — the caller (MainWindow) builds one
    error dialog naming every failed file from *failed*.
    """
    succeeded: list[LoadedMeasurement] = field(default_factory=list)
    failed: list[tuple[str, MdfLoadError]] = field(default_factory=list)


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


@dataclass
class TabWorkspace:
    """Everything that is independent per tab (#99).

    Each tab gets its own plot area, Active Signals Table, active-signal
    list, selection, and cursor/zoom controllers. AppController stays a
    single instance and switches which TabWorkspace its proxy methods
    operate on via `_active_tab_index`, rather than one AppController per
    tab — see docs/architecture.md "Main Widget Tabs (#99)".
    """
    plot: PlotAreaProtocol
    table: SignalTableProtocol
    active: list[ActiveSignal] = field(default_factory=list)
    selected: ActiveSignal | None = None
    selected_signals: list[ActiveSignal] = field(default_factory=list)
    color_index: int = 0
    cursor_ctrl: object = None  # set by set_cursor_controller()
    zoom_ctrl: object = None    # set by set_zoom_controller()
    cursor_stripes_view: object = None  # set directly by app.py's _wire_tab
    y_grid_enabled: bool = False


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
        loader_factory: Callable[[], MdfLoader] | None = None,
    ) -> None:
        # *loader* is the single-file legacy entry point's loader (load_file()
        # keeps driving this exact instance, matching pre-#101 behavior) and
        # the fallback used by add_signal()/find_signal_by_name()/etc. when
        # the multi-measurement pool below is empty. *loader_factory*
        # constructs a fresh MdfLoader for each measurement added via
        # replace_measurements()/add_measurements() — defaults to MdfLoader
        # itself (the real app's path); tests can override it to control
        # what each newly "opened" measurement looks like.
        self._loader = loader
        self._loader_factory: Callable[[], MdfLoader] = loader_factory or MdfLoader
        self._measurements: list[LoadedMeasurement] = []
        self._browser = signal_browser
        self._info_box = measurement_info_box
        self._signal_info = signal_info_box
        self._settings = settings

        self._workspaces: list[TabWorkspace] = [
            TabWorkspace(plot=plot_area, table=active_signals_table)
        ]
        self._active_tab_index: int = 0

        self._current_config_path: Path | None = None
        self.events = EventBus()

    def _default_measurement(self) -> LoadedMeasurement | None:
        """Resolve an implicit measurement when the pool has exactly one entry.

        Lets single-measurement call sites (including every pre-#101 test)
        keep calling add_signal(gi, ci) without naming a measurement.
        Returns None when the pool is empty (falls back to the legacy
        self._loader) or ambiguous (>=2 measurements — the caller must
        specify one explicitly; MainWindow does so from M3 onward).
        """
        if len(self._measurements) == 1:
            return self._measurements[0]
        return None

    @property
    def measurement_count(self) -> int:
        return len(self._measurements)

    @property
    def measurements(self) -> list[LoadedMeasurement]:
        return list(self._measurements)

    def measurement_at(self, index: int) -> LoadedMeasurement | None:
        """The pool entry at *index* (Signal Browser selector position), or None if out of range."""
        if 0 <= index < len(self._measurements):
            return self._measurements[index]
        return None

    def channel_tree_for_measurement(self, index: int) -> list:
        """The channel_tree() for the measurement at *index* (REQ-BROWSER-051), or [] if out of range."""
        measurement = self.measurement_at(index)
        return measurement.loader.channel_tree() if measurement is not None else []

    @property
    def current_workspace(self) -> TabWorkspace:
        """The active tab's TabWorkspace bundle.

        Public so app.py's tab-wiring factory can attach a freshly built
        CursorController/ZoomController to a specific tab (including the
        first one, created by __init__) without AppController needing to
        import those concrete view/controller classes itself.
        """
        return self._workspaces[self._active_tab_index]

    def create_tab(
        self, plot_area: PlotAreaProtocol, active_signals_table: SignalTableProtocol
    ) -> TabWorkspace:
        """Register a new tab's view widgets and make it the active tab.

        Returns the new TabWorkspace, still missing its cursor_ctrl/zoom_ctrl —
        the caller (app.py's tab-wiring factory) builds those against this
        specific workspace and attaches them via set_cursor_controller()/
        set_zoom_controller(), which target current_workspace and therefore
        this new tab as long as nothing else changes the active tab first.
        """
        workspace = TabWorkspace(plot=plot_area, table=active_signals_table)
        self._workspaces.append(workspace)
        self._active_tab_index = len(self._workspaces) - 1
        return workspace

    def switch_tab(self, index: int) -> None:
        """Make the tab at *index* the active one.

        Restores that tab's own last-selected signal in the shared
        Info/Properties drawer (REQ-PLOT-233) — the drawer is a single
        instance shared across tabs, so switching tabs must explicitly
        re-push whichever signal was last selected in the tab being
        switched to, rather than continuing to show the previous tab's.
        """
        if 0 <= index < len(self._workspaces):
            self._active_tab_index = index
            self._push_selection_to_drawer(self.current_workspace.selected)

    def remove_tab(self, index: int) -> None:
        """Remove the tab at *index*. No-op if it's the only remaining tab.

        Runs every one of that tab's active signals through the normal
        remove_signal pipeline first — closing a tab that still has signals
        in it (the view allows this after a confirmation prompt) used to
        just drop the TabWorkspace reference, leaking every curve/ViewBox/
        axis in it (same leak class as the stripe/signal-lifecycle bugs
        fixed in plot_stripe.py, #120, just in the tab-lifecycle path
        instead).

        Does not change which tab is active — the view computes the tab to
        activate next (REQ-PLOT-253: the left neighbor) before this shifts
        list positions, then calls switch_tab() itself. The clamp here is
        just a safety net in case switch_tab() isn't called immediately.
        """
        if len(self._workspaces) <= 1:
            return
        workspace = self._workspaces[index]
        if workspace.cursor_ctrl is not None:
            workspace.cursor_ctrl.on_all_signals_cleared()
        for sig in list(workspace.active):
            workspace.plot.remove_signal(sig)
            self.events.signal_removed.emit(SignalRemovedEvent(signal=sig, tab=workspace))
        workspace.active.clear()
        workspace.table.clear()
        del self._workspaces[index]
        if self._active_tab_index >= len(self._workspaces):
            self._active_tab_index = len(self._workspaces) - 1

    def tab_has_signals(self, index: int) -> bool:
        """Whether the tab at *index* has any active signals (REQ-PLOT-252)."""
        if not (0 <= index < len(self._workspaces)):
            return False
        return bool(self._workspaces[index].active)

    @property
    def tab_count(self) -> int:
        return len(self._workspaces)

    def reorder_tabs(self, plot_areas_in_order: list) -> None:
        """Resync workspace order after a tab-bar drag reorder (REQ-PLOT-243).

        Reordering is cosmetic only, but `_workspaces` must still track visual
        tab order — switch_tab(index) resolves by list position, so a
        drag-reorder that isn't mirrored here would silently point future
        switch_tab() calls at the wrong workspace. Takes the new order as
        plot-area identities (matched against each TabWorkspace.plot) rather
        than raw indices, since the view rebuilds this from the tab widget's
        settled state rather than trying to interpret individual drag events.
        """
        active_workspace = self.current_workspace
        by_plot = {ws.plot: ws for ws in self._workspaces}
        self._workspaces = [by_plot[plot_area] for plot_area in plot_areas_in_order]
        self._active_tab_index = self._workspaces.index(active_workspace)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_cursor_controller(self, cursor_ctrl) -> None:
        """Wire in the CursorController after construction."""
        workspace = self.current_workspace
        workspace.cursor_ctrl = cursor_ctrl
        # Bind the callback to *workspace* specifically (captured now, while
        # it's still the current tab) rather than reading current_workspace
        # when the callback fires later — otherwise a background tab's
        # cursor move would get tagged with whichever tab happens to be
        # active at that moment instead of the tab it actually came from.
        cursor_ctrl.set_position_changed_callback(
            lambda positions, mode: self._emit_cursor_moved(positions, mode, workspace)
        )

    def _emit_cursor_moved(self, positions: list[float], mode, tab) -> None:
        self.events.cursor_moved.emit(CursorMovedEvent(positions=positions, mode=mode, tab=tab))

    def set_zoom_controller(self, zoom_ctrl) -> None:
        """Wire in the ZoomController after construction."""
        self.current_workspace.zoom_ctrl = zoom_ctrl

    # ------------------------------------------------------------------
    # Cursor proxy — MainWindow calls these instead of CursorController
    # directly, so the view has a single controller contact point.
    # ------------------------------------------------------------------

    def toggle_cursor(self) -> None:
        if self.current_workspace.cursor_ctrl is not None:
            self.current_workspace.cursor_ctrl.toggle()

    def press_cursor1(self) -> None:
        if self.current_workspace.cursor_ctrl is not None:
            self.current_workspace.cursor_ctrl.press_cursor1()

    def press_cursor2(self) -> None:
        if self.current_workspace.cursor_ctrl is not None:
            self.current_workspace.cursor_ctrl.press_cursor2()

    def zoom_to_cursors(self) -> bool:
        """Zoom X to the cursor span in TWO mode. Returns True if applied."""
        current = self.current_workspace
        if current.cursor_ctrl is None:
            return False
        span = current.cursor_ctrl.zoom_to_cursors()
        if span is None:
            return False
        if current.zoom_ctrl is not None:
            current.zoom_ctrl.before_discrete_action()
        current.plot.zoom_to_x_range(*span)
        if current.zoom_ctrl is not None:
            current.zoom_ctrl.after_discrete_action()
        return True

    def press_left(self) -> None:
        if self.current_workspace.cursor_ctrl is not None:
            self.current_workspace.cursor_ctrl.press_left()

    def press_right(self) -> None:
        if self.current_workspace.cursor_ctrl is not None:
            self.current_workspace.cursor_ctrl.press_right()

    def set_cursor_mode_callback(self, cb) -> None:
        if self.current_workspace.cursor_ctrl is not None:
            self.current_workspace.cursor_ctrl.set_mode_changed_callback(cb)

    def refresh_cursors(self) -> None:
        """Refresh cursor display after preference changes."""
        if self.current_workspace.cursor_ctrl is not None:
            self.current_workspace.cursor_ctrl.refresh()

    # ------------------------------------------------------------------
    # Zoom proxy — MainWindow calls these for all zoom actions so the
    # ZoomController can wrap each one with before/after_discrete_action.
    # ------------------------------------------------------------------

    def zoom_to_fit(self) -> None:
        current = self.current_workspace
        if current.zoom_ctrl is not None:
            current.zoom_ctrl.before_discrete_action()
        current.plot.zoom_to_fit(all_stripes=self._zoom_all_stripes)
        if current.zoom_ctrl is not None:
            current.zoom_ctrl.after_discrete_action()

    def zoom_y_to_view(self) -> bool:
        current = self.current_workspace
        if current.zoom_ctrl is not None:
            current.zoom_ctrl.before_discrete_action()
        result = current.plot.zoom_y_to_view(all_stripes=self._zoom_all_stripes)
        if current.zoom_ctrl is not None:
            current.zoom_ctrl.after_discrete_action()
        return result

    # ------------------------------------------------------------------
    # Undo/redo proxy
    # ------------------------------------------------------------------

    def undo(self) -> None:
        if self.current_workspace.zoom_ctrl is not None:
            self.current_workspace.zoom_ctrl.undo()

    def redo(self) -> None:
        if self.current_workspace.zoom_ctrl is not None:
            self.current_workspace.zoom_ctrl.redo()

    def load_file(self, path: str | os.PathLike) -> None:
        """Open an MDF file and populate the Signal Browser.

        Back-compat single-file entry point, kept for existing callers and
        tests — new code should prefer replace_measurements()/
        add_measurements() (#101). Drives the loader injected at
        construction (self._loader) rather than loader_factory, matching
        pre-#101 behavior of reusing one fixed loader across repeated
        calls; also registers the loaded file as the sole entry in the
        multi-measurement pool so downstream #101 code (axis rows, name
        prefixing, etc.) sees it uniformly.

        Clears all existing active signals and resets the color counter.
        Raises MdfLoadError if the file cannot be opened or read — the
        caller is responsible for showing an error dialog.
        """
        # Clear existing state; loader.open() closes the old file regardless
        # of whether the new one succeeds, so the UI must clear first.
        self.remove_all()
        self._browser.clear()
        self._info_box.clear()
        self.current_workspace.color_index = 0

        self._loader.open(path)  # raises MdfLoadError on failure

        groups = self._loader.channel_tree()
        info = self._loader.measurement_info()
        self._measurements = [
            LoadedMeasurement(loader=self._loader, info=info, label=make_label(path, []))
        ]
        self._browser.populate(groups)
        self._info_box.set_info(info)
        if self.current_workspace.cursor_ctrl is not None:
            self.current_workspace.cursor_ctrl.reset()
        if self.current_workspace.zoom_ctrl is not None:
            self.current_workspace.zoom_ctrl.clear()
        if self._settings is not None:
            self._settings.add_recent(path)
        self._current_config_path = None
        self.events.file_loaded.emit(FileLoadedEvent(path=str(path), tab=self.current_workspace))

    def replace_measurements(self, paths: list[str | os.PathLike]) -> LoadResult:
        """Replace every currently loaded measurement with newly opened file(s) (REQ-FILE-021).

        Clears the active tab's signals, the Signal Browser, and the
        Measurement Info Box, then opens every path in *paths* as a fresh
        measurement (each via its own loader_factory()-built MdfLoader).
        Files that fail to open are collected into the returned LoadResult
        rather than aborting the whole operation (REQ-FILE-023); the
        Signal Browser/Info Box are populated from the first successfully
        opened measurement, with the rest reachable via the browser's own
        measurement selector (REQ-BROWSER-050).
        """
        self.remove_all()
        self._browser.clear()
        self._info_box.clear()
        self.current_workspace.color_index = 0

        result = LoadResult()
        new_measurements: list[LoadedMeasurement] = []
        labels: list[str] = []
        for path in paths:
            loader = self._loader_factory()
            try:
                loader.open(path)
            except MdfLoadError as exc:
                result.failed.append((str(path), exc))
                continue
            info = loader.measurement_info()
            label = make_label(path, labels)
            labels.append(label)
            measurement = LoadedMeasurement(loader=loader, info=info, label=label)
            new_measurements.append(measurement)
            result.succeeded.append(measurement)
            if self._settings is not None:
                self._settings.add_recent(path)

        self._measurements = new_measurements
        self._browser.set_measurements([m.label for m in new_measurements])
        self._refresh_measurement_axes()
        self.refresh_display_names()

        if new_measurements:
            first = new_measurements[0]
            self._browser.populate(first.loader.channel_tree())
            self._info_box.set_info(first.info)
        if self.current_workspace.cursor_ctrl is not None:
            self.current_workspace.cursor_ctrl.reset()
        if self.current_workspace.zoom_ctrl is not None:
            self.current_workspace.zoom_ctrl.clear()
        self._current_config_path = None
        if new_measurements:
            self.events.file_loaded.emit(
                FileLoadedEvent(path=str(paths[0]), tab=self.current_workspace)
            )
        return result

    def add_measurements(self, paths: list[str | os.PathLike]) -> LoadResult:
        """Load *paths* as additional measurements alongside what's already open (REQ-FILE-022).

        Purely additive: no existing tab's signals, zoom, cursor, or
        undo/redo state is touched. Files that fail to open are collected
        into the returned LoadResult rather than aborting the whole
        operation (REQ-FILE-023); a failure never affects any
        already-loaded measurement (REQ-FILE-024).
        """
        result = LoadResult()
        labels = [m.label for m in self._measurements]
        for path in paths:
            loader = self._loader_factory()
            try:
                loader.open(path)
            except MdfLoadError as exc:
                result.failed.append((str(path), exc))
                continue
            info = loader.measurement_info()
            label = make_label(path, labels)
            labels.append(label)
            measurement = LoadedMeasurement(loader=loader, info=info, label=label)
            self._measurements.append(measurement)
            result.succeeded.append(measurement)
            if self._settings is not None:
                self._settings.add_recent(path)
        if result.succeeded:
            self._browser.set_measurements([m.label for m in self._measurements])
            self._refresh_measurement_axes()
            self.refresh_display_names()
        return result

    def close_measurement(self, measurement: LoadedMeasurement) -> None:
        """Remove *measurement* and every one of its active signals from every tab (REQ-FILE-028).

        Confirmation (warn when the measurement has active signals) is
        MainWindow's job, mirroring the stripe/tab-close pattern — this
        method always proceeds unconditionally once called.
        """
        saved_index = self._active_tab_index
        try:
            for index, workspace in enumerate(self._workspaces):
                affected = [a for a in workspace.active if a.measurement is measurement]
                if not affected:
                    continue
                self._active_tab_index = index
                self.remove_signals(affected)
        finally:
            self._active_tab_index = saved_index
        # Identity comparison, not `in`/`.remove()`'s `==` — LoadedMeasurement
        # is a mutable dataclass with no custom __eq__, so two structurally
        # matching-but-distinct instances could otherwise compare equal.
        self._measurements = [m for m in self._measurements if m is not measurement]
        self._browser.set_measurements([m.label for m in self._measurements])
        if self._measurements:
            self._browser.populate(self._measurements[0].loader.channel_tree())
        else:
            self._browser.clear()
        self._refresh_measurement_axes()
        self.refresh_display_names()

    def _refresh_measurement_axes(self) -> None:
        """Push the current measurement pool to every tab's plot area (#101).

        Measurements are a single global pool shared across tabs, so every
        tab's bottom-most-stripe axis rows (REQ-PLOT-301) must reflect it,
        not just the currently active tab.
        """
        for workspace in self._workspaces:
            workspace.plot.refresh_measurement_axes(self._measurements)

    def on_measurement_offset_changed(self, measurement: LoadedMeasurement) -> None:
        """Refresh every active signal belonging to *measurement*, in every
        tab (#101) — the offset changed via dragging that measurement's own
        axis row (PlotStripesArea.measurement_offset_changed), so every
        curve using it must be redrawn at its new display_timestamps.
        """
        for workspace in self._workspaces:
            for active in workspace.active:
                if active.measurement is measurement:
                    workspace.plot.refresh_signal_data(active)

    def add_signal(
        self,
        group_index: int,
        channel_index: int,
        stripe=None,
        measurement: LoadedMeasurement | None = None,
    ) -> bool:
        """Load a channel and add it to the plot and the Active Signals Table.

        *stripe*, when given, is the target PlotStripe (e.g. a drag-and-drop
        onto a specific stripe); omitted/None adds to the current active stripe.

        *measurement* identifies which loaded measurement (#101)
        group_index/channel_index refer to — required to disambiguate once
        more than one measurement is loaded. Omitted (or when exactly one
        measurement is loaded) resolves automatically via
        _default_measurement(), preserving single-measurement call sites;
        with no measurement loaded through the pool APIs at all, falls back
        to the loader injected at construction (legacy/back-compat path).

        Returns True if added, False if the channel was already active in
        the current tab for the same measurement (the same channel may
        still be active in another tab, or under a different measurement —
        see REQ-BROWSER-040).
        Raises MdfLoadError if the channel cannot be read or its samples are
        not numeric.
        """
        current = self.current_workspace
        measurement = measurement or self._default_measurement()
        loader = measurement.loader if measurement is not None else self._loader
        if any(
            s.metadata.group_index == group_index
            and s.metadata.channel_index == channel_index
            and s.measurement is measurement
            for s in current.active
        ):
            return False
        data, meta = loader.load_signal(group_index, channel_index)
        rgb = _COLOR_PALETTE[current.color_index % len(_COLOR_PALETTE)]
        current.color_index += 1
        active = ActiveSignal(
            data=data, metadata=meta, color=rgb, step_mode=meta.is_integer, measurement=measurement,
        )
        current.active.append(active)
        current.plot.add_signal(active, stripe=stripe)
        current.table.add_row(active, current.plot.get_stripe_for_signal(active))
        self.refresh_z_order()
        if current.cursor_ctrl is not None:
            current.cursor_ctrl.refresh()
        self.events.signal_added.emit(SignalAddedEvent(signal=active, stripe=stripe, tab=current))
        return True

    # ------------------------------------------------------------------
    # Plot Stripes
    # ------------------------------------------------------------------

    def create_stripe(self):
        """Create a new empty plot stripe."""
        return self.current_workspace.plot.create_stripe()

    def delete_stripe(self, stripe, force: bool = False) -> bool:
        """Delete *stripe*. Refuses if it's the last stripe, or non-empty without force.

        With force=True, every signal in the stripe is removed first via the
        normal full removal pipeline (remove_signal — plot, table row, cursor
        labels, selection), not just torn down from the plot (REQ-PLOT-194).
        """
        current = self.current_workspace
        if len(current.plot.get_stripes()) <= 1:
            return False
        signals = current.plot.get_signals_in_stripe(stripe)
        if signals and not force:
            return False
        for active in list(signals):
            self.remove_signal(active)
        return current.plot.delete_stripe(stripe)

    def get_stripes(self) -> list:
        return self.current_workspace.plot.get_stripes()

    def get_stripe_for_signal(self, active: ActiveSignal):
        return self.current_workspace.plot.get_stripe_for_signal(active)

    def get_signals_in_stripe(self, stripe) -> list[ActiveSignal]:
        return self.current_workspace.plot.get_signals_in_stripe(stripe)

    def move_signals_to_stripe(self, signals: list[ActiveSignal], stripe) -> None:
        """Move each of *signals* into *stripe* (REQ-PLOT-202/203)."""
        current = self.current_workspace
        for active in signals:
            current.plot.move_signal_to_stripe(active, stripe)
        current.table.move_to_stripe(signals, stripe)
        # Cursor labels are parented to the signal's ViewBox, which just
        # changed — refresh so they re-attach to the new one immediately
        # rather than waiting for the next unrelated cursor move.
        if current.cursor_ctrl is not None:
            current.cursor_ctrl.refresh()

    def move_signals_to_new_stripe(self, signals: list[ActiveSignal]) -> None:
        """Create a new stripe and move each of *signals* into it (REQ-PLOT-191)."""
        current = self.current_workspace
        stripe = current.plot.create_stripe()
        for active in signals:
            current.plot.move_signal_to_stripe(active, stripe)
        current.table.move_to_stripe(signals, stripe)
        if current.cursor_ctrl is not None:
            current.cursor_ctrl.refresh()

    def toggle_step_mode(self, active_signal: ActiveSignal) -> None:
        """Flip the step-mode flag for a signal and update the plot."""
        current = self.current_workspace
        if active_signal not in current.active:
            return
        active_signal.step_mode = not active_signal.step_mode
        current.plot.set_step_mode(active_signal, active_signal.step_mode)

    def recolor_signal(self, active_signal: ActiveSignal, color: QColor) -> None:
        """Update the color of an active signal's curve, axis, and cursor labels."""
        current = self.current_workspace
        current.plot.recolor_signal(active_signal, color)
        if current.cursor_ctrl is not None:
            current.cursor_ctrl.recolor_signal(active_signal, color)

    def recolor_signals(self, actives: list, color: QColor) -> None:
        """Recolor multiple signals to the same color."""
        for active in actives:
            self.recolor_signal(active, color)

    def on_merge_y_axis_requested(self, signals: list) -> None:
        """Merge all given signals onto a single Y-axis (ViewBox).

        No-op if any signal is already in a Synced group — a signal can't be
        both merged and synced at once (#84).
        """
        current = self.current_workspace
        actives = [s for s in signals if s in current.active]
        if len(actives) < 2:
            return
        if any(current.plot.get_group_type(a) == "synced" for a in actives):
            return
        current.plot.merge_signals(actives)
        self._refresh_table_group_state()
        if current.cursor_ctrl is not None:
            current.cursor_ctrl.refresh()

    def on_sync_y_axis_requested(self, signals: list) -> None:
        """Sync the Y-axes of all given signals so they pan/zoom together.

        No-op if any signal is already in a Merged group — a signal can't be
        both merged and synced at once (#84).
        """
        current = self.current_workspace
        actives = [s for s in signals if s in current.active]
        if len(actives) < 2:
            return
        if any(current.plot.get_group_type(a) == "merged" for a in actives):
            return
        current.plot.sync_signals(actives)
        self._refresh_table_group_state()
        if current.cursor_ctrl is not None:
            current.cursor_ctrl.refresh()

    def on_ungroup_y_axis_requested(self, signals: list) -> None:
        """Remove each given signal from its merged or synced group."""
        current = self.current_workspace
        for active in signals:
            if active in current.active:
                current.plot.ungroup_signal(active)
        self._refresh_table_group_state()
        if current.cursor_ctrl is not None:
            current.cursor_ctrl.refresh()

    def _refresh_table_group_state(self) -> None:
        """Push current Merged/Synced group membership to the Active Signals Table."""
        current = self.current_workspace
        current.table.set_group_membership(
            current.plot.get_merged_signals(), current.plot.get_synced_signals(),
        )

    def remove_signals(self, actives: list) -> None:
        """Remove multiple signals from the plot and the table."""
        current = self.current_workspace
        for active in list(actives):
            if active not in current.active:
                continue
            if current.cursor_ctrl is not None:
                current.cursor_ctrl.on_signal_removed(active)
            current.plot.remove_signal(active)
            current.active.remove(active)
            current.table.remove_row(active)
            self.events.signal_removed.emit(SignalRemovedEvent(signal=active, tab=current))
        if current.cursor_ctrl is not None:
            current.cursor_ctrl.refresh()
        self._refresh_table_group_state()

    def set_step_modes(self, actives: list, enabled: bool) -> None:
        """Set step mode to a specific state for each signal in *actives*."""
        current = self.current_workspace
        for active in actives:
            if active not in current.active:
                continue
            active.step_mode = enabled
            current.plot.set_step_mode(active, enabled)

    def on_enum_table_requested(self, enabled: bool) -> None:
        """Toggle enum label display in the cursor-value table columns."""
        current = self.current_workspace
        for active in current.selected_signals:
            if active not in current.active:
                continue
            active.enum_display_table = enabled
        if current.cursor_ctrl is not None:
            current.cursor_ctrl.refresh()

    def on_enum_cursor_requested(self, enabled: bool) -> None:
        """Toggle enum label display on the floating cursor plot label."""
        current = self.current_workspace
        for active in current.selected_signals:
            if active not in current.active:
                continue
            active.enum_display_cursor = enabled
        if current.cursor_ctrl is not None:
            current.cursor_ctrl.refresh()

    def on_enum_yaxis_requested(self, enabled: bool) -> None:
        """Toggle enum label display on the Y-axis tick labels."""
        current = self.current_workspace
        for active in current.selected_signals:
            if active not in current.active:
                continue
            active.enum_display_yaxis = enabled
            current.plot.set_enum_display_yaxis(active, enabled)

    def on_multi_selection(self, multi: bool) -> None:
        """Called when the table switches between single and multi-row selection."""
        if multi:
            self._signal_info.show_multi_selection()

    def set_multi_selected(self, actives: list) -> None:
        """Update the full multi-selection list and populate the Properties tab."""
        current = self.current_workspace
        current.selected_signals = list(actives)
        self.events.selection_changed.emit(SelectionChangedEvent(selected=list(current.selected_signals), tab=current))
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
        ordered = [a for a in current.active if a in set(actives)]
        current.plot.set_selected_signals(ordered, all_signals=current.active, top_first=self._top_first)
        self._signal_info.set_properties(mode, shape, width, style)
        self._signal_info.set_enum_options(None, None, None)
        self._signal_info.enable_properties(True)

    def on_display_mode_requested(self, mode: str) -> None:
        """Apply a display mode change to all currently selected signals."""
        current = self.current_workspace
        for active in current.selected_signals:
            if active not in current.active:
                continue
            active.display_mode = mode
            current.plot.set_display_mode(active, mode, active.marker_shape)

    def on_marker_shape_requested(self, shape: str) -> None:
        """Apply a marker shape change to all currently selected signals."""
        current = self.current_workspace
        for active in current.selected_signals:
            if active not in current.active:
                continue
            active.marker_shape = shape
            if active.display_mode != "line":
                current.plot.set_display_mode(active, active.display_mode, shape)

    def on_line_width_requested(self, width: int) -> None:
        """Apply a line width change to all currently selected signals."""
        current = self.current_workspace
        for active in current.selected_signals:
            if active not in current.active:
                continue
            current.plot.set_line_width(active, width)

    def on_line_style_requested(self, style: str) -> None:
        """Apply a line style change to all currently selected signals."""
        current = self.current_workspace
        for active in current.selected_signals:
            if active not in current.active:
                continue
            current.plot.set_line_style(active, style)

    def refresh_display_names(self) -> None:
        """Reapply the display name formatter to every tab's Active Signals Table.

        The display-name-shortening rule is a global preference (REQ-PLOT-160),
        so all tabs update together rather than just the currently active one.
        Once more than one measurement is loaded, every name is additionally
        prefixed with its measurement's label (REQ-PLOT-306) — applied last,
        wrapping the already-shortened name (REQ-PLOT-307), so the
        shortening rule behaves identically regardless of measurement count.
        """
        for workspace in self._workspaces:
            workspace.table.set_name_formatter(self._format_display_name)

    def _format_display_name(self, active: ActiveSignal) -> str:
        """Shared display-name formatting: shorten, then measurement-prefix.

        Used by both refresh_display_names() (Active Signals Table) and
        _push_selection_to_drawer() (Signal Info Box), so the two panels
        never disagree on what a signal's display name is (REQ-PLOT-306/307).
        """
        if self._settings is not None:
            from mdf_viewer.settings import apply_display_name_rule
            name = apply_display_name_rule(active.metadata.name, self._settings)
        else:
            name = active.metadata.name
        if self.measurement_count > 1 and active.measurement is not None:
            return f"[{active.measurement.label}] {name}"
        return name

    def refresh_z_order(self) -> None:
        """Reapply Z-order, selection boost, and Y-axis visibility after a preference change."""
        current = self.current_workspace
        current.plot.set_selected_line_boost(self._line_boost)
        current.plot.set_show_only_selected_y_axis(self._show_only_selected_y_axis)
        current.plot.set_selected_signals(
            current.selected_signals,
            all_signals=current.active,
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

    @property
    def _zoom_all_stripes(self) -> bool:
        if self._settings is None:
            return True
        return self._settings.zoom_scope == "all_stripes"

    def remove_signal(self, active_signal: ActiveSignal) -> None:
        """Remove one signal from the plot and the table.

        No-op if the signal is not currently active.
        """
        current = self.current_workspace
        if active_signal not in current.active:
            return
        # Cursor labels must be removed before the plot destroys the ViewBox.
        if current.cursor_ctrl is not None:
            current.cursor_ctrl.on_signal_removed(active_signal)
        current.plot.remove_signal(active_signal)
        current.active.remove(active_signal)
        current.table.remove_row(active_signal)
        self.events.signal_removed.emit(SignalRemovedEvent(signal=active_signal, tab=current))
        if current.cursor_ctrl is not None:
            current.cursor_ctrl.refresh()
        if current.selected is active_signal:
            self.set_selected_signal(None)
        self._refresh_table_group_state()

    def remove_all(self) -> None:
        """Remove all active signals from the plot and the table."""
        current = self.current_workspace
        # Clear cursor labels before ViewBoxes are destroyed.
        if current.cursor_ctrl is not None:
            current.cursor_ctrl.on_all_signals_cleared()
        for sig in list(current.active):
            current.plot.remove_signal(sig)
            self.events.signal_removed.emit(SignalRemovedEvent(signal=sig, tab=current))
        current.active.clear()
        current.table.clear()
        self.set_selected_signal(None)
        self._refresh_table_group_state()

    def swimlanes(self) -> bool:
        """Arrange active signals in horizontal swimlanes.

        Returns True if applied, False when no signals are active.
        """
        current = self.current_workspace
        if current.zoom_ctrl is not None:
            current.zoom_ctrl.before_discrete_action()
        result = current.plot.swimlanes(current.active)
        if current.zoom_ctrl is not None:
            current.zoom_ctrl.after_discrete_action()
        return result

    def reorder_signals(self, ordered: list) -> None:
        """Update the active signal order to match the table's new row order."""
        current = self.current_workspace
        current.active = list(ordered)
        self.refresh_z_order()
        if current.cursor_ctrl is not None:
            current.cursor_ctrl.refresh()

    def on_y_grid_toggled(self, enabled: bool) -> None:
        """Called when the user toggles Y-grid in the plot context menu."""
        current = self.current_workspace
        current.y_grid_enabled = enabled
        if current.selected is not None:
            current.plot.set_y_grid(current.selected, enabled)

    def set_selected_signal(self, active_signal: ActiveSignal | None) -> None:
        """Update the selection and drive the Signal Info Box."""
        current = self.current_workspace
        if current.y_grid_enabled:
            if current.selected is not None:
                current.plot.set_y_grid(current.selected, False)
            if active_signal is not None:
                current.plot.set_y_grid(active_signal, True)
        current.selected = active_signal
        current.selected_signals = [active_signal] if active_signal is not None else []
        current.plot.set_selected_signals(current.selected_signals, all_signals=current.active, top_first=self._top_first)
        self.events.selection_changed.emit(SelectionChangedEvent(selected=list(current.selected_signals), tab=current))
        self._push_selection_to_drawer(active_signal)

    def _push_selection_to_drawer(self, active_signal: ActiveSignal | None) -> None:
        """Show *active_signal*'s info/properties in the shared drawer, or clear it.

        Shared by set_selected_signal() (a real selection change) and
        switch_tab() (restoring a tab's previous selection without changing
        any tab's actual selection state).
        """
        if active_signal is None:
            self._signal_info.clear()
        else:
            self._signal_info.set_metadata(
                active_signal.metadata, display_name=self._format_display_name(active_signal),
            )
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
        """Capture the display state of the active tab's active signals, in table order."""
        return self._snapshot_signals(self.current_workspace)

    def snapshot_tab_signals(self, index: int) -> list[ActiveSignalSnapshot]:
        """Capture the display state of the tab at *index*'s active signals.

        Used by MainWindow to re-resolve every tab's signals by name when a
        new measurement file is loaded (REQ-PLOT-260), not just the active
        tab — does not change which tab is active.
        """
        if not (0 <= index < len(self._workspaces)):
            return []
        return self._snapshot_signals(self._workspaces[index])

    def _snapshot_signals(self, workspace: "TabWorkspace") -> list[ActiveSignalSnapshot]:
        snapshots = []
        for active in workspace.active:
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
        """Return all SignalMetadata entries matching *name*.

        Searches the union of every currently loaded measurement (#101,
        resolving carry-over/near-match across a multi-file Replace);
        falls back to the loader injected at construction when the pool
        is empty (legacy/back-compat path — also used directly by tests).
        """
        if not self._measurements:
            return self._loader.find_signal_by_name(name)
        result: list = []
        for measurement in self._measurements:
            result.extend(measurement.loader.find_signal_by_name(name))
        return result

    def find_similar_signal_by_name(self, name: str) -> list:
        """Return SignalMetadata entries that near-match *name* (REQ-FILE-032/033).

        Same union-across-the-pool / legacy-fallback behavior as
        find_signal_by_name() above.
        """
        if not self._measurements:
            return self._loader.find_similar_signal_by_name(name)
        result: list = []
        for measurement in self._measurements:
            result.extend(measurement.loader.find_similar_signal_by_name(name))
        return result

    def find_signal_locations_by_name(
        self, name: str
    ) -> list[tuple[LoadedMeasurement, "object"]]:
        """Return (measurement, SignalMetadata) pairs matching *name* across the pool.

        Used by MainWindow's multi-file Replace carry-over resolution
        (#101) to disambiguate a name that matches in more than one
        loaded measurement — plain find_signal_by_name() can't, since its
        flat SignalMetadata results don't say which measurement they came
        from. Empty when the pool is empty (no legacy fallback: the
        single-measurement legacy path has no ambiguity to resolve).
        """
        result: list[tuple[LoadedMeasurement, object]] = []
        for measurement in self._measurements:
            for meta in measurement.loader.find_signal_by_name(name):
                result.append((measurement, meta))
        return result

    def find_similar_signal_locations_by_name(
        self, name: str
    ) -> list[tuple[LoadedMeasurement, "object"]]:
        """Same as find_signal_locations_by_name() but for near-matches (REQ-FILE-032/033)."""
        result: list[tuple[LoadedMeasurement, object]] = []
        for measurement in self._measurements:
            for meta in measurement.loader.find_similar_signal_by_name(name):
                result.append((measurement, meta))
        return result

    def restore_signals(
        self,
        resolved: list[
            tuple[ActiveSignalSnapshot, int, int]
            | tuple[ActiveSignalSnapshot, int, int, LoadedMeasurement | None]
        ],
    ) -> None:
        """Re-add signals from (snapshot, group_index, channel_index[, measurement]) tuples.

        The trailing *measurement* is optional (#101) — omitted (3-tuple)
        resolves via add_signal()'s own _default_measurement() fallback,
        preserving pre-#101 single-measurement callers unchanged; given
        explicitly (4-tuple), disambiguates which loaded measurement
        group_index/channel_index refer to (used by MainWindow's
        multi-file Replace carry-over resolution).

        Each signal is added via the normal path (palette color), then all
        display attributes from the snapshot are applied immediately.
        """
        from PyQt6.QtGui import QColor
        current = self.current_workspace
        for entry in resolved:
            if len(entry) == 4:
                snap, gi, ci, measurement = entry
            else:
                snap, gi, ci = entry
                measurement = None
            try:
                added = self.add_signal(gi, ci, measurement=measurement)
            except Exception:
                continue
            if not added:
                continue
            active = current.active[-1]
            new_color = QColor(*snap.color)
            # Set color on the active signal first, then propagate to the plot.
            active.color = new_color
            current.plot.recolor_signal(active, new_color)
            current.table.set_row_color(active, new_color)
            # Restore other display properties.
            if snap.line_width != active.line_width:
                current.plot.set_line_width(active, snap.line_width)
                active.line_width = snap.line_width
            if snap.line_style != active.line_style:
                current.plot.set_line_style(active, snap.line_style)
                active.line_style = snap.line_style
            if snap.display_mode != active.display_mode or snap.marker_shape != active.marker_shape:
                current.plot.set_display_mode(active, snap.display_mode, snap.marker_shape)
                active.display_mode = snap.display_mode
                active.marker_shape = snap.marker_shape
            if snap.step_mode != active.step_mode:
                current.plot.set_step_mode(active, snap.step_mode)
                active.step_mode = snap.step_mode
            active.enum_display_table = snap.enum_display_table
            active.enum_display_cursor = snap.enum_display_cursor
            if snap.enum_display_yaxis != active.enum_display_yaxis:
                current.plot.set_enum_display_yaxis(active, snap.enum_display_yaxis)
                active.enum_display_yaxis = snap.enum_display_yaxis
        if current.cursor_ctrl is not None:
            current.cursor_ctrl.refresh()

    def restore_tab_signals(
        self,
        index: int,
        resolved: list[
            tuple[ActiveSignalSnapshot, int, int]
            | tuple[ActiveSignalSnapshot, int, int, LoadedMeasurement | None]
        ],
    ) -> None:
        """Restore resolved snapshots into the tab at *index* (REQ-PLOT-260).

        Temporarily makes that tab current so the existing restore_signals()/
        add_signal() logic can be reused unchanged, then restores whichever
        tab was actually active — the caller never sees the active tab change.
        """
        if not (0 <= index < len(self._workspaces)):
            return
        saved_index = self._active_tab_index
        self._active_tab_index = index
        try:
            self.restore_signals(resolved)
        finally:
            self._active_tab_index = saved_index

    def capture_config(self, config_path: Path) -> "ViewerConfig":
        """Capture the current viewer state as a ViewerConfig.

        *config_path* is the intended save location — needed to compute
        relative measurement paths later in ConfigManager.save().

        Scoped to the active tab only — ViewerConfig is still the flat,
        single-workspace format it was before tabs existed. Multi-tab
        `.mvc` save/load is #106's job (it depends on #99); this is a
        deliberate provisional scope for #99, not an oversight.
        """
        from mdf_viewer.model.viewer_config import SignalConfig, ViewerConfig

        current = self.current_workspace
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

        zoom = current.plot.get_zoom_state(current.active)
        x_range = tuple(zoom.x_range)  # type: ignore[arg-type]
        y_ranges: dict[str, tuple[float, float]] = {}
        for active, yr in zoom.y_ranges.items():
            y_ranges[active.metadata.name] = tuple(yr)  # type: ignore[assignment]

        merged_raw, synced_raw = current.plot.get_axis_grouping()
        merged_groups = tuple(tuple(g) for g in merged_raw)
        synced_groups = tuple(tuple(g) for g in synced_raw)

        cursor_snap: dict = {}
        if current.cursor_ctrl is not None:
            cursor_snap = current.cursor_ctrl.snapshot()
        cursor_mode = cursor_snap.get("mode", "HIDDEN")
        cursor_pos_raw = cursor_snap.get("positions", [0.0, 0.0])
        cursor_positions: tuple[float, float] = (
            float(cursor_pos_raw[0]),
            float(cursor_pos_raw[1]),
        )

        selected_name = (
            current.selected.metadata.name if current.selected is not None else None
        )

        # .mvc save/restore stays single-measurement scope for #101 (#106's
        # job to extend it) — always the first pool entry, or the legacy
        # loader when the pool is empty.
        meas_loader = self._measurements[0].loader if self._measurements else self._loader
        meas_path = ""
        if meas_loader.is_open and meas_loader._path is not None:
            meas_path = str(meas_loader._path)

        if self._settings is not None:
            name_separator = self._settings.display_name_separator
            name_direction = self._settings.display_name_direction
            name_segments = self._settings.display_name_segments
        else:
            name_separator, name_direction, name_segments = ".", "right", 1

        from mdf_viewer.config_manager import CONFIG_FORMAT_VERSION
        return ViewerConfig(
            format_version=CONFIG_FORMAT_VERSION,
            measurement_path=meas_path,
            signals=signal_configs,
            x_range=x_range,  # type: ignore[arg-type]
            y_ranges=y_ranges,
            merged_groups=merged_groups,
            synced_groups=synced_groups,
            cursor_mode=cursor_mode,
            cursor_positions=cursor_positions,
            selected_signal=selected_name,
            display_name_separator=name_separator,
            display_name_direction=name_direction,
            display_name_segments=name_segments,
        )

    def restore_config(
        self,
        config: "ViewerConfig",
        resolved_signals: "list[tuple[ActiveSignalSnapshot, int, int]]",
    ) -> None:
        """Restore a saved viewer session after the measurement file is loaded.

        *resolved_signals* is a list of (snapshot, group_index, channel_index)
        tuples — the caller is responsible for resolving name → indices.

        Restores into the active tab only — see capture_config()'s docstring
        for why (provisional #99 scope, superseded by #106).
        """
        from PyQt6.QtGui import QColor
        from mdf_viewer.view_model.zoom_state import ZoomState

        current = self.current_workspace
        self.restore_signals(resolved_signals)

        # Restore axis grouping — must happen after signals are added
        merged = [list(g) for g in config.merged_groups]
        synced = [list(g) for g in config.synced_groups]
        current.plot.restore_axis_grouping(merged, synced, current.active)
        self._refresh_table_group_state()

        # Restore zoom — must happen after grouping (ViewBoxes may have changed)
        y_ranges: dict = {}
        for active in current.active:
            name = active.metadata.name
            if name in config.y_ranges:
                y_ranges[active] = config.y_ranges[name]
        zoom_state = ZoomState(x_range=config.x_range, y_ranges=y_ranges)
        current.plot.set_zoom_state(zoom_state, current.active)

        # Restore cursor state
        if current.cursor_ctrl is not None:
            current.cursor_ctrl.restore({
                "mode": config.cursor_mode,
                "positions": list(config.cursor_positions),
            })

        # Restore selection
        if config.selected_signal is not None:
            for active in current.active:
                if active.metadata.name == config.selected_signal:
                    self.set_selected_signal(active)
                    break

        # Restore display-name-shortening rule *parameters* used by this
        # session (not whether the rule is enabled — that stays governed
        # solely by Preferences). Settings' setters auto-persist, so this
        # becomes the new global default too (#89).
        if self._settings is not None:
            self._settings.display_name_separator = config.display_name_separator
            self._settings.display_name_direction = config.display_name_direction
            self._settings.display_name_segments = config.display_name_segments
            self.refresh_display_names()

    # ------------------------------------------------------------------
    # Read-only state accessors
    # ------------------------------------------------------------------

    @property
    def is_file_loaded(self) -> bool:
        return bool(self._measurements) or self._loader.is_open

    @property
    def active_signals(self) -> list[ActiveSignal]:
        return list(self.current_workspace.active)

    @property
    def selected_signal(self) -> ActiveSignal | None:
        return self.current_workspace.selected

    @property
    def current_config_path(self) -> Path | None:
        return self._current_config_path

    @current_config_path.setter
    def current_config_path(self, value: Path | None) -> None:
        self._current_config_path = value
