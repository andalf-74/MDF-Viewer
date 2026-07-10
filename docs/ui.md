# MDF-Viewer – UI Layout Reference

## Application Layout

```
+---------------------------+-----------------------------------------------+------------------+
| ‹ (pin/collapse button)   |  [Tab 1] [Tab 2] [+]                           |                  |
| Signal Browser (TreeView) |  +---------------------+----------------+      |  Signal Info /   |
| + measurement selector    |  | Plot Stripe 1        | Active Signals |      |  Properties      |
| (2+ measurements loaded)  |  +---------------------+ Table (per-    |      |  drawer          |
|                           |  | Plot Stripe 2 (opt.) | stripe         |      |  (pin/collapse   |
| Measurement Info Box      |  +---------------------+ segments)      |      |   button ›)      |
+---------------------------+-----------------------------------------------+------------------+
```

- **Left panel** (`DockablePanel`, pinned or hover-reveal overlay) – vertical splitter:
  - **Top** – Signal Browser (channel tree + measurement selector once 2+ measurements are loaded)
  - **Bottom** – Measurement Info Box
  - Pin-toggle chevron button collapses the panel to a hidden drawer that slides out on hovering near the window's left edge
- **Center** – one `QTabWidget` (tabs #99), each tab holding an independent workspace: a horizontal splitter of `[Plot Stripes | Active Signals Table]`. A "+" tab pinned at the end creates a new tab; closing the last tab shows a "No tabs open" placeholder with its own "New Tab" button.
  - Each tab's plot area can itself be split into multiple vertically-stacked **stripes** (#97) — see "Plot Area (Stripes)" below.
- **Right panel** (`DockablePanel`, mirrors the left panel's mechanism for the right edge) – the Signal Info/Properties drawer (#98), shared across every tab, showing whichever signal was most recently selected in the currently active tab.

---

## Menu Bar

- **File**
  - Open… (Ctrl+O; opens file dialog; accepts measurement file(s) and `.mvc` configs; loading with a measurement already open prompts Replace vs. Add)
  - Recently opened files (up to 4; shown between Open… and Preferences when non-empty)
  - Save Config (Ctrl+S) / Save Config As… — saves the active tab's session (active signals, colors, axis grouping, zoom, cursor state, window/splitter layout) to a `.mvc` file
  - Preferences… (opens Preferences dialog)
  - Exit (Ctrl+Q)
- **Edit**
  - New Tab / New Stripe (#115 — moved here from File)
  - Undo (Ctrl+Z) / Redo (Ctrl+Shift+Z) — zoom/pan history
  - Sync Measurements — checkable; collapses/restores every loaded measurement's own time axis into one shared ruler (#102); disabled with fewer than 2 measurements loaded
- **Help**
  - Check for Update… (fetches GitHub releases API; shows update dialog or "up to date" dialog)
  - License (Enter / View/Change)
  - About MDF-Viewer

---

## Toolbar

Order (#114 — "All Stripes" moved next to Load, ahead of the two zoom actions it governs, with a separator after "Zoom Y to View" marking where its effect ends):

- **Load File** – folder icon, opens file dialog (Ctrl+O)
- **All Stripes** – checkable; whether "Zoom to Fit"/"Zoom Y to View" apply to every stripe or only the active one (Swimlanes and box-zoom are always scoped to the stripe they're used in, regardless of this toggle)
- **Zoom to Fit** – resets viewport to show all active signals fully (X: full time range, Y: auto-scaled per signal) (Ctrl+0 / F)
- **Zoom Y to View** – auto-scales Y axes for all signals within the current X span (Y)
- **Swimlanes** – arranges the active stripe's signals in non-overlapping horizontal swimlanes (B)
- **Zoom to Cursors** – zooms X axis to the span between the two cursors; enabled only in two-cursor mode (C)
- **Cursor Toggle** – cycles through: 1 cursor → 2 cursors → cursors hidden → (repeat)

Keyboard shortcuts for cursors: `.` toggles Cursor 1 (HIDDEN↔ONE, TWO→ONE), `,` toggles Cursor 2 (HIDDEN/ONE→TWO, TWO→HIDDEN). Left/Right arrow keys step the active cursor (step size configurable in Preferences).

A per-stripe "Sync"/"Un-Sync" button also floats in the corner of the measurement-axis area at the bottom of the plot, mirroring the Edit menu's "Sync Measurements" action (#102) — see `docs/architecture.md`'s "Measurement Synchronization" entry.

---

## Tabs (#99)

- Each tab is an independent workspace: its own plot stripes, Active Signals Table, active-signal list, zoom/cursor history, and axis grouping — nothing is shared between tabs except the Signal Browser, Measurement Info Box, and the Signal Info/Properties drawer.
- Double-click a tab to rename it; right-click for a context menu; drag to reorder (the "+" tab stays pinned last).
- Closing a tab that still has active signals asks for confirmation first; closing the last tab shows the "No tabs open" placeholder.
- Ctrl+Tab / Ctrl+Shift+Tab cycle through tabs.
- The measurement pool (loaded MDF files) and the Sync Measurements state are global, shared across every tab — only the plot/signal/zoom state above is per-tab.

---

## Plot Area (Stripes) (#97)

- The plot area can be split into multiple vertically-stacked **stripes**, each with its own independent Y-axes, sharing one X-axis and one pair of cursors across all of them. "New Stripe" (Edit menu) or a stripe's own right-click context menu adds one; a stripe's context menu can also delete it (the last remaining stripe can't be deleted; deleting one that still has signals asks for confirmation).
- Right-clicking inside a stripe shows PyQtGraph's standard plot context menu (view-all, per-axis auto-range, grid) minus "Mouse Mode" (fixed to pan), plus "Create new Stripe" / "Delete this Stripe".
- Clicking inside a stripe makes it the active one (colored marker on its left edge) — Swimlanes, box-zoom, and (when "All Stripes" is off) Zoom to Fit/Zoom Y to View all act on the active stripe only.
- Each active signal gets its own Y-axis on the right, colored to match its curve; dragging a Y-axis pans/zooms that signal alone. Signals can be merged (one shared Y-axis) or synced (separate axes, ranges kept in lockstep) via the Active Signals Table's context menu.
- Accepts drag-and-drop: MDF/`.mvc` files, and signals dragged from the Signal Browser or between Active Signals Table segments (dropping directly onto a stripe's plot area moves/adds to that stripe).
- **Multiple measurements** (#101): once 2+ measurement files are loaded, each gets its own X-axis row stacked below the bottom-most stripe, showing that measurement's real recorded time; dragging a measurement's own row pans its curves independently (wheel/box zoom always stays shared across every measurement). "Sync Measurements" (#102) collapses these rows into one shared ruler (the first-loaded measurement's) once they've been manually aligned; "Un-Sync" restores the separate rows.

---

## Cursors

- Vertical line(s), draggable, kept in lockstep across every stripe in a tab.
- On first activation: placed at the start of the time range; subsequent toggles restore the last position.
- Value label at the intersection of cursor and signal curve, shown only on whichever cursor is currently closer to the mouse pointer.
- Off-screen chevron indicators at the plot edge when a cursor (or the delta-time line) is panned out of view; clicking one jumps back to it.
- The delta-time line (difference between Cursor 1 and Cursor 2) is shown only in the active stripe, and remembers its vertical position independently per stripe.
- Left/Right arrow keys step the active cursor by a configurable amount (Preferences → Cursors).

---

## Signal Browser (Left Panel)

- TreeView reflecting the full channel-group hierarchy of the currently-selected loaded measurement.
- A measurement selector combo box appears above the tree once 2+ measurements are loaded (hidden with 0 or 1); picking one repopulates the tree with that measurement's channels. All three ways of adding a signal below implicitly target whichever measurement the selector currently shows.
- A wildcard filter field (`*`/`?`) above the tree narrows the currently-shown tree by name.
- Signals can be added to the plot via:
  - Double-click on a signal node
  - Select (highlight) + click "Add Signal" button below the list
  - Drag one or more selected signals onto a Plot Stripe or the Active Signals Table
- Multi-select: `ExtendedSelection` mode — Ctrl+click (individual), Shift+click (range); all three add paths emit all selected channels at once.

---

## Active Signals Table (#100)

Divided into one segment per stripe, stacked top-to-bottom in the same order as their stripes, each showing only that stripe's active signals — a divider between adjacent segments aligns to the boundary between those stripes in the plot. A shared header row (same columns, kept in sync with every segment) stays fixed at the top regardless of stripe count.

| # | Column | Description |
|---|--------|--------------|
| 1 | Color swatch | Small colored rectangle; clicking opens a color picker and updates curve + Y-axis color |
| 2 | Signal name | Display name from MDF metadata (prefixed with its measurement's label once 2+ measurements are loaded) |
| 3 | Cursor 1 value | Current value at Cursor 1 position (shown only when cursor is active) |
| 4 | Cursor 2 value | Current value at Cursor 2 position (shown only when cursor is active) |
| 5 | Delta | Difference between Cursor 2 and Cursor 1 values |

- Each segment's stripe name is shown as a label above it (double-click to rename, mirroring tab renaming).
- Dragging a row within or across segments reorders it or moves the signal to a different stripe (the drop target's segment); this also relocates the signal in the plot.
- Right-click context menu: Remove Signal(s), Enable/Disable Step Mode, Shorten Signal Names (toggle), Display Name Rule…, Merge Y-Axis / Sync Y-Axis / Remove from merged-synced axis (2+ signals), Move to Stripe / Move to new Stripe.
- **Remove Signal** / **Remove All** buttons below the table (spanning all segments) remove the selected/every active signal from the table and plot.
- Selection here drives the Signal Info/Properties drawer's content.

---

## Signal Info / Properties Drawer (#98)

Right-edge `DockablePanel` (pin-toggle chevron ›, or hover-reveal near the window's right edge when unpinned), shared across tabs, driven by whichever signal was most recently selected in the Active Signals Table. Two sections stacked vertically in a resizable inner splitter — both visible at once, not tabs:

- **Info** (read-only) — Name, Unit, Data type, Samples, Raster, Min, Max, Comment, and any other MDF metadata fields present. Shows a placeholder when no/multiple signals are selected.
- **Properties** (editable, disabled when no signal is selected) — Display mode (Line / Line & Marker / Marker Only), Marker shape, Line width (1–8), Line style (Solid/Dashes/Dots/Dash-Dot), and — only for signals with an enum/value table — which of Value table / Cursor label / Y-axis should show the enum's text labels instead of raw numbers. Editing with 2+ signals selected applies the change to all of them; mismatched values show a blank/"—".

---

## Preferences Dialog

Tabbed dialog (Edit → Preferences…):
- **General** — "Check for updates on startup" checkbox; "Undo steps" spinbox (1–100, zoom/pan history depth)
- **Cursors** — cursor mode, "persistent" toggle, 4 color swatches (Cursor 1 / Cursor 2 / Cursor Left / Cursor Right chevrons), "Show ∆-Time" checkbox + its own color swatch, arrow-key step size (unit combo box + spinbox), reset-to-defaults button
