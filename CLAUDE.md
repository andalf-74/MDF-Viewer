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
  - Recently opened files (up to 4; shown between Load MDF and Exit when non-empty)
  - Exit

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

**As of 2026-06-20:** v1.5 released — 426 tests passing. Arch cleanup for v2.0 complete (issues #46–#52).

### Implemented

| Module | Description | Tests |
|--------|-------------|-------|
| `errors.py` | `MdfLoadError` — shared error type imported by model and view | — |
| `model/mdf_loader.py` | `MdfLoader` + `ChannelGroupInfo` | 31 |
| `model/signal_data.py` | `SignalData` dataclass | 2 |
| `view/_mime.py` | Shared MIME type constant for signal drag-and-drop | — |
| `view/signal_browser.py` | `SignalBrowser` — TreeView, multi-select, Add Signal button, drag | 21 |
| `view/main_window.py` | `MainWindow` — splitter layout, menu, toolbar, status bar, wiring | 32 |
| `view/measurement_info_box.py` | `MeasurementInfoBox` — file metadata, QFormLayout + placeholder | 18 |
| `view/signal_info_box.py` | `SignalInfoBox` — signal metadata, QFormLayout + placeholder | 18 |
| `view/active_signals_table.py` | `ActiveSignalsTable` — color swatch, name, cursor cols, buttons, drop target | 32 |
| `view/plot_area.py` | `PlotArea` — PyQtGraph, shared X-axis, per-signal ViewBox + Y-axis, drop target | 35 |
| `view/cursors.py` | `CursorView` — InfiniteLine items, value labels, nearest-cursor logic | 18 |
| `view_model/active_signal.py` | `ActiveSignal` dataclass (model data + plot objects + color) | — |
| `controller/interfaces.py` | Protocol contracts for all controller-view dependencies | — |
| `controller/app_controller.py` | `AppController` — coordinates all layers | 39 |
| `controller/cursor_controller.py` | `CursorController` — toggle, position memory, interpolation | 28 |
| `settings.py` | `Settings` — JSON persistence for recent files | 12 |
| `license/license_info.py` | `LicenseInfo` dataclass, `Tier` enum, `FORMAT_VERSION`, embedded public key | — |
| `license/license_manager.py` | `LicenseManager` — verify, import, load_stored; `LicenseError` | 26 |
| `view/license_dialog.py` | `LicenseDialog` — import mode (browse/drop) + view mode (details + expiry notice); on successful import shows a "restart required" message and closes | — |
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
- `load_file(path)` — clears all state, opens file, populates browser + info box; resets color counter and cursor system; calls `settings.add_recent(path)` on success only; UI cleared before `open()` so state is clean on failure
- `add_signal(gi, ci) -> bool` — loads channel, assigns next palette color, notifies plot + table; calls `cursor_ctrl.refresh()` to recompute values for the new signal; returns `True` if added, `False` if already active (duplicate)
- `remove_signal(active)` — removes from plot/table/list; calls `cursor_ctrl.on_signal_removed` (label cleanup) then `cursor_ctrl.refresh()`; clears selection if that signal was selected
- `remove_all()` — calls `cursor_ctrl.on_all_signals_cleared()` (label cleanup), then removes all signals, clears table, clears selection
- `set_selected_signal(active | None)` — drives the Signal Info Box
- `set_cursor_controller(cc)` — optional; wired from `app.py` after construction
- Cursor proxy methods (so `MainWindow` has a single controller contact point): `toggle_cursor()`, `press_cursor1()`, `press_cursor2()`, `zoom_to_cursors() -> tuple[float,float] | None`, `set_cursor_mode_callback(cb)` — all delegate to `_cursor_ctrl`, guarded by `None` check
- Constructor accepts optional `settings: Settings` — omitting it disables recent-file tracking without any other effect
- `active_signals` / `selected_signal` / `is_file_loaded` — read-only state accessors

**`CursorController`** public API:
- Constructor: `(cursor_view, get_x_range, active_signals_table, get_active_signals=None)` — active signal list is read on demand via `get_active_signals` callable (avoids a second authoritative list); `app.py` passes `lambda: controller.active_signals`
- `toggle()` — HIDDEN → ONE → TWO → HIDDEN; on first activation places cursors at plot X range start + 10% span; subsequent toggles use remembered positions
- `press_cursor1()` / `press_cursor2()` — direct single-cursor activation (dot / comma keys)
- `zoom_to_cursors() -> tuple[float,float] | None` — returns the span between the two cursors in TWO mode; None otherwise
- `reset()` — called by `AppController.load_file()`; hides cursors and marks positions for re-initialisation on next activation
- `refresh()` — called by `AppController` after any change to the active signal list; re-computes values and updates labels
- `on_signal_removed(active)` / `on_all_signals_cleared()` — label cleanup only; must be called before `PlotArea.remove_signal()` so the ViewBox is still in the scene
- `set_mode_changed_callback(cb)` — registers a callable invoked with the new `CursorMode` on every toggle
- `recolor_signal(active, color)` — delegates to `CursorView.recolor_labels()`
- Drives `ActiveSignalsTable.update_cursor_values()` and `CursorView.update_labels()` on every drag and toggle

**`CursorView`** (`QObject`, lives inside `PlotArea.plot_item`):
- Two dashed-yellow `pg.InfiniteLine` items (hidden until activated); `apply_mode(mode, positions)` shows/hides and repositions them
- `update_labels(active_signals, positions, mode)` — creates/repositions `pg.TextItem` value labels (signal color, `{value:.4g}` — no unit); prunes stale labels
- `remove_labels_for(active)` / `clear_labels()` — called on signal removal
- Nearest-cursor logic: `pg.SignalProxy` on `scene.sigMouseMoved` (30 fps) — in TWO mode, only the closer cursor's labels are shown
- `cursor_moved(index, x)` — `pyqtSignal` emitted on every drag step

**`MainWindow`** public API:
- Constructor creates all five view widgets as public attrs: `signal_browser`, `plot_area`, `active_signals_table`, `measurement_info_box`, `signal_info_box`
- `set_controller(ctrl)` — wires browser, table remove/selection signals to controller, drop signals from plot_area and active_signals_table; all cursor actions (toggle, cursor1, cursor2, zoom_to_cursors) call through `ctrl` proxy methods; calls `ctrl.set_cursor_mode_callback(self._on_cursor_mode_changed)` so the toolbar button reflects the active mode
- `set_recent_files_provider(callable)` — supplies a `() -> list[Path]` called on every `File` menu open; results are inserted between Load MDF and Exit (section hidden when list is empty)
- `show_status(message, timeout_ms=3000)` — displays a transient message in the `QStatusBar`
- Layout: outer H-splitter → [SignalBrowser (260px) | center V-splitter | ActiveSignalsTable (260px)]; center → [PlotArea (3×) | bottom H-splitter → [MeasurementInfoBox | SignalInfoBox]]
- Menu: File → Load MDF… (Ctrl+O) / [recent files] / Exit (Ctrl+Q)
- Toolbar: Load File | Zoom to Fit (Ctrl+0) | Cursors (toggle) — all three use custom PNG icons from `resources/icons/`
- All load paths (dialog, recent files, file drop) catch `MdfLoadError` and show `QMessageBox.critical`
- `_on_add_signals(locations)` — called by browser `add_signals_requested`, plot `signals_dropped`, and table `signals_dropped`; loops over locations, counts duplicates (skipped silently), shows status bar message if any were skipped
- `_on_file_dropped(path)` — called by `plot_area.file_dropped`; shows `QMessageBox.question` if a file is already loaded, then calls `controller.load_file`

**`app.py`**: constructs `MainWindow`, reads view attrs, builds `MdfLoader` + `Settings` + `AppController`, constructs `CursorView(plot_area.plot_item)` + `CursorController` (with `get_active_signals=lambda: controller.active_signals`), wires all together via `controller.set_cursor_controller(cursor_ctrl)` and `window.set_controller(controller)`; calls `set_recent_files_provider(settings.get_and_prune)`. License is loaded once here via `license_manager.load_stored()` and applied via `window.set_license(license_info, license_manager)`. If `sys.argv[1]` is a file path (e.g. via `.mf4` file association), loads it immediately after `window.show()`.

**`MeasurementInfoBox`** / **`SignalInfoBox`**: both use a `QStackedWidget` — page 0 is a centred placeholder label, page 1 is a `QScrollArea` + `QFormLayout`. `set_info` / `set_metadata` populates the form and switches to page 1; `clear()` switches back. Optional fields (empty string / `None`) are omitted. MDF4 XML tags in comment fields are stripped by regex. `_clear_form`, `_add_row`, `_clean_text` shared via import from `measurement_info_box`. `SignalInfoBox` shows a "Data type" row (e.g. `uint8`, `float64`) when `SignalMetadata.data_type` is populated.

**`ActiveSignalsTable`** public API:
- `add_row(active)` / `remove_row(active)` / `clear()` — row management; identity-based lookup (`is`) avoids numpy `__eq__` ambiguity on `SignalData`
- `show_cursor_columns(bool)` — reveals/hides C1, C2, Δ columns (hidden by default)
- `update_cursor_values(active, c1, c2, delta)` — fills cursor cells by row
- Signals: `selection_changed(object)`, `remove_requested(object)`, `remove_all_requested()`, `color_change_requested(object, QColor)`, `signals_dropped(list)`
- `_ColorSwatch`: flat `QPushButton` with styled background; click → `QColorDialog` → updates swatch + emits `color_change_requested`
- Uses `selectionModel().selectedRows()` (not `currentRow()`) so `clearSelection()` correctly emits `None`
- Drop target: event filter on `_table.viewport()` accepts `application/x-mdf-viewer-signals` MIME data and emits `signals_dropped`

**`Settings`** (`src/mdf_viewer/settings.py`):
- `add_recent(path)` — resolves to absolute path, prepends, deduplicates, trims to `MAX_RECENT=4`, saves immediately
- `recent_files() -> list[Path]` — raw list (may include missing paths)
- `get_and_prune() -> list[Path]` — filters to existing paths, saves if anything was removed; used as the `MainWindow` recent-files provider
- Config path: `%APPDATA%\mdf-viewer\settings.json` (Windows) / `~/.config/mdf-viewer/settings.json` (Linux); detected via `sys.platform`; parent dirs created on first save
- Constructor accepts an optional `path` override (used in tests via `tmp_path`)

### Decisions made
- **Qt binding:** PyQt6, licensed GPL-3.0-only by Riverbank (not LGPL — that was an earlier misconception); PyQtGraph supports it.
- **Project license (1.x):** GPL-3.0-only (`LICENSE`, `pyproject.toml`), required by PyQt6's own GPL terms for the combined work and consistent with "free, open-source." Replaces the earlier `Proprietary` placeholder.
- **`ActiveSignal` location:** `src/mdf_viewer/view_model/` (not `model/`), to keep the data layer free of Qt/PyQtGraph imports. Layer rules are documented in `docs/architecture.md`.
- **Build:** `pyproject.toml` (src-layout, entry point `mdf-viewer`) + `requirements.txt` / `requirements-dev.txt`.
- **MDF4 `header.author`** does not round-trip via asammdf (stored in XML comment block). The `MeasurementInfo.extra` dict is available for raw fields if needed later.
- **Signal color palette:** 8-color cycling tuple defined in `app_controller.py`; resets on `load_file()`.
- **View imports in controller:** `TYPE_CHECKING`-only — no runtime view imports; all views are injected.
- **MVC assembly:** `MainWindow` creates view widgets; `app.py` reads them to construct `AppController`; `set_controller` completes the wiring. No layer constructs another's object graph.
- **Identity-based row lookup in `ActiveSignalsTable`:** `ActiveSignal` is a mutable dataclass with numpy-array fields; `__eq__` raises `ValueError` on boolean coercion. All lookups use `is` via `_find_row()`.
- **`PlotArea` multi-axis pattern:** `pi.vb` (main ViewBox) is the X-axis host only — no curves added to it. Each signal gets its own `ViewBox` with `setXLink(pi)` for shared X, and a `AxisItem('right')` placed at the next layout column. `pi.vb.sigResized` → `_update_view_geometries()` keeps extra ViewBoxes geometrically aligned.
- **`PlotArea` zoom_to_fit:** computes X bounds from `active.data.timestamps` across all signals, calls `pi.vb.setXRange` (propagates via XLink), then `vb.autoRange()` per signal for independent Y reset.

**`PlotArea`** public API:
- `add_signal(active)` — creates `ViewBox` + `AxisItem('right')` + `PlotDataItem`; sets `active.curve` and `active.view_box`; no-op for duplicates
- `remove_signal(active)` — removes curve/ViewBox/axis from scene and layout; clears `active.curve` and `active.view_box`; no-op for unknowns
- `recolor_signal(active, color)` — updates curve pen, axis pen, axis text pen, and `active.color`; no-op for unknowns
- `zoom_to_fit()` — full X range from timestamps, auto Y per signal; no-op when empty
- `plot_item` — read-only property exposing the inner `pg.PlotItem` (used by `CursorView`)
- Signals: `y_grid_toggled(bool)`, `file_dropped(object)` (Path), `signals_dropped(list)`
- Drop target: event filter on `_pw.viewport()` accepts MDF file URLs (`.mf4`/`.mdf`/`.dat`) and `application/x-mdf-viewer-signals` MIME data

### Decisions made (continued)
- **`CursorController` wiring:** optional dependency injected via `AppController.set_cursor_controller()`; all notify calls are guarded by `None` check so the cursor system can be omitted without touching `AppController`.
- **CursorView lifetime:** `CursorView` is a `QObject` that holds references to PyQtGraph items added to `PlotArea.plot_item`. It is constructed in `app.py` after `MainWindow` so the PlotItem scene already exists. Tests keep the parent `PlotWidget` alive via a separate pytest fixture to prevent C++ object deletion.
- **Nearest-cursor label logic:** uses identity-based label keys `(cursor_index, active)` to avoid numpy `__eq__` ambiguity (same pitfall as `ActiveSignalsTable._find_row`).
- **Cursor label Y-tracking:** labels are added to the signal's own `ViewBox` (not the main PlotItem) so `setPos(x, y)` is in the signal's Y coordinate space and the label tracks Y pan/zoom automatically. `_labels` stores `(TextItem, ViewBox)` tuples. Cursor cleanup (`on_signal_removed`, `on_all_signals_cleared`) is called in `AppController` *before* `plot_area.remove_signal` so the ViewBox is still in the scene when `vb.removeItem(lbl)` runs.
- **Cursor labels show value only:** no unit suffix — the unit is already on the Y-axis and in the Signal Info Box.
- **`SignalMetadata.data_type` / `is_integer`:** `MdfLoader.load_signal` captures the raw asammdf dtype before the mandatory float64 conversion. `is_integer` is used by `PlotArea._SignalAxisItem` to suppress fractional ticks on discrete/integer signals (gear, enum, flag). `data_type` (e.g. `"uint8"`) is displayed in `SignalInfoBox`.
- **`ActiveSignal.__eq__ = object.__eq__`:** list `in` and `remove` also use `__eq__`, which the dataclass version raises on numpy arrays. Identity equality is set alongside `__hash__` so both dict and list operations are consistent.
- **Duplicate signal prevention:** `AppController.add_signal` checks `(group_index, channel_index)` against active signals' metadata before loading; returns `False` on duplicates (callers use the return value to count skips for the status bar message).
- **Y-axis tick formatting:** `_SignalAxisItem` subclasses `pg.AxisItem`; float signals use `:.6g` (strips floating-point noise like "256.000000007"); integer signals snap ticks to integer positions and format as plain integers.
- **Recent files persistence:** plain JSON (no `QSettings`/registry) for transparency and portability; platform path via `sys.platform` with no extra dependency; written immediately on successful load so a crash doesn't lose the entry; failed loads are never recorded; stale entries pruned silently when the File menu opens.
- **Recent files menu wiring:** `MainWindow` takes a provider callable (`settings.get_and_prune`) rather than a direct `Settings` reference, keeping the view layer free of settings knowledge; `File.aboutToShow` triggers the rebuild so the list is always fresh.
- **Enum/string signal fallback:** `load_signal` retries with `raw=True` when physical values are non-numeric byte strings (common for CAN enum signals like gear position or state flags); raw integer encoding is numeric and plots correctly with the existing integer-tick axis.
- **Toolbar icons:** custom PNGs in `src/mdf_viewer/resources/icons/`; 32×32 px 1× and 64×64 px `@2x` HiDPI variants loaded via `QIcon.addFile()`; `_load_icon(name)` helper in `main_window.py` wires both sizes into one `QIcon`.
- **Theme-aware toolbar icons:** each icon (`folder`, `zoom_to_fit`, `cursors`) has a light-gray variant (for dark backgrounds) and a dark-gray `_light` variant (for light backgrounds). `_icon_suffix()` reads `QApplication.styleHints().colorScheme()` once at startup — `Qt.ColorScheme.Dark` → unsuffixed (light-gray) icons, `Light` or `Unknown` → `_light` (dark-gray) icons, since light mode is the more common default. Detected once; no live theme-change handling (#out of scope for now).
- **Application icon:** `src/mdf_viewer/resources/icons/app_icon.ico`; set via `MainWindow.setWindowIcon()`, baked into the EXE via `icon=` in `mdf_viewer.spec`, and used as the installer icon via `SetupIconFile` in `mdf_viewer.iss`.
- **Windows taskbar icon (unfrozen run):** `app.py` calls `ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("mdf-viewer.mdf-viewer")` on `sys.platform == "win32"` before creating the `QApplication`. Without an explicit AppUserModelID, Windows shows `python.exe`'s icon in the taskbar instead of `MainWindow`'s icon when run via the debugger/`python -m mdf_viewer`. Not needed for the PyInstaller build (the EXE has its own icon resource).
- **Splash screen:** `app.py` builds a `QSplashScreen` pixmap (`_build_splash_pixmap()`) from `app_icon.ico` plus "MDF-Viewer" and "Version {`mdf_viewer.__version__`}" text, shown immediately after `QApplication` construction (before the heavier view/controller imports) and closed via `splash.finish(window)` once `MainWindow` is shown. No minimum display time — on fast machines it may barely be visible, which is fine. Not unit-tested (consistent with the rest of `app.py`, which is untested bootstrap/glue code).
- **`__version__`:** defined in `src/mdf_viewer/__init__.py`, used by the splash screen and the About dialog. Kept in sync with `pyproject.toml`'s `version` (and the installer `.iss`) manually as part of the release process — not derived via `importlib.metadata` because editable installs cache a stale version at install time.
- **Help > About:** `MainWindow` has a `Help` menu with an "About MDF-Viewer" action (`_about_action` / `_on_about`) that calls `QMessageBox.about()` with the version, a one-line description, author, and a link to the GitHub repo (`_GITHUB_URL`).
- **Drag-and-drop MIME type:** `application/x-mdf-viewer-signals` (defined in `view/_mime.py`); payload is a JSON-encoded list of `[group_index, channel_index]` pairs. Event filters installed on `_pw.viewport()` (PlotArea) and `_table.viewport()` (ActiveSignalsTable) handle DragEnter/DragMove/Drop without subclassing PyQtGraph or QTableWidget.
- **File drop confirmation:** `MainWindow._on_file_dropped` checks `controller.is_file_loaded` (delegated to `loader.is_open`) before replacing an open file; uses `QMessageBox.question` so the user can cancel.
- **Status bar skip notification:** `MainWindow._on_add_signals` counts duplicates via `add_signal`'s `bool` return value and calls `show_status` with a singular/plural message ("1 signal already active, skipped." / "N signals already active, skipped.").
- **Curve downsampling:** each `PlotDataItem` in `PlotArea.add_signal` has `setClipToView(True)` and `setDownsampling(auto=True, method="peak")`. The curve is constructed without data, added to its `ViewBox` via `vb.addItem(curve)`, and only then given data via `curve.setData(...)` — calling `setData` before the curve has a parent `ViewBox` made pyqtgraph fall back to the `PlotWidget` for `getViewBox()`, which raised `AttributeError: autoRangeEnabled` once downsampling was enabled.
- **`tools/profile_plot.py`:** permanent ad-hoc profiling script (loads `data/test.mf4`, adds 6 high-sample-count signals, simulates pan/zoom and cursor drag under `cProfile`). Run with `python tools/profile_plot.py` from the repo root.
- **`ActiveSignalsTable.remove_row` / `clear` ordering:** the table widget is mutated first (`removeRow` / `setRowCount(0)`), then `_signals` — `removeRow`/`setRowCount(0)` can synchronously emit `itemSelectionChanged` before returning, and the handler indexes into `_signals`. Mutating `_signals` first left it shorter than the row indices Qt reported, raising `IndexError`. `_on_selection_changed` also has a bounds check as a defensive fallback.
- **Signal Browser filter debounce (#9):** `_filter_edit.textChanged` no longer calls `setFilterFixedString` directly; it (re)starts a single-shot `QTimer` (`_FILTER_DELAY_MS = 250`), and `_apply_filter()` runs on timeout. Recursive filtering over a large channel tree is expensive, so re-filtering on every keystroke made typing feel sluggish. `populate()`/`clear()` use `_clear_filter()`, which stops the timer and applies the empty filter immediately so the new tree isn't shown through a stale filter.
- **Load busy feedback (#9):** `MainWindow._load_file()` is the single entry point for all three load paths (Load MDF…, recent files, file drop). It sets a wait cursor and a persistent "Loading <file>…" status message for the duration of `controller.load_file()`, restoring both in a `finally` block.
- **`MdfLoadError` in `errors.py` (#46):** moved from `model/mdf_loader.py` so that `view/main_window.py` can import it without creating a view→model dependency. Both `mdf_loader.py` and `main_window.py` now import from `mdf_viewer.errors`.
- **Single controller contact point for `MainWindow` (#48):** `MainWindow` no longer holds a reference to `CursorController`. All cursor actions (`toggle_cursor`, `press_cursor1`, `press_cursor2`, `zoom_to_cursors`, `set_cursor_mode_callback`) are proxy methods on `AppController`, which delegates to `_cursor_ctrl`. `set_controller(ctrl)` lost its `cursor_ctrl` parameter.
- **`CursorController` reads signals on demand (#49):** the controller no longer owns a `list[ActiveSignal]` or responds to `on_signal_added`. Instead it receives a `get_active_signals: Callable[[], list]` at construction (`app.py` passes `lambda: controller.active_signals`). This eliminates a second authoritative list and removes the need for a matching add-notification. `AppController.add_signal` calls `cursor_ctrl.refresh()` after appending; `remove_signal` calls `on_signal_removed` (label cleanup only, before ViewBox destruction) then `refresh()`.
- **License state read once at startup; restart required after import (#51):** `app.py` calls `license_manager.load_stored()` once at startup; `window.set_license(info, manager)` is called once and never again. `MainWindow._on_license()` opens the dialog and does nothing on accept — the dialog's own "restart required" message is the canonical flow. `LicenseDialog.accepted_license()` was removed as dead code.
- **Protocol contracts in `controller/interfaces.py` (#50):** seven `typing.Protocol` classes declare every method each controller calls on its view dependencies. Interface segregation applied to `ActiveSignalsTable`: `SignalTableProtocol` (add/remove/clear rows — `AppController`) and `CursorValueSinkProtocol` (cursor value columns — `CursorController`) are separate. All protocols live under `TYPE_CHECKING` — no runtime cost.

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

**Latest release — v1.5:** https://github.com/andalf-74/MDF-Viewer/releases/tag/v1.5 — ships `MDF-Viewer-1.5-Setup.exe` (installer) and `MDF-Viewer-1.5-Windows.zip` (portable).

### Environment
- `.venv` exists with deps installed (`pip install -e ".[dev]"`). Python 3.14.5. asammdf resolved to 8.x.
- Activate with `.venv\Scripts\activate`, then `pytest` (426 passing) and `python -m mdf_viewer` both work.

### Changelog
Notable changes are tracked in `CHANGELOG.md` (Keep a Changelog style). Update it alongside `CLAUDE.md` when shipping a fix or feature.

### Next steps
v2.0 in progress. Arch cleanup done (#46–#52). Remaining for v2.0: #10 (check for updates). Then v2.1 "Cursor Stuff" (#11, #25, #26, #29, #39).

### v2.0 planning
- **Direction:** v1.5 is the last free/GPL-3.0 feature release. v2.0 onward stays GPL-3.0 and adds an honor-based license-key system: a cosmetic "Licensed to: ..." display (vs. "unregistered") with no hard enforcement.
- **Qt binding:** staying on PyQt6/GPL-3.0 — GPL does not prohibit charging money, only requires distributing source.
- **Feature-gating model (Option A):** paid features ship as normal GPL code gated by a license-key check; the gate can be removed by anyone building from source — acceptable under the honor model.
- **Repo/secrets:** the Ed25519 private key and `generate_license.py` are saved at `C:\Users\andal\Documents\mdf-viewer-private\` — never commit either to any repo. `.gitignore` blocks `generate_license.py`, `*.lic`, and `*.pem`.

**License system decisions:**
- **File format:** JSON with a `payload` block (fields inside are signed) and a `signature` field (base64 Ed25519). `format_version` lives inside the payload so it cannot be tampered with post-signing.
- **Canonical signing:** `json.dumps(payload, sort_keys=True, separators=(',', ':'))` — deterministic, no whitespace.
- **Tiers:** Personal (1 seat), Team (5 seats fixed, `TEAM_SEATS = 5`), Enterprise (0 = unlimited).
- **Perpetual + 2-year updates:** license never expires; `updates_until` date is signed into payload. After expiry the app keeps working but shows a notice in the About dialog and update checker.
- **Backwards compatibility:** new payload fields must always be optional with defaults — old licenses remain valid. Only key rotation invalidates old licenses (avoid rotating the key pair).
- **`load_stored()` never raises** — returns `None` on missing or corrupt file so a bad license file never prevents the app from starting.
- **Help menu order:** License Key action first, separator, About last.
