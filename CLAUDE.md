# MDF-Viewer – Project Context for Claude Code

## Project Overview

MDF-Viewer is a desktop application for visualizing ASAM MDF measurement data files (MDF3 and MDF4). It is a greenfield rewrite based on the author's prior experience with a working prototype. The goal is a clean, maintainable architecture from the start – the prototype suffered from tight coupling between data, UI, and plotting components.

The application is developed as a free, open-source project, targeting individual engineers and automotive measurement professionals.

**GitHub:** https://github.com/andalf-74/MDF-Viewer (public)

**Target platforms:** Windows, Linux  
**Language:** Python  
**Key libraries:** PyQt (UI), PyQtGraph (plotting), asammdf (MDF file I/O)

---

## Architecture Philosophy

Strict MVC separation is mandatory:

- **Model** – Pure data, no UI knowledge. Signal samples, timestamps, metadata.
- **View** – Pure UI, no business logic. Plots, widgets, dialogs.
- **Controller** – Coordinates between Model and View. Manages active signals, cursor state, selection state.

The prototype's core problem was that data classes, viewer, and plotter were too tightly coupled. This rewrite must not repeat that mistake. Every architectural decision should reinforce this separation.

### Signal Data Model

Three distinct signal classes have been identified from the prototype:

- **SignalData** – Raw timestamps and sample values. No UI knowledge whatsoever.
- **SignalMetadata** – Descriptive information about a signal: name, unit, min/max, sample count, comment, and any other MDF metadata fields.
- **ActiveSignal** – Represents a signal that has been added to the plot. Knows its curve object, ViewBox, and color. Bridge between Model and View.

---

## Project Structure

```
src/mdf_viewer/
    model/          # Pure data — no Qt/PyQtGraph imports
    view/           # Pure UI — no business logic
    view_model/     # ActiveSignal: bridges model data with plot objects
    controller/     # Coordinates model ↔ view
tests/
    model/
    view/
docs/
pyproject.toml      # src-layout, entry point mdf-viewer
requirements.txt / requirements-dev.txt
```

`.gitignore` covers Windows and macOS development environments.

---

## Application Layout

### Menu Bar
- **File**
  - Load MDF (opens file dialog)
  - Recently opened files (up to 4; shown between Load MDF and Preferences when non-empty)
  - Preferences… (opens Preferences dialog)
  - Exit
- **Help**
  - Check for Update… (fetches GitHub releases API; shows update dialog or "up to date" dialog)
  - License (Enter / View/Change)
  - About MDF-Viewer

### Toolbar
- **Load File** – folder icon, opens file dialog (Ctrl+O)
- **Zoom to Fit** – resets viewport to show all active signals fully (X: full time range, Y: auto-scaled per signal) (Ctrl+0 / F)
- **Zoom Y to View** – auto-scales Y axes for all signals within the current X span (Y)
- **Swimlanes** – arranges signals in non-overlapping horizontal swimlanes (B)
- **Zoom to Cursors** – zooms X axis to the span between the two cursors; enabled only in two-cursor mode (C)
- **Cursor Toggle** – cycles through: 1 cursor → 2 cursors → cursors hidden → (repeat)

Keyboard shortcuts for cursors: `.` toggles Cursor 1 (HIDDEN↔ONE, TWO→ONE), `,` toggles Cursor 2 (HIDDEN/ONE→TWO, TWO→HIDDEN).

### Main Layout

```
+-------------------------------+--------------------+------------------+
| ‹ (pin/collapse button)       |                    |                  |
| Signal Browser (TreeView)     |   Plot Area        | Active Signals   |
|                               |                    | Table            |
| Measurement Info Box          |                    | Signal Info Box  |
+-------------------------------+--------------------+------------------+
```

- **Left panel** (collapsible drawer) – vertical splitter:
  - **Top** – Signal Browser (TreeView showing full MDF channel hierarchy)
  - **Bottom** – Measurement Info Box
  - Pin button (‹/›) in the top-right corner collapses the panel to a hidden drawer that slides out on hover
- **Center** – Plot Area
- **Right panel** – vertical splitter:
  - **Top** – Active Signals Table
  - **Bottom** – Signal Info Box

---

## Signal Browser (Left Panel)

- TreeView reflecting the full channel group hierarchy of the loaded MDF file
- Signals can be added to the plot via:
  - Double-click on a signal node
  - Select (highlight) + click "Add Signal" button below the list
  - Drag one or more selected signals onto the Plot Area or Active Signals Table
- Multi-select: `ExtendedSelection` mode — Ctrl+click (individual), Shift+click (range); all three add paths emit all selected channels at once

---

## Active Signals Table (Right Panel)

A table with the following columns:

| # | Column | Description |
|---|--------|-------------|
| 1 | Color swatch | Small colored rectangle; clicking opens a color picker dialog and updates curve + Y-axis color |
| 2 | Signal name | Display name from MDF metadata |
| 3 | Cursor 1 value | Current value at Cursor 1 position (shown only when cursor is active) |
| 4 | Cursor 2 value | Current value at Cursor 2 position (shown only when cursor is active) |
| 5 | Delta | Difference between Cursor 2 and Cursor 1 values |

**Buttons below the table:**
- **Remove Signal** – removes highlighted signal from table and plot
- **Remove All** – removes all active signals (also accessible via menu)

Selection in this table drives the Signal Info Box content.

---

## Plot Area

- Shared X-axis (time) across all signals – pan and zoom on X affects all signals simultaneously
- Each active signal has its own Y-axis on the right side, colored to match the signal
- Individual Y-axis pan and zoom per signal
- PyQtGraph ViewBox per signal for independent Y scaling
- Accepts drag-and-drop: MDF files (loads file; prompts for confirmation if one is already open) and signals dragged from the Signal Browser

### Cursors
- Vertical line(s) draggable via drag & drop in the plot
- On first activation: placed at the start of the time range
- On subsequent toggles: hidden/shown at their last position (position is remembered)
- Value label at the intersection of cursor and signal curve:
  - Only shown on the cursor that is currently closer to the mouse pointer
  - Positioned close to the intersection point

---

## Info Boxes

### Measurement Info Box
Displays all available MDF file metadata:
- File name
- Author
- Date/time of recording
- MDF version
- Duration
- Comment
- Any other available metadata fields

### Signal Info Box
Displays metadata for the currently selected signal in the Active Signals Table:
- Signal name
- Unit
- Sample count
- Min value
- Max value
- Comment
- Any other available metadata fields

---

## File Handling

- **Single file only (MVP)** – loading a new file replaces the current one
- **Recently opened files** – up to 4 entries persisted in `settings.json`; shown in File menu; stale paths pruned silently on menu open; failed loads are not recorded
- **No session persistence (MVP)** – application always starts fresh; saving/restoring active signals, colors, and window state is planned for a future version
- **Robust error handling is mandatory** – the application must never crash on malformed, incomplete, or unexpected MDF content; errors must be caught and communicated to the user gracefully

---

## MDF Support

- MDF3 and MDF4 via the `asammdf` library
- All available channel groups and signals must be represented in the Signal Browser TreeView

### Known asammdf bug — `__del__` on corrupt files

When `asammdf.MDF(path)` fails to open a corrupt file, it raises an exception midway through `MDF4.__init__` before assigning `self._file`. Python's GC later calls `MDF4.__del__`, which calls `close()`, which unconditionally accesses `self._file` — triggering:

```
Exception ignored while calling deallocator <function MDF4.__del__ ...>:
AttributeError: 'MDF4' object has no attribute '_file'
```

This is printed to stderr but does **not** affect app behaviour — `MdfLoader.open()` correctly raises `MdfLoadError` and the error dialog is shown. **Do not chase this as our bug.** The fix belongs in asammdf's `close()` method (guard with `getattr(self, '_file', None)`). We have no clean way to suppress it from our side without redirecting stderr.

---

## Todo / Future Features (not MVP)

- Multi-file support with multiple X-axes and synchronization (by timestamp overlap, manual time offset, or signal-based alignment)
- Session persistence (active signals, colors, window layout)
- Additional toolbar and menu items (TBD)

---

## Development Workflow

### Reviewing Issues
When asked to look at / check / review the GitHub issues, always fetch and display them grouped by milestone so the current development priority is immediately visible.

### Grill-Me Skill
When the user says **"grill me"** about a feature or topic, Claude should enter interview mode: ask focused, one-at-a-time questions to surface requirements, edge cases, and design decisions before writing any code. Summarize findings before proceeding.

### General Rules
- **Always check the codebase first** – before making assumptions or proposing solutions, check whether the answer already exists in the codebase
- Always propose architecture and structure before writing code
- Ask clarifying questions when requirements are ambiguous
- Write tests alongside implementation, not after
- Prefer explicit, readable code over clever one-liners
- All user-facing strings should be in English (internationalization not in scope for MVP)
- Commit messages should be clear and descriptive

### Branching & Release Policy (#20)

**Lazy release-branch model** — chosen for low overhead given infrequent releases and a small team:

- **`main`** is the trunk. All bugfixes and features land here (directly or via PR), and each release is tagged `vX.Y` on `main`.
- A **`release/X.Y`** branch is created only when it's actually needed: you've started work on a feature for the *next* release on `main`, but still need to ship a bugfix to the *currently released* version (which must not receive that in-progress feature). Cut `release/X.Y` from the `vX.Y` tag at that point.
- Bugfixes to a released version go to its `release/X.Y` branch, get tagged `vX.Y.Z`, and must be cherry-picked forward to `main` so the fix isn't lost in the next release.
- If no feature work is in flight on `main` when a bugfix is needed, just commit the fix directly to `main` and re-tag/patch-release from there — no branch needed.

`master` was renamed to `main` as part of adopting this policy.

---

## Current Status

**As of 2026-06-25:** v2.0.1 released — 564 tests passing. Cursor Stuff work (#59, #62, #63, #25, #26, #29, #39) complete and merged to main; next release will be v2.1.1.

### Implemented

| Module | Description | Tests |
|--------|-------------|-------|
| `errors.py` | `MdfLoadError` — shared error type imported by model and view | — |
| `model/mdf_loader.py` | `MdfLoader` + `ChannelGroupInfo` | 31 |
| `model/signal_data.py` | `SignalData` dataclass | 2 |
| `model/interpolate.py` | `interpolate(active, x)` — shared linear interpolation helper used by `CursorController` and `CursorView` | — |
| `view/_mime.py` | Shared MIME type constant for signal drag-and-drop | — |
| `view/signal_browser.py` | `SignalBrowser` — TreeView, multi-select, Add Signal button, drag | 21 |
| `view/main_window.py` | `MainWindow` — splitter layout, menu, toolbar, status bar, wiring | 31 |
| `view/measurement_info_box.py` | `MeasurementInfoBox` — file metadata, QFormLayout + placeholder | 18 |
| `view/signal_info_box.py` | `SignalInfoBox` — signal metadata, QFormLayout + placeholder | 18 |
| `view/widgets/color_swatch.py` | `ColorSwatch` — flat `QPushButton` color indicator; reusable across views | — |
| `view/active_signals_table.py` | `ActiveSignalsTable` — color swatch, name, cursor cols, buttons, drop target | 32 |
| `view/plot_area.py` | `PlotArea` — PyQtGraph, shared X-axis, per-signal ViewBox + Y-axis, drop target, zoom state snapshot | 35 |
| `view/cursors.py` | `CursorView` — InfiniteLine items, value labels, nearest-cursor logic, delta-time line + label, off-screen chevron indicators | 43 |
| `view_model/active_signal.py` | `ActiveSignal` dataclass (model data + plot objects + color) | — |
| `view_model/zoom_state.py` | `ZoomState` dataclass — snapshot of X range + per-signal Y ranges | — |
| `controller/interfaces.py` | Protocol contracts for all controller-view dependencies | — |
| `controller/app_controller.py` | `AppController` — coordinates all layers | 39 |
| `controller/cursor_controller.py` | `CursorController` — toggle, position memory, interpolation, delta-time | 41 |
| `controller/zoom_controller.py` | `ZoomController` — zoom undo/redo, gesture coalescing, stable-state pre-capture | 27 |
| `settings.py` | `Settings` — JSON persistence for recent files + preferences | 36 |
| `update_checker.py` | `fetch_latest_release()`, `is_newer()`, `ReleaseInfo`, `UpdateCheckError` — GitHub releases API, no Qt | 13 |
| `license/license_info.py` | `LicenseInfo` dataclass, `Tier` enum, `FORMAT_VERSION`, embedded public key | — |
| `license/license_manager.py` | `LicenseManager` — verify, import, load_stored, export_license; `LicenseError` | 29 |
| `view/license_dialog.py` | `LicenseDialog` — import mode (browse/drop) + view mode (details + expiry notice + Retrieve License button); on successful import shows a "restart required" message and closes | — |
| `view/preferences_dialog.py` | `PreferencesDialog` — tabbed `QDialog`; General tab with "Check for updates on startup" checkbox and "Undo steps" spinbox (1–100); Cursors tab with mode, persistent, 4 cursor color swatches (C1/C2/CL/CR), Show ∆-Time checkbox + color swatch, arrow-key step (unit combobox + spinbox), reset button | 4 |
| `app.py` | MVC assembly point | — |

**`MdfLoader`** is the sole importer of `asammdf`. Public API:
- `open(path)` / `close()` / `is_open`
- `measurement_info()` → `MeasurementInfo`
- `channel_tree()` → `list[ChannelGroupInfo]`
- `load_signal(group_index, channel_index)` → `(SignalData, SignalMetadata)` — captures raw asammdf dtype before float64 conversion; sets `SignalMetadata.data_type` and `is_integer`; if float64 conversion fails (enum/string samples), retries with `raw=True` to get the underlying integer encoding; raises `MdfLoadError` only if raw values are also non-numeric

**`SignalBrowser`** public API:
- `populate(groups: list[ChannelGroupInfo])` — rebuilds the tree, groups expanded, filter cleared
- `clear()` — resets the tree and clears the filter
- `add_signals_requested(list[tuple[int,int]])` — PyQt signal emitted with all selected channel locations on double-click, Add Signal button click, or drag initiation
- Filter field: `QLineEdit` at the top; connected to a `QSortFilterProxyModel` with `setRecursiveFilteringEnabled(True)` (case-insensitive, partial match; groups visible when any child matches). `setClearButtonEnabled(True)` provides a built-in × button. `populate()` and `clear()` both reset the filter.
- Selection mode: `ExtendedSelection` — Ctrl+click and Shift+click select multiple channels; the Add Signal button emits all selected channels at once
- Drag: `_DragTreeView` subclass encodes selected `(group_index, channel_index)` pairs as JSON in `application/x-mdf-viewer-signals` MIME data; drop targets are `PlotArea` and `ActiveSignalsTable`

**`ActiveSignal`** fields: `data`, `metadata`, `color: QColor` (set by controller from palette); `curve` and `view_box` are `None` until `PlotArea.add_signal()` fills them in. `__hash__ = object.__hash__` and `__eq__ = object.__eq__` — identity semantics throughout to avoid numpy `__eq__` ambiguity (list `in` / `remove` also use `__eq__`).

**`AppController`** public API:
- `load_file(path)` — clears all state, opens file, populates browser + info box; resets color counter, cursor system, and zoom history; calls `settings.add_recent(path)` on success only; UI cleared before `open()` so state is clean on failure
- `add_signal(gi, ci) -> bool` — loads channel, assigns next palette color, notifies plot + table; calls `cursor_ctrl.refresh()` to recompute values for the new signal; returns `True` if added, `False` if already active (duplicate)
- `remove_signal(active)` — removes from plot/table/list; calls `cursor_ctrl.on_signal_removed` (label cleanup) then `cursor_ctrl.refresh()`; clears selection if that signal was selected
- `remove_all()` — calls `cursor_ctrl.on_all_signals_cleared()` (label cleanup), then removes all signals, clears table, clears selection
- `toggle_step_mode(active)` — flips `active.step_mode`; calls `PlotArea.set_step_mode()` to switch between linear and staircase rendering
- `recolor_signal(active, color)` — updates curve + axis color via `PlotArea.recolor_signal()` and cursor labels via `cursor_ctrl.recolor_signal()`
- `reorder_signals(ordered)` — updates `_active` list order to match new table row order; calls `cursor_ctrl.refresh()`; connected to `ActiveSignalsTable.order_changed`
- `on_y_grid_toggled(enabled)` — tracks Y-grid state; turns grid off on the previously selected signal and on for the newly selected one; connected to `PlotArea.y_grid_toggled`
- `set_selected_signal(active | None)` — drives the Signal Info Box; also manages per-signal Y-grid when `_y_grid_enabled`
- `refresh_cursors()` — calls `cursor_ctrl.refresh()`; used by `PreferencesDialog` after cursor preference changes
- `set_cursor_controller(cc)` — optional; wired from `app.py` after construction
- `set_zoom_controller(zc)` — optional; wired from `app.py` after construction
- Cursor proxy methods: `toggle_cursor()`, `press_cursor1()`, `press_cursor2()`, `press_left()`, `press_right()`, `zoom_to_cursors() -> bool`, `set_cursor_mode_callback(cb)` — all delegate to `_cursor_ctrl`, guarded by `None` check; `zoom_to_cursors()` now applies the zoom internally and returns `True` if applied (was: returned the span tuple)
- Zoom proxy methods: `zoom_to_fit()`, `zoom_y_to_view() -> bool`, `swimlanes() -> bool` — each calls `zoom_ctrl.before/after_discrete_action()` around the `PlotArea` call so the action is recorded as a single undo step
- Undo/redo proxies: `undo()`, `redo()` — delegate to `_zoom_ctrl`, guarded by `None` check
- Constructor accepts optional `settings: Settings` — omitting it disables recent-file tracking without any other effect
- `active_signals` / `selected_signal` / `is_file_loaded` — read-only state accessors

**`CursorController`** public API:
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

**`ZoomController`** (`controller/zoom_controller.py`):
- Constructor: `(plot_area, get_active_signals, get_max_steps, _timer=None)` — `_timer` is injectable for testing (avoids requiring QApplication in unit tests); connects to `plot_area.range_changed`
- `before_discrete_action()` / `after_discrete_action()` — bracket toolbar zoom calls; `before` captures the current state onto the undo stack and sets `_ignore_range_changed`; `after` clears the flag and refreshes `_stable_state`
- `undo()` / `redo()` — restore/re-apply zoom state; each saves the current state to the opposite stack and refreshes `_stable_state`
- `clear()` — empties both stacks, resets `_stable_state` to `None`; called by `AppController.load_file()`
- `can_undo` / `can_redo` — bool properties
- Gesture coalescing: `PlotArea.range_changed` fires on every pan/scroll step; `ZoomController` uses a 300 ms debounce timer — `_on_range_changed()` marks gesture start and records the `_stable_state` as `_pre_gesture_state`; `_on_gesture_end()` pushes it to undo and refreshes `_stable_state`
- `_stable_state` design: PyQtGraph fires `sigRangeChanged` synchronously inside `setRange`/`showAxRect`, so capturing "current state" in `_on_range_changed` would already see the post-change position. Instead, `_stable_state` is updated after each gesture ends (idle period), so it always reflects the view before the gesture that triggered `range_changed`. This is especially important for the zoom rectangle, which makes a large one-shot X+Y change.
- History depth trimmed to `get_max_steps()` on every push

**`CursorView`** (`QObject`, lives inside `PlotArea.plot_item`):
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

**`MainWindow`** public API:
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

**`app.py`**: constructs `MainWindow`, reads view attrs, builds `MdfLoader` + `Settings` + `AppController`, constructs `CursorView(plot_area.plot_item)` + `CursorController` (with `get_active_signals=lambda: controller.active_signals`), constructs `ZoomController(plot_area, get_active_signals=lambda: controller.active_signals, get_max_steps=lambda: settings.max_undo_steps)`, wires all together via `controller.set_cursor_controller(cursor_ctrl)`, `controller.set_zoom_controller(zoom_ctrl)`, and `window.set_controller(controller)`; calls `set_recent_files_provider(settings.get_and_prune)` and `window.set_settings(settings)`. License is loaded once here via `license_manager.load_stored()` and applied via `window.set_license(license_info, license_manager)`. After `window.show()`: calls `window.trigger_startup_update_check()` if `settings.check_for_updates` is `True`. If `sys.argv[1]` is a file path (e.g. via `.mf4` file association), loads it immediately after `window.show()`.

**`MeasurementInfoBox`** / **`SignalInfoBox`**: both use a `QStackedWidget` — page 0 is a centred placeholder label, page 1 is a `QScrollArea` + `QFormLayout`. `set_info` / `set_metadata` populates the form and switches to page 1; `clear()` switches back. Optional fields (empty string / `None`) are omitted. MDF4 XML tags in comment fields are stripped by regex. `_clear_form`, `_add_row`, `_clean_text` shared via import from `measurement_info_box`. `SignalInfoBox` shows a "Data type" row (e.g. `uint8`, `float64`) when `SignalMetadata.data_type` is populated.

**`ActiveSignalsTable`** public API:
- `add_row(active)` / `remove_row(active)` / `clear()` — row management; identity-based lookup (`is`) avoids numpy `__eq__` ambiguity on `SignalData`
- `show_cursor_columns(bool)` — reveals/hides C1, C2, Δ columns (hidden by default)
- `set_cursor_column_headers(c3, c4)` — updates C1/C2 column header text (e.g. "Cursor L" / "Cursor R")
- `set_delta_column_header(text)` — updates Δ column header; set to `"Δt = X s"` in TWO mode, `"Δ"` otherwise
- `update_cursor_values(active, c1, c2, delta)` — fills cursor cells by row
- Signals: `selection_changed(object)`, `remove_requested(object)`, `remove_all_requested()`, `color_change_requested(object, QColor)`, `signals_dropped(list)`, `step_mode_toggle_requested(object)` (right-click context menu), `order_changed(list[ActiveSignal])` (emitted after row drag-and-drop reorder with the full new signal order)
- `ColorSwatch` (from `view/widgets/`): flat `QPushButton` with styled background; click → `QColorDialog` → updates swatch + emits `color_change_requested`
- Row drag-and-drop reorder: drag initiated inside the table moves a row; `_apply_reorder` is deferred via `QTimer.singleShot(0)` so it runs after `startDrag()` returns; emits `order_changed` with the new `_signals` list
- Uses `selectionModel().selectedRows()` (not `currentRow()`) so `clearSelection()` correctly emits `None`
- Drop target: event filter on `_table.viewport()` accepts `application/x-mdf-viewer-signals` MIME data and emits `signals_dropped`

**`Settings`** (`src/mdf_viewer/settings.py`):
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

**`PlotArea`** public API:
- `add_signal(active)` — creates `ViewBox` + `AxisItem('right')` + `PlotDataItem`; sets `active.curve` and `active.view_box`; no-op for duplicates; connects `vb.sigRangeChanged` AFTER `enableAutoRange()` so the initial auto-range is not captured as a zoom step
- `remove_signal(active)` — removes curve/ViewBox/axis from scene and layout; clears `active.curve` and `active.view_box`; no-op for unknowns
- `recolor_signal(active, color)` — updates curve pen, axis pen, axis text pen, and `active.color`; no-op for unknowns
- `set_step_mode(active, enabled)` — switches curve between linear and staircase (`pg.PlotDataItem(stepMode="right")`) rendering; no-op for unknowns
- `set_y_grid(active, enabled)` — shows or hides horizontal Y-grid lines on a signal's `ViewBox`; no-op for unknowns
- `zoom_to_fit()` — full X range from timestamps, auto Y per signal; no-op when empty
- `zoom_to_x_range(x_min, x_max)` — sets the shared X axis to the given range without touching Y axes; used by `AppController.zoom_to_cursors()`
- `get_zoom_state(active_signals) -> ZoomState` — snapshots current X range and each active signal's Y range; keyed by `ActiveSignal` identity
- `set_zoom_state(state, active_signals)` — restores X and per-signal Y ranges from a `ZoomState`; signals in `active_signals` but absent from state keep their current Y; removed signals are silently skipped
- `plot_item` — read-only property exposing the inner `pg.PlotItem` (used by `CursorView`)
- Signals: `y_grid_toggled(bool)`, `file_dropped(object)` (Path), `signals_dropped(list)`, `range_changed()` — emitted whenever the X or any signal Y range changes (used by `ZoomController` for gesture detection)
- Drop target: event filter on `_pw.viewport()` accepts MDF file URLs (`.mf4`/`.mdf`/`.dat`) and `application/x-mdf-viewer-signals` MIME data
- Private internals: `_ViewBox` subclass handles pan/zoom with a context menu (Y-grid toggle); `_SignalAxisItem` subclass formats integer tick labels without decimals; `_SignalPlotData` dataclass bundles the ViewBox + axis + curve per signal

### Decisions made
See [`docs/architecture.md`](docs/architecture.md) — decision log is maintained there, grouped by topic.

### Release build

| File | Purpose |
|------|---------|
| `installer/mdf_viewer.spec` | PyInstaller spec — one-folder Windows bundle |
| `installer/mdf_viewer.iss` | Inno Setup 6 script — per-user installer with optional file associations |

**To build:**
1. `pyinstaller installer/mdf_viewer.spec --distpath dist --workpath dist/_build -y` → produces `dist/MDF-Viewer/`
2. `"C:/Program Files (x86)/Inno Setup 6/ISCC.exe" installer/mdf_viewer.iss` → produces `installer/dist/MDF-Viewer-X.Y-Setup.exe`
3. `Compress-Archive -Path dist\MDF-Viewer -DestinationPath dist\MDF-Viewer-X.Y-Windows.zip -Force` → portable zip
4. Upload both to the GitHub release: `gh release upload vX.Y installer/dist/MDF-Viewer-X.Y-Setup.exe dist/MDF-Viewer-X.Y-Windows.zip`

`dist/` is in `.gitignore`; build artifacts are never committed. The `.spec` and `.iss` files are committed under `installer/`.

**Latest release — v2.0:** https://github.com/andalf-74/MDF-Viewer/releases/tag/v2.0 — ships `MDF-Viewer-2.0-Setup.exe` (installer) and `MDF-Viewer-2.0-Windows.zip` (portable).

### Environment
- `.venv` exists with deps installed (`pip install -e ".[dev]"`). Python 3.14.5. asammdf resolved to 8.x.
- Activate with `.venv\Scripts\activate`, then `pytest` (564 passing) and `python -m mdf_viewer` both work.
- `cryptography` must be installed separately on macOS: `.venv/bin/pip install cryptography`

### Changelog
Notable changes are tracked in `CHANGELOG.md` (Keep a Changelog style). Update it alongside `CLAUDE.md` when shipping a fix or feature.

### Next steps
Cursor Stuff features are merged to main; version stays at 2.0.1 until a release build can be produced (requires Windows). Next milestone is v2.1.1 — keep adding features to main.

### Security — secrets that must never be committed

The Ed25519 private key and `generate_license.py` are saved at `C:\Users\andal\Documents\mdf-viewer-private\` — **never commit either to any repo**. `.gitignore` blocks `generate_license.py`, `*.lic`, and `*.pem`. See `docs/architecture.md` for full license system design decisions.
