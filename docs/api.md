# MDF-Viewer – Module API Reference

## Implemented Modules

| Module | Description |
|--------|-------------|
| `errors.py` | `MdfLoadError` — shared error type imported by model and view |
| `model/mdf_loader.py` | `MdfLoader` + `ChannelGroupInfo` |
| `model/loaded_measurement.py` | `LoadedMeasurement` dataclass — one measurement in the global multi-measurement pool (#101); `make_label(path, existing_labels)` |
| `model/signal_data.py` | `SignalData` dataclass |
| `model/interpolate.py` | `interpolate(active, x)` — shared linear interpolation helper used by `CursorController` and `CursorStripesView` |
| `view/_mime.py` | Shared MIME type constants for drag-and-drop: `SIGNAL_MIME_TYPE` (Signal Browser → plot/AST) and `ROW_MIME_TYPE` (AST-internal row moves, #100/#116), plus their encode/decode helpers |
| `view/signal_browser.py` | `SignalBrowser` — TreeView, multi-select, Add Signal button, drag; measurement selector combo once 2+ measurements are loaded (#101) |
| `view/main_window.py` | `MainWindow` — tabs (#99), menu/toolbar, status bar, per-tab wiring |
| `view/dockable_panel.py` | `DockablePanel` — pin/hover collapsible panel shell for a window edge (left or right); used for both the Signal Browser/Measurement Info panel and the Info/Properties drawer (#98) |
| `view/measurement_info_box.py` | `MeasurementInfoBox` — file metadata, QFormLayout + placeholder |
| `view/signal_info_box.py` | `SignalInfoBox` — Info section (metadata, incl. raster) + Properties section (display mode, marker shape), stacked vertically in a resizable inner splitter (#98) |
| `view/widgets/color_swatch.py` | `ColorSwatch` — flat `QPushButton` color indicator; reusable across views |
| `view/active_signals_table.py` | `ActiveSignalsTable` — facade over one shared header + per-stripe segments (#100); drag-to-move rows, context menu, multi-select |
| `view/near_match_dialog.py` | `NearMatchDialog` — batches every near-match signal (different source/protocol) into one confirmation dialog (#109) |
| `view/signals_not_found_dialog.py` | `SignalsNotFoundDialog` — reports signals that couldn't be matched at all after a reload/`.mvc` load, with a copy-to-clipboard button |
| `view/signal_group_picker_dialog.py` | `SignalGroupPickerDialog` — asks which channel group/measurement to use when a signal name is ambiguous |
| `view/plot_stripe.py` | `PlotStripe` — one plot stripe: PyQtGraph, shared X-axis, per-signal ViewBox + Y-axis, per-measurement axis rows (#101), Sync/Un-Sync button (#102), drop target, zoom state snapshot |
| `view/plot_stripes_area.py` | `PlotStripesArea` — composes one or more `PlotStripe`s: stripe lifecycle, signal-to-stripe routing, active-stripe tracking, cross-stripe X-sharing, axis-width alignment, zoom-scope rules, measurement axis/sync fan-out (#101/#102) |
| `view/cursors.py` | `CursorView` — per-stripe InfiniteLine items, delta-time line + label, off-screen chevron indicators; `CursorStripesView` — composes one `CursorView` per stripe: value labels, nearest-cursor logic, lockstep cursor dragging, active-stripe-only delta-time routing |
| `view_model/active_signal.py` | `ActiveSignal` dataclass (model data + plot objects + color + display mode + marker shape + line width + owning measurement) |
| `view_model/zoom_state.py` | `ZoomState` dataclass — snapshot of X range + per-signal Y ranges |
| `controller/interfaces.py` | Protocol contracts for all controller-view dependencies |
| `controller/app_controller.py` | `AppController` — coordinates all layers; multi-tab (#99), multi-measurement (#101), Measurement Synchronization (#102) |
| `controller/events.py` | `EventBus` + event dataclasses (`FileLoadedEvent`, `SignalAddedEvent`, `SignalRemovedEvent`, `SelectionChangedEvent`, `CursorMovedEvent`) — plugin groundwork (#70) |
| `controller/cursor_controller.py` | `CursorController` — toggle, position memory, interpolation, delta-time |
| `controller/zoom_controller.py` | `ZoomController` — zoom undo/redo, gesture coalescing, stable-state pre-capture |
| `settings.py` | `Settings` — JSON persistence for recent files + preferences |
| `update_checker.py` | `fetch_latest_release()`, `is_newer()`, `ReleaseInfo`, `UpdateCheckError` — GitHub releases API, no Qt |
| `license/license_info.py` | `LicenseInfo` dataclass, `Tier` enum, `FORMAT_VERSION`, embedded public key |
| `license/license_manager.py` | `LicenseManager` — verify, import, load_stored, export_license; `LicenseError` |
| `view/license_dialog.py` | `LicenseDialog` — import mode (browse/drop) + view mode (details + expiry notice + Retrieve License button); on successful import shows a "restart required" message and closes |
| `view/preferences_dialog.py` | `PreferencesDialog` — tabbed `QDialog`; General tab with "Check for updates on startup" checkbox and "Undo steps" spinbox (1–100); Cursors tab with mode, persistent, 4 cursor color swatches (C1/C2/CL/CR), Show ∆-Time checkbox + color swatch, arrow-key step (unit combobox + spinbox), reset button |
| `app.py` | MVC assembly point; per-tab controller wiring factory (#99) |

Run `pytest --collect-only -q` for current per-file test counts — not tracked here since they drift on every change.

---

## MdfLoader

`MdfLoader` is the sole importer of `asammdf`. Public API:
- `open(path)` / `close()` / `is_open`
- `measurement_info()` → `MeasurementInfo`
- `channel_tree()` → `list[ChannelGroupInfo]`
- `load_signal(group_index, channel_index)` → `(SignalData, SignalMetadata)` — captures raw asammdf dtype before float64 conversion; sets `SignalMetadata.data_type` and `is_integer`; computes `SignalMetadata.raster_s` via `_compute_raster()` (p99 interval deviation ≤ 5 % → fixed rate in seconds, else `None`); if float64 conversion fails (enum/string samples), retries with `raw=True` to get the underlying integer encoding; raises `MdfLoadError` only if raw values are also non-numeric
- `find_signal_by_name(name)` / `find_similar_signal_by_name(name)` — exact / near-match (same name up to the last `\`, differing only after — different recording protocol/source, #109 REQ-FILE-032/033) lookups over `channel_tree()`; `AppController.find_signal_by_name`/`find_similar_signal_by_name` fan these out across the whole measurement pool

## SignalBrowser

Public API:
- `populate(groups: list[ChannelGroupInfo])` — rebuilds the tree from the currently-selected measurement's channels, groups expanded, filter cleared
- `clear()` — resets the tree, hides/clears the measurement selector, and clears the filter
- `add_signals_requested(list[tuple[int,int]])` — PyQt signal emitted with all selected channel locations on double-click, Add Signal button click, or drag initiation
- `set_measurements(labels: list[str])` (#101) — rebuilds the measurement selector combo from `labels`; visible only with 2+ (hidden with 0 or 1); does **not** itself repopulate the tree — caller follows up with `populate()` for whichever measurement should be current
- `current_measurement_index() -> int` — index of the measurement whose channels the tree currently shows; all three add paths (double-click, Add Signal, drag) implicitly target this measurement
- `measurement_selected(int)` — PyQt signal emitted when the user picks a different entry in the combo; caller (`AppController` via `MainWindow`) re-populates the tree via `populate()`
- Filter field: `QLineEdit` at the top; connected to a `QSortFilterProxyModel` with `setRecursiveFilteringEnabled(True)` (case-insensitive, partial match; groups visible when any child matches). `setClearButtonEnabled(True)` provides a built-in × button. `populate()` and `clear()` both reset the filter.
- Selection mode: `ExtendedSelection` — Ctrl+click and Shift+click select multiple channels; the Add Signal button emits all selected channels at once
- Drag: `_DragTreeView` subclass encodes selected `(group_index, channel_index)` pairs, plus `current_measurement_index()`, as `encode_signal_payload(measurement_index, locations)` JSON in `application/x-mdf-viewer-signals` MIME data; drop targets are each `PlotStripe` (dropping onto a specific stripe adds there — see `PlotStripesArea`) and `ActiveSignalsTable`

## ActiveSignal

Fields: `data`, `metadata`, `color: QColor` (set by controller from palette); `step_mode: bool`; `display_mode: str` (`"line"` / `"line_marker"` / `"marker"`, default `"line"`); `marker_shape: str` (`"circle"` / `"square"` / `"diamond"` / `"cross"`, default `"circle"`); `line_width: int` (1–8, default `1`); `line_style: str` (`"solid"` / `"dashes"` / `"dots"` / `"dash-dot"`, default `"solid"`); `measurement: LoadedMeasurement | None = None` (#101) — a live reference (not a copied offset) to the measurement this signal was added from, `None` outside multi-measurement contexts; `curve` and `view_box` are `None` until `PlotStripe.add_signal()` fills them in (called by whichever stripe `PlotStripesArea` routes the signal to). `__hash__ = object.__hash__` and `__eq__ = object.__eq__` — identity semantics throughout to avoid numpy `__eq__` ambiguity (list `in` / `remove` also use `__eq__`).

- `display_timestamps` property — `data.timestamps + measurement.offset_s`, or raw `data.timestamps` unchanged when `measurement is None` (e.g. tests constructing `ActiveSignal` directly). Every place `PlotStripe`/`PlotStripesArea` positions a curve on X (`add_signal`'s `curve.setData`, `zoom_to_fit`, `swimlanes`, `zoom_y_to_view`) reads this instead of raw timestamps, so panning one measurement's axis row shifts its curves without touching the shared X-zoom (REQ-PLOT-303).

## LoadedMeasurement

(`model/loaded_measurement.py`, #101) — one measurement in the app's global multi-measurement pool. Plain (non-frozen) dataclass, no custom `__eq__` (identity comparisons used deliberately, e.g. `AppController.close_measurement`).
- `loader: MdfLoader` — owns this measurement's channel data
- `info: MeasurementInfo` — file-level measurement info snapshot
- `label: str` — user-facing label (from `make_label()`; file stem, or stem + " (n)" on collision, REQ-FILE-027)
- `offset_s: float = 0.0` — mutable X-axis time offset the user pans independently per measurement, via dragging that measurement's own axis row; drives `on_measurement_offset_changed`

`make_label(path, existing_labels) -> str` — derives `Path(path).stem`, disambiguating against `existing_labels` by appending " (2)", " (3)", etc.

## AppController

`AppController` stays a single instance; multi-tab support (#99) makes it internally tab-aware via a `TabWorkspace` bundle rather than one `AppController` per tab.

### TabWorkspace

Everything independent per tab: `plot: PlotAreaProtocol`, `table: SignalTableProtocol`, `active: list[ActiveSignal] = []`, `selected: ActiveSignal | None = None`, `selected_signals: list[ActiveSignal] = []`, `color_index: int = 0` (reset on a fresh load), `cursor_ctrl`/`zoom_ctrl: object = None` (set post-construction), `cursor_stripes_view: object = None` (set directly by `app.py`'s `_wire_tab`), `y_grid_enabled: bool = False`.

### Tab lifecycle (#99)

- `create_tab(plot_area, active_signals_table) -> TabWorkspace` — builds and appends a new `TabWorkspace`, makes it active; returned workspace still needs `set_cursor_controller`/`set_zoom_controller` from the caller
- `switch_tab(index)` — sets the active tab; re-pushes that tab's own previously-selected signal into the shared Info/Properties drawer (REQ-PLOT-233) without touching any workspace's `selected` state
- `remove_tab(index)` — no-op if only 1 tab remains; runs every active signal through the normal `remove_signal()` pipeline first (avoiding the #120 leak class — closing a tab used to just drop the `TabWorkspace` reference, leaking every curve/ViewBox/axis in it), clamps `_active_tab_index`; does not itself pick the next active tab — the view computes that (REQ-PLOT-253: left neighbor) and calls `switch_tab()`
- `current_workspace` property — the active tab's `TabWorkspace`; public so `app.py`'s tab-wiring factory can attach controllers to any tab, including the first
- `tab_has_signals(index) -> bool` (REQ-PLOT-252), `reorder_tabs(plot_areas_in_order)` (resyncs `_workspaces` after a tab-bar drag, REQ-PLOT-243, matching by `TabWorkspace.plot` identity), `tab_count` property
- `snapshot_tab_signals(index)` / `restore_tab_signals(index, resolved)` — per-tab variants of the signal snapshot/restore below, used by `MainWindow` to carry active signals across a file reload for *every* tab, not just the active one (REQ-PLOT-260)

### Measurement lifecycle (#101)

- `load_file(path)` — **legacy single-file entry point**, kept for old callers/tests; drives the loader injected at construction rather than `loader_factory`. Clears current tab, resets color/sync state, opens the file, rebuilds `_measurements` as a single-entry pool, populates browser/info box, resets cursor/zoom, emits `FileLoadedEvent`.
- `replace_measurements(paths) -> LoadResult` (REQ-FILE-021) — clears the active tab and resets `color_index`/sync state; opens each path via a fresh `loader_factory()`-built `MdfLoader`, collecting failures into `result.failed` rather than aborting (REQ-FILE-023); replaces `self._measurements` wholesale; populates browser/info box from the first successful measurement (the rest reachable via the browser's selector, REQ-BROWSER-050); emits `FileLoadedEvent` if anything succeeded.
- `add_measurements(paths) -> LoadResult` (REQ-FILE-022) — purely additive: touches no existing tab's signals/zoom/cursor/undo state, and a failure never affects an already-loaded measurement (REQ-FILE-024). Appends to `self._measurements` rather than replacing it; no `FileLoadedEvent`.
- `close_measurement(measurement)` (REQ-FILE-028) — confirmation is `MainWindow`'s job, this always proceeds. Removes every active signal belonging to `measurement`, in every tab, via the normal `remove_signal()` pipeline; drops it from the pool (identity comparison); re-populates browser from whatever remains.
- `measurement_count` / `measurements` (copy) / `measurement_at(index)` / `channel_tree_for_measurement(index)` (REQ-BROWSER-051) — pool accessors
- `_default_measurement()` — resolves an implicit measurement when the pool has exactly one entry, so single-measurement call sites (incl. every pre-#101 test) can keep calling `add_signal(gi, ci)` unqualified

### Measurement Synchronization (#102)

- `is_measurements_synchronized` property — global flag (not per-tab, mirrors the measurement pool's own global-across-tabs scope)
- `toggle_measurements_synchronized()` — flips the flag, then calls `_refresh_measurement_axes()` to push the new state to every tab (collapses/expands the per-measurement axis rows into one shared ruler)
- `_refresh_measurement_axes()` — loops every workspace, calling `workspace.plot.refresh_measurement_axes(self._measurements, self._measurements_synchronized)`; called from `replace_measurements`, `add_measurements`, `close_measurement`, and `toggle_measurements_synchronized`
- `on_measurement_offset_changed(measurement)` — wired from `PlotStripesArea.measurement_offset_changed` (fired on axis-row drag); refreshes every active signal belonging to `measurement`, in every tab, so its curve redraws at the new `display_timestamps`

### Signal add/remove/query

- `add_signal(group_index, channel_index, stripe=None, measurement=None) -> bool` — resolves `measurement` via param or `_default_measurement()` (falls back to the legacy loader if the pool is empty); returns `False` if that (group, channel, measurement) combo is already active in the current tab; else loads, allocates the next palette color, adds to plot/table, refreshes Z-order + cursor, emits `SignalAddedEvent`
- `remove_signal(active)` / `remove_signals(actives)` / `remove_all()` — remove from plot/table/active list; notify `cursor_ctrl` for label cleanup first; emit `SignalRemovedEvent` per signal; clear selection if affected
- `toggle_step_mode(active)` / `set_step_modes(actives, enabled)` — linear vs. staircase rendering
- `recolor_signal(active, color)` / `recolor_signals(actives, color)` — updates plot + cursor label color
- `reorder_signals(ordered)` — replaces the active list order (from a table row reorder), refreshes Z-order + cursor

### Selection

- `on_multi_selection(multi)` — shows the multi-selection view in the Signal Info drawer when entering multi-select
- `set_multi_selected(actives)` — computes common display properties across the selection (`None` where mixed), pushes to plot + drawer, emits `SelectionChangedEvent`
- `set_selected_signal(active | None)` — single-select path; manages per-signal Y-grid, updates plot highlighting, emits `SelectionChangedEvent`, calls `_push_selection_to_drawer`
- `_push_selection_to_drawer(active)` — shared by `set_selected_signal` and `switch_tab`
- `selected_signal` / `active_signals` — read-only accessors (current tab)

### Property/appearance mutation

Act on `current.selected_signals`: `on_display_mode_requested`, `on_marker_shape_requested`, `on_line_width_requested`, `on_line_style_requested`, `on_enum_table_requested`/`on_enum_cursor_requested`/`on_enum_yaxis_requested`, `on_y_grid_toggled(enabled)`.

### Grouping (merge/sync Y-axis)

`on_merge_y_axis_requested`/`on_sync_y_axis_requested` (mutually exclusive, #84) / `on_ungroup_y_axis_requested` — filter to currently-active signals, delegate to plot, refresh table group state + cursor. `_refresh_table_group_state()` pushes `plot.get_merged_signals()`/`get_synced_signals()` to `table.set_group_membership`.

### Display names / Z-order

`refresh_display_names()` — reapplies the name formatter to every tab's table (global preference, REQ-PLOT-160); `_format_display_name(active)` shortens via the display-name rule then prefixes `[label]` once `measurement_count > 1` (REQ-PLOT-306/307). `refresh_z_order()` reapplies line-boost/selection ordering per `Settings`.

### Zoom/cursor proxies, undo/redo, stripes

- Zoom: `zoom_to_fit()`, `zoom_y_to_view() -> bool`, `swimlanes() -> bool` — each wraps `zoom_ctrl.before/after_discrete_action()`; the first two pass `all_stripes=self._zoom_all_stripes` (read from `Settings.zoom_scope`); swimlanes/box-zoom are always active-stripe-scoped
- Cursor: `toggle_cursor()`, `press_cursor1()`, `press_cursor2()`, `press_left()`, `press_right()`, `zoom_to_cursors() -> bool`, `set_cursor_mode_callback(cb)`, `refresh_cursors()` — delegate to `current.cursor_ctrl`, guarded by `None` check
- Undo/redo: `undo()`, `redo()` — delegate to `current.zoom_ctrl`; one shared history across all stripes (`ZoomState` is keyed by `ActiveSignal` identity, not stripe)
- Stripes: `create_stripe()`, `delete_stripe(stripe, force=False) -> bool` (removes every contained signal via `remove_signal()` first when `force=True`, REQ-PLOT-194), `get_stripes()`, `get_stripe_for_signal(active)`, `get_signals_in_stripe(stripe)`, `move_signals_to_stripe(signals, stripe)`, `move_signals_to_new_stripe(signals)` — the latter two also refresh cursor labels so they re-attach to the signal's new ViewBox immediately

### Near-match / lookup (#101, #109)

- `find_signal_by_name(name)` / `find_similar_signal_by_name(name)` — union across the whole measurement pool, falling back to the legacy loader if the pool is empty
- `find_signal_locations_by_name(name)` / `find_similar_signal_locations_by_name(name)` — like the above but tag each result with its source `LoadedMeasurement`, to disambiguate a name matching in more than one loaded measurement (multi-file Replace carry-over); no legacy fallback

### Config (`.mvc`) capture/restore

`capture_config(config_path)` / `restore_config(config, resolved_signals)` — scoped to the active tab only (provisional #99 scope; full multi-tab config is #106's job). Also: `snapshot_active_signals()`, `restore_signals(resolved)` (each entry `(snapshot, group_index, channel_index[, measurement])`; reapplies every display attribute from the snapshot onto the freshly re-added signal).

### Other

- `set_cursor_controller(cc)` / `set_zoom_controller(zc)` — wired from `app.py`, target `current_workspace`
- `is_file_loaded` — `bool(self._measurements) or self._loader.is_open`
- `current_config_path` property + setter
- `self.events: EventBus` — see below

## EventBus (#70)

(`controller/events.py`) — plugin groundwork: every event fires alongside `AppController`'s existing direct view calls, so future subscribers (plugins, via `PluginContext`) can observe lifecycle changes without `AppController` needing to know about them. All payloads are frozen dataclasses carried as `pyqtSignal(object)`, exposed as `AppController.events.<name>`.

- `FileLoadedEvent(path: str, tab=None)` → `file_loaded` — from `load_file()` and `replace_measurements()` (only if something succeeded); not emitted by `add_measurements()`
- `SignalAddedEvent(signal, stripe=None, tab=None)` → `signal_added` — from `add_signal()`
- `SignalRemovedEvent(signal, tab=None)` → `signal_removed` — from `remove_signal()`, `remove_signals()`, `remove_all()`, and `remove_tab()` (once per signal in the closed tab)
- `SelectionChangedEvent(selected=[], tab=None)` → `selection_changed` — from `set_selected_signal()` and `set_multi_selected()`
- `CursorMovedEvent(positions, mode, tab=None)` → `cursor_moved` — bound as the cursor controller's position-changed callback in `set_cursor_controller()` (captures the workspace at wiring time)

## LoadResult

Per-file outcome of `replace_measurements()`/`add_measurements()` (#101): `succeeded: list[LoadedMeasurement] = []`, `failed: list[tuple[str, MdfLoadError]] = []` — caller builds one error dialog naming every failed file, rather than aborting on the first.

## CursorController

Public API:
- Constructor: `(cursor_view, get_x_range, active_signals_table, get_active_signals=None, get_cursor_persistent=None, get_cursor_mode=None, get_cursor_colors=None, get_y_range=None, get_show_delta_time=None, get_delta_time_color=None, get_selected_signal=None, get_cursor_step_unit=None, get_cursor_step_samples=None, get_cursor_step_pixels=None, get_cursor_step_time_ms=None, get_x_per_pixel=None, get_active_stripe=None)` — `cursor_view` satisfies `CursorViewProtocol` and in practice is always a `CursorStripesView`; all settings read on demand via callables; `get_cursor_colors` returns `(c1, c2, cl, cr)` RGB tuples; `get_selected_signal` used for sample-step mode when no cursor has been touched; `get_active_stripe` keys the delta-time line's remembered vertical position per stripe (`_delta_y_pos_by_stripe`), defaulting to one fixed sentinel key so single-stripe callers/tests are unaffected; defaults to module-level constants / empty-list / `None` when omitted
- `on_active_stripe_changed(stripe)` — re-triggers `_refresh_delta_time()` so the delta-time line reappears at the newly active stripe's own remembered position (REQ-PLOT-105); must be connected *after* the view's own active-stripe bookkeeping in the same signal (see `app.py`)
- `toggle()` — HIDDEN → ONE → TWO → HIDDEN; on first activation places cursors at plot X range start + 10% span; subsequent toggles use remembered positions
- `press_cursor1()` / `press_cursor2()` — direct single-cursor activation (dot / comma keys)
- `press_left()` / `press_right()` — move the active cursor one step left/right (arrow keys); no-op when HIDDEN or no cursor touched in TWO mode
- `zoom_to_cursors() -> tuple[float,float] | None` — returns the span between the two cursors in TWO mode; None otherwise
- `reset()` — called by `AppController.load_file()`; hides cursors and marks positions for re-initialisation on next activation
- `refresh()` — called by `AppController` after any change to the active signal list; re-computes values and updates labels
- `on_signal_removed(active)` / `on_all_signals_cleared()` — label cleanup only; must be called before `PlotStripe.remove_signal()` so the ViewBox is still in the scene
- `set_mode_changed_callback(cb)` — registers a callable invoked with the new `CursorMode` on every toggle
- `recolor_signal(active, color)` — delegates to `CursorStripesView.recolor_labels()`
- Drives `ActiveSignalsTable.update_cursor_values()` and `CursorStripesView.update_labels()` on every drag and toggle
- Active cursor tracking: `_active_cursor_idx` set by drag/click events, cleared on reset(); auto-set to 0 when entering ONE mode
- Arrow-key step settings injected via callables: `get_cursor_step_unit` ("samples"/"pixels"/"time"), `get_cursor_step_samples`, `get_cursor_step_pixels`, `get_cursor_step_time_ms`, `get_x_per_pixel`

## ZoomController

(`controller/zoom_controller.py`):
- Constructor: `(plot_area, get_active_signals, get_max_steps, _timer=None)` — `_timer` is injectable for testing (avoids requiring QApplication in unit tests); connects to `plot_area.range_changed`. `plot_area` is a `PlotStripesArea`, but this class has zero stripe-awareness: it only ever calls `get_zoom_state`/`set_zoom_state` (which already capture/restore the shared X range plus every signal's own Y range regardless of which stripe owns it) and listens to one aggregated `range_changed` signal — one linear undo/redo history covers actions in any stripe, at any zoom-scope setting
- `before_discrete_action()` / `after_discrete_action()` — bracket toolbar zoom calls; `before` captures the current state onto the undo stack and sets `_ignore_range_changed`; `after` clears the flag and refreshes `_stable_state`
- `undo()` / `redo()` — restore/re-apply zoom state; each saves the current state to the opposite stack and refreshes `_stable_state`
- `clear()` — empties both stacks, resets `_stable_state` to `None`; called by `AppController.load_file()`
- `can_undo` / `can_redo` — bool properties
- Gesture coalescing: `PlotStripesArea.range_changed` (aggregated from every stripe's own `range_changed`) fires on every pan/scroll step; `ZoomController` uses a 300 ms debounce timer — `_on_range_changed()` marks gesture start and records the `_stable_state` as `_pre_gesture_state`; `_on_gesture_end()` pushes it to undo and refreshes `_stable_state`
- `_stable_state` design: PyQtGraph fires `sigRangeChanged` synchronously inside `setRange`/`showAxRect`, so capturing "current state" in `_on_range_changed` would already see the post-change position. Instead, `_stable_state` is updated after each gesture ends (idle period), so it always reflects the view before the gesture that triggered `range_changed`. This is especially important for the zoom rectangle, which makes a large one-shot X+Y change.
- History depth trimmed to `get_max_steps()` on every push

## CursorView

(`QObject`, lives inside one `PlotStripe.plot_item` — has no knowledge of other stripes; see `CursorStripesView` for everything cross-stripe):
- Two dashed `pg.InfiniteLine` items (hidden until activated); `apply_mode(mode, positions)` shows/hides and repositions them; hides delta-time line when leaving TWO mode
- `update_delta_time(x1, x2, delta_t_str, y_pos, show, color)` — shows/hides the horizontal delta-time `InfiniteLine` and its `TextItem` label; if `y_pos` is `None` places at 10% from top of current view range; `_delta_label_x` stores last midpoint so the label follows line drags without a full refresh
- `cursor_moved(index, x)` — `pyqtSignal` emitted on every cursor drag step
- `cursor_clicked(index)` — `pyqtSignal` emitted when a cursor line is clicked (sets active cursor for arrow-key stepping)
- `delta_line_moved(y)` — `pyqtSignal` emitted when the delta-time line is dragged (controller stores position)
- Off-screen chevron indicators: `_ChevronItem` (bold `pg.TextItem` subclass, clickable) — one per cursor plus one for the delta-time line, added to this stripe's own ViewBox; `_update_chevrons()` repositions them on every mode/position change and on `sigRangeChanged`; cursor chevrons show `<`/`>` at the left/right edge, delta chevron shows `^`/`v` at the top/bottom edge; two chevrons on the same side are stacked at ±7% of the Y span around centre
- `set_cursor_names(name0, name1)` — updates chevron tooltip text (called from controller on each refresh)
- `cursor_fetch_requested(index, x)` — `pyqtSignal(int, float)` emitted when a cursor chevron is clicked; `x` is the data-X coordinate of the click
- `delta_fetch_requested(y)` — `pyqtSignal(float)` emitted when the delta-time chevron is clicked; `y` is the data-Y coordinate of the click

## CursorStripesView

(`QObject`, `cursors.py`) — composes one `CursorView` per stripe into a single object satisfying `CursorViewProtocol`, so `CursorController` has zero stripe-awareness:
- `add_stripe(stripe)` / `remove_stripe(stripe)` — wired directly to `PlotStripesArea.stripe_created`/`stripe_deleted` in `app.py`; `add_stripe` constructs a new `CursorView(stripe.plot_item)`, registers it as that stripe's own drag claimant, and immediately applies the current mode/positions/colors/names so a stripe created mid-session starts in sync rather than waiting for the next unrelated cursor move
- `set_active_stripe(stripe)` — wired to `PlotStripesArea.active_stripe_changed`; must be connected *before* `CursorController.on_active_stripe_changed` in the same signal (see `app.py`)
- Lockstep cursor dragging (REQ-PLOT-182): `_on_cursor_moved(source_view, index, x)` re-applies the new position to every other stripe's `CursorView` via `apply_mode()`, guarded by a `_propagating` flag (same pattern as `PlotStripe`'s own `_syncing_y` for Synced Y-axis groups) so a sibling's resulting `sigPositionChanged` echo doesn't re-trigger the fan-out or double-emit `cursor_moved` upward
- `update_delta_time(...)` — routes `show=True` only to the currently active stripe's `CursorView`; every other stripe gets `show=False`, so the delta-time line is never duplicated (REQ-PLOT-105/183)
- Value labels — `update_labels`, `remove_labels_for`, `clear_labels`, `recolor_labels` lifted verbatim from the pre-stripes `CursorView`: each label is parented to the signal's own `ViewBox`, which was already correct regardless of which stripe owns that ViewBox, so none of this logic needed to change for multi-stripe support
- Nearest-cursor logic: one `pg.SignalProxy` per stripe's `scene.sigMouseMoved` (30 fps), all feeding one shared `_nearest_cursor` — the user's mouse can be over any stripe

## PlotAreaProtocol / CursorViewProtocol

Neither Protocol (`controller/interfaces.py`) needed new *methods* for multi-stripe cursor support — `CursorStripesView` satisfies the exact same `CursorViewProtocol` `CursorView` always did. `PlotAreaProtocol` grew across several features, all with defaults so no earlier-era caller needed to change: `add_signal(active, stripe=None)`, `zoom_to_fit(all_stripes=True)`, `zoom_y_to_view(all_stripes=True)`, the Plot Stripes lifecycle methods (`create_stripe`, `delete_stripe`, `get_stripes`, `get_active_stripe`, `get_signals_in_stripe`, `get_stripe_for_signal`, `move_signal_to_stripe`), and `refresh_measurement_axes(measurements, synchronized=False)` (#102 added the second parameter).

## MainWindow

Tabs (#99) mean `self.plot_area`/`self.active_signals_table` are **only tab 1's** widgets — every other tab's pair lives inside `_tab_widget`'s pages (`page.plot_area`/`page.active_signals_table`). The Signal Browser, Measurement Info Box, and Signal Info/Properties drawer are the only widgets still genuinely shared/singleton across tabs.

### Construction

Constructor creates the five view widgets above as public attrs, then `_build_actions()` → `_build_menu()` → `_build_toolbar()` → `_build_layout()`.

### Tabs (#99)

- `self._tab_widget` (`QTabWidget`, closable + movable) holds one page per tab (`_make_tab_page(plot_area, active_signals_table)` — a horizontal splitter pairing them) plus a pinned "+" placeholder tab (a real tab, not a corner widget, so it sits immediately after the last real tab with no gap and moves as tabs are added/removed).
- `_wire_tab_view(plot_area, active_signals_table)` — the real per-tab wiring entry point: connects one tab's plot/AST signals to the single shared controller (drops, selection, remove, color/step-mode changes, `move_to_stripe_requested`, the #100 divider-size sync, and `plot_area.synchronize_toggled.connect(self._on_sync_button_clicked)` for #102). Called once per tab: from `set_controller()` for tab 1, from `_on_new_tab()` for every subsequent tab.
- `set_tab_factory(factory)` — stores the callback `app.py` uses to build a new tab's controller-side stack (`controller.create_tab()` + its own `CursorController`/`ZoomController`) whenever `_on_new_tab()` fires.
- `_on_new_tab()` — builds a fresh `PlotStripesArea`+`ActiveSignalsTable` pair, runs `_tab_factory` if set, inserts the page before the placeholder, wires it, makes it current.
- `_on_tab_close_requested(index)` — confirms first if `controller.tab_has_signals(index)`; computes the left-neighbor index *before* removal (QTabBar's own default picks the wrong one); `removeTab(index)` then **`page.deleteLater()`** (explicit — `removeTab()` alone leaks the whole tab's `PlotStripesArea`/`ActiveSignalsTable`, the #120 leak class) then `controller.remove_tab(index)`; shows the empty-tabs placeholder if that was the last tab.
- `_on_tab_changed`, `_on_tab_bar_clicked` (clicking "+" — deliberately not `currentChanged`, which also fires from Qt's own post-removal reindexing and must not auto-create a tab, REQ-PLOT-254), `_on_tab_bar_double_clicked` → `_rename_tab` (`QInputDialog`), `_on_tab_bar_tab_moved` (keeps "+" pinned last, then `controller.reorder_tabs(...)`, REQ-PLOT-243), `_on_tab_context_menu` (Rename/Close), `_cycle_tab(delta)` (Ctrl+Tab/Ctrl+Shift+Tab).
- `_real_tab_count()`, `_placeholder_index()`, `_is_placeholder(index)`, `_all_active_signals_tables()` (every real tab's table, for global preferences), `_build_empty_tabs_placeholder()`, `self._content_stack` (`QStackedWidget` swapping between `_tab_widget` and the empty placeholder).

### Multi-measurement file loading (#101, #109)

- `_load_file(path)` — back-compat single-file entry point, literally `_load_files([path])`.
- `_load_files(paths)` — the real load path: prompts Replace-vs-Add via `_ask_replace_or_add()` only if `measurement_count > 0` (REQ-FILE-012/020); `_collect_snapshots_if_keeping()` gathers every tab's active-signal snapshots first (REQ-PLOT-260, not just the active tab, per `Settings.keep_signals_on_load`); calls `controller.replace_measurements`/`add_measurements`; updates `_sync_measurements_action`'s enabled state; shows one error dialog naming every failed file (REQ-FILE-023); on a successful Replace with snapshots, calls `_restore_snapshots(snapshots)`.
- `_classify_signal_name(name, group_name="", *, measurement_aware=False) -> (status, candidates)` — exact match first, near-match fallback only if none; `status ∈ {exact_single, exact_multiple, near_single, near_multiple, not_found}`; `measurement_aware=True` returns `(LoadedMeasurement, SignalMetadata)` tuples (multi-file Replace carry-over), `False` returns plain `SignalMetadata` (`.mvc` restore, single-measurement scope #106).
- `_restore_snapshots(snapshots_by_tab)` — per tab, classifies each snapshot; `exact_multiple`/`near_multiple` go through `SignalGroupPickerDialog`; every `near_single`/resolved-`near_multiple` candidate across **every tab** is batched into one `NearMatchDialog` at the end (REQ-FILE-036, not one popup per signal); accepted matches resolve, declined ones join `not_found`; resolved entries call `controller.restore_tab_signals(tab_index, resolved)`; any remaining `not_found` names across every tab surface in one `SignalsNotFoundDialog`. The `.mvc`-restore counterpart (`_resolve_config_signals`, used by `_load_config`) follows the identical classify → picker → batch-near-match → not-found-dialog pattern, but is single-measurement and single-tab shaped.

### Measurement Synchronization (#102)

- `self._sync_measurements_action` — checkable Edit-menu action, starts disabled, enabled only once `controller.measurement_count >= 2` (set in `_load_files`).
- `_on_sync_button_clicked()` — fired from *any* tab's bottom-stripe Sync/Un-Sync button (every tab routes to this one handler, since sync is a global controller flag, not per-tab); calls `controller.toggle_measurements_synchronized()` then mirrors the result into `_sync_measurements_action.setChecked(...)`.
- `_on_sync_action_toggled(checked)` — only calls `toggle_measurements_synchronized()` if `checked != controller.is_measurements_synchronized`, distinguishing a real user click on the menu item from the mirrored `setChecked` above (loop-guard preventing a double-toggle).

### Menu Bar / Toolbar (ground truth, see also `docs/ui.md`)

- **File**: Open… (Ctrl+O) → Save Config (Ctrl+S) → Save Config As… → [recent files, dynamically inserted here on `aboutToShow`] → separator → Preferences… → separator → Exit (Ctrl+Q)
- **Edit** (#115): New Tab → New Stripe → separator → Undo (Ctrl+Z) → Redo (Ctrl+Shift+Z) → separator → Sync Measurements (checkable, #102)
- **Help**: Check for Update… → separator → License (text toggles Enter/View) → separator → About MDF-Viewer
- **Toolbar** (#114): Open… → separator → All Stripes (checkable) → Zoom to Fit (Ctrl+0/F) → Zoom Y to View (Y) → separator → Swimlanes (B) → Zoom to Cursors (C, enabled only in two-cursor mode) → Cursors (toggle)
- Global `QShortcut`s not on any menu/toolbar: `.`/`,` (cursor1/cursor2 press), Left/Right arrows (step active cursor; guarded so typing in a text field doesn't steal them), Ctrl+Tab/Ctrl+Shift+Tab (cycle tabs)

### Dock panels (#98)

`_dock_left_panel`/`_dock_info_panel` re-insert each `DockablePanel` into its splitter on re-pin. Left dock wraps `[SignalBrowser, MeasurementInfoBox]` (a vertical splitter) at the left edge; info dock wraps `SignalInfoBox` at the right edge of `_content_splitter`, alongside `_content_stack` (which holds the tab widget). Both default pinned; unpinned, they float as hover-reveal overlays reparented onto `_central`. `_update_child_geometries()` (fed by `eventFilter`/`resizeEvent`/`showEvent`) keeps the outer splitter and both docks' overlay geometry correct. Window/splitter layout persistence (`.mvc`) covers window geometry, all splitter sizes, both docks' pinned/width state, and `signal_info_box.splitter_sizes()` — global window chrome only, not per-tab or per-stripe state.

### Other public methods

`set_controller(controller)` (wires the shared Signal Browser/drawer once, then `_wire_tab_view` for tab 1 only), `set_recent_files_provider(provider)`, `set_settings(settings)`, `trigger_startup_update_check()`, `show_status(message, timeout_ms=3000)`, `set_zoom_all_stripes(enabled)`, `set_license(info, manager=None)`, `open_config(path)` (`.mvc`, called from `app.py`).

## app.py

Constructs `MainWindow`, reads its view attrs, builds `MdfLoader` + `Settings` + `AppController`. Constructs a `CursorStripesView()` and calls `add_stripe()` for every stripe already present, then connects `plot_area.stripe_created`/`stripe_deleted` to `cursor_view.add_stripe`/`remove_stripe`. Constructs `CursorController` (with `get_active_signals`/`get_active_stripe` reading from the active tab/stripe) and `ZoomController(plot_area, get_active_signals=..., get_max_steps=...)`. Wires `controller.set_cursor_controller`/`set_zoom_controller` and `window.set_controller(controller)`; **then** connects `plot_area.active_stripe_changed` to `cursor_view.set_active_stripe` *and* `cursor_ctrl.on_active_stripe_changed`, in that order.

`_wire_tab(controller, workspace, settings)` (#99) — the reusable per-tab wiring block factored out of the above, called once for the initial tab and, via `window.set_tab_factory(...)`, once for every tab created afterward: builds that tab's own `CursorStripesView`/`CursorController`/`ZoomController` against its specific `TabWorkspace`, avoiding the closure-binding trap of capturing `controller.active_signals`/`controller.current_workspace` (which would always read whichever tab is *currently* active, not the one being wired).

Also: `set_recent_files_provider(settings.get_and_prune)`, `window.set_settings(settings)`, `window.set_zoom_all_stripes(settings.zoom_scope == "all_stripes")`. License loaded once via `license_manager.load_stored()`, applied via `window.set_license(...)`. After `window.show()`: `window.trigger_startup_update_check()` if enabled; loads `sys.argv[1]` immediately if present (e.g. via `.mf4` file association).

## DockablePanel (#98)

Wraps a content widget with a pin-toggle chevron button, `edge: Qt.Edge.LeftEdge | RightEdge`. Pinned: a normal widget the owner docks into a splitter — `dock_callback(panel)` is invoked on re-pin so the owner (which knows the splitter layout and desired sizing) can re-insert it, e.g. `MainWindow._dock_left_panel`/`_dock_info_panel`. Unpinned: re-parents itself onto `overlay_parent` (`MainWindow._central`) as a floating overlay, hidden until the mouse hovers near the panel's edge (50 ms poll timer), then slides in/out via a `QPropertyAnimation` on `pos`. `pinned` / `width_px` properties, `set_width(px)`, `set_pinned(bool)`, `toggle_pin()`. `update_geometry(parent_width, parent_height)` — called by the owner's resize handling; no-op while pinned (the host splitter manages geometry then).

## MeasurementInfoBox

Uses a `QStackedWidget` — page 0 is a centred placeholder, page 1 is a `QScrollArea` + `QFormLayout`. `set_info` populates the form; `clear()` switches back. Optional fields omitted; MDF4 XML tags stripped by regex. `_clear_form`, `_add_row`, `_add_wrapped_row`, `_clean_text` shared via import from `measurement_info_box`. `_add_row` puts label/value side by side; `_add_wrapped_row` (used for "Comment") puts the label on its own full-width row with the value wrapped below — used wherever free text is long enough to need its own line. Both route the value through `_make_wrapped_value_label`, which sets `QSizePolicy.Policy.Ignored` horizontally (#98): `QLabel.setWordWrap(True)` alone still reports a `minimumSizeHint()` based on the longest unbreakable substring, which without this would propagate up through the scroll area and force the whole containing panel wider than its column.

## SignalInfoBox (#98)

Info and Properties sections stacked vertically (Properties on top) in `self._splitter`, a resizable `QSplitter(Qt.Vertical)` — not tabs, so both are visible at once in the drawer's narrow-but-tall shape. Bold `QLabel` section headers substitute for the tab labels that used to identify each section.
- **Info section** — `QStackedWidget`: page 0 placeholder ("No signal selected." / "Multiple signals selected."), page 1 `QScrollArea` + `QFormLayout` with metadata rows (name, unit, data type, samples, raster, min, max, comment). `set_metadata(meta)` populates and shows the form; `show_multi_selection()` shows the multi-select placeholder; `clear()` shows "No signal selected." and disables Properties. Raster row shown only when `sample_count ≥ 2`; displays the interval in ms (≤ 500 ms) or s (> 500 ms), or "variable" when `raster_s` is `None`. Comment row uses `_add_wrapped_row`.
- **Properties section** (`_SignalPropertiesWidget`) — display mode `QComboBox` ("Line" / "Line & Marker" / "Marker Only"), marker shape `QComboBox` ("Circle" / "Square" / "Diamond" / "Cross", disabled when mode is "Line"), line width `QSpinBox` (1–8, disabled in "Marker Only"), line style `QComboBox` (Solid/Dashes/Dots/Dash-Dot, disabled in "Marker Only"), and — only for signals with an enum/value table — 3 checkboxes (Value table / Cursor label / Y-axis) controlling which surface shows the enum's text labels instead of raw numbers. `setCurrentIndex(-1)`/blank spinbox used for mismatched multi-select values. Signals: `display_mode_requested(str)`, `marker_shape_requested(str)`, `line_width_requested(int)`, `line_style_requested(str)`, `enum_table_requested(bool)`, `enum_cursor_requested(bool)`, `enum_yaxis_requested(bool)`. `set_properties(mode, shape, width, style)` populates all four, blocking signals during update. `enable_properties(bool)` enables/disables the whole section.
- `splitter_sizes()` / `set_splitter_sizes(list[int])` — the Info/Properties inner splitter's pixel sizes, read/restored by `MainWindow` as part of `.mvc` session persistence (folded into the `"info_drawer"` dict's `"inner"` key).

## ActiveSignalsTable (#100)

A facade over one shared **header** (a `QTableWidget` that never gets rows — REQ-PLOT-272) and a vertical `QSplitter` of per-stripe **segments** (`_ActiveTable`), each a small container stacking `[name_label, seg]`, plus one shared Remove Signal/Remove All button row.

### Data model

One shared ordered list for the whole tab, `self._signals: list[ActiveSignal]` (mirrors `TabWorkspace.active`), plus `self._stripe_for_signal: dict` (mirrors `PlotStripesArea._signal_stripe`). A segment holds **no independent row data** — its rows are always a pure derived rendering via `_segment_signals(seg)`: "signals whose stripe is this segment's stripe, in list order." (#100 postmortem: an earlier version gave each segment its own independently-tracked list, and a sync gap orphaned rows when a stripe was deleted — deriving from one shared list removes that bug class structurally.)

### Segment lifecycle

`add_stripe_segment(stripe)` (idempotent, builds via `_add_segment()` if needed), `remove_stripe_segment(stripe)` (assumes the stripe is already empty; `container.deleteLater()`), `set_stripe_providers(get_stripes, get_stripe_for_signal)` (wired from `MainWindow._wire_tab_view` with `controller.get_stripes`/`get_stripe_for_signal`; gates the context menu's "Move to Stripe" section).

### Row operations, drag-and-drop

- `add_row(active, stripe=None)` — appends to `_signals`, sets its stripe, incremental single-row insert into the segment (always lands last in that segment's filtered view, so no full rebuild needed).
- `move_to_stripe(actives, target_stripe)` — reassigns stripe mapping for each (no-op if already there); re-renders every affected segment; list position otherwise untouched (REQ-PLOT-202/203, no explicit target position).
- `_apply_row_move(moving, target_seg, dst_row)` — the drag-drop landing logic, handling same-segment reorder and cross-segment move uniformly: splices `moving` into the target segment's filtered order at the (selection-adjusted) drop row, rewrites the shared list's slots for the target stripe's positions, re-renders every affected segment, always emits `order_changed`. **#116 fix**: if any dragged signal actually changed stripe, also emits `move_to_stripe_requested(cross_stripe_moves, target_stripe)` — needed because the plot side previously never learned about a cross-segment AST drag, leaving the curve behind in its old stripe.
- Drag mechanics use a custom `QDrag` + `ROW_MIME_TYPE` (from `_mime.py`), not Qt's native item drag (`setDragEnabled(False)`): `_start_segment_drag(seg)` always drags the full cross-segment selection, not just that segment's own rows (REQ-PLOT-279 M8); an `eventFilter` on every segment's viewport handles `DragEnter`/`DragMove`/`Drop` for both `SIGNAL_MIME_TYPE` (from the Signal Browser → `signals_dropped_on_stripe`) and `ROW_MIME_TYPE` (→ `_on_row_move_drop` → `_apply_row_move`).
- `_ActiveTable` (the segment widget) implements manual drag-gesture detection (`mousePressEvent`/`mouseMoveEvent`/`mouseReleaseEvent`) rather than Qt's native drag, and defers "clear sibling segments' selection" to release rather than press when the press landed on an already-selected row (so dragging an existing cross-segment selection doesn't get pre-empted, REQ-PLOT-276/279).

### Rename, context menu

- `_rename_segment(seg)` — double-click a segment's name label → `QInputDialog`, mirrors `MainWindow._rename_tab`'s pattern exactly (no controller round-trip; names aren't persisted model state, REQ-PLOT-294).
- Context menu (`_on_context_menu`), in order: Remove Signal(s) → separator → Enable/Disable Step Mode (for all) → separator → Shorten Signal Names (checkable) → Display Name Rule… → separator → Merge Y-Axis (n≥2, not already synced) / Sync Y-Axis (n≥2, not already merged) → Remove from merged/synced axis (if any selected signal is grouped) → separator → Move to Stripe submenu (other stripes only) → Move to new Stripe.

### Divider size sync with the plot's stripe splitter (REQ-PLOT-274)

Fixed `_top_size_offset`/`_bottom_size_offset` (header height; button-row height, each + layout spacing) computed once, since this widget's column has chrome the plot's own splitter doesn't. `set_segment_sizes(sizes)` applies incoming stripe sizes, subtracting the offsets only from the first/last segment so every interior segment matches its stripe's height exactly (a straight 1:1 copy, or Qt's own `setSizes()` squash-to-fit, only preserves *ratios* — #100 postmortem). `segment_sizes_changed` pushes local drags back out. Wired bidirectionally in `MainWindow._wire_tab_view`, plus a one-time bootstrap push right after wiring (a freshly created segment otherwise keeps whatever arbitrary size `QSplitter.addWidget()` gave it).

### Signals

`selection_changed(object)`, `multi_selection_active(bool)`, `multi_selection_changed(list)`, `remove_requested(list)`, `remove_all_requested()`, `color_change_requested(list, QColor)`, `step_mode_set_requested(list, bool)`, `signals_dropped_on_stripe(list, object, int)`, `order_changed(list)`, `configure_display_names_requested(str)`, `shorten_names_toggled(bool)`, `merge_y_axis_requested(list)`, `sync_y_axis_requested(list)`, `ungroup_y_axis_requested(list)`, `move_to_stripe_requested(list, object)`, `move_to_new_stripe_requested(list)`, `segment_sizes_changed(list)`, `segment_activated(object)` (any mouse-press in a segment, REQ-PLOT-278).

### Other public methods

`select_signal`, `set_shorten_names_enabled`, `set_group_membership(merged, synced)`, `set_row_color`, `set_name_formatter(formatter)`, `remove_row`, `clear`, `show_cursor_columns`, `set_cursor_column_headers`, `set_delta_column_header`, `update_cursor_values`.

## Signal restore dialogs (#101, #109)

- **`SignalGroupPickerDialog(signal_name, candidates, parent=None)`** — asks which channel group (or, once measurement-aware, which measurement) to use when a name is ambiguous; `candidates` is either `list[SignalMetadata]` (single-measurement, `.mvc` restore, #106) or `list[tuple[LoadedMeasurement, SignalMetadata]]` (multi-file Replace carry-over, #101), detected by shape so existing call sites keep working unchanged. `selected` property returns the chosen entry (matching whichever shape was given) or `None`.
- **`NearMatchDialog(pending, parent=None)`** — one dialog batching *every* near-match across a whole operation (all tabs, for reload; #109 REQ-FILE-036), not one popup per signal. `pending` is `list[tuple[original_name, candidate]]` (candidate either shape as above). One checkable row per pending item (checked by default). `accepted_matches()`, `declined_matches()`, `checked_mask()` (per-row checked state in original order, so a caller can re-associate rows with external data like "which tab" without name-matching, which breaks on duplicate names).
- **`SignalsNotFoundDialog(signal_names, parent=None)`** — reports signals that couldn't be matched at all (distinct from a near-match); plain list + "Copy to Clipboard" button; no accepted-state accessor, purely a report/acknowledge dialog.

## Settings

(`src/mdf_viewer/settings.py`):
- `add_recent(path)` — resolves to absolute path, prepends, deduplicates, trims to `MAX_RECENT=4`, saves immediately
- `recent_files() -> list[Path]` — raw list (may include missing paths)
- `get_and_prune() -> list[Path]` — filters to existing paths, saves if anything was removed; used as the `MainWindow` recent-files provider
- `check_for_updates: bool` — property (default `True`); setting it saves immediately
- `cursor_persistent: bool` — property (default `True`); setting it saves immediately
- `cursor_mode: str` — property (`"1/2"` or `"L/R"`, default `"1/2"`); setting it saves immediately
- `cursor_color_c1 / c2 / cl / cr: tuple[int,int,int]` — per-cursor RGB colors (default: C1/CL yellow `(220,220,50)`, C2 orange `(255,140,0)`, CR blue `(50,150,255)`); stored as `[r,g,b]` lists in JSON; `_load_color()` falls back to default on malformed values
- `show_delta_time_in_plot: bool` — property (default `True`); setting it saves immediately
- `delta_time_color: tuple[int,int,int]` — delta-time line color (default light gray `(200,200,200)`)
- `cursor_step_unit: str` — "samples" / "pixels" / "time" (default `"samples"`); setting saves immediately
- `cursor_step_samples: int` — step size in samples mode (default `1`)
- `cursor_step_pixels: int` — step size in pixels mode (default `1`)
- `cursor_step_time_ms: float` — step size in time mode, milliseconds (default `10.0`)
- `max_undo_steps: int` — zoom undo history depth (default `1`, min `1`); setting saves immediately
- `zoom_scope: str` — `"all_stripes"` or `"active_stripe"` (default `"all_stripes"`); governs whether "Zoom to Fit" / "Zoom Y to View" apply to every plot stripe or only the active one; setting saves immediately
- `keep_signals_on_load: str` — `"always"` / `"ask"` / `"never"` (default; see `DEFAULT_KEEP_SIGNALS_ON_LOAD`) — whether `MainWindow._collect_snapshots_if_keeping()` carries active signals across a Replace load, prompts first, or never bothers
- Module-level constants `DEFAULT_CURSOR_COLOR_C1/C2/CL/CR`, `DEFAULT_DELTA_TIME_COLOR`, `DEFAULT_CURSOR_STEP_UNIT/SAMPLES/PIXELS/TIME_MS`, `DEFAULT_MAX_UNDO_STEPS`, `DEFAULT_ZOOM_SCOPE`, `DEFAULT_KEEP_SIGNALS_ON_LOAD` exported for use by `PreferencesDialog`
- Config path: `%APPDATA%\mdf-viewer\settings.json` (Windows) / `~/.config/mdf-viewer/settings.json` (Linux); detected via `sys.platform`; parent dirs created on first save
- Constructor accepts an optional `path` override (used in tests via `tmp_path`)

## PlotStripe

One plot stripe — everything below is scoped to "this stripe's own signals"; cross-stripe behavior lives in `PlotStripesArea`. Public API:
- `add_signal(active)` — creates `ViewBox` + `AxisItem('right')` + `PlotDataItem`; sets `active.curve` and `active.view_box`; respects `active.display_mode` and `active.marker_shape` at creation; no-op for duplicates; connects `vb.sigRangeChanged` AFTER `enableAutoRange()` so the initial auto-range is not captured as a zoom step
- `remove_signal(active)` — removes curve/ViewBox/axis; clears `active.curve`/`active.view_box`; no-op for unknowns. Curve destruction goes through `_destroy_curve` (below), not `ViewBox.removeItem()` directly.
- `recolor_signal(active, color)` — updates curve pen, symbol colors, axis pen, axis text pen, and `active.color`; handles marker-only pen (NoPen) correctly; no-op for unknowns
- `set_step_mode(active, enabled)` — switches curve between linear and staircase (`pg.PlotDataItem(stepMode="left")`) rendering; no-op for unknowns
- `set_display_mode(active, mode, shape)` — switches between `"line"` / `"line_marker"` / `"marker"` rendering; updates curve pen and symbol (`_PG_SYMBOL` map: `circle→"o"`, `square→"s"`, `diamond→"d"`, `cross→"+"`); marker size from `_symbol_size(line_width)` = `max(6, width*4)`; no-op for unknowns
- `set_line_width(active, width)` — updates curve pen width and symbol size; no pen update in `"marker"` mode; no symbol size update in `"line"` mode; no-op for unknowns
- `set_line_style(active, style)` — updates curve pen style (`"solid"` / `"dashes"` / `"dots"` / `"dash-dot"`); no-op in `"marker"` mode or for unknowns
- `set_selected_signals(actives, all_signals=None, top_first=True)` — applies the selection line-boost and raised Z-value to each signal in `actives`; `PlotStripesArea` fans the *full, unfiltered* global list to every stripe, since a stripe's own Z-order math only ever touches signals it actually owns
- `_effective_width(active)` — returns `active.line_width + boost` if selected, else `active.line_width`; used internally by all pen-building paths
- `set_y_grid(active, enabled)` — shows or hides horizontal Y-grid lines on a signal's `ViewBox`; no-op for unknowns
- `zoom_to_fit()` — full X range from this stripe's own signals' `display_timestamps` (#101), then `autorange_y()`; no-op when empty
- `autorange_y()` — auto-ranges Y independently for every display unit, computed directly from each unit's own sample data via `setYRange` rather than pyqtgraph's `ViewBox.autoRange()` — that call also recomputes X from the curve's bounding rect, which would silently fight the "full data range" X that `zoom_to_fit()` (or `PlotStripesArea`'s cross-stripe version) just set
- `zoom_to_x_range(x_min, x_max)` — sets this stripe's X axis to the given range (0.02 padding) without touching Y; used by `AppController.zoom_to_cursors()`
- `sync_x_range(x_min, x_max)` — sets the exact X range with **no** padding; used only by `PlotStripesArea`'s cross-stripe X broadcast (padding would compound outward on every hop)
- `swimlanes(ordered_signals) -> bool` — arranges display units in equal horizontal lanes by adjusting each unit's Y range to its visible-data band plus 5% padding; returns `False` if there are no active signals
- `zoom_y_to_view() -> bool` — rescales each display unit's Y-axis to fit the currently visible X range; returns `False` if there are no active signals
- `_display_units(ordered_signals=None) -> list[(view_box, member_signals, is_synced_group)]` — groups active signals into independent Y-display units for `zoom_to_fit`/`swimlanes`/`zoom_y_to_view`/`autorange_y` (#84): an ungrouped signal or Merged group is one unit (already one ViewBox); a Synced group is one unit spanning multiple ViewBoxes, since the sync handler forces their ranges to match and treating them as N independent units would have each `setYRange()`/`autoRange()` call clobber the others
- `get_zoom_state(active_signals) -> ZoomState` — snapshots current X range and each active signal's Y range; keyed by `ActiveSignal` identity
- `set_zoom_state(state, active_signals)` — restores X and per-signal Y ranges from a `ZoomState`; signals in `active_signals` but absent from state keep their current Y; removed signals are silently skipped
- `content_axis_width() -> float` — sum of the pixel widths of this stripe's own visible Y-axes (forces `layout.activate()` first so a pending style/visibility change is reflected immediately rather than on the next paint cycle); excludes any padding spacer
- `set_axis_padding(px)` — adds/resizes/removes a blank right-side spacer axis so this stripe's plotting viewport ends at the same pixel offset as other stripes with wider axis areas (see `PlotStripesArea._realign_axis_widths`); the spacer's own removal path goes through the same `deleteLater()` fix as the axis/curve teardown below (#120) — this branch only runs the *first* time a stripe's needed padding drops to exactly 0, which is what made the original leak easy to miss
- `set_active(bool)` — shows/hides the left-edge colored active-stripe marker
- `set_show_x_axis_ticks(bool)` — shows/hides this stripe's bottom X-axis tick labels *and* its "Time" axis title (`showLabel`) — only the bottom-most stripe shows either
- `plot_item` — read-only property exposing the inner `pg.PlotItem` (used by `CursorView`/`CursorStripesView`)
- Signals: `y_grid_toggled(bool)`, `file_dropped(object)` (Path), `signals_dropped(list, int)` (locations + measurement index, #101), `active_signals_dropped(object)` (id-set of `ActiveSignal`s dragged from the AST onto this stripe's plot area, #116), `range_changed()` (X or any signal Y range changed), `activated(self)` (any mouse-press in this stripe's viewport, for active-stripe tracking), `create_stripe_requested(self)`, `delete_stripe_requested(self)`
- Drop target: event filter on `_pw.viewport()` accepts MDF file URLs, `SIGNAL_MIME_TYPE` (Signal Browser), and `ROW_MIME_TYPE` (AST row drag, #116); shows a border highlight while a drag hovers (cleared on `DragLeave`/`Drop`)
- Context menu: `_ViewBox`'s `extra_menu_items` constructor param appends "Create new Stripe" / "Delete this Stripe" once at construction (not inside `getMenu()`, which pyqtgraph calls on every right-click but always returns the same cached `QMenu` — adding items there would duplicate them)
- Private internals: `_ViewBox` subclass handles pan/zoom with a context menu (Y-grid toggle, stripe actions); `_SignalAxisItem` subclass formats integer tick labels without decimals; `_SignalPlotData` dataclass bundles the ViewBox + axis + curve per signal

### Per-measurement axis rows (#101)

- `_MeasurementAxisItem(measurement, on_offset_changed=None, draggable=True, *args, **kwargs)` — a `pg.AxisItem` (orientation forced to `'bottom'`) linked to the **same shared ViewBox** as every other axis in the stripe (not its own), so tick *positions* track the shared X-zoom/pan for free; only `tickStrings()` differs per row, subtracting `measurement.offset_s` so the row reads as that measurement's real recorded time. `mouseDragEvent` is fully overridden (never forwards to the linked view's own pan): ignores if `not draggable` or non-left-button; on drag, mutates `measurement.offset_s` directly and calls `on_offset_changed(measurement)` if set, forcing a repaint.
- `set_measurement_axes(measurements, on_offset_changed=None, draggable=True)` — builds one row per entry in `measurements`, stacked below `PlotItem`'s own rows 0–3 starting at row 4, same column as the ViewBox/"Time" axis; only ever called non-empty on the bottom-most stripe (REQ-PLOT-301, enforced by the caller). Teardown of prior rows goes through the same `deleteLater()` fix described below (#120) rather than `removeItem()`/`hide()` alone.

### Synchronize/Un-Sync button (#102)

- `set_measurement_sync_control(visible, synchronized, on_toggle=None)` — shows/hides/relabels ("Sync"/"Un-Sync") a `QPushButton` parented directly to `self._pw` (the `PlotWidget`/`QGraphicsView`) rather than added to the stripe's `QHBoxLayout` — it needs to float *on top of* the plot near the measurement axis rows, not sit beside it. Only ever shown (`visible=True`) on the bottom-most stripe once 2+ measurements are loaded (REQ-PLOT-316); hidden entirely otherwise, not shown-disabled.
- Positioned via `_reposition_sync_button()` (bottom-right corner of the viewport rect, 6px margin, `raise_()` after moving) — called from `set_measurement_sync_control` itself, from the `self._pw.viewport()` `eventFilter`'s `QEvent.Type.Resize` branch (the one branch that deliberately doesn't consume its event, since the viewport still needs to process the resize), and from `_update_view_geometries()` (called after any signal add/remove). The last call site was a live-found fix: adding a signal changes the axis layout without necessarily firing a viewport Resize event, and Qt's own `QGraphicsView` appears to re-raise its own viewport internally on scene changes — burying the sync button (a sibling `QWidget`) behind it again unless explicitly re-raised too.

### Teardown fixes (#120)

`_destroy_vb_and_axis(vb, axis)` and `_destroy_curve(curve, vb)` (static) replace what used to be `removeItem()`/`hide()`-only detachment, which left the `ViewBox`/`AxisItem`/curve alive as orphaned scene members — still linked to `self._pi.vb` (whose X range is kept in sync across every stripe), so they kept reacting to range-change signals indefinitely, and (for curves specifically) `ViewBox.removeItem()`'s intermediate None-parent state made PyQtGraph's `getViewBox()` wrongly cache the enclosing `QGraphicsView`, crashing the next `viewRangeChanged()`. Both now `deleteLater()` after properly detaching from the scene. Called from `remove_signal`, `merge_signals`/`ungroup_signal` (VB/axis ownership changes), and `set_measurement_axes`/`set_axis_padding`'s own teardown paths (all three explicitly reference this same fix).

## PlotStripesArea

Composes one or more `PlotStripe`s (a vertical `QSplitter`) into what `MainWindow` builds as `self.plot_area` (one instance per tab, #99) and what `AppController` receives as its `plot_area` dependency. Public API beyond the per-signal `PlotAreaProtocol` passthroughs (routed via an identity-keyed `_signal_stripe: dict[ActiveSignal, PlotStripe]`, no new `ActiveSignal` field):
- `create_stripe() -> PlotStripe` — appends a new stripe, redistributes `_splitter` sizes equally, and immediately matches the new stripe's X range to the others
- `delete_stripe(stripe) -> bool` — refuses if it's the last stripe or still has signals; **has no `force` concept** — `AppController.delete_stripe` removes each signal via the full `remove_signal()` pipeline first (table row, cursor labels), then calls this with an already-empty stripe; already correctly `deleteLater()`s the removed stripe (this was not part of the #120 leak — that fix was about sub-objects `PlotStripe` itself detached without destroying, not the stripe-level teardown here)
- `set_active_stripe(stripe)` / `get_active_stripe()` / `get_stripes()` / `get_signals_in_stripe(stripe)` / `get_stripe_for_signal(active)` / `move_signal_to_stripe(active, target)`
- Signals: `stripe_created(stripe)`, `stripe_deleted(stripe)`, `active_stripe_changed(stripe)`, `delete_stripe_requested(stripe)` (bubbled up unhandled — a non-empty stripe needs `MainWindow`'s confirmation dialog), `signals_dropped_on_stripe(list, stripe, int)` (a Signal Browser drag was dropped onto a specific stripe, #101 added the measurement-index arg), `active_signals_dropped_on_stripe(object, stripe)` (an AST row was dropped directly onto a stripe's plot area, #116), `measurement_offset_changed(object)` (a measurement axis row was dragged, #101), `synchronize_toggled()` (a stripe's Sync/Un-Sync button was clicked, #102 — `AppController` owns the actual flag, this just asks it to flip)
- Cross-stripe X sharing: **not** pyqtgraph's native `setXLink` — a `ViewBox` can only listen to one other view per axis, which can't express "any stripe may drive all the others." Instead, each stripe's `sigXRangeChanged` is connected to `_on_stripe_x_changed`, which broadcasts the new range to every other stripe via `sync_x_range()`, guarded by a `_syncing_x` flag against feedback loops (same pattern as `PlotStripe`'s own `_syncing_y`)
- Axis-width alignment: `_schedule_realign()` (debounced via `QTimer.singleShot(0, ...)`, coalescing several structural changes in one event-loop tick) → `_realign_axis_widths()` computes every stripe's `content_axis_width()` and pads the narrower ones via `set_axis_padding()` to match the widest — otherwise stripes with a different number/width of Y-axes would have differently-sized plotting viewports, so the same X value would land at a different screen pixel per stripe. Triggered after any signal add/remove/move, merge/sync/ungroup, selection change, or stripe create/delete. A separate `_range_realign_timer` (300 ms singleshot, restarted on every `range_changed`) also re-checks alignment once panning/zooming settles, since an integer signal's tick-label digit count — and therefore its axis width — can change with no structural change at all; debounced the same way `ZoomController` debounces gesture-settle rather than recomputing on every frame of a drag.
- Click-selection cross-stripe rule (REQ-PLOT-047): `_on_signal_clicked` tracks which stripe's last *hit* click "owns" the current selection; a miss-click (empty space) in a *different* stripe is swallowed rather than re-emitted, so it can't clear a selection that belongs to another stripe
- `zoom_to_fit(all_stripes=True)` / `zoom_y_to_view(all_stripes=True)` — X always spans every stripe's data (it's shared); Y-autorange applies to every stripe or only the active one, per the argument (driven by `AppController` from `Settings.zoom_scope`)
- `swimlanes(signals)` — always filtered to the active stripe's own signals before delegating, regardless of the above toggle (REQ-PLOT-057)
- `merge_signals(signals)` / `sync_signals(signals)` — validated same-stripe via `_same_stripe_or_none()` first (REQ-PLOT-038); no-op if the signals span stripes
- `get_zoom_state`/`set_zoom_state`/`zoom_to_x_range`/`plot_item` — delegate to `self._stripes[0]` as a representative stripe (X is always equal across stripes; Y goes through each signal's own `view_box` regardless of which stripe currently owns it)

### Multiple Measurements / Synchronization additions (#101, #102)

- `self._measurements: list` — current global measurement pool (#101), pushed here by `AppController` via `refresh_measurement_axes()`; applied to whichever stripe is currently bottom-most (REQ-PLOT-301), re-applied whenever the bottom-most stripe changes.
- `self._synchronized: bool = False` (#102) — whether the per-measurement axis rows are collapsed into one shared ruler; pushed alongside `self._measurements`, same lifetime/re-apply rules.
- `refresh_measurement_axes(measurements, synchronized=False)` — stores both, calls `_update_x_axis_tick_visibility()`.
- `_update_x_axis_tick_visibility()` — for the bottom stripe: when synchronized and the pool is non-empty, passes `[measurements[0]]` (the first-loaded/reference measurement) to `set_measurement_axes` instead of the full pool, with `draggable=False`; `set_show_x_axis_ticks(...)` still gates on the *full* pool, not the collapsed list, so per-measurement rows never fall back to the plain "Time" axis just because they collapsed to one. Also calls `stripe.set_measurement_sync_control(visible=is_bottom and len(measurements) >= 2, synchronized=self._synchronized, on_toggle=self.synchronize_toggled.emit)` for every stripe in the same loop.
