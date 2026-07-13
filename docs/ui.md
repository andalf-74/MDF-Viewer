# MDF-Viewer – UI Layout Reference

## Application Layout

```
+---------------------------+-----------------------------------------------+------------------+
| ‹ (pin/collapse button)   |  [Tab 1] [Tab 2] [+]                           |                  |
| Signal Browser (flat list)|  +---------------------+----------------+      |  Signal Info /   |
| + measurement filter      |  | Plot Stripe 1        | Active Signals |      |  Properties      |
| (2+ measurements loaded)  |  +---------------------+ Table (per-    |      |  drawer          |
|                           |  | Plot Stripe 2 (opt.) | stripe         |      |  (pin/collapse   |
| Measurement Info (tabbed) |  +---------------------+ segments)      |      |   button ›)      |
+---------------------------+-----------------------------------------------+------------------+
```

- **Left panel** (`DockablePanel`, pinned or hover-reveal overlay) – vertical splitter:
  - **Top** – Signal Browser (flat, cross-measurement channel list + measurement filter once 2+ measurements are loaded, #103)
  - **Bottom** – Measurement Info Box (always tabbed, one tab per loaded measurement, #103)
  - Pin-toggle chevron button collapses the panel to a hidden drawer that slides out on hovering near the window's left edge
- **Center** – one `QTabWidget` (tabs #99), each tab holding an independent workspace: a horizontal splitter of `[Plot Stripes | Active Signals Table]`. A "+" tab pinned at the end creates a new tab; closing the last tab shows a "No tabs open" placeholder with its own "New Tab" button.
  - Each tab's plot area can itself be split into multiple vertically-stacked **stripes** (#97) — see "Plot Area (Stripes)" below.
- **Right panel** (`DockablePanel`, mirrors the left panel's mechanism for the right edge) – the Signal Info/Properties drawer (#98), shared across every tab, showing whichever signal was most recently selected in the currently active tab.

---

## Menu Bar

- **File**
  - Open… (Ctrl+O; opens file dialog; accepts measurement file(s) and `.mvc` configs; loading with a measurement already open prompts Replace vs. Add)
  - Apply Config… (#105) — opens a file dialog filtered to `.mvc` files; applies that workspace's tabs/stripes/signal selections onto whichever measurement(s) are already loaded, without opening any file the config itself records. Prompts to map each of the config's saved measurement slots onto an already-loaded measurement (or "None" to drop it); every other loaded measurement, and the pool's own Primary/Sync state, are left untouched. Automatically opens Save Workspace As… afterward so the result can be saved as a new file. Disabled when nothing is loaded.
  - Save Workspace (Ctrl+S) / Save Workspace As… — saves the full session to a `.mvc` file (#106): every tab (name, plot|AST divider width, AST column widths), every tab's plot-stripe layout (names/sizes/active stripe), every active signal (colors, stripe/measurement placement, axis grouping, zoom, cursor state, selection), every loaded measurement (path, short name, offset, Primary, Sync state), and window/splitter layout
  - Replace Measurement — submenu listing every loaded measurement by its short name (#122); selecting one opens a file dialog and swaps that measurement's underlying file in place, keeping its short name, position, offset, Primary status, and Sync membership; every other loaded measurement is untouched; disabled/empty when nothing is loaded
  - Close Measurement — submenu listing every loaded measurement by its short name (#103); selecting one closes it, warning first if it still has active signals; disabled/empty when nothing is loaded
  - Recently opened files (up to 4; shown between Open… and Preferences when non-empty)
  - Preferences… (opens Preferences dialog)
  - Exit (Ctrl+Q)
- **Edit**
  - New Tab / New Stripe (#115 — moved here from File)
  - Undo (Ctrl+Z) / Redo (Ctrl+Shift+Z) — zoom/pan history
  - Sync Measurements — checkable; collapses/restores every loaded measurement's own time axis into one shared ruler (#102); disabled with fewer than 2 measurements loaded
- **Plugins** (#73) — one entry per plugin-registered menu action, plus one entry per plugin dialog-type dock widget (labeled "\<title\>…", opening it in a modal dialog on demand). Not shown at all when no plugin has registered anything — today's actual state, since the plugin loader (#74) doesn't exist yet and nothing populates this.
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
- The context menu's **"Duplicate Tab"** (#119) makes a full copy of a tab — stripes, signals (color/line style/every display property preserved), cursor, zoom, and axis grouping — sharing only the underlying measurement(s), not any plot object; the copy starts with no selection and an empty zoom undo/redo history. **"Copy Signals to new Tab"** (#119, disabled when the source tab has no active signals) instead opens a new tab with a single stripe holding every one of the source's signals flattened into it, keeping their display properties but none of the source's stripe layout, zoom, cursor, or axis grouping. Both insert the new tab immediately after the source, named "Copy of \<source name\>", and continue the source's color sequence for any signal added afterward.
- Closing a tab that still has active signals asks for confirmation first; closing the last tab shows the "No tabs open" placeholder.
- Ctrl+Tab / Ctrl+Shift+Tab cycle through tabs.
- The measurement pool (loaded MDF files), the Sync Measurements state, and which measurement is Primary (#103) are global, shared across every tab — only the plot/signal/zoom state above is per-tab.

---

## Plot Area (Stripes) (#97)

- The plot area can be split into multiple vertically-stacked **stripes**, each with its own independent Y-axes, sharing one X-axis and one pair of cursors across all of them. "New Stripe" (Edit menu) or a stripe's own right-click context menu adds one; a stripe's context menu can also delete it (the last remaining stripe can't be deleted; deleting one that still has signals asks for confirmation).
- Right-clicking inside a stripe shows PyQtGraph's standard plot context menu (view-all, per-axis auto-range, grid) minus "Mouse Mode" (fixed to pan), plus "Create new Stripe" / "Delete this Stripe".
- Clicking inside a stripe makes it the active one (colored marker on its left edge) — Swimlanes, box-zoom, and (when "All Stripes" is off) Zoom to Fit/Zoom Y to View all act on the active stripe only.
- Each active signal gets its own Y-axis on the right, colored to match its curve; dragging a Y-axis pans/zooms that signal alone. Signals can be merged (one shared Y-axis) or synced (separate axes, ranges kept in lockstep) via the Active Signals Table's context menu.
- Accepts drag-and-drop: MDF/`.mvc` files, and signals dragged from the Signal Browser or between Active Signals Table segments (dropping directly onto a stripe's plot area moves/adds to that stripe).
- **Multiple measurements** (#101): once 2+ measurement files are loaded, each gets its own X-axis row stacked below the bottom-most stripe (the **Primary** measurement's row always topmost, #103), showing that measurement's real recorded time; dragging a measurement's own row pans its curves independently (wheel/box zoom always stays shared across every measurement). "Sync Measurements" (#102) collapses these rows into one shared ruler (the **Primary** measurement's, defaulting to first-loaded — set/changed via its checkbox in the Measurement Info Box) once they've been manually aligned; "Un-Sync" restores the separate rows.

---

## Cursors

- Vertical line(s), draggable, kept in lockstep across every stripe in a tab.
- On first activation: placed at the start of the time range; subsequent toggles restore the last position.
- Value label at the intersection of cursor and signal curve, shown only on whichever cursor is currently closer to the mouse pointer.
- Off-screen chevron indicators at the plot edge when a cursor (or the delta-time line) is panned out of view; clicking one jumps back to it.
- The delta-time line (difference between Cursor 1 and Cursor 2) is shown only in the active stripe, and remembers its vertical position independently per stripe.
- Left/Right arrow keys step the active cursor by a configurable amount (Preferences → Cursors).

---

## Signal Browser (Left Panel) (#103)

- A single flat, alphabetically-sorted list of every channel from every loaded measurement — no channel-group tree. A channel's original channel-group name is still shown as a hover tooltip.
- Once 2+ measurements are loaded, each row is prefixed with its measurement's short name (e.g. `[M1] Drehzahl`, `[M2] Drehzahl`) — sorting is keyed on the bare channel name, not the prefix, so identically-named channels from different measurements land next to each other. With exactly one measurement loaded, no prefix is shown.
- A measurement filter combo ("All" / one short name per measurement) appears above the list once 2+ measurements are loaded (hidden with 0 or 1); it narrows the list without reloading anything, and composes with the text filter below (both narrow together).
- A wildcard filter field (`*`/`?`) above the list narrows it further by name.
- Signals can be added to the plot via:
  - Double-click on a channel
  - Select (highlight) + click "Add Signal" button below the list
  - Drag one or more selected channels onto a Plot Stripe or the Active Signals Table
- Multi-select: `ExtendedSelection` mode — Ctrl+click (individual), Shift+click (range); a selection (and a single drag gesture) can span rows from different measurements — each channel resolves its own measurement rather than sharing one for the whole request.

---

## Measurement Info Box (Left Panel) (#103)

Below the Signal Browser in the same left panel. Always tabbed, one tab per loaded measurement — even with only one loaded, so the panel's structure doesn't change as measurements are added or removed. Each tab shows:

- A header row with a **Primary** checkbox (exactly one measurement is Primary at all times; checking a different tab's box unchecks the previous one) and an editable **short name** field (defaults "M1", "M2", ... by load order; rejects a name already used by another loaded measurement, reverting the edit).
- Below that, a right-aligned actions row (#122) with a **Replace…** button (opens a file dialog and swaps this measurement's file in place, keeping its short name/position/offset/Primary/Sync membership; every other loaded measurement is untouched) and a **Close** button (same flow/confirmation as the File ▸ Close Measurement submenu, just a second entry point).
- The existing read-only metadata below: File, MDF version, Author, Recorded, Duration, Comment, and any other MDF metadata fields present.

The Primary measurement's X-axis row is always drawn topmost in the plot area, and is the reference measurement when Sync Measurements is active. Closing the Primary measurement reassigns Primary to the first-loaded of the remaining measurements automatically.

---

## Active Signals Table (#100)

Divided into one segment per stripe, stacked top-to-bottom in the same order as their stripes, each showing only that stripe's active signals — a divider between adjacent segments aligns to the boundary between those stripes in the plot. A shared header row (same columns, kept in sync with every segment) stays fixed at the top regardless of stripe count.

| # | Column | Description |
|---|--------|--------------|
| 1 | Visibility | Eye icon button (#133) — open when the signal's curve/axis are shown, closed when hidden; click toggles it (or the whole current selection, if this row is part of one) |
| 2 | Color swatch | Small colored rectangle; clicking opens a color picker and updates curve + Y-axis color |
| 3 | Signal name | Display name from MDF metadata (prefixed with its measurement's short name once 2+ measurements are loaded) |
| 4 | Cursor 1 value | Current value at Cursor 1 position (shown only when cursor is active) |
| 5 | Cursor 2 value | Current value at Cursor 2 position (shown only when cursor is active) |
| 6 | Delta | Difference between Cursor 2 and Cursor 1 values |

- Each segment's stripe name is shown as a label above it (double-click to rename, mirroring tab renaming).
- Dragging a row within or across segments reorders it or moves the signal to a different stripe (the drop target's segment); this also relocates the signal in the plot.
- Right-click context menu: Remove Signal(s), Toggle Visibility (#133), Enable/Disable Step Mode, Shorten Signal Names (toggle), Display Name Rule…, Merge Y-Axis / Sync Y-Axis / Remove from merged-synced axis (2+ signals), Move to Stripe / Move to new Stripe.
- **Remove Signal** / **Remove All** buttons below the table (spanning all segments) remove the selected/every active signal from the table and plot.
- **Ctrl+W** toggles visibility for whichever row(s) are currently selected, each independently — a mix of visible/hidden rows ends up with each one inverted, never forced to one shared state (#133).
- Hiding a signal (#133) hides its curve and its own Y-axis (a Merged/Synced group's shared axis stays until every member is hidden); it stays fully selectable and editable, its Cursor 1/2/Delta values keep updating, and Zoom to Fit/Zoom Y to View/Swimlanes ignore its data range.
- Selection here drives the Signal Info/Properties drawer's content.

---

## Signal Info / Properties Drawer (#98)

Right-edge `DockablePanel` (pin-toggle chevron ›, or hover-reveal near the window's right edge when unpinned), shared across tabs, driven by whichever signal was most recently selected in the Active Signals Table. Two sections stacked vertically in a resizable inner splitter — both visible at once, not tabs:

- **Info** (read-only) — Name, Unit, Data type, Samples, Raster, Min, Max, Comment, and any other MDF metadata fields present. Shows a placeholder when no/multiple signals are selected.
- **Properties** (editable, disabled when no signal is selected) — Display mode (Line / Line & Marker / Marker Only), Marker shape, Line width (1–8), Line style (Solid/Dashes/Dots/Dash-Dot), and — only for signals with an enum/value table — which of Value table / Cursor label / Y-axis should show the enum's text labels instead of raw numbers. Editing with 2+ signals selected applies the change to all of them; mismatched values show a blank/"—".
- **Plugin sections** (#73) — a plugin registering a docked-mode dock widget gets one additional titled section stacked into this same splitter, alongside Info/Properties. None exist today (the plugin loader, #74, doesn't exist yet), so this drawer shows only Info/Properties in practice.

---

## Preferences Dialog

Tabbed dialog (Edit → Preferences…):
- **General** — "Check for updates on startup" checkbox; "Undo steps" spinbox (1–100, zoom/pan history depth)
- **Cursors** — cursor mode, "persistent" toggle, 4 color swatches (Cursor 1 / Cursor 2 / Cursor Left / Cursor Right chevrons), "Show ∆-Time" checkbox + its own color swatch, arrow-key step size (unit combo box + spinbox), reset-to-defaults button
