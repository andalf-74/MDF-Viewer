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

**As of 2026-05-31:** App is runnable end-to-end (blank panels) — 101 tests passing.

### Implemented

| Module | Description | Tests |
|--------|-------------|-------|
| `model/mdf_loader.py` | `MdfLoader` + `ChannelGroupInfo` + `MdfLoadError` | 26 |
| `model/signal_data.py` | `SignalData` dataclass | 2 |
| `view/signal_browser.py` | `SignalBrowser` QWidget (TreeView + Add Signal button) | 18 |
| `view/main_window.py` | `MainWindow` — splitter layout, menu, toolbar, wiring | 21 |
| `view_model/active_signal.py` | `ActiveSignal` dataclass (model data + plot objects + color) | — |
| `controller/app_controller.py` | `AppController` — coordinates all layers | 34 |
| `app.py` | MVC assembly point | — |

**`MdfLoader`** is the sole importer of `asammdf`. Public API:
- `open(path)` / `close()` / `is_open`
- `measurement_info()` → `MeasurementInfo`
- `channel_tree()` → `list[ChannelGroupInfo]`
- `load_signal(group_index, channel_index)` → `(SignalData, SignalMetadata)`

**`SignalBrowser`** public API:
- `populate(groups: list[ChannelGroupInfo])` — rebuilds the tree, groups expanded by default
- `clear()` — resets the tree
- `add_signal_requested(group_index, channel_index)` — PyQt signal emitted on double-click or Add Signal button

**`ActiveSignal`** fields: `data`, `metadata`, `color: QColor` (set by controller from palette); `curve` and `view_box` are `None` until `PlotArea.add_signal()` fills them in.

**`AppController`** public API:
- `load_file(path)` — clears all state, opens file, populates browser + info box; resets color counter; UI cleared before `open()` so state is clean on failure
- `add_signal(gi, ci)` — loads channel, assigns next palette color, notifies plot + table
- `remove_signal(active)` — removes from plot/table/list; clears selection if that signal was selected
- `remove_all()` — removes all signals, clears table and selection
- `set_selected_signal(active | None)` — drives the Signal Info Box
- `active_signals` / `selected_signal` — read-only state accessors

All six `AppController` dependencies are injected (loader, browser, plot\_area, active\_signals\_table, measurement\_info\_box, signal\_info\_box). Controller tests use `MagicMock` — no QApplication or real file needed.

**`MainWindow`** public API:
- Constructor creates all five view widgets as public attrs: `signal_browser`, `plot_area`, `active_signals_table`, `measurement_info_box`, `signal_info_box`
- `set_controller(ctrl)` — wires `browser.add_signal_requested → controller.add_signal`; called from `app.py` after controller construction
- Layout: outer H-splitter → [SignalBrowser (260px) | center V-splitter | ActiveSignalsTable (260px)]; center → [PlotArea (3×) | bottom H-splitter → [MeasurementInfoBox | SignalInfoBox]]
- Menu: File → Load MDF… (Ctrl+O) / Exit (Ctrl+Q)
- Toolbar: Load File (folder icon) | Zoom to Fit (Ctrl+0) | Cursors (toggle stub)
- Both load paths catch `MdfLoadError` and show `QMessageBox.critical`

**`app.py`**: constructs `MainWindow`, reads its view attrs, builds `MdfLoader` + `AppController`, calls `set_controller`, shows the window.

### Decisions made
- **Qt binding:** PyQt6 (LGPL-friendly path; PyQtGraph supports it).
- **`ActiveSignal` location:** `src/mdf_viewer/view_model/` (not `model/`), to keep the data layer free of Qt/PyQtGraph imports. Layer rules are documented in `docs/architecture.md`.
- **Build:** `pyproject.toml` (src-layout, entry point `mdf-viewer`) + `requirements.txt` / `requirements-dev.txt`.
- **MDF4 `header.author`** does not round-trip via asammdf (stored in XML comment block). The `MeasurementInfo.extra` dict is available for raw fields if needed later.
- **Signal color palette:** 8-color cycling tuple defined in `app_controller.py`; resets on `load_file()`.
- **View imports in controller:** `TYPE_CHECKING`-only — no runtime view imports; all views are injected.
- **MVC assembly:** `MainWindow` creates view widgets; `app.py` reads them to construct `AppController`; `set_controller` completes the wiring. No layer constructs another's object graph.

### Environment
- `.venv` exists with deps installed (`pip install -e ".[dev]"`). Python 3.14.5. asammdf resolved to 8.x.
- Activate with `.venv\Scripts\activate`, then `pytest` (101 passing) and `python -m mdf_viewer` both work.

### Next steps (remaining stubs)
Implement the four remaining view stubs in roughly this order:
1. `view/measurement_info_box.py` — `set_info(MeasurementInfo)` / `clear()`, read-only label grid
2. `view/signal_info_box.py` — `set_metadata(SignalMetadata)` / `clear()`, read-only label grid
3. `view/active_signals_table.py` — color swatch, name, cursor values, Remove/Remove All buttons
4. `view/plot_area.py` — PyQtGraph, shared X-axis, per-signal ViewBox + Y-axis, zoom\_to\_fit
