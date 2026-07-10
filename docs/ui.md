# MDF-Viewer – UI Layout Reference

## Application Layout

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

## Menu Bar

- **File**
  - Open… (Ctrl+O; opens file dialog; accepts measurement files and `.mvc` configs)
  - Recently opened files (up to 4; shown between Open… and Preferences when non-empty)
  - Save Config (Ctrl+S) / Save Config As…
  - Preferences… (opens Preferences dialog)
  - Exit (Ctrl+Q)
- **Edit**
  - New Tab / New Stripe (#115 — moved here from File)
  - Undo (Ctrl+Z) / Redo (Ctrl+Shift+Z)
  - Sync Measurements — checkable; collapses/restores every loaded measurement's own time axis into one shared ruler (#102); disabled with fewer than 2 measurements loaded
- **Help**
  - Check for Update… (fetches GitHub releases API; shows update dialog or "up to date" dialog)
  - License (Enter / View/Change)
  - About MDF-Viewer

---

## Toolbar

Order (#114 — "All Stripes" moved next to Load, ahead of the two zoom actions it governs, with a separator after "Zoom Y to View" marking where its effect ends):

- **Load File** – folder icon, opens file dialog (Ctrl+O)
- **All Stripes** – checkable; whether "Zoom to Fit"/"Zoom Y to View" apply to every stripe or only the active one
- **Zoom to Fit** – resets viewport to show all active signals fully (X: full time range, Y: auto-scaled per signal) (Ctrl+0 / F)
- **Zoom Y to View** – auto-scales Y axes for all signals within the current X span (Y)
- **Swimlanes** – arranges signals in non-overlapping horizontal swimlanes (B)
- **Zoom to Cursors** – zooms X axis to the span between the two cursors; enabled only in two-cursor mode (C)
- **Cursor Toggle** – cycles through: 1 cursor → 2 cursors → cursors hidden → (repeat)

Keyboard shortcuts for cursors: `.` toggles Cursor 1 (HIDDEN↔ONE, TWO→ONE), `,` toggles Cursor 2 (HIDDEN/ONE→TWO, TWO→HIDDEN).

A per-stripe "Sync"/"Un-Sync" button also floats in the corner of the measurement-axis area at the bottom of the plot, mirroring the Edit menu's "Sync Measurements" action (#102) — see `docs/architecture.md`'s "Measurement Synchronization" entry.

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
- File name, Author, Date/time of recording, MDF version, Duration, Comment
- Any other available metadata fields

### Signal Info Box

Displays metadata for the currently selected signal in the Active Signals Table:
- Signal name, Unit, Sample count, Min value, Max value, Comment
- Any other available metadata fields
