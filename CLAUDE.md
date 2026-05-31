# MDF-Viewer – Project Context for Claude Code

## Project Overview

MDF-Viewer is a desktop application for visualizing ASAM MDF measurement data files (MDF3 and MDF4). It is a greenfield rewrite based on the author's prior experience with a working prototype. The goal is a clean, maintainable architecture from the start – the prototype suffered from tight coupling between data, UI, and plotting components.

The application is developed as a private project, targeting individual engineers and automotive measurement professionals. A future commercial release (one-time purchase model) is possible.

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
  - *(placeholder for future menu items)*
  - Exit

### Toolbar
- **Load File** – folder icon, opens file dialog
- **Zoom to Fit** – resets viewport to show all active signals fully (X: full time range, Y: auto-scaled per signal)
- **Cursor Toggle** – cycles through: 1 cursor → 2 cursors → cursors hidden → (repeat)

### Main Layout (horizontal splitter)
- **Left panel** – Signal Browser (TreeView showing full MDF channel hierarchy)
- **Center panel** (vertical splitter)
  - **Top** – Plot Area
  - **Bottom** (horizontal splitter)
    - **Left** – Measurement Info Box
    - **Right** – Selected Signal Info Box
- **Right panel** – Active Signals Table

---

## Signal Browser (Left Panel)

- TreeView reflecting the full channel group hierarchy of the loaded MDF file
- Signals can be added to the plot via:
  - Double-click on a signal node
  - Select (highlight) + click "Add Signal" button below the list
- Future feature (not MVP): Multi-select to add multiple signals at once

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

### Cursors
- Vertical line(s) draggable via drag & drop in the plot
- On first activation: placed at the start of the time range
- On subsequent toggles: hidden/shown at their last position (position is remembered)
- Value label at the intersection of cursor and signal curve:
  - Only shown on the cursor that is currently closer to the mouse pointer
  - Positioned close to the intersection point

---

## Info Boxes (Bottom Center)

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
- **No "recently opened" list (MVP)** – planned for future version
- **No session persistence (MVP)** – application always starts fresh; saving/restoring active signals, colors, and window state is planned for a future version
- **Robust error handling is mandatory** – the application must never crash on malformed, incomplete, or unexpected MDF content; errors must be caught and communicated to the user gracefully

---

## MDF Support

- MDF3 and MDF4 via the `asammdf` library
- All available channel groups and signals must be represented in the Signal Browser TreeView

---

## Todo / Future Features (not MVP)

- Multi-file support with multiple X-axes and synchronization (by timestamp overlap, manual time offset, or signal-based alignment)
- Recently opened files list
- Session persistence (active signals, colors, window layout)
- Multi-select in Signal Browser
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

---

## Current Status

**As of 2026-05-31:** All planned features complete + signal filter — 245 tests passing.

### Implemented

| Module | Description | Tests |
|--------|-------------|-------|
| `model/mdf_loader.py` | `MdfLoader` + `ChannelGroupInfo` + `MdfLoadError` | 26 |
| `model/signal_data.py` | `SignalData` dataclass | 2 |
| `view/signal_browser.py` | `SignalBrowser` QWidget (TreeView + Add Signal button) | 18 |
| `view/main_window.py` | `MainWindow` — splitter layout, menu, toolbar, wiring | 21 |
| `view/measurement_info_box.py` | `MeasurementInfoBox` — file metadata, QFormLayout + placeholder | 18 |
| `view/signal_info_box.py` | `SignalInfoBox` — signal metadata, QFormLayout + placeholder | 16 |
| `view/active_signals_table.py` | `ActiveSignalsTable` — color swatch, name, cursor cols, buttons | 28 |
| `view/plot_area.py` | `PlotArea` — PyQtGraph, shared X-axis, per-signal ViewBox + Y-axis | 18 |
| `view/cursors.py` | `CursorView` — InfiniteLine items, value labels, nearest-cursor logic | 17 |
| `view_model/active_signal.py` | `ActiveSignal` dataclass (model data + plot objects + color) | — |
| `controller/app_controller.py` | `AppController` — coordinates all layers | 34 |
| `controller/cursor_controller.py` | `CursorController` — toggle, position memory, interpolation | 28 |
| `app.py` | MVC assembly point | — |

**`MdfLoader`** is the sole importer of `asammdf`. Public API:
- `open(path)` / `close()` / `is_open`
- `measurement_info()` → `MeasurementInfo`
- `channel_tree()` → `list[ChannelGroupInfo]`
- `load_signal(group_index, channel_index)` → `(SignalData, SignalMetadata)`

**`SignalBrowser`** public API:
- `populate(groups: list[ChannelGroupInfo])` — rebuilds the tree, groups expanded, filter cleared
- `clear()` — resets the tree and clears the filter
- `add_signal_requested(group_index, channel_index)` — PyQt signal emitted on double-click or Add Signal button
- Filter field: `QLineEdit` at the top; connected to a `QSortFilterProxyModel` with `setRecursiveFilteringEnabled(True)` (case-insensitive, partial match; groups visible when any child matches). `setClearButtonEnabled(True)` provides a built-in × button. `populate()` and `clear()` both reset the filter.

**`ActiveSignal`** fields: `data`, `metadata`, `color: QColor` (set by controller from palette); `curve` and `view_box` are `None` until `PlotArea.add_signal()` fills them in. `__hash__ = object.__hash__` added so instances can be used as dict keys (auto-generated `__eq__` from `@dataclass` compares numpy arrays, which sets `__hash__` to `None` by default).

**`AppController`** public API:
- `load_file(path)` — clears all state, opens file, populates browser + info box; resets color counter and cursor system; UI cleared before `open()` so state is clean on failure
- `add_signal(gi, ci)` — loads channel, assigns next palette color, notifies plot + table + cursor system
- `remove_signal(active)` — removes from plot/table/list; notifies cursor system; clears selection if that signal was selected
- `remove_all()` — removes all signals, clears table, notifies cursor system, clears selection
- `set_selected_signal(active | None)` — drives the Signal Info Box
- `set_cursor_controller(cc)` — optional; wired from `app.py` after construction
- `active_signals` / `selected_signal` — read-only state accessors

**`CursorController`** public API:
- `toggle()` — HIDDEN → ONE → TWO → HIDDEN; on first activation places cursors at plot X range start + 10% span; subsequent toggles use remembered positions
- `reset()` — called by `AppController.load_file()`; hides cursors and marks positions for re-initialisation on next activation
- `on_signal_added(active)` / `on_signal_removed(active)` / `on_all_signals_cleared()` — keep label state in sync
- Drives `ActiveSignalsTable.update_cursor_values()` and `CursorView.update_labels()` on every drag and toggle

**`CursorView`** (`QObject`, lives inside `PlotArea.plot_item`):
- Two dashed-yellow `pg.InfiniteLine` items (hidden until activated); `apply_mode(mode, positions)` shows/hides and repositions them
- `update_labels(active_signals, positions, mode)` — creates/repositions `pg.TextItem` value labels (signal color, `{value:.4g} {unit}`); prunes stale labels
- `remove_labels_for(active)` / `clear_labels()` — called on signal removal
- Nearest-cursor logic: `pg.SignalProxy` on `scene.sigMouseMoved` (30 fps) — in TWO mode, only the closer cursor's labels are shown
- `cursor_moved(index, x)` — `pyqtSignal` emitted on every drag step

**`MainWindow`** public API:
- Constructor creates all five view widgets as public attrs: `signal_browser`, `plot_area`, `active_signals_table`, `measurement_info_box`, `signal_info_box`
- `set_controller(ctrl, cursor_ctrl=None)` — wires browser, table remove/selection signals to controller, and cursor toggle to `cursor_ctrl.toggle()`
- Layout: outer H-splitter → [SignalBrowser (260px) | center V-splitter | ActiveSignalsTable (260px)]; center → [PlotArea (3×) | bottom H-splitter → [MeasurementInfoBox | SignalInfoBox]]
- Menu: File → Load MDF… (Ctrl+O) / Exit (Ctrl+Q)
- Toolbar: Load File (folder icon) | Zoom to Fit (Ctrl+0) | Cursors (toggle)
- Both load paths catch `MdfLoadError` and show `QMessageBox.critical`

**`app.py`**: constructs `MainWindow`, reads view attrs, builds `MdfLoader` + `AppController`, constructs `CursorView(plot_area.plot_item)` + `CursorController`, wires all three together, calls `set_controller`.

**`MeasurementInfoBox`** / **`SignalInfoBox`**: both use a `QStackedWidget` — page 0 is a centred placeholder label, page 1 is a `QScrollArea` + `QFormLayout`. `set_info` / `set_metadata` populates the form and switches to page 1; `clear()` switches back. Optional fields (empty string / `None`) are omitted. MDF4 XML tags in comment fields are stripped by regex. `_clear_form`, `_add_row`, `_clean_text` shared via import from `measurement_info_box`.

**`ActiveSignalsTable`** public API:
- `add_row(active)` / `remove_row(active)` / `clear()` — row management; identity-based lookup (`is`) avoids numpy `__eq__` ambiguity on `SignalData`
- `show_cursor_columns(bool)` — reveals/hides C1, C2, Δ columns (hidden by default)
- `update_cursor_values(active, c1, c2, delta)` — fills cursor cells by row
- Signals: `selection_changed(object)`, `remove_requested(object)`, `remove_all_requested()`, `color_change_requested(object, QColor)`
- `_ColorSwatch`: flat `QPushButton` with styled background; click → `QColorDialog` → updates swatch + emits `color_change_requested`
- Uses `selectionModel().selectedRows()` (not `currentRow()`) so `clearSelection()` correctly emits `None`

### Decisions made
- **Qt binding:** PyQt6 (LGPL-friendly path; PyQtGraph supports it).
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

### Decisions made (continued)
- **`CursorController` wiring:** optional dependency injected via `AppController.set_cursor_controller()`; all notify calls are guarded by `None` check so the cursor system can be omitted without touching `AppController`.
- **CursorView lifetime:** `CursorView` is a `QObject` that holds references to PyQtGraph items added to `PlotArea.plot_item`. It is constructed in `app.py` after `MainWindow` so the PlotItem scene already exists. Tests keep the parent `PlotWidget` alive via a separate pytest fixture to prevent C++ object deletion.
- **Nearest-cursor label logic:** uses identity-based label keys `(cursor_index, active)` to avoid numpy `__eq__` ambiguity (same pitfall as `ActiveSignalsTable._find_row`).
- **Cursor label Y-tracking:** labels are added to the signal's own `ViewBox` (not the main PlotItem) so `setPos(x, y)` is in the signal's Y coordinate space and the label tracks Y pan/zoom automatically. `_labels` stores `(TextItem, ViewBox)` tuples. Cursor cleanup (`on_signal_removed`, `on_all_signals_cleared`) is called in `AppController` *before* `plot_area.remove_signal` so the ViewBox is still in the scene when `vb.removeItem(lbl)` runs.

### Environment
- `.venv` exists with deps installed (`pip install -e ".[dev]"`). Python 3.14.5. asammdf resolved to 8.x.
- Activate with `.venv\Scripts\activate`, then `pytest` (246 passing) and `python -m mdf_viewer` both work.

### Next steps
All MVP features are implemented. Possible next work:
- Manual testing with real MDF files (drop into `data/`)
- Bug fixes and polish from real-world use
- Future features from the Todo list in the spec (session persistence, recently opened files, multi-select in Signal Browser, etc.)
