# MDF-Viewer – Module API Reference

## Implemented Modules

| Module | Description | Tests |
|--------|-------------|-------|
| `errors.py` | `MdfLoadError` — shared error type imported by model and view | — |
| `model/mdf_loader.py` | `MdfLoader` + `ChannelGroupInfo` | 32 |
| `model/signal_data.py` | `SignalData` dataclass | 2 |
| `model/interpolate.py` | `interpolate(active, x)` — shared linear interpolation helper used by `CursorController` and `CursorView` | — |
| `view/_mime.py` | Shared MIME type constant for signal drag-and-drop | — |
| `view/signal_browser.py` | `SignalBrowser` — TreeView, multi-select, Add Signal button, drag | 43 |
| `view/main_window.py` | `MainWindow` — splitter layout, menu, toolbar, status bar, wiring | 48 |
| `view/measurement_info_box.py` | `MeasurementInfoBox` — file metadata, QFormLayout + placeholder | 21 |
| `view/signal_info_box.py` | `SignalInfoBox` — Info tab (metadata, incl. raster) + Properties tab (display mode, marker shape); QTabWidget | 41 |
| `view/widgets/color_swatch.py` | `ColorSwatch` — flat `QPushButton` color indicator; reusable across views | — |
| `view/active_signals_table.py` | `ActiveSignalsTable` — color swatch, name, cursor cols, buttons, drop target; multi-select | 54 |
| `view/plot_area.py` | `PlotArea` — PyQtGraph, shared X-axis, per-signal ViewBox + Y-axis, drop target, zoom state snapshot | 62 |
| `view/cursors.py` | `CursorView` — InfiniteLine items, value labels, nearest-cursor logic, delta-time line + label, off-screen chevron indicators | 33 |
| `view_model/active_signal.py` | `ActiveSignal` dataclass (model data + plot objects + color + display mode + marker shape + line width) | — |
| `view_model/zoom_state.py` | `ZoomState` dataclass — snapshot of X range + per-signal Y ranges | — |
| `controller/interfaces.py` | Protocol contracts for all controller-view dependencies | — |
| `controller/app_controller.py` | `AppController` — coordinates all layers | 84 |
| `controller/cursor_controller.py` | `CursorController` — toggle, position memory, interpolation, delta-time | 93 |
| `controller/zoom_controller.py` | `ZoomController` — zoom undo/redo, gesture coalescing, stable-state pre-capture | 27 |
| `settings.py` | `Settings` — JSON persistence for recent files + preferences | 43 |
| `update_checker.py` | `fetch_latest_release()`, `is_newer()`, `ReleaseInfo`, `UpdateCheckError` — GitHub releases API, no Qt | 13 |
| `license/license_info.py` | `LicenseInfo` dataclass, `Tier` enum, `FORMAT_VERSION`, embedded public key | — |
| `license/license_manager.py` | `LicenseManager` — verify, import, load_stored, export_license; `LicenseError` | 29 |
| `view/license_dialog.py` | `LicenseDialog` — import mode (browse/drop) + view mode (details + expiry notice + Retrieve License button); on successful import shows a "restart required" message and closes | — |
| `view/preferences_dialog.py` | `PreferencesDialog` — tabbed `QDialog`; General tab with "Check for updates on startup" checkbox and "Undo steps" spinbox (1–100); Cursors tab with mode, persistent, 4 cursor color swatches (C1/C2/CL/CR), Show ∆-Time checkbox + color swatch, arrow-key step (unit combobox + spinbox), reset button | 4 |
| `app.py` | MVC assembly point | — |

---

## MdfLoader

`MdfLoader` is the sole importer of `asammdf`. Public API:
- `open(path)` / `close()` / `is_open`
- `measurement_info()` → `MeasurementInfo`
- `channel_tree()` → `list[ChannelGroupInfo]`
- `load_signal(group_index, channel_index)` → `(SignalData, SignalMetadata)` — captures raw asammdf dtype before float64 conversion; sets `SignalMetadata.data_type` and `is_integer`; computes `SignalMetadata.raster_s` via `_compute_raster()` (p99 interval deviation ≤ 5 % → fixed rate in seconds, else `None`); if float64 conversion fails (enum/string samples), retries with `raw=True` to get the underlying integer encoding; raises `MdfLoadError` only if raw values are also non-numeric

## SignalBrowser

Public API:
- `populate(groups: list[ChannelGroupInfo])` — rebuilds the tree, groups expanded, filter cleared
- `clear()` — resets the tree and clears the filter
- `add_signals_requested(list[tuple[int,int]])` — PyQt signal emitted with all selected channel locations on double-click, Add Signal button click, or drag initiation
- Filter field: `QLineEdit` at the top; connected to a `QSortFilterProxyModel` with `setRecursiveFilteringEnabled(True)` (case-insensitive, partial match; groups visible when any child matches). `setClearButtonEnabled(True)` provides a built-in × button. `populate()` and `clear()` both reset the filter.
- Selection mode: `ExtendedSelection` — Ctrl+click and Shift+click select multiple channels; the Add Signal button emits all selected channels at once
- Drag: `_DragTreeView` subclass encodes selected `(group_index, channel_index)` pairs as JSON in `application/x-mdf-viewer-signals` MIME data; drop targets are `PlotArea` and `ActiveSignalsTable`

## ActiveSignal

Fields: `data`, `metadata`, `color: QColor` (set by controller from palette); `step_mode: bool`; `display_mode: str` (`"line"` / `"line_marker"` / `"marker"`, default `"line"`); `marker_shape: str` (`"circle"` / `"square"` / `"diamond"` / `"cross"`, default `"circle"`); `line_width: int` (1–8, default `1`); `line_style: str` (`"solid"` / `"dashes"` / `"dots"` / `"dash-dot"`, default `"solid"`); `curve` and `view_box` are `None` until `PlotArea.add_signal()` fills them in. `__hash__ = object.__hash__` and `__eq__ = object.__eq__` — identity semantics throughout to avoid numpy `__eq__` ambiguity (list `in` / `remove` also use `__eq__`).

## AppController

Public API:
- `load_file(path)` — clears all state, opens file, populates browser + info box; resets color counter, cursor system, and zoom history; calls `settings.add_recent(path)` on success only; UI cleared before `open()` so state is clean on failure
- `add_signal(gi, ci) -> bool` — loads channel, assigns next palette color, notifies plot + table; calls `cursor_ctrl.refresh()` to recompute values for the new signal; returns `True` if added, `False` if already active (duplicate)
- `remove_signal(active)` — removes from plot/table/list; calls `cursor_ctrl.on_signal_removed` (label cleanup) then `cursor_ctrl.refresh()`; clears selection if that signal was selected
- `remove_signals(actives)` — removes a list of signals; calls `on_signal_removed` per signal then a single `cursor_ctrl.refresh()`; connected to `ActiveSignalsTable.remove_requested`
- `remove_all()` — calls `cursor_ctrl.on_all_signals_cleared()` (label cleanup), then removes all signals, clears table, clears selection
- `toggle_step_mode(active)` — flips `active.step_mode`; calls `PlotArea.set_step_mode()` to switch between linear and staircase rendering
- `set_step_modes(actives, enabled)` — sets step mode to a specific state for each signal; connected to `ActiveSignalsTable.step_mode_set_requested`
- `recolor_signal(active, color)` — updates curve + axis color via `PlotArea.recolor_signal()` and cursor labels via `cursor_ctrl.recolor_signal()`
- `recolor_signals(actives, color)` — loops `recolor_signal()` for each; connected to `ActiveSignalsTable.color_change_requested`
- `on_multi_selection(multi)` — called when table switches to >1 selected rows; calls `signal_info.show_multi_selection()` when True; connected to `ActiveSignalsTable.multi_selection_active`
- `set_multi_selected(actives)` — stores full multi-selection list in `_selected_signals`; computes shared display_mode/marker_shape (None when mismatched); calls `signal_info.set_properties()` and `enable_properties(True)`; connected to `ActiveSignalsTable.multi_selection_changed`
- `on_display_mode_requested(mode)` — applies `display_mode` to all `_selected_signals`; calls `PlotArea.set_display_mode()`; connected to `SignalInfoBox.display_mode_requested`
- `on_marker_shape_requested(shape)` — applies `marker_shape` to all `_selected_signals`; calls `PlotArea.set_display_mode()` only when signal is not in "line" mode; connected to `SignalInfoBox.marker_shape_requested`
- `on_line_width_requested(width)` — applies `line_width` to all `_selected_signals` via `PlotArea.set_line_width()`; connected to `SignalInfoBox.line_width_requested`
- `on_line_style_requested(style)` — applies `line_style` to all `_selected_signals` via `PlotArea.set_line_style()`; connected to `SignalInfoBox.line_style_requested`
- `reorder_signals(ordered)` — updates `_active` list order to match new table row order; calls `cursor_ctrl.refresh()`; connected to `ActiveSignalsTable.order_changed`
- `on_y_grid_toggled(enabled)` — tracks Y-grid state; turns grid off on the previously selected signal and on for the newly selected one; connected to `PlotArea.y_grid_toggled`
- `set_selected_signal(active | None)` — drives the Signal Info Box (metadata + properties tab); also manages per-signal Y-grid when `_y_grid_enabled`; updates `_selected_signals = [active]` or `[]`
- `refresh_cursors()` — calls `cursor_ctrl.refresh()`; used by `PreferencesDialog` after cursor preference changes
- `set_cursor_controller(cc)` — optional; wired from `app.py` after construction
- `set_zoom_controller(zc)` — optional; wired from `app.py` after construction
- Cursor proxy methods: `toggle_cursor()`, `press_cursor1()`, `press_cursor2()`, `press_left()`, `press_right()`, `zoom_to_cursors() -> bool`, `set_cursor_mode_callback(cb)` — all delegate to `_cursor_ctrl`, guarded by `None` check; `zoom_to_cursors()` now applies the zoom internally and returns `True` if applied (was: returned the span tuple)
- Zoom proxy methods: `zoom_to_fit()`, `zoom_y_to_view() -> bool`, `swimlanes() -> bool` — each calls `zoom_ctrl.before/after_discrete_action()` around the `PlotArea` call so the action is recorded as a single undo step
- Undo/redo proxies: `undo()`, `redo()` — delegate to `_zoom_ctrl`, guarded by `None` check
- Constructor accepts optional `settings: Settings` — omitting it disables recent-file tracking without any other effect
- `active_signals` / `selected_signal` / `is_file_loaded` — read-only state accessors

## CursorController

Public API:
- Constructor: `(cursor_view, get_x_range, active_signals_table, get_active_signals=None, get_cursor_persistent=None, get_cursor_mode=None, get_cursor_colors=None, get_y_range=None, get_show_delta_time=None, get_delta_time_color=None, get_selected_signal=None, get_cursor_step_unit=None, get_cursor_step_samples=None, get_cursor_step_pixels=None, get_cursor_step_time_ms=None, get_x_per_pixel=None)` — all settings read on demand via callables; `get_cursor_colors` returns `(c1, c2, cl, cr)` RGB tuples; `get_selected_signal` used for sample-step mode when no cursor has been touched; defaults to module-level constants / empty-list / `None` when omitted
- `toggle()` — HIDDEN → ONE → TWO → HIDDEN; on first activation places cursors at plot X range start + 10% span; subsequent toggles use remembered positions
- `press_cursor1()` / `press_cursor2()` — direct single-cursor activation (dot / comma keys)
- `press_left()` / `press_right()` — move the active cursor one step left/right (arrow keys); no-op when HIDDEN or no cursor touched in TWO mode
- `zoom_to_cursors() -> tuple[float,float] | None` — returns the span between the two cursors in TWO mode; None otherwise
- `reset()` — called by `AppController.load_file()`; hides cursors and marks positions for re-initialisation on next activation
- `refresh()` — called by `AppController` after any change to the active signal list; re-computes values and updates labels
- `on_signal_removed(active)` / `on_all_signals_cleared()` — label cleanup only; must be called before `PlotArea.remove_signal()` so the ViewBox is still in the scene
- `set_mode_changed_callback(cb)` — registers a callable invoked with the new `CursorMode` on every toggle
- `recolor_signal(active, color)` — delegates to `CursorView.recolor_labels()`
- Drives `ActiveSignalsTable.update_cursor_values()` and `CursorView.update_labels()` on every drag and toggle
- Active cursor tracking: `_active_cursor_idx` set by drag/click events, cleared on reset(); auto-set to 0 when entering ONE mode
- Arrow-key step settings injected via callables: `get_cursor_step_unit` ("samples"/"pixels"/"time"), `get_cursor_step_samples`, `get_cursor_step_pixels`, `get_cursor_step_time_ms`, `get_x_per_pixel`

## ZoomController

(`controller/zoom_controller.py`):
- Constructor: `(plot_area, get_active_signals, get_max_steps, _timer=None)` — `_timer` is injectable for testing (avoids requiring QApplication in unit tests); connects to `plot_area.range_changed`
- `before_discrete_action()` / `after_discrete_action()` — bracket toolbar zoom calls; `before` captures the current state onto the undo stack and sets `_ignore_range_changed`; `after` clears the flag and refreshes `_stable_state`
- `undo()` / `redo()` — restore/re-apply zoom state; each saves the current state to the opposite stack and refreshes `_stable_state`
- `clear()` — empties both stacks, resets `_stable_state` to `None`; called by `AppController.load_file()`
- `can_undo` / `can_redo` — bool properties
- Gesture coalescing: `PlotArea.range_changed` fires on every pan/scroll step; `ZoomController` uses a 300 ms debounce timer — `_on_range_changed()` marks gesture start and records the `_stable_state` as `_pre_gesture_state`; `_on_gesture_end()` pushes it to undo and refreshes `_stable_state`
- `_stable_state` design: PyQtGraph fires `sigRangeChanged` synchronously inside `setRange`/`showAxRect`, so capturing "current state" in `_on_range_changed` would already see the post-change position. Instead, `_stable_state` is updated after each gesture ends (idle period), so it always reflects the view before the gesture that triggered `range_changed`. This is especially important for the zoom rectangle, which makes a large one-shot X+Y change.
- History depth trimmed to `get_max_steps()` on every push

## CursorView

(`QObject`, lives inside `PlotArea.plot_item`):
- Two dashed `pg.InfiniteLine` items (hidden until activated); `apply_mode(mode, positions)` shows/hides and repositions them; hides delta-time line when leaving TWO mode
- `update_labels(active_signals, positions, mode)` — creates/repositions `pg.TextItem` value labels (signal color, `{value:.4g}` — no unit); prunes stale labels
- `update_delta_time(x1, x2, delta_t_str, y_pos, show, color)` — shows/hides the horizontal delta-time `InfiniteLine` and its `TextItem` label; if `y_pos` is `None` places at 10% from top of current view range; `_delta_label_x` stores last midpoint so the label follows line drags without a full refresh
- `remove_labels_for(active)` / `clear_labels()` — called on signal removal
- Nearest-cursor logic: `pg.SignalProxy` on `scene.sigMouseMoved` (30 fps) — in TWO mode, only the closer cursor's labels are shown
- `cursor_moved(index, x)` — `pyqtSignal` emitted on every cursor drag step
- `cursor_clicked(index)` — `pyqtSignal` emitted when a cursor line is clicked (sets active cursor for arrow-key stepping)
- `delta_line_moved(y)` — `pyqtSignal` emitted when the delta-time line is dragged (controller stores position)
- Off-screen chevron indicators: `_ChevronItem` (bold `pg.TextItem` subclass, clickable) — one per cursor plus one for the delta-time line, added to the main ViewBox; `_update_chevrons()` repositions them on every mode/position change and on `sigRangeChanged`; cursor chevrons show `<`/`>` at the left/right edge, delta chevron shows `^`/`v` at the top/bottom edge; two chevrons on the same side are stacked at ±7% of the Y span around centre
- `set_cursor_names(name0, name1)` — updates chevron tooltip text (called from controller on each refresh)
- `cursor_fetch_requested(index, x)` — `pyqtSignal(int, float)` emitted when a cursor chevron is clicked; `x` is the data-X coordinate of the click
- `delta_fetch_requested(y)` — `pyqtSignal(float)` emitted when the delta-time chevron is clicked; `y` is the data-Y coordinate of the click

## MainWindow

Public API:
- Constructor creates all five view widgets as public attrs: `signal_browser`, `plot_area`, `active_signals_table`, `measurement_info_box`, `signal_info_box`
- `set_controller(ctrl)` — wires browser, table remove/selection signals to controller, drop signals from plot_area and active_signals_table; all cursor and zoom actions (toggle, cursor1, cursor2, zoom_to_cursors, zoom_to_fit, zoom_y_to_view, swimlanes, undo, redo) call through `ctrl` proxy methods; calls `ctrl.set_cursor_mode_callback(self._on_cursor_mode_changed)` so the toolbar button reflects the active mode
- `set_recent_files_provider(callable)` — supplies a `() -> list[Path]` called on every `File` menu open; results are inserted between Load MDF separator and Preferences (section hidden when list is empty)
- `set_settings(settings)` — stores the `Settings` instance; required before Preferences dialog can open
- `trigger_startup_update_check()` — launches `_UpdateCheckThread` in the background; silently shows the update-available dialog if a newer version is found, silent on error or up-to-date
- `show_status(message, timeout_ms=3000)` — displays a transient message in the `QStatusBar`
- Layout: outer H-splitter → [SignalBrowser (260px) | center V-splitter | ActiveSignalsTable (260px)]; center → [PlotArea (3×) | bottom H-splitter → [MeasurementInfoBox | SignalInfoBox]]
- Menu: File → Load MDF… (Ctrl+O) / [recent files] / Preferences… / Exit (Ctrl+Q); Edit → Undo (Ctrl+Z) / Redo (Ctrl+Shift+Z); Help → Check for Update… / License / About
- Toolbar: Load File | Zoom to Fit (Ctrl+0) | Cursors (toggle) — all three use custom PNG icons from `resources/icons/`
- All load paths (dialog, recent files, file drop) catch `MdfLoadError` and show `QMessageBox.critical`
- `_on_add_signals(locations)` — called by browser `add_signals_requested`, plot `signals_dropped`, and table `signals_dropped`; loops over locations, counts duplicates (skipped silently), shows status bar message if any were skipped
- `_on_file_dropped(path)` — called by `plot_area.file_dropped`; shows `QMessageBox.question` if a file is already loaded, then calls `controller.load_file`
- `_on_check_for_update()` — manual update check: synchronous with wait cursor; shows update-available dialog or "up to date" dialog; error dialog on network failure
- `_UpdateCheckThread` — module-level `QThread` subclass; emits `update_available(tag, url)` signal if a newer version is found; exceptions are swallowed (startup-check use case)

## app.py

Constructs `MainWindow`, reads view attrs, builds `MdfLoader` + `Settings` + `AppController`, constructs `CursorView(plot_area.plot_item)` + `CursorController` (with `get_active_signals=lambda: controller.active_signals`), constructs `ZoomController(plot_area, get_active_signals=lambda: controller.active_signals, get_max_steps=lambda: settings.max_undo_steps)`, wires all together via `controller.set_cursor_controller(cursor_ctrl)`, `controller.set_zoom_controller(zoom_ctrl)`, and `window.set_controller(controller)`; calls `set_recent_files_provider(settings.get_and_prune)` and `window.set_settings(settings)`. License is loaded once here via `license_manager.load_stored()` and applied via `window.set_license(license_info, license_manager)`. After `window.show()`: calls `window.trigger_startup_update_check()` if `settings.check_for_updates` is `True`. If `sys.argv[1]` is a file path (e.g. via `.mf4` file association), loads it immediately after `window.show()`.

## MeasurementInfoBox

Uses a `QStackedWidget` — page 0 is a centred placeholder, page 1 is a `QScrollArea` + `QFormLayout`. `set_info` populates the form; `clear()` switches back. Optional fields omitted; MDF4 XML tags stripped by regex. `_clear_form`, `_add_row`, `_clean_text` shared via import from `measurement_info_box`.

## SignalInfoBox

Uses a `QTabWidget` with two tabs:
- **Info tab** — `QStackedWidget`: page 0 placeholder ("No signal selected." / "Multiple signals selected."), page 1 `QScrollArea` + `QFormLayout` with metadata rows (name, unit, data type, samples, raster, min, max, comment). `set_metadata(meta)` populates and shows the form; `show_multi_selection()` shows the multi-select placeholder; `clear()` shows "No signal selected." and disables the Properties tab. Raster row shown only when `sample_count ≥ 2`; displays the interval in ms (≤ 500 ms) or s (> 500 ms), or "variable" when `raster_s` is `None`.
- **Properties tab** (`_SignalPropertiesWidget`) — display mode `QComboBox` ("Line" / "Line & Marker" / "Marker Only") and marker shape `QComboBox` ("Circle" / "Square" / "Diamond" / "Cross"); shape combo disabled when mode is "Line". `setCurrentIndex(-1)` used for mismatched multi-select values. Signals: `display_mode_requested(str)`, `marker_shape_requested(str)` — forwarded to `SignalInfoBox` signals. `set_properties(mode | None, shape | None)` — populates dropdowns, blocks signals during update. `enable_properties(bool)` — enables/disables the Properties tab via `QTabWidget.setTabEnabled`.

## ActiveSignalsTable

Public API:
- `add_row(active)` / `remove_row(active)` / `clear()` — row management; identity-based lookup (`is`) avoids numpy `__eq__` ambiguity on `SignalData`
- `show_cursor_columns(bool)` — reveals/hides C1, C2, Δ columns (hidden by default)
- `set_cursor_column_headers(c3, c4)` — updates C1/C2 column header text (e.g. "Cursor L" / "Cursor R")
- `set_delta_column_header(text)` — updates Δ column header; set to `"Δt = X s"` in TWO mode, `"Δ"` otherwise
- `update_cursor_values(active, c1, c2, delta)` — fills cursor cells by row
- Selection: `ExtendedSelection` mode — Ctrl+click / Shift+click for multi-select; right-clicking a row already in the selection keeps the selection intact (`_ActiveTable` subclass overrides `mousePressEvent`)
- Signals: `selection_changed(object)` (single signal or `None`), `multi_selection_active(bool)` (True when >1 rows selected), `multi_selection_changed(list[ActiveSignal])` (emitted alongside `multi_selection_active(True)` with the full selection list), `remove_requested(list[ActiveSignal])`, `remove_all_requested()`, `color_change_requested(list[ActiveSignal], QColor)`, `step_mode_set_requested(list[ActiveSignal], bool)` (context menu), `signals_dropped(list)`, `order_changed(list[ActiveSignal])`
- Remove button, Del/Backspace key, and context menu "Remove Signal(s)" all remove the entire selection
- Color swatch click: applies to all selected signals when the clicked signal is in the selection; single-signal otherwise
- Context menu: "Remove Signal(s)", separator, "Enable Step Mode (for all)", "Disable Step Mode (for all)"
- `ColorSwatch` (from `view/widgets/`): flat `QPushButton` with styled background; click → `QColorDialog` → updates swatch + emits `color_change_requested`
- Row drag-and-drop reorder: selected block moves as a unit; `_apply_reorder` is deferred via `QTimer.singleShot(0)` so it runs after `startDrag()` returns; emits `order_changed` with the new `_signals` list
- Drop target: event filter on `_table.viewport()` accepts `application/x-mdf-viewer-signals` MIME data and emits `signals_dropped`

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
- Module-level constants `DEFAULT_CURSOR_COLOR_C1/C2/CL/CR`, `DEFAULT_DELTA_TIME_COLOR`, `DEFAULT_CURSOR_STEP_UNIT/SAMPLES/PIXELS/TIME_MS`, `DEFAULT_MAX_UNDO_STEPS` exported for use by `PreferencesDialog`
- Config path: `%APPDATA%\mdf-viewer\settings.json` (Windows) / `~/.config/mdf-viewer/settings.json` (Linux); detected via `sys.platform`; parent dirs created on first save
- Constructor accepts an optional `path` override (used in tests via `tmp_path`)

## PlotArea

Public API:
- `add_signal(active)` — creates `ViewBox` + `AxisItem('right')` + `PlotDataItem`; sets `active.curve` and `active.view_box`; respects `active.display_mode` and `active.marker_shape` at creation; no-op for duplicates; connects `vb.sigRangeChanged` AFTER `enableAutoRange()` so the initial auto-range is not captured as a zoom step
- `remove_signal(active)` — removes curve/ViewBox/axis from scene and layout; clears `active.curve` and `active.view_box`; no-op for unknowns
- `recolor_signal(active, color)` — updates curve pen, symbol colors, axis pen, axis text pen, and `active.color`; handles marker-only pen (NoPen) correctly; no-op for unknowns
- `set_step_mode(active, enabled)` — switches curve between linear and staircase (`pg.PlotDataItem(stepMode="left")`) rendering; no-op for unknowns
- `set_display_mode(active, mode, shape)` — switches between `"line"` / `"line_marker"` / `"marker"` rendering; updates curve pen and symbol (`_PG_SYMBOL` map: `circle→"o"`, `square→"s"`, `diamond→"d"`, `cross→"+"`); marker size from `_symbol_size(line_width)` = `max(6, width*4)`; no-op for unknowns
- `set_line_width(active, width)` — updates curve pen width and symbol size; no pen update in `"marker"` mode; no symbol size update in `"line"` mode; no-op for unknowns
- `set_line_style(active, style)` — updates curve pen style (`"solid"` / `"dashes"` / `"dots"` / `"dash-dot"`); no-op in `"marker"` mode or for unknowns
- `set_y_grid(active, enabled)` — shows or hides horizontal Y-grid lines on a signal's `ViewBox`; no-op for unknowns
- `zoom_to_fit()` — full X range from timestamps, auto Y per signal; no-op when empty
- `zoom_to_x_range(x_min, x_max)` — sets the shared X axis to the given range without touching Y axes; used by `AppController.zoom_to_cursors()`
- `get_zoom_state(active_signals) -> ZoomState` — snapshots current X range and each active signal's Y range; keyed by `ActiveSignal` identity
- `set_zoom_state(state, active_signals)` — restores X and per-signal Y ranges from a `ZoomState`; signals in `active_signals` but absent from state keep their current Y; removed signals are silently skipped
- `plot_item` — read-only property exposing the inner `pg.PlotItem` (used by `CursorView`)
- Signals: `y_grid_toggled(bool)`, `file_dropped(object)` (Path), `signals_dropped(list)`, `range_changed()` — emitted whenever the X or any signal Y range changes (used by `ZoomController` for gesture detection)
- Drop target: event filter on `_pw.viewport()` accepts MDF file URLs (`.mf4`/`.mdf`/`.dat`) and `application/x-mdf-viewer-signals` MIME data
- Private internals: `_ViewBox` subclass handles pan/zoom with a context menu (Y-grid toggle); `_SignalAxisItem` subclass formats integer tick labels without decimals; `_SignalPlotData` dataclass bundles the ViewBox + axis + curve per signal
