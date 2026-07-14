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
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from mdf_viewer.controller.events import (
    CursorMovedEvent,
    EventBus,
    FileLoadedEvent,
    MeasurementClosedEvent,
    SelectionChangedEvent,
    SignalAddedEvent,
    SignalRemovedEvent,
)
from mdf_viewer.errors import MdfLoadError
from mdf_viewer.model.loaded_measurement import LoadedMeasurement, make_label
from mdf_viewer.model.mdf_loader import MdfLoader
from mdf_viewer.model.virtual_measurement_loader import VirtualMeasurementLoader
from mdf_viewer.plugin_api.registry import PluginRegistry
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
    # Which stripe this signal was in when snapshotted (#106) — empty
    # string means "no stripe info" (pre-#106 callers, or a signal not
    # currently in any tracked stripe), matching today's single-stripe
    # behavior when absent.
    stripe_name: str = ""
    # The specific measurement this signal must resolve against on
    # restore (#106 M6, REQ-FILE-093) — set only by session-config
    # restore, which knows exactly which saved measurement a signal came
    # from; left None for the file-reload "keep signals" flow, which has
    # no such prior knowledge and resolves across the whole pool instead.
    measurement: "LoadedMeasurement | None" = None
    visible: bool = True  # #133 — curve/axis shown or hidden

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
        # Whether the measurement pool's per-measurement axis rows are
        # collapsed into one shared ruler (#102) — global, not per-tab,
        # matching the measurement pool's own global-across-tabs scope.
        self._measurements_synchronized: bool = False
        # Exactly one measurement is "Primary" whenever any are loaded
        # (#103, REQ-PLOT-317) — an object reference, not a bool field on
        # LoadedMeasurement itself, so "exactly one" is structural rather
        # than something that can drift out of sync.
        self._primary_measurement: LoadedMeasurement | None = None
        # Monotonic — only ever reset by a fresh Replace (or the legacy
        # single-file load_file), never decremented by closing a
        # measurement, so a default short name is never reused within the
        # same "session" just because it happens to be free again
        # (REQ-FILE-027).
        self._measurement_load_counter: int = 0
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
        # Shared across every future PluginContext (#71/#73) — one instance
        # per AppController, mirroring self.events' ownership pattern.
        self.plugin_registry = PluginRegistry()

        # Opaque, plugin-facing signal handles (#71) — see token_for_signal().
        # id(active) is only ever used as a transient lookup key while
        # `active` is still referenced by some workspace's `active` list
        # (so its address can't yet have been reused), and is dropped the
        # moment the signal itself is removed (_drop_signal_token()) —
        # never handed to a plugin, which only ever sees the minted token.
        self._signal_tokens: dict[int, ActiveSignal] = {}
        self._signal_token_by_id: dict[int, int] = {}
        self._next_signal_token: int = 1

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

    @property
    def primary_measurement(self) -> LoadedMeasurement | None:
        """The measurement currently designated Primary (REQ-PLOT-317), or None if none loaded."""
        return self._primary_measurement

    def set_primary_measurement(self, measurement: LoadedMeasurement) -> None:
        """Designate *measurement* as Primary (REQ-PLOT-317), a user-driven change.

        No-op if *measurement* isn't currently loaded. Pushes the new
        ordering to every tab's axis rows (REQ-PLOT-319) and, if
        Synchronized, the new Sync reference (REQ-PLOT-312/320), and
        rebuilds the Measurement Info tabs so the checkbox that's actually
        checked always matches (REQ-PLOT-317).
        """
        if measurement not in self._measurements:
            return
        self._primary_measurement = measurement
        self._refresh_measurement_axes()
        self._refresh_info_box()

    def rename_measurement(self, measurement: LoadedMeasurement, new_name: str) -> bool:
        """Rename *measurement*'s short name to *new_name* (REQ-FILE-027).

        Rejects (returns False, leaves the name unchanged) a name that
        collides with another currently-loaded measurement's short name,
        so short names stay unique at all times. Either way, rebuilds the
        Measurement Info tabs: on success to show the new name everywhere
        else it's displayed, on rejection to revert the edit box's stale
        rejected text back to the still-current label — the same
        set_measurements() call does both, since it always renders
        whatever self._measurements/self._primary_measurement currently
        are, regardless of which branch is taken.
        """
        if any(m is not measurement and m.label == new_name for m in self._measurements):
            self._refresh_info_box()
            return False
        measurement.label = new_name
        self._refresh_signal_browser()
        self.refresh_display_names()
        self._refresh_measurement_axes()
        self._refresh_info_box()
        return True

    @property
    def current_workspace(self) -> TabWorkspace:
        """The active tab's TabWorkspace bundle.

        Public so app.py's tab-wiring factory can attach a freshly built
        CursorController/ZoomController to a specific tab (including the
        first one, created by __init__) without AppController needing to
        import those concrete view/controller classes itself.
        """
        return self._workspaces[self._active_tab_index]

    def all_workspaces(self) -> list[TabWorkspace]:
        """Every tab's TabWorkspace, in tab order.

        Returns a shallow copy (matching active_signals' own convention),
        not the live `_workspaces` list — reorder_tabs() reassigns that
        list wholesale and remove_tab() deletes from it in place, either of
        which would otherwise mutate/invalidate whatever a caller (e.g.
        PluginContext, #71) is still iterating.
        """
        return list(self._workspaces)

    @property
    def active_tab_index(self) -> int:
        """Index of the currently active tab (read-only view of `current_workspace`'s position)."""
        return self._active_tab_index

    def create_tab(
        self, plot_area: PlotAreaProtocol, active_signals_table: SignalTableProtocol
    ) -> TabWorkspace:
        """Register a new tab's view widgets and make it the active tab.

        Returns the new TabWorkspace, still missing its cursor_ctrl/zoom_ctrl —
        the caller (app.py's tab-wiring factory) builds those against this
        specific workspace and attaches them via set_cursor_controller()/
        set_zoom_controller(), which target current_workspace and therefore
        this new tab as long as nothing else changes the active tab first.

        Also pushes the current measurement pool/sync state (#101, #102) to
        the new tab's plot area, so it starts with the same per-measurement
        axis rows as every other tab (#124) instead of the empty-pool
        default of a single generic axis; and the current display-name
        formatter (REQ-PLOT-160/306/307), so it starts shortened/
        measurement-prefixed the same as every other tab (#131) instead of
        its Active Signals Table's own raw-name default.
        """
        workspace = TabWorkspace(plot=plot_area, table=active_signals_table)
        self._workspaces.append(workspace)
        self._active_tab_index = len(self._workspaces) - 1
        self._refresh_measurement_axes()
        self.refresh_display_names()
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
        """Remove the tab at *index*, or clear it in place if it's the only
        remaining one — current_workspace must never resolve to nothing,
        since dozens of call sites throughout this class assume it always
        exists.

        Runs every one of that tab's active signals through the normal
        remove_signal pipeline first — closing a tab that still has signals
        in it (the view allows this after a confirmation prompt) used to
        just drop the TabWorkspace reference, leaking every curve/ViewBox/
        axis in it (same leak class as the stripe/signal-lifecycle bugs
        fixed in plot_stripe.py, #120, just in the tab-lifecycle path
        instead). This cleanup always runs, even for the last workspace, so
        "close anyway" actually discards its content either way.

        Does not change which tab is active — the view computes the tab to
        activate next (REQ-PLOT-253: the left neighbor) before this shifts
        list positions, then calls switch_tab() itself. The clamp here is
        just a safety net in case switch_tab() isn't called immediately.
        """
        workspace = self._workspaces[index]
        if workspace.cursor_ctrl is not None:
            workspace.cursor_ctrl.on_all_signals_cleared()
        for sig in list(workspace.active):
            workspace.plot.remove_signal(sig)
            # Emit before dropping the token (#149) — see remove_signals()'s comment.
            self.events.signal_removed.emit(SignalRemovedEvent(signal=sig, tab=workspace))
            self._drop_signal_token(sig)
        workspace.active.clear()
        workspace.table.clear()
        if len(self._workspaces) <= 1:
            # Keep this sole workspace's widgets alive rather than
            # discarding the TabWorkspace entry — the view mirrors this by
            # parking (not deleting) the corresponding page and reusing it
            # on the next "New Tab" instead of registering a duplicate
            # workspace for a freshly built one (#130).
            return
        del self._workspaces[index]
        if self._active_tab_index >= len(self._workspaces):
            self._active_tab_index = len(self._workspaces) - 1

    def _clone_active_signal(self, old: ActiveSignal) -> ActiveSignal:
        """Build a new ActiveSignal from *old* for a duplicated/copied tab (#119).

        `data`/`metadata`/`measurement` are shared by reference — no loader
        I/O, no re-parsing — since a same-session duplicate already holds
        the exact loaded objects the source signal does; every display
        property (color, line style, line width, marker shape, display
        mode, step mode, enum-display flags) copies by value automatically.
        `curve`/`view_box` are reset so PlotStripesArea.add_signal() builds
        fresh ones for the new plot, exactly like a normal add_signal()
        call constructs them. Using dataclasses.replace() rather than a
        hand-written field list means a future new ActiveSignal field is
        cloned automatically with no edit needed here.
        """
        return replace(old, curve=None, view_box=None)

    def _signals_in_stripe_ordered(self, workspace: TabWorkspace, stripe) -> list[ActiveSignal]:
        """The signals in *stripe*, in on-screen order (#119).

        Sourced from workspace.active filtered by get_stripe_for_signal(),
        not PlotStripesArea.get_signals_in_stripe() — that method reads
        insertion order from an internal dict that a same-stripe row drag
        never updates (only workspace.active's own order changes), so it
        can silently diverge from what the user actually sees. Mirrors how
        _capture_tab() (#106) already sources stripe-scoped order correctly.
        """
        return [a for a in workspace.active if workspace.plot.get_stripe_for_signal(a) is stripe]

    def _clone_signals_into_stripe(
        self,
        source: TabWorkspace,
        dest: TabWorkspace,
        source_stripe,
        dest_stripe,
    ) -> dict[ActiveSignal, ActiveSignal]:
        """Clone every signal in *source_stripe*, in on-screen order, into
        *dest_stripe* on *dest* (#119). Returns the old-to-new signal map
        for this stripe, so callers needing per-signal identity elsewhere
        (e.g. remapping a captured ZoomState) can build a full mapping
        across every stripe without re-deriving it.
        """
        old_to_new: dict[ActiveSignal, ActiveSignal] = {}
        for old in self._signals_in_stripe_ordered(source, source_stripe):
            new = self._clone_active_signal(old)
            dest.active.append(new)
            dest.plot.add_signal(new, stripe=dest_stripe)
            dest.table.add_row(new, dest_stripe)
            self.events.signal_added.emit(
                SignalAddedEvent(signal=new, stripe=dest_stripe, tab=dest)
            )
            old_to_new[old] = new
        return old_to_new

    def copy_signals_to_new_tab(self, source_index: int, dest_index: int) -> None:
        """Copy every active signal from the tab at *source_index* into the
        tab at *dest_index*'s single stripe (REQ-PLOT-267/268).

        Assumes the destination tab already exists (view-side has already
        created it via create_tab()) with its one auto-created default
        stripe untouched — no stripe layout, zoom, cursor, or axis grouping
        is copied, only signals, flattened across every source stripe in
        top-to-bottom, then within-stripe, order. Continues the source
        tab's color sequence (REQ-PLOT-269) rather than restarting it.
        """
        source = self._workspaces[source_index]
        dest = self._workspaces[dest_index]
        dest_stripe = dest.plot.get_stripes()[0]
        for stripe in source.plot.get_stripes():
            self._clone_signals_into_stripe(source, dest, stripe, dest_stripe)
        dest.color_index = source.color_index
        self.refresh_z_order(dest)

    def duplicate_tab_signals(self, source_index: int, dest_index: int) -> None:
        """Clone every signal from the tab at *source_index* into the
        matching stripe of the tab at *dest_index*, then restore zoom,
        axis grouping, and cursor state (REQ-PLOT-265).

        Assumes the destination tab and its stripe skeleton already exist
        (view-side builds both — create_tab() then _build_stripe_skeleton())
        with stripes in the same order as the source's, so
        zip(source stripes, dest stripes) pairs them up correctly.

        Zoom state needs an explicit old-to-new remap — ZoomState.y_ranges
        is keyed by the exact ActiveSignal object it was read from, so the
        source's captured state doesn't resolve against the destination's
        (distinct) cloned objects without translation. Axis grouping needs
        no such remap: get_axis_grouping()/restore_axis_grouping() already
        match by (name, id(measurement)) — a clone keeps the same name and
        the same measurement reference, so the source's captured pairs
        already resolve correctly against the destination's clones.
        """
        source = self._workspaces[source_index]
        dest = self._workspaces[dest_index]
        old_to_new: dict[ActiveSignal, ActiveSignal] = {}
        for source_stripe, dest_stripe in zip(source.plot.get_stripes(), dest.plot.get_stripes()):
            old_to_new.update(
                self._clone_signals_into_stripe(source, dest, source_stripe, dest_stripe)
            )
        dest.color_index = source.color_index

        zoom_state = source.plot.get_zoom_state(source.active)
        remapped_ranges = {
            old_to_new[old]: rng for old, rng in zoom_state.y_ranges.items() if old in old_to_new
        }
        dest.plot.set_zoom_state(replace(zoom_state, y_ranges=remapped_ranges), dest.active)

        merged, synced = source.plot.get_axis_grouping()
        dest.plot.restore_axis_grouping(merged, synced, dest.active)

        if source.cursor_ctrl is not None and dest.cursor_ctrl is not None:
            dest.cursor_ctrl.restore(source.cursor_ctrl.snapshot())

        self.refresh_z_order(dest)

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
        # Tear down every currently-loaded measurement (real or virtual)
        # before wiping the pool — fixes a latent bug where a discarded
        # measurement's active signals in a non-current tab were left
        # orphaned, and gives a plugin-owned virtual measurement its
        # measurement_closed notification (#147). remove_all() below still
        # runs as the current tab's final safety-net clear.
        for old_measurement in self._measurements:
            self._teardown_measurement(old_measurement)
        self.remove_all()
        self._browser.clear()
        self._info_box.clear()
        self.current_workspace.color_index = 0
        self._measurements_synchronized = False
        self._measurement_load_counter = 0

        self._loader.open(path)  # raises MdfLoadError on failure

        info = self._loader.measurement_info()
        self._measurements = [
            LoadedMeasurement(loader=self._loader, info=info, label=make_label(0, []))
        ]
        self._measurement_load_counter = 1
        self._primary_measurement = self._measurements[0]
        self._refresh_signal_browser()
        self._refresh_info_box()
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
        rather than aborting the whole operation (REQ-FILE-023); the Signal
        Browser shows every successfully opened measurement's channels at
        once (REQ-BROWSER-010), and the Measurement Info Box is populated
        from the first.
        """
        # Tear down every currently-loaded measurement before wiping the
        # pool — see load_file()'s identical comment above (#147).
        for old_measurement in self._measurements:
            self._teardown_measurement(old_measurement)
        self.remove_all()
        self._browser.clear()
        self._info_box.clear()
        self.current_workspace.color_index = 0
        self._measurements_synchronized = False
        self._measurement_load_counter = 0

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
            label = make_label(self._measurement_load_counter, labels)
            self._measurement_load_counter += 1
            labels.append(label)
            measurement = LoadedMeasurement(loader=loader, info=info, label=label)
            new_measurements.append(measurement)
            result.succeeded.append(measurement)
            if self._settings is not None:
                self._settings.add_recent(path)

        self._measurements = new_measurements
        # Primary always resets to the first-loaded of the new set on
        # Replace, the same as offset_s/Synchronized state already reset
        # here (REQ-PLOT-322) — a fresh set of files has no relationship
        # to whichever measurement was Primary before.
        self._primary_measurement = new_measurements[0] if new_measurements else None
        self._refresh_signal_browser()
        self._refresh_info_box()
        self._refresh_measurement_axes()
        self.refresh_display_names()

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
            label = make_label(self._measurement_load_counter, labels)
            self._measurement_load_counter += 1
            labels.append(label)
            measurement = LoadedMeasurement(loader=loader, info=info, label=label)
            self._measurements.append(measurement)
            result.succeeded.append(measurement)
            if self._settings is not None:
                self._settings.add_recent(path)
        if result.succeeded:
            # Adding never disturbs an existing Primary (REQ-PLOT-322); the
            # only exception is establishing one at all when the pool was
            # previously empty (REQ-PLOT-317's "exactly one whenever at
            # least one is loaded" invariant still applies here).
            if self._primary_measurement is None:
                self._primary_measurement = self._measurements[0]
            self._refresh_signal_browser()
            self._refresh_info_box()
            self._refresh_measurement_axes()
            self.refresh_display_names()
        return result

    def add_virtual_measurement(
        self, loader: VirtualMeasurementLoader, label: str, owner_plugin: str
    ) -> LoadedMeasurement:
        """Add a plugin-contributed virtual measurement to the pool (#147, REQ-PLUGIN-292).

        Mirrors add_measurements()'s tail logic (Primary-if-empty, the same
        refreshes) but skips the file-specific parts — loader.open() and
        settings.add_recent() — since *loader* is already fully built and
        there is no file path to remember. *label* is disambiguated against
        existing labels the same way a collision is handled elsewhere,
        rather than through make_label()'s "M{n}" numbering, which doesn't
        fit an arbitrary plugin-supplied name.
        """
        existing_labels = [m.label for m in self._measurements]
        resolved_label = label
        n = 2
        while resolved_label in existing_labels:
            resolved_label = f"{label} ({n})"
            n += 1
        measurement = LoadedMeasurement(
            loader=loader,
            info=loader.measurement_info(),
            label=resolved_label,
            owner_plugin=owner_plugin,
        )
        self._measurements.append(measurement)
        if self._primary_measurement is None:
            self._primary_measurement = measurement
        self._refresh_signal_browser()
        self._refresh_info_box()
        self._refresh_measurement_axes()
        self.refresh_display_names()
        return measurement

    def remove_virtual_measurements_for(self, owner_plugin: str) -> None:
        """Remove every virtual measurement contributed by *owner_plugin* (#147, REQ-PLUGIN-301).

        Reuses close_measurement()'s already-hardened teardown (active-signal
        removal, Primary reassignment, refreshes, measurement_closed
        notification) for each one, rather than duplicating any of it.
        """
        for measurement in [m for m in self._measurements if m.owner_plugin == owner_plugin]:
            self.close_measurement(measurement)

    def measurement_has_signals(self, measurement: LoadedMeasurement) -> bool:
        """Whether *measurement* has any active signals in any tab (REQ-FILE-028)."""
        return any(
            a.measurement is measurement
            for workspace in self._workspaces
            for a in workspace.active
        )

    def _remove_measurement_signals(self, measurement: LoadedMeasurement) -> None:
        """Remove every one of *measurement*'s active signals from every tab,
        via the same #120-hardened `remove_signals()` teardown path used
        everywhere else — shared by `close_measurement()` and
        `replace_single_measurement()` (#137).
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

    def _teardown_measurement(self, measurement: LoadedMeasurement) -> None:
        """Remove *measurement*'s active signals from every tab and notify
        that it closed (#147) — shared by close_measurement() and the
        wholesale-discard paths (load_file(), replace_measurements()), so
        every removal path gives the same guarantees: a plugin-owned
        virtual measurement is always notified, and a discarded
        measurement's signals never linger orphaned in a non-current tab.
        """
        self._remove_measurement_signals(measurement)
        self.events.measurement_closed.emit(
            MeasurementClosedEvent(
                label=measurement.label,
                is_virtual=measurement.owner_plugin is not None,
                owner_plugin=measurement.owner_plugin,
            )
        )

    def close_measurement(self, measurement: LoadedMeasurement) -> None:
        """Remove *measurement* and every one of its active signals from every tab (REQ-FILE-028).

        Confirmation (warn when the measurement has active signals) is
        MainWindow's job, mirroring the stripe/tab-close pattern — this
        method always proceeds unconditionally once called.
        """
        self._teardown_measurement(measurement)
        # Identity comparison, not `in`/`.remove()`'s `==` — LoadedMeasurement
        # is a mutable dataclass with no custom __eq__, so two structurally
        # matching-but-distinct instances could otherwise compare equal.
        self._measurements = [m for m in self._measurements if m is not measurement]
        # Reassign Primary *before* the axes/browser refresh below, not
        # after — REQ-PLOT-321. Must run here, between the list mutation
        # and the existing tail calls, or the axes push once against a
        # stale/removed Primary with no second refresh to correct it.
        if self._primary_measurement is measurement:
            self._primary_measurement = self._measurements[0] if self._measurements else None
        self._refresh_signal_browser()
        self._refresh_info_box()
        self._refresh_measurement_axes()
        self.refresh_display_names()

    def replace_single_measurement(
        self, measurement: LoadedMeasurement, path: str | os.PathLike
    ) -> LoadResult:
        """Swap *measurement*'s underlying file for *path* in place (REQ-FILE-100..107).

        Opens *path* into a fresh loader before touching anything else — on
        failure, *measurement* and everything else is left exactly as it was
        (REQ-FILE-106) and the failure is returned via LoadResult.failed,
        mirroring add_measurements()'s per-file failure isolation (REQ-FILE-024)
        rather than replace_measurements()'s all-or-nothing failure mode.

        On success, tears down *measurement*'s own active signals across
        every tab through the same remove_signals() path close_measurement()
        uses (the #120-hardened teardown, not a new one), then reassigns
        `.loader`/`.info` on the *same* LoadedMeasurement instance — keeping
        its identity means label, offset_s, Primary status, and Synchronized
        membership all carry over for free, with nothing else to reassign.
        Does not touch color_index, cursor_ctrl, or zoom_ctrl: other
        measurements' signals remain live in the same tabs throughout.
        """
        result = LoadResult()
        # Identity comparison, not `in`'s `==` — LoadedMeasurement (and the
        # MdfLoader it wraps) are plain dataclasses with field-equality
        # __eq__, so two distinct measurements loaded from the same path
        # could otherwise compare equal (same pattern as close_measurement's
        # own identity-comparison guard above).
        if not any(m is measurement for m in self._measurements):
            return result

        # A virtual measurement has no file to browse to in the first place
        # (#147, REQ-VMEAS-440) — rejecting here, not just disabling the UI
        # button, avoids leaving owner_plugin stuck set on a measurement
        # that's just swapped in a real MdfLoader (it would keep showing
        # the virtual badge, stay excluded from .mvc save, and still
        # vanish if the plugin that "owns" it deactivates).
        if measurement.owner_plugin is not None:
            result.failed.append(
                (str(path), MdfLoadError("Cannot replace a virtual measurement's data."))
            )
            return result

        loader = self._loader_factory()
        try:
            loader.open(path)
        except MdfLoadError as exc:
            result.failed.append((str(path), exc))
            return result
        info = loader.measurement_info()

        self._remove_measurement_signals(measurement)

        measurement.loader = loader
        measurement.info = info
        result.succeeded.append(measurement)
        if self._settings is not None:
            self._settings.add_recent(path)

        self._refresh_signal_browser()
        self._refresh_info_box()
        self._refresh_measurement_axes()
        self.refresh_display_names()
        self.events.file_loaded.emit(FileLoadedEvent(path=str(path), tab=self.current_workspace))
        return result

    def restore_measurements(
        self,
        measurement_configs: "list[MeasurementConfig]",
        primary_index: int | None,
        synchronized: bool,
    ) -> "list[LoadedMeasurement | None]":
        """Load every saved MeasurementConfig, index-aligned with the saved
        list (#106 Phase 1) — a failure at position *i* leaves `None` at
        that same index rather than shifting the rest, unlike
        `replace_measurements()`, whose `LoadResult.succeeded` drops
        failed paths and loses positional alignment with the saved list.

        Bypasses `make_label()`/`rename_measurement()` entirely — each
        measurement's short name and offset come directly from the saved
        config, not generated or validated against a live pool mid-restore.
        Confirming what to do about any `None` entries (REQ-FILE-097/098)
        is the caller's job (`MainWindow`), the same "confirmation is the
        caller's job, this method always proceeds" split already used by
        `close_measurement`; call this only with the *final* list to keep
        (already dropped any the user chose not to continue without).

        Sets Primary from *primary_index* into the resulting pool — if
        *primary_index* itself is `None` (no real measurement was Primary
        at save time, e.g. it was virtual — #147/REQ-VMEAS-040), or that
        slot is `None` or out of range, falls back to the first-loaded of
        whatever succeeded (mirrors `close_measurement`'s
        own REQ-PLOT-321 reassignment). Sets Synchronized directly from
        *synchronized*. Resets the load-order naming counter (REQ-FILE-027)
        to the number of measurements attempted, so a later `add_measurements`
        never reissues a default name already used by this restore.
        Refreshes signal browser/info box/measurement axes once at the end.

        Assumes `AppController` is already down to a single, clean tab
        (Phase 0) — this method only touches the measurement pool.
        """
        results: list[LoadedMeasurement | None] = []
        for mc in measurement_configs:
            loader = self._loader_factory()
            try:
                loader.open(mc.path)
            except MdfLoadError:
                results.append(None)
                continue
            info = loader.measurement_info()
            results.append(
                LoadedMeasurement(loader=loader, info=info, label=mc.label, offset_s=mc.offset_s)
            )

        self._measurements = [m for m in results if m is not None]
        self._measurements_synchronized = synchronized
        self._measurement_load_counter = len(results)

        # primary_index is None when the saved workspace had no real
        # measurement to point at — either none were loaded at all, or the
        # Primary at save time was itself virtual (#147) — same fallback
        # as an out-of-range index: first-loaded of whatever succeeded.
        primary = (
            results[primary_index]
            if primary_index is not None and 0 <= primary_index < len(results)
            else None
        )
        if primary is None:
            primary = self._measurements[0] if self._measurements else None
        self._primary_measurement = primary

        self._refresh_signal_browser()
        self._refresh_info_box()
        self._refresh_measurement_axes()
        return results

    def _refresh_info_box(self) -> None:
        """Rebuild the Measurement Info panel's tabs from the full
        measurement pool and current Primary (#103, REQ-PLOT-318).

        Called from every mutation site of self._measurements or
        self._primary_measurement, mirroring _refresh_signal_browser()'s
        centralization — including a bare Primary change with no
        measurement added/removed, since MeasurementInfoBox always fully
        rebuilds its tabs rather than needing a separate incremental sync
        path (see its own docstring for why).
        """
        self._info_box.set_measurements(self._measurements, self._primary_measurement)

    def _refresh_signal_browser(self) -> None:
        """Rebuild the Signal Browser's flat, cross-measurement channel list
        from the full measurement pool (#103, REQ-BROWSER-010).

        Centralized here and called from every mutation site of
        self._measurements (replace_measurements, add_measurements,
        close_measurement, rename_measurement) so none of them can
        silently skip repopulating it — add_measurements previously never
        did under the old switcher, a real gap caught during the
        architecture review.
        """
        self._browser.populate_all(
            [(m.label, m.loader.channel_tree(), m.owner_plugin is not None) for m in self._measurements]
        )

    def _refresh_measurement_axes(self) -> None:
        """Push the current measurement pool and sync state to every tab's
        plot area (#101, #102).

        Measurements (and whether they're synchronized) are a single global
        state shared across tabs, so every tab's bottom-most-stripe axis
        rows (REQ-PLOT-301/313) must reflect it, not just the currently
        active tab. The Primary measurement (#103) is always reordered to
        the front here — the only place this ordering happens — so that
        both the topmost axis row (REQ-PLOT-319) and the Sync reference
        (REQ-PLOT-312), which both just use "whichever measurement is
        first," automatically reflect Primary with no changes needed in
        PlotStripesArea/PlotStripe themselves.
        """
        ordered = self._measurements
        primary = self._primary_measurement
        if primary is not None and primary in self._measurements:
            ordered = [primary] + [m for m in self._measurements if m is not primary]
        for workspace in self._workspaces:
            workspace.plot.refresh_measurement_axes(ordered, self._measurements_synchronized)

    @property
    def is_measurements_synchronized(self) -> bool:
        return self._measurements_synchronized

    def toggle_measurements_synchronized(self) -> None:
        """Flip whether the measurement axis rows are collapsed into one
        shared ruler (#102) and push the new state to every tab."""
        self._measurements_synchronized = not self._measurements_synchronized
        self._refresh_measurement_axes()

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
            # Emit before dropping the token (#149) — a plugin's
            # signal_removed handler can still call get_samples() one last
            # time; the token becomes invalid immediately afterward.
            self.events.signal_removed.emit(SignalRemovedEvent(signal=active, tab=current))
            self._drop_signal_token(active)
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

    def toggle_signal_visibility(self, actives: list) -> None:
        """Toggle each signal in *actives* independently (#133, REQ-PLOT-333)
        — never forces every signal to one target state.

        `plot.set_signal_visible()` sets `active.visible` itself (mirroring
        `set_line_width`/`set_line_style`'s own field-updating convention),
        so the new value is computed here before calling it, then read back
        for the Active Signals Table icon update.
        """
        current = self.current_workspace
        for active in actives:
            if active not in current.active:
                continue
            current.plot.set_signal_visible(active, not active.visible)
            current.table.set_row_visible_icon(active, active.visible)

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

    def refresh_z_order(self, workspace: TabWorkspace | None = None) -> None:
        """Reapply Z-order, selection boost, and Y-axis visibility after a preference change.

        *workspace* defaults to current_workspace — pass one explicitly to
        target a tab that isn't (or might not yet be) the active one, e.g.
        right after populating a just-created tab (#119) whose active-tab
        status shouldn't be assumed by the caller.
        """
        current = workspace or self.current_workspace
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
        # Emit before dropping the token (#149) — see remove_signals()'s comment.
        self.events.signal_removed.emit(SignalRemovedEvent(signal=active_signal, tab=current))
        self._drop_signal_token(active_signal)
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
            # Emit before dropping the token (#149) — see remove_signals()'s comment.
            self.events.signal_removed.emit(SignalRemovedEvent(signal=sig, tab=current))
            self._drop_signal_token(sig)
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

    def snapshot_measurement_signals(
        self, measurement: LoadedMeasurement
    ) -> dict[int, list[ActiveSignalSnapshot]]:
        """Capture *measurement*'s own active signals only, across every tab (REQ-FILE-104).

        Each returned snapshot is tagged with `.measurement = measurement`,
        the same field session restore already uses (#106 M6, REQ-FILE-093)
        to scope by-name resolution to one specific measurement — so
        MainWindow's existing resolve/restore pipeline (_classify_signal_name,
        _resolve_and_confirm_snapshots, _restore_snapshots) handles a
        single-measurement replace's carry-over with no changes of its own.
        """
        result: dict[int, list[ActiveSignalSnapshot]] = {}
        for index, workspace in enumerate(self._workspaces):
            actives = [a for a in workspace.active if a.measurement is measurement]
            if not actives:
                continue
            result[index] = [
                replace(snap, measurement=measurement)
                for snap in self._snapshot_signals(workspace, actives)
            ]
        return result

    def _snapshot_signals(
        self, workspace: "TabWorkspace", actives: "list[ActiveSignal] | None" = None
    ) -> list[ActiveSignalSnapshot]:
        if actives is None:
            actives = workspace.active
        snapshots = []
        for active in actives:
            c = active.color
            stripe = workspace.plot.get_stripe_for_signal(active)
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
                stripe_name=getattr(stripe, "name", "") if stripe is not None else "",
                visible=active.visible,
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
        stripes = current.plot.get_stripes()
        for entry in resolved:
            if len(entry) == 4:
                snap, gi, ci, measurement = entry
            else:
                snap, gi, ci = entry
                measurement = None
            stripe = None
            if snap.stripe_name:
                stripe = next(
                    (s for s in stripes if getattr(s, "name", None) == snap.stripe_name), None
                )
            try:
                added = self.add_signal(gi, ci, stripe=stripe, measurement=measurement)
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
            if snap.visible != active.visible:
                current.plot.set_signal_visible(active, snap.visible)
                active.visible = snap.visible
                current.table.set_row_visible_icon(active, snap.visible)
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

    def capture_config(
        self,
        config_path: Path,
        tab_names: "list[str] | None" = None,
        page_splitter_sizes: "list[tuple[int, int]] | None" = None,
    ) -> "ViewerConfig":
        """Capture the current viewer state as a ViewerConfig — every tab,
        each tab's stripe layout and signal placement, and every loaded
        measurement (#106).

        *config_path* is the intended save location — needed to compute
        relative measurement paths later in ConfigManager.save().
        *tab_names* supplies each tab's saved name in workspace order
        (`MainWindow` owns the actual `QTabWidget`, so `AppController` has
        no other way to know tab titles); a missing or too-short entry
        defaults to "Tab {n}" by position. *page_splitter_sizes* similarly
        supplies each tab's plot|AST divider widths (`MainWindow` owns that
        QSplitter too, #106); a missing or too-short entry defaults to
        `TabConfig.page_splitter_sizes`'s own default.
        """
        from mdf_viewer.model.viewer_config import MeasurementConfig, ViewerConfig

        # Virtual measurements are excluded from a saved workspace entirely
        # (REQ-VMEAS-410) — every index below this point is computed
        # against this filtered list, never the raw pool, or a virtual
        # measurement sitting earlier in the pool would silently shift
        # every real measurement's saved index (#147).
        real_measurements = [m for m in self._measurements if m.owner_plugin is None]

        tabs = tuple(
            self._capture_tab(
                workspace,
                tab_names[i] if tab_names is not None and i < len(tab_names) else f"Tab {i + 1}",
                real_measurements,
                page_splitter_sizes[i]
                if page_splitter_sizes is not None and i < len(page_splitter_sizes) else None,
            )
            for i, workspace in enumerate(self._workspaces)
        )

        measurements = tuple(
            MeasurementConfig(
                path=str(m.loader.path) if m.loader.is_open and m.loader.path is not None else "",
                label=m.label,
                offset_s=m.offset_s,
            )
            for m in real_measurements
        )
        if not measurements and self._loader.is_open and self._loader.path is not None:
            measurements = (
                MeasurementConfig(path=str(self._loader.path), label="M1", offset_s=0.0),
            )

        # None when there's no real measurement to point a saved index at —
        # either the pool has none at all, or the current Primary is
        # itself virtual (REQ-VMEAS-040 allows this in-session; there is no
        # slot in *real_measurements* to reference) (#147).
        primary_index = next(
            (i for i, m in enumerate(real_measurements) if m is self._primary_measurement), None
        )

        if self._settings is not None:
            name_separator = self._settings.display_name_separator
            name_direction = self._settings.display_name_direction
            name_segments = self._settings.display_name_segments
        else:
            name_separator, name_direction, name_segments = ".", "right", 1

        from mdf_viewer.config_manager import CONFIG_FORMAT_VERSION
        return ViewerConfig(
            format_version=CONFIG_FORMAT_VERSION,
            measurements=measurements,
            primary_measurement_index=primary_index,
            measurements_synchronized=self._measurements_synchronized,
            tabs=tabs,
            active_tab_index=self._active_tab_index,
            display_name_separator=name_separator,
            display_name_direction=name_direction,
            display_name_segments=name_segments,
        )

    def _measurement_index(
        self, measurement, real_measurements: list[LoadedMeasurement]
    ) -> int | None:
        """Identity-match *measurement* against *real_measurements* (#101/#106,
        filtered to exclude virtual measurements — #147/REQ-VMEAS-430) —
        never `.index()`/`in`, since `LoadedMeasurement` is a plain
        `@dataclass` with field-equality `__eq__`, so two distinct
        measurements loaded from the same path/label/offset would
        otherwise compare equal.

        `measurement is None` (legacy single-file mode, pool empty) keeps
        its original fallback of `0`, unchanged by #147. A *virtual*
        measurement — found in `self._measurements` but never in
        *real_measurements* — returns `None`, signaling the caller to
        exclude whatever referenced it from the saved config entirely,
        rather than write a wrong or dangling index.
        """
        if measurement is None:
            return 0
        if measurement.owner_plugin is not None:
            return None
        return next((i for i, m in enumerate(real_measurements) if m is measurement), 0)

    def _capture_tab(
        self,
        workspace: "TabWorkspace",
        name: str,
        real_measurements: list[LoadedMeasurement],
        page_splitter_sizes: "tuple[int, int] | None" = None,
    ) -> "TabConfig":
        """Capture one tab's stripe layout, active signals (with their
        stripe/measurement placement), zoom, axis grouping, cursor, and
        selection state (#106)."""
        from mdf_viewer.model.viewer_config import SignalConfig, SignalRef, StripeConfig, TabConfig

        stripes_view = workspace.plot.get_stripes()
        stripe_index_of = {stripe: i for i, stripe in enumerate(stripes_view)}
        stripe_configs = tuple(
            StripeConfig(name=getattr(stripe, "name", f"Stripe {i + 1}"), size=size)
            for i, (stripe, size) in enumerate(zip(stripes_view, workspace.plot.get_stripe_sizes()))
        )
        active_stripe_index = stripe_index_of.get(workspace.plot.get_active_stripe(), 0)

        # A signal plotted from a virtual measurement has no slot in
        # *real_measurements* to be saved against, so it's excluded here
        # entirely — from signals, zoom y_ranges, axis grouping, and the
        # selection below — rather than corrupted with a wrong index
        # (REQ-VMEAS-430, #147).
        snapshots = self._snapshot_signals(workspace)
        signal_configs = []
        for snap, active in zip(snapshots, workspace.active):
            midx = self._measurement_index(active.measurement, real_measurements)
            if midx is None:
                continue
            stripe = workspace.plot.get_stripe_for_signal(active)
            stripe_idx = stripe_index_of.get(stripe, 0)
            signal_configs.append(SignalConfig(
                name=snap.name,
                group_name=snap.group_name,
                color=snap.color,
                line_width=snap.line_width,
                line_style=snap.line_style,
                display_mode=snap.display_mode,
                marker_shape=snap.marker_shape,
                step_mode=snap.step_mode,
                enum_display_table=snap.enum_display_table,
                enum_display_cursor=snap.enum_display_cursor,
                enum_display_yaxis=snap.enum_display_yaxis,
                stripe_index=stripe_idx,
                measurement_index=midx,
                visible=snap.visible,
            ))

        zoom = workspace.plot.get_zoom_state(workspace.active)
        x_range = tuple(zoom.x_range)  # type: ignore[arg-type]
        y_ranges = []
        for active, yr in zoom.y_ranges.items():
            midx = self._measurement_index(active.measurement, real_measurements)
            if midx is None:
                continue
            y_ranges.append((SignalRef(name=active.metadata.name, measurement_index=midx), tuple(yr)))
        y_ranges = tuple(y_ranges)

        def _group_refs(group) -> tuple:
            """SignalRefs for one merge/sync group, dropping any member
            belonging to a virtual measurement (REQ-VMEAS-430)."""
            refs = []
            for n, m in group:
                midx = self._measurement_index(m, real_measurements)
                if midx is not None:
                    refs.append(SignalRef(name=n, measurement_index=midx))
            return tuple(refs)

        merged_raw, synced_raw = workspace.plot.get_axis_grouping()
        merged_groups = tuple(g for g in (_group_refs(group) for group in merged_raw) if g)
        synced_groups = tuple(g for g in (_group_refs(group) for group in synced_raw) if g)

        cursor_snap: dict = {}
        if workspace.cursor_ctrl is not None:
            cursor_snap = workspace.cursor_ctrl.snapshot()
        cursor_mode = cursor_snap.get("mode", "HIDDEN")
        cursor_pos_raw = cursor_snap.get("positions", [0.0, 0.0])
        cursor_positions: tuple[float, float] = (
            float(cursor_pos_raw[0]),
            float(cursor_pos_raw[1]),
        )

        selected_midx = (
            self._measurement_index(workspace.selected.measurement, real_measurements)
            if workspace.selected is not None else None
        )
        # A selected signal belonging to a virtual measurement is not saved
        # either — same exclusion as everything else above (REQ-VMEAS-430).
        selected_ref = (
            SignalRef(name=workspace.selected.metadata.name, measurement_index=selected_midx)
            if selected_midx is not None else None
        )

        kwargs = dict(
            name=name,
            stripes=stripe_configs,
            active_stripe_index=active_stripe_index,
            signals=tuple(signal_configs),
            x_range=x_range,  # type: ignore[arg-type]
            y_ranges=y_ranges,
            merged_groups=merged_groups,
            synced_groups=synced_groups,
            cursor_mode=cursor_mode,
            cursor_positions=cursor_positions,
            selected_signal=selected_ref,
            ast_column_widths=tuple(workspace.table.column_widths()),
        )
        if page_splitter_sizes is not None:
            kwargs["page_splitter_sizes"] = page_splitter_sizes
        return TabConfig(**kwargs)

    def restore_config(
        self,
        config: "ViewerConfig",
        resolved_by_tab: "dict[int, list[tuple[ActiveSignalSnapshot, int, int] | tuple[ActiveSignalSnapshot, int, int, LoadedMeasurement | None]]]",
        measurements: "list[LoadedMeasurement | None] | None" = None,
    ) -> None:
        """Restore a saved viewer session's per-tab display state (#106 M6,
        Phase 4) — axis grouping, zoom, cursor, and selection for every
        tab, then the window's active tab and the display-name rule.

        Assumes every tab/stripe skeleton already exists (Phase 2,
        `MainWindow._build_tab_skeletons`) and *resolved_by_tab* already
        holds each tab's resolved (snapshot, group_index, channel_index[,
        measurement]) tuples (Phase 3, `_resolve_and_confirm_snapshots`) —
        this call re-adds the signals themselves (routed into their saved
        stripe via each snapshot's `stripe_name`, see `restore_signals()`)
        and restores everything layered on top of them. A `config.tabs`
        index with nothing in *resolved_by_tab* still gets its
        grouping/zoom/cursor/selection restored (an empty signal list is a
        valid — if unusual — starting point, not a reason to skip the rest).

        *measurements* is Phase 1's index-aligned `restore_measurements()`
        result (may contain `None` for a measurement that failed to load) —
        used to resolve each `SignalRef.measurement_index` (y_ranges,
        merged/synced groups, selection) back to the actual `LoadedMeasurement`
        those saved names must match against, since a bare name is
        ambiguous once the same channel name can be active from two
        different loaded measurements (REQ-FILE-093, found via live-testing
        #106 M6). Defaults to the current `self._measurements` pool, which
        is index-identical to Phase 1's result whenever nothing failed to
        load (the common case, and every pre-#106 test's implicit scope).
        """
        from mdf_viewer.view_model.zoom_state import ZoomState

        if measurements is None:
            measurements = self._measurements

        def resolve(ref) -> tuple:
            # Returns (name, measurement) for identity-based use downstream —
            # LoadedMeasurement is a plain, unhashable @dataclass (mutable,
            # field-equality __eq__), so callers needing a dict key use
            # resolve_key() below instead of hashing this tuple directly.
            target = measurements[ref.measurement_index] if 0 <= ref.measurement_index < len(measurements) else None
            return (ref.name, target)

        def resolve_key(ref) -> tuple:
            name, target = resolve(ref)
            return (name, id(target))

        for tab_index, tab_config in enumerate(config.tabs):
            if not (0 <= tab_index < len(self._workspaces)):
                continue
            self._active_tab_index = tab_index
            current = self._workspaces[tab_index]
            self.restore_signals(resolved_by_tab.get(tab_index, []))

            # Restore axis grouping — must happen after signals are added
            merged = [[resolve(ref) for ref in g] for g in tab_config.merged_groups]
            synced = [[resolve(ref) for ref in g] for g in tab_config.synced_groups]
            current.plot.restore_axis_grouping(merged, synced, current.active)
            self._refresh_table_group_state()

            # Restore zoom — must happen after grouping (ViewBoxes may have changed)
            wanted = {resolve_key(ref): rng for ref, rng in tab_config.y_ranges}
            y_ranges: dict = {}
            for active in current.active:
                key = (active.metadata.name, id(active.measurement))
                if key in wanted:
                    y_ranges[active] = wanted[key]
            zoom_state = ZoomState(x_range=tab_config.x_range, y_ranges=y_ranges)
            current.plot.set_zoom_state(zoom_state, current.active)

            # Restore cursor state
            if current.cursor_ctrl is not None:
                current.cursor_ctrl.restore({
                    "mode": tab_config.cursor_mode,
                    "positions": list(tab_config.cursor_positions),
                })

            # Restore selection
            if tab_config.selected_signal is not None:
                wanted_name, wanted_measurement = resolve(tab_config.selected_signal)
                for active in current.active:
                    # Identity, not equality — LoadedMeasurement's
                    # auto-generated field-equality __eq__ would otherwise
                    # spuriously match two distinct measurements sharing
                    # the same path/label/offset.
                    if active.metadata.name == wanted_name and active.measurement is wanted_measurement:
                        self.set_selected_signal(active)
                        break

            # Restore active stripe — after signals/grouping so it reflects
            # the final stripe layout, not a transient one.
            stripes = current.plot.get_stripes()
            if 0 <= tab_config.active_stripe_index < len(stripes):
                current.plot.set_active_stripe(stripes[tab_config.active_stripe_index])

            current.table.set_column_widths(list(tab_config.ast_column_widths))

        if 0 <= config.active_tab_index < len(self._workspaces):
            self._active_tab_index = config.active_tab_index

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

    def token_for_signal(self, active: ActiveSignal) -> int:
        """Mint (or reuse) *active*'s opaque plugin-facing token (#71).

        Lazy — a signal never exposed to a plugin never gets a token.
        Called by PluginContext when building a PluginSignalView; never
        called with a signal that isn't currently in some workspace's
        `active` list (see the `_signal_token_by_id` comment in __init__).
        """
        key = id(active)
        token = self._signal_token_by_id.get(key)
        if token is None:
            token = self._next_signal_token
            self._next_signal_token += 1
            self._signal_token_by_id[key] = token
            self._signal_tokens[token] = active
        return token

    def find_active_signal_by_id(self, token: int) -> ActiveSignal | None:
        """The live ActiveSignal *token* refers to, or None if it's since been removed (#71)."""
        return self._signal_tokens.get(token)

    def _drop_signal_token(self, active: ActiveSignal) -> None:
        """Invalidate *active*'s token, if it was ever minted (#71).

        Called from every path that removes a signal from a workspace's
        `active` list (remove_signal, remove_signals, remove_all,
        remove_tab), so find_active_signal_by_id() reliably returns None
        afterward instead of a stale or address-reused result.
        """
        token = self._signal_token_by_id.pop(id(active), None)
        if token is not None:
            self._signal_tokens.pop(token, None)

    @property
    def selected_signal(self) -> ActiveSignal | None:
        return self.current_workspace.selected

    @property
    def current_config_path(self) -> Path | None:
        return self._current_config_path

    @current_config_path.setter
    def current_config_path(self, value: Path | None) -> None:
        self._current_config_path = value
