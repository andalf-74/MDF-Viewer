# MDF-Viewer – UI Layout Reference

## Application Layout

```
+---------------------------+-----------------------------------------------+------------------+
| ‹ (pin/collapse button)   |  [Tab 1] [Tab 2] [+]                           |                  |
| Signal Browser (Flat/Tree)|  +---------------------+----------------+      |  Signal Info /   |
| + measurement filter      |  | Plot Stripe 1        | Active Signals |      |  Properties      |
| (2+ measurements loaded)  |  +---------------------+ Table (per-    |      |  drawer          |
|                           |  | Plot Stripe 2 (opt.) | stripe         |      |  (pin/collapse   |
| Measurement Info (tabbed) |  +---------------------+ segments)      |      |   button ›)      |
+---------------------------+-----------------------------------------------+------------------+
```

- **Left panel** (`DockablePanel`, pinned or hover-reveal overlay) – vertical splitter:
  - **Top** – Signal Browser (Flat, #103, or Tree, #141, chosen in Preferences → Signals; Flat is the default)
  - **Bottom** – Measurement Info Box (always tabbed, one tab per loaded measurement, #103)
  - Pin-toggle chevron button collapses the panel to a hidden drawer that slides out on hovering near the window's left edge
- **Center** – one `QTabWidget` (tabs #99), each tab holding an independent workspace: a horizontal splitter of `[Plot Stripes | Active Signals Table]`. A "+" tab pinned at the end creates a new tab; closing the last tab shows a "No tabs open" placeholder with its own "New Tab" button.
  - Each tab's plot area can itself be split into multiple vertically-stacked **stripes** (#97) — see "Plot Area (Stripes)" below.
  - **Pluggable tab types (#148)** — once a plugin has registered at least one tab type via `register_tab_type()`, every "New Tab" trigger (the Edit-menu action, the pinned "+" tab, and the empty-state placeholder button) shows a small popup menu listing "Plot" plus every registered type's display name, instead of immediately creating a Plot tab; with no registered types, behavior is unchanged. A non-plot tab has no Active Signals Table, no stripes, and no "still has signals" close confirmation; Duplicate Tab and Copy Signals to new Tab are unavailable for it. Its own content does not survive a `.mvc` save/restore round-trip in v1 — only its existence, name, and type — so a saved non-plot tab reappears empty on reload if its owning plugin is still loaded, or is silently dropped if not.
- **Right panel** (`DockablePanel`, mirrors the left panel's mechanism for the right edge) – the Signal Info/Properties drawer (#98), shared across every tab, showing whichever signal was most recently selected in the currently active tab.

---

## Menu Bar

- **File**
  - Open… (Ctrl+O; opens file dialog; accepts measurement file(s) and `.mvc` configs; loading with a measurement already open prompts Replace vs. Add)
  - Apply Config… (#105) — opens a file dialog filtered to `.mvc` files; applies that workspace's tabs/stripes/signal selections onto whichever measurement(s) are already loaded, without opening any file the config itself records. Prompts to map each of the config's saved measurement slots onto an already-loaded measurement (or "None" to drop it); every other loaded measurement, and the pool's own Primary/Sync state, are left untouched. Automatically opens Save Workspace As… afterward so the result can be saved as a new file. Disabled when nothing is loaded.
  - Save Workspace (Ctrl+S) / Save Workspace As… (Ctrl+Shift+S) — saves the full session to a `.mvc` file (#106): every tab (name, plot|AST divider width, AST column widths), every tab's plot-stripe layout (names/sizes/active stripe), every active signal (colors, stripe/measurement placement, axis grouping, zoom, cursor state, selection), every loaded measurement (path, short name, offset, Primary, Sync state), and window/splitter layout
  - Import Labels… / Export Labels… (#143) — bulk import/export of a Vector CANape-style `.lab` label list. Import opens a file dialog filtered to `*.lab`; each group in the file becomes a new Plot Stripe in the active tab, named after the group, populated with every candidate signal name that matches exactly against any currently loaded measurement; a group that ends up with nothing newly plotted (no matches, or every match already active) gets no stripe. A summary dialog lists not-found and already-active-skipped names, shown only when there's something to report. Export writes one group per stripe in the active tab (using the stripe's name and each signal's native channel name), skipping stripes with nothing exportable and excluding virtual signals; disabled until at least one measurement (Import) or active signal (Export) exists.
  - Replace Measurement — submenu listing every loaded *real* measurement by its short name (#122; virtual measurements excluded, #147 — they have no file to replace); selecting one opens a file dialog and swaps that measurement's underlying file in place, keeping its short name, position, offset, Primary status, and Sync membership; every other loaded measurement is untouched; disabled/empty when nothing (replaceable) is loaded
  - Close Measurement — submenu listing every loaded measurement by its short name, real or virtual (#103); selecting one closes it, warning first if it still has active signals; disabled/empty when nothing is loaded
  - Recently opened files (up to 4; shown between Open… and Preferences when non-empty)
  - Preferences… (Ctrl+, — opens Preferences dialog)
  - Exit (Ctrl+Q)
- **Edit**
  - New Tab (Ctrl+T; Ctrl+N on the MDA shortcut preset) — opens a small chooser: **Plot** (an ordinary time-based tab) or **X-Axis Signal…** (#86 — opens a signal-picker dialog first, see "Tabs" below), plus one entry per plugin-registered tab type (#148) when any exist. The pinned "+" tab at the end of the tab bar offers the identical chooser. New Stripe (Ctrl+Shift+N) (#115 — moved here from File)
  - Undo (Ctrl+Z) / Redo (Ctrl+Shift+Z) — zoom/pan history
  - Search… (Ctrl+F, #110) — opens the non-modal Search dialog, blank (see "Search Dialog" below)
  - Sync Measurements (Ctrl+M) — checkable; collapses/restores every loaded measurement's own time axis into one shared ruler (#102); disabled with fewer than 2 measurements loaded
- **Plugins** (#73, #150, #159, #160) — always present now, regardless of whether any plugin is currently active (#150 reverses the original "hidden when empty" rule, since Rescan must be reachable even from a plugins directory with nothing loaded). At the top, above a separator: **Rescan Plugins** (discovers and activates any plugin package not yet active — a new folder dropped in, or one that failed to load before, retried the same way every time), **Plugin Overview…** (#160 — disabled without a loader wired; opens a single dialog listing every plugin *package* found in the plugins directory, one row per folder, each with a checkbox showing whether it's enabled. A never-enabled package's row shows only its folder name; once it's been active at least once, the row also shows its declared name/version/description/author. A folder that's enabled but currently failing to activate shows a warning icon with the failure reason as a tooltip. Unchecking an active package deactivates it immediately — the same teardown Reload already does, including closing any of its open tabs — with no confirmation prompt; checking a disabled one activates it immediately, the same as a targeted Rescan of just that folder. Every toggle persists right away and refreshes the whole dialog from the current state, so a package that's enabled but still broken is always shown checked with its failure indicator, never silently reverted to unchecked — the app keeps retrying it on every future Rescan/restart, the same "never permanently remembered as broken" policy Rescan already has), a **Reload Plugin** submenu (lists every currently active plugin by name; disabled/empty when nothing is active; reloading stops the plugin, re-imports its code from disk, and reactivates it — closing any of its open dock section/dialog/tabs/preferences page first, and never rolling back if the fresh reactivation fails), and **Plugin Preferences…** (#159 — disabled until at least one active plugin has registered a preferences page; opens a single dialog listing one tab per such plugin, with only a Close button — each plugin's page persists its own changes immediately as it's edited, there's no separate Apply/OK step). Below the separator: one entry per plugin-registered menu action, plus one entry per plugin dialog-type dock widget (labeled "\<title\>…", opening it in a modal dialog on demand). Rescan/Reload report a brief status-bar summary of their outcome. **Check for Update…** (#76 — moved here from the Help menu when the update checker became the first-party Update Checker plugin; fetches GitHub releases API, shows an update-available dialog or an "up to date" dialog) is one of these plugin-registered menu actions, not a fixed entry.
- **Help**
  - License (Enter / View/Change)
  - About MDF-Viewer

---

## Toolbar

Order:

- **Load File** – open-file icon, opens file dialog (Ctrl+O)
- **Zoom to Fit** – resets viewport to show all active signals fully; X spans the full time range, Y auto-scales every stripe, not just the active one (Ctrl+0 / F)
- **Zoom Y to View** – auto-scales Y axes for all signals within the current X span, active stripe only (Y). Zoom to Fit and Zoom Y to View have different, fixed scopes rather than a shared toggle (#170 — the earlier "All Stripes" toggle was removed since Zoom to Fit's X reset was already global regardless of it)
- **Swimlanes** – arranges the active stripe's signals in non-overlapping horizontal swimlanes (B)
- **Zoom to Cursors** – zooms X axis to the span between the two cursors; enabled only in two-cursor mode (C)
- **Cursor Toggle** (Ctrl+R) – cycles through: 1 cursor → 2 cursors → cursors hidden → (repeat)

Keyboard shortcuts for cursors: `.` toggles Cursor 1 (HIDDEN↔ONE, TWO→ONE), `,` toggles Cursor 2 (HIDDEN/ONE→TWO, TWO→HIDDEN). Left/Right arrow keys step the active cursor (step size configurable in Preferences).

A per-stripe "Sync"/"Un-Sync" button also floats in the corner of the measurement-axis area at the bottom of the plot, mirroring the Edit menu's "Sync Measurements" action (#102) — see `docs/architecture.md`'s "Measurement Synchronization" entry.

---

## Status Bar (#125)

Transient status messages (e.g. "Workspace saved to X", plugin rescan/reload results) show briefly on the status bar as before. An always-visible button on the **left** side of the status bar opens the non-modal **Status Message History** dialog — every message shown this session, each prefixed with its `HH:MM:SS` timestamp, in a read-only, selectable text area. The dialog live-updates as new messages arrive while it stays open, and its "Copy to Clipboard" button always copies the entire history (not just a selection) — useful for pasting recent activity into a bug report. History is in-memory only and resets on the next launch; non-routine messages (most of them — routine guard messages like "No active signals to zoom" are excluded, matching the log file's own exclusion) are also written to the application log at INFO level (see the Logging entry in `docs/requirements/logging.md`). Only one instance of the dialog exists per session — clicking the button again while it's open raises the existing window instead of opening a second one.

---

## Tabs (#99)

- Each tab is an independent workspace: its own plot stripes, Active Signals Table, active-signal list, zoom/cursor history, and axis grouping — nothing is shared between tabs except the Signal Browser, Measurement Info Box, and the Signal Info/Properties drawer.
- Double-click a tab to rename it; right-click for a context menu; drag to reorder (the "+" tab stays pinned last).
- The context menu's **"Duplicate Tab"** (#119) makes a full copy of a tab — stripes, signals (color/line style/every display property preserved), cursor, zoom, and axis grouping — sharing only the underlying measurement(s), not any plot object; the copy starts with no selection and an empty zoom undo/redo history. **"Copy Signals to new Tab"** (#119, disabled when the source tab has no active signals) instead opens a new tab with a single stripe holding every one of the source's signals flattened into it, keeping their display properties but none of the source's stripe layout, zoom, cursor, or axis grouping. Both insert the new tab immediately after the source, named "Copy of \<source name\>", and continue the source's color sequence for any signal added afterward.
- Closing a tab that still has active signals asks for confirmation first; closing the last tab shows the "No tabs open" placeholder.
- Ctrl+Tab / Ctrl+Shift+Tab cycle through tabs.
- The measurement pool (loaded MDF files), the Sync Measurements state, and which measurement is Primary (#103) are global, shared across every tab — only the plot/signal/zoom state above is per-tab.
- **X-Axis Signal tabs** (#86) are a second built-in tab type, alongside the ordinary Plot type — created via the "X-Axis Signal…" chooser option (see "Menu Bar" above) or by right-clicking a single active signal in the Active Signals Table and choosing **"Promote to X-Axis Signal Tab…"** (copies that signal to become the new tab's axis — the original stays plotted, unaffected, in its own tab; a full move would only make sense within one plot view, e.g. "Move to new Stripe", not across two independent ones). The shared X-axis shows the chosen "axis signal"'s own recorded value instead of time; every other signal's curve is plotted at that axis signal's own recorded instants, in the axis signal's own recorded order — so a non-monotonic axis signal (e.g. vehicle speed, which rises, falls, and can sit at zero) can visually loop back on itself, matching MDA/CANape's signal-vs-signal plots. Cursors, zoom, and arrow-key stepping all work normally; a cursor's position is still a genuine point in time internally, just rendered at the axis signal's value at that time. The axis signal itself can't be changed once the tab is created — pick a different one via a new tab instead. Full stripe/Merged-Synced-axis/Swimlanes/multi-measurement support and `.mvc` persistence parity with ordinary Plot tabs. See `docs/requirements/x-axis-signal.md` for the complete spec.

---

## Plot Area (Stripes) (#97)

- The plot area can be split into multiple vertically-stacked **stripes**, each with its own independent Y-axes, sharing one X-axis and one pair of cursors across all of them. "New Stripe" (Edit menu) or a stripe's own right-click context menu adds one; a stripe's context menu can also delete it (the last remaining stripe can't be deleted; deleting one that still has signals asks for confirmation).
- Right-clicking inside a stripe shows PyQtGraph's standard plot context menu (view-all, per-axis auto-range, grid) minus "Mouse Mode" (fixed to pan), plus "Create new Stripe" / "Delete this Stripe".
- Clicking inside a stripe makes it the active one (colored marker on its left edge) — Swimlanes, box-zoom, and Zoom Y to View all act on the active stripe only; Zoom to Fit's Y-autorange always acts on every stripe.
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

## Signal Browser (Left Panel) (#103, #141)

Two display modes, chosen via Preferences → Signals → "Signal Browser view" (Flat/Tree combo, applies immediately on OK, no restart); **Flat is the default**.

**Flat mode (#103):**
- A single flat, alphabetically-sorted list of every channel from every loaded measurement — no channel-group tree. A channel's original channel-group name is still shown as a hover tooltip.
- Once 2+ measurements are loaded, each row is prefixed with its measurement's short name (e.g. `[M1] Drehzahl`, `[M2] Drehzahl`) — sorting is keyed on the bare channel name, not the prefix, so identically-named channels from different measurements land next to each other. With exactly one measurement loaded, no prefix is shown.
- A channel belonging to a virtual (plugin-contributed, not file-backed) measurement is marked with a `(virtual)` prefix on the channel name (#147) — shown regardless of whether the `[label]` prefix itself is shown, so a lone virtual measurement isn't mistaken for a real one with no other measurement loaded for contrast.
- A measurement filter combo ("All" / one short name per measurement) appears above the list once 2+ measurements are loaded (hidden with 0 or 1); it narrows the list without reloading anything, and composes with the text filter below (both narrow together).

**Tree mode (#141):**
- Each loaded measurement is a top-level, collapsible node (its own label carries the short name and `(virtual)` marker, so channel/group rows underneath stay plain); its channel groups are child nodes; its channels are leaves — reflecting the file's own hierarchy and order, not an alphabetical resort.
- A measurement node starts expanded, its channel-group children start collapsed.
- No measurement filter combo — a measurement's own node is already collapsible.
- Typing a match into the filter field auto-expands the ancestor group/measurement of any match; clearing the filter collapses back to the default state.
- Only channel (leaf) rows are selectable/addable/draggable — a Channel Group or Measurement node exists purely to organize the hierarchy and can't be bulk-selected.

**Both modes:**
- A wildcard filter field (`*`/`?`) above the list narrows it further by name.
- Signals can be added to the plot via:
  - Double-click on a channel
  - Select (highlight) + click "Add Signal" button below the list
  - Drag one or more selected channels onto a Plot Stripe or the Active Signals Table
- Multi-select: `ExtendedSelection` mode — Ctrl+click (individual), Shift+click (range); a selection (and a single drag gesture) can span rows from different measurements — each channel resolves its own measurement rather than sharing one for the whole request.
- **Ctrl+C** (#163) copies the raw channel name(s) — no `[M1]` measurement prefix, no unit — of the current selection to the system clipboard, one per line; a status bar message reports how many were copied. No-op with nothing selected.

---

## Measurement Info Box (Left Panel) (#103)

Below the Signal Browser in the same left panel. Always tabbed, one tab per loaded measurement — even with only one loaded, so the panel's structure doesn't change as measurements are added or removed. Each tab shows:

- A header row with a **Primary** checkbox (exactly one measurement is Primary at all times; checking a different tab's box unchecks the previous one), an editable **short name** field (defaults "M1", "M2", ... by load order; rejects a name already used by another loaded measurement, reverting the edit), and a `(virtual)` badge (#147) shown only for a plugin-contributed measurement with no real file behind it.
- Below that, a right-aligned actions row (#122) with a **Replace…** button (opens a file dialog and swaps this measurement's file in place, keeping its short name/position/offset/Primary/Sync membership; every other loaded measurement is untouched — disabled for a virtual measurement, #147, since it has no file to browse to) and a **Close** button (same flow/confirmation as the File ▸ Close Measurement submenu, just a second entry point).
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
- Right-click context menu: Copy Name(s) (#163), Remove Signal(s), Toggle Visibility (#133), Y Autozoom (#142), Search… (#110 — opens the Search dialog pre-filled for the selected signal(s), see "Search Dialog" below), Enable/Disable Step Mode, Shorten Signal Names (toggle), Display Name Rule…, Merge Y-Axis / Sync Y-Axis / Remove from merged-synced axis (2+ signals), Move to Stripe / Move to new Stripe, Promote to X-Axis Signal Tab… (#86 — single-signal selection only; see "Tabs" above).
- In an X-Axis Signal tab (#86), a pinned, non-removable "(X-axis)" row is shown above the stripe-segmented area for that tab's axis signal — same columns as an ordinary row, including its own live Cursor 1/2/Delta values, but excluded from drag-reorder, removal, and every other-signal-scoped context-menu action.
- **Remove Signal** / **Remove All** buttons below the table (spanning all segments) remove the selected/every active signal from the table and plot.
- **Ctrl+W** toggles visibility for whichever row(s) are currently selected, each independently — a mix of visible/hidden rows ends up with each one inverted, never forced to one shared state (#133).
- **Ctrl+D** (or the "Y Autozoom" context-menu entry) rescales the Y-axis of whichever row(s) are currently selected to fit the data visible within the current X range, applied independently to each selected signal's own axis (or its whole Merged/Synced group, if it's in one) (#142).
- **Ctrl+C** (or the "Copy Name(s)" context-menu entry, #163) copies the raw channel name(s) of the current selection to the system clipboard, one per line; a status bar message reports how many were copied. The keyboard shortcut is a no-op with nothing selected; the context-menu entry falls back to the right-clicked row instead, matching every other entry in this menu.
- Hiding a signal (#133) hides its curve and its own Y-axis (a Merged/Synced group's shared axis stays until every member is hidden); it stays fully selectable and editable, its Cursor 1/2/Delta values keep updating, and Zoom to Fit/Zoom Y to View/Swimlanes ignore its data range.
- Selection here drives the Signal Info/Properties drawer's content.

---

## Search Dialog (#110)

Non-modal, singleton — reachable via Edit → Search… (Ctrl+F, rebindable) or the Active Signals Table's "Search…" context-menu entry; triggering either while it's already open brings it to the front instead of opening a second one, but always rebuilds its row list fresh from whichever tab is current at that moment. A "Searching in: `<tab name>`" label always shows which tab a Search click will actually affect.

- One row per signal currently active in the current tab (across all its stripes): the signal's display name (the same shortened + measurement-prefixed name shown in the Active Signals Table, not the raw channel name), an operator dropdown (`=`, `≠`, `>`, `<`, `≥`, `≤`, defaulting to `=`), and a value field. Leaving a row's value blank excludes that signal from the search (the default state).
- Any change to which tab is active while the dialog is open — switching to a different existing tab, the tab the dialog was searching in being closed (some other tab always becomes active in that case), or a new tab becoming active as a side effect of its own creation (New Tab, Duplicate Tab, Copy Signals to New Tab) — rebuilds it for the newly active tab: a row whose signal name also exists in the new tab carries its operator/value forward, an unmatched old row is dropped, and each of the new tab's signals with no match gets a fresh blank row. Closing the tab the dialog was searching in when it was the only tab left open (no other tab to fall back to) closes the dialog itself instead.
- The Active Signals Table's context-menu entry pre-fills the selected signal(s)' rows with `=` and their current Cursor 1 value (blank if no cursor is currently shown), letting a value combination already visible on the plot be turned directly into a search.
- **Search** (disabled while every row is blank) scans for the first timestamp where every non-blank row's condition holds simultaneously (an AND conjunction), scanning from the beginning of the time range on the first click and from just after the previous match on a repeated click with unchanged criteria ("find next"); changing any operator or value restarts from the beginning.
- On a match, Cursor 1 (or Cursor L, if delta-time cursor labeling is on) jumps to that timestamp — auto-enabling from hidden if needed, leaving Cursor 2/R untouched — and the plot recenters on it at the current zoom width, across every stripe in the tab (they share one X-axis). In an X-Axis Signal tab (#86), recentering uses the axis signal's own value at that timestamp, since that tab type's shared X-axis isn't time. The dialog stays open either way; when nothing matches, an inline "No match found" message appears instead.

---

## Signal Info / Properties Drawer (#98)

Right-edge `DockablePanel` (pin-toggle chevron ›, or hover-reveal near the window's right edge when unpinned), shared across tabs, driven by whichever signal was most recently selected in the Active Signals Table. Two sections stacked vertically in a resizable inner splitter — both visible at once, not tabs:

- **Info** (read-only) — Name, Unit, Data type, Samples, Raster, Min, Max, Comment, and any other MDF metadata fields present. Shows a placeholder when no/multiple signals are selected.
- **Properties** (editable, disabled when no signal is selected) — Display mode (Line / Line & Marker / Marker Only), Marker shape, Line width (1–8), Line style (Solid/Dashes/Dots/Dash-Dot), and — only for signals with an enum/value table — which of Value table / Cursor label / Y-axis should show the enum's text labels instead of raw numbers. Editing with 2+ signals selected applies the change to all of them; mismatched values show a blank/"—".
- **Plugin sections** (#73) — a plugin registering a docked-mode dock widget gets one additional titled section stacked into this same splitter, alongside Info/Properties. None exist today (the plugin loader, #74, doesn't exist yet), so this drawer shows only Info/Properties in practice.

---

## Preferences Dialog

Tabbed dialog (Edit → Preferences…). Reopens on whichever tab was showing
when it was last closed (#169, OK or Cancel either way) — session-only, so
it starts back on the first tab after an app restart:
- **General** — "Undo steps" spinbox (1–100, zoom/pan history depth). The "Check for updates on startup" checkbox that used to live here moved to the Update Checker plugin's own tab in Plugins → Plugin Preferences… (#76) — a separate dialog, not a tab of this one. "Enable logging" checkbox + log level combo box (DEBUG/INFO/WARNING/ERROR, grayed out while disabled) + "Open log folder" button (#126 — opens the log file's folder in the OS file browser, creating it first if it doesn't exist yet; always enabled, independent of the checkbox, so old logs stay reachable after disabling). Changes to the logging controls apply immediately, no restart required.
- **Cursors** — cursor mode, "persistent" toggle, 4 color swatches (Cursor 1 / Cursor 2 / Cursor Left / Cursor Right chevrons), "Show ∆-Time" checkbox + its own color swatch, arrow-key step size (unit combo box + spinbox), reset-to-defaults button
- **Signals** — "Signal Browser view" combo box (Flat/Tree, #141, defaults to Flat), Z-Order combo box (which Active Signals Table row renders on top), selected-signal line-width boost spinbox, "Show only selected signal's Y-axis" checkbox, plot background color swatch + reset-to-default button (#117, defaults to black), Display Name Rule controls (enable toggle, separator/direction/segment count, live preview)
- **Shortcuts** (#111, #167) — one row per rebindable action (26 total: every existing keyboard shortcut in the app except Copy Name(s)/Ctrl+C, which stays fixed and isn't rebindable), each with a primary and secondary key field, aligned in fixed columns regardless of each row's label length. Click a field, then press the desired key combination to capture it — no typing. A preset dropdown (Default / MDA / CANape) instantly loads that preset's bindings into every row; "Load…"/"Save As…" buttons read/write a named `.mvck` file so a custom set can be shared. Each row has its own "Reset" button, plus one "Reset All to Defaults" for the whole tab. Assigning a key already used by another action is rejected with a dialog naming the conflicting action — no two actions can ever share a key. A status line shows which preset the current set matches, or "Custom" once anything has been hand-edited. Takes effect immediately on OK, no restart.
