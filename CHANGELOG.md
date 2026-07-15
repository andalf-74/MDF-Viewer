# Changelog

All notable changes to MDF-Viewer are documented in this file.

## [Unreleased]

### Fixed
- Raster detection (#145): a signal's raster is no longer misdetected as
  "variable" when it's actually fixed-rate but has occasional dropped
  samples (e.g. a bus signal that skips a frame under load) — detection now
  uses the median sample interval and tolerates gaps that are clean
  multiples of it, instead of a mean that dropped frames could drag off the
  true rate.

## [2.2] - 2026-07-12

### Added
- Plot Stripes (#97): the plot area can now be split into multiple
  vertically-stacked stripes, each with its own independent Y-axes, sharing
  one X-axis and one pair of cursors across all of them.
  - "Create new Stripe" / "Delete this Stripe" from the plot area's
    right-click menu; the last remaining stripe can't be deleted, and
    deleting a stripe that still has signals asks for confirmation first.
  - Drag a signal from the Signal Browser onto a specific stripe to add it
    there directly (the stripe highlights while dragging); double-clicking a
    signal adds it to the currently active stripe.
  - "Move to Stripe" / "Move to new Stripe" added to the Active Signals
    Table's context menu.
  - Clicking inside a stripe makes it the active one, shown by a colored
    marker on its left edge; only the bottom-most stripe shows the X-axis
    time labels.
  - Cursor lines and their value labels stay in lockstep across every
    stripe; the delta-time line is shown only in the active stripe and
    remembers its vertical position independently per stripe.
  - A new "All Stripes / Active Stripe" toolbar toggle controls whether
    "Zoom to Fit" and "Zoom Y to View" apply to every stripe or only the
    active one; Swimlanes and box-zoom always stay scoped to the stripe
    they were used in. Merge/Sync Y-Axis is confined to signals sharing one
    stripe.
  - `docs/requirements/plotting.md` gained a new "Plot Stripes" section
    (REQ-PLOT-180 through 212) plus amendments to existing zoom/selection/
    grouping requirements to describe the multi-stripe scoping rules.
- Side Drawer for Signal Info / Properties (#98): the Info/Properties panel
  moved out of the Active Signals Table's own splitter into a full-height
  drawer to its right, so the table can grow vertically regardless of how
  many stripes exist.
  - The drawer pins (docked) or unpins (hover-reveal overlay at the
    window's right edge) exactly like the existing Signal Browser /
    Measurement Info panel on the left — that shared mechanism was
    extracted into a new reusable `DockablePanel`.
  - Within the drawer, Info and Properties are stacked vertically behind
    bold section headers instead of tabs, divided by a user-resizable
    splitter, so both are visible at once.
  - Pinned/unpinned state, width, and the inner Info/Properties split are
    all saved to and restored from `.mvc` session files.
  - A long, space-less signal name or comment no longer forces the drawer
    wider than its column — value labels now wrap/shrink to fit instead of
    propagating their unwrapped width as a hard minimum.
  - `docs/requirements/plotting.md` gained a new "Info/Properties Drawer"
    section (REQ-PLOT-220 through 229).
- Main Widget Tabs (#99): the plot area now lives in a tab bar, so multiple
  independent workspaces on the same measurement — different signal
  selections, different stripe layouts — can be built side by side.
  - Each tab keeps its own signal selection, stripe layout, cursors,
    zoom/pan view, and zoom undo/redo history; the same channel can be
    active in more than one tab at once. The Signal Browser, Measurement
    Info Box, and the Info/Properties drawer stay shared across all tabs —
    the drawer restores whichever signal was last selected in a tab when
    switching back to it.
  - New tabs via a "+" control pinned at the end of the tab bar or File →
    New Tab; auto-named "Tab 1", "Tab 2", … and renamable via double-click
    or the tab's right-click menu. Tabs can be dragged to reorder.
    Ctrl+Tab / Ctrl+Shift+Tab cycles between them.
  - Closing an empty tab needs no confirmation; closing one with active
    signals asks "Close anyway?" first. Closing a tab activates the one to
    its left (or the next remaining tab if it was first); closing the last
    tab shows a "No tabs open" placeholder with its own "New Tab" action.
  - Loading a new measurement file preserves every tab's stripe layout and
    re-resolves each tab's signals by name against the new file
    independently, the same way single-tab "keep signals" restore already
    worked.
  - `docs/requirements/plotting.md` gained a new "Main Widget Tabs" section
    (REQ-PLOT-230 through 260).
- Near-match signal resolution on reload (#109): when keeping active
  signals across a file reload (or restoring a `.mvc` config) and a signal
  isn't found by exact name, the app now also checks for a signal recorded
  under a different protocol or source — same name up to the last `\`,
  differing only in what follows it (e.g. `...\ETKC:1` vs `...\XCP:1`).
  Any such near-matches found are shown in one confirmation dialog listing
  original name → matched name, with a checkbox per row (checked by
  default); declined or unmatched signals still end up in the existing
  "signals not found" summary.
  - `docs/requirements/file-handling.md` gained REQ-FILE-032 through 036.
- "New Stripe" File-menu action (#112): a new plot stripe can now be
  created from the File menu, in addition to the existing plot-area
  right-click menu and "Move to new Stripe" — adds to whichever tab is
  currently active.
- Per-Stripe Active Signals Table (#100): the Active Signals Table is now
  split into one segment per plot stripe, each positioned directly beside
  its stripe, sharing one fixed column header at the top of the whole
  table area.
  - Every segment's divider tracks its stripe's divider exactly — dragging
    either one resizes both in lockstep, and a segment with more signals
    than fit in its height scrolls independently without disturbing the
    header or other segments.
  - A multi-row selection can span more than one segment (Ctrl-click to
    build it); dragging a row moves it within its segment or onto a
    different segment's stripe — including dragging a whole cross-segment
    selection together. Dropping a signal from the Signal Browser directly
    onto a segment adds it to that segment's stripe. Clicking anywhere in
    a segment makes its stripe the active one.
  - Each stripe now has a name, shown as a label on its segment
    (auto-named "Stripe 1", "Stripe 2", … by creation order, never reused
    or renumbered) and renamable by double-clicking the label; the
    existing "Move to Stripe" context-menu submenu lists stripes by this
    name instead of position.
  - `docs/requirements/plotting.md` gained a new "Per-Stripe Active
    Signals Table" section (REQ-PLOT-270 through 280) and a "Stripe
    Naming" section (REQ-PLOT-290 through 294).
- Multi-Measurement Loading (#101): multiple MDF files can now be loaded
  and displayed together, each independently pannable relative to the
  others.
  - File ▸ Open now allows selecting multiple files at once; once at
    least one measurement is already loaded, opening or dropping another
    file asks whether to Replace every currently loaded measurement or
    Add the new one(s) alongside them. Loading multiple files at once
    loads every file that succeeds and reports the rest together in one
    error dialog, rather than aborting on the first failure.
  - Each loaded measurement gets its own X-axis row, stacked below the
    plot; dragging a measurement's own row pans its curves independently
    of every other measurement, while wheel/box zoom always stays shared
    across all of them. Cursor values stay correct regardless of how far
    a measurement has been panned.
  - The Signal Browser gains a measurement selector above the channel
    tree once more than one measurement is loaded, so signals from any
    loaded measurement can be added to any stripe or tab (superseded by
    #103's unified flat list before release, within this same
    unreleased cycle).
  - Once two or more measurements are loaded, every active signal's
    displayed name (Active Signals Table, Signal Info Box) is prefixed
    with its measurement's label so identically-named channels from
    different files stay distinguishable.
  - Carrying active signals over on a multi-file Replace (the existing
    "keep signals" preference) now disambiguates a name that matches in
    more than one of the newly-loaded measurements via the existing
    channel-group picker, extended to show which measurement each
    candidate belongs to.
  - `.mvc` session save/restore now covers the full multi-measurement
    workspace (#106).
  - `docs/requirements/file-handling.md` and `docs/requirements/
    plotting.md` gained new "Multiple Measurements" sections
    (REQ-FILE-010 through 028, REQ-PLOT-300 through 309) and
    `docs/requirements/signal-browser.md` gained REQ-BROWSER-050 through
    052.
- Measurement Synchronization (#102): once two or more measurements are
  loaded and manually panned into visual alignment, a "Sync" button
  (bottom-right corner of the plot, next to the measurement axis rows) or
  the Edit menu's "Sync Measurements" collapses every measurement's own
  time axis into a single shared ruler, showing the first-loaded
  measurement's real time. "Un-Sync" restores the separate rows at
  whatever offsets they already had — synchronizing never changes any
  measurement's offset, only how the rows are displayed. Now saved to
  `.mvc` as part of the session workspace (#106).
  - `docs/requirements/plotting.md` gained a "Measurement Synchronization"
    section (REQ-PLOT-310 through 316).
- Signal Browser multi-measurement unification (#103): once two or more
  measurements are loaded, the Signal Browser is now a single flat,
  alphabetically-sorted list of every loaded measurement's channels,
  replacing the previous one-measurement-at-a-time selector.
  - Each channel is prefixed with its measurement's short name (e.g.
    `[M1] Drehzahl`, `[M2] Drehzahl`) once 2+ measurements are loaded;
    sorting is keyed on the channel name itself, so identically-named
    channels from different measurements land next to each other. A
    channel's channel-group is now shown as a hover tooltip instead of
    organizing the list into a tree.
  - A measurement filter above the list narrows it to "All" or one
    specific measurement, composing with the existing text filter rather
    than overriding it. A selection (or a single drag) can span channels
    from different measurements at once.
  - Each loaded measurement now has an editable short name (defaults
    "M1", "M2", ... by load order; rejects a name already in use by
    another loaded measurement) instead of a fixed file-derived label,
    editable from the Measurement Info Box.
  - The Measurement Info Box is now always tabbed, one tab per loaded
    measurement (even with only one loaded), each with the short-name
    editor and a new "Primary Measurement" checkbox — exactly one
    measurement is Primary at all times. The Primary measurement's X-axis
    row is always drawn topmost, and is the reference measurement for
    Sync Measurements; closing the Primary measurement reassigns it to
    the first-loaded of whatever remains automatically.
  - File ▸ Close Measurement is a new submenu listing every loaded
    measurement by its short name; selecting one closes it, warning first
    if it still has active signals.
  - `docs/requirements/signal-browser.md`, `file-handling.md`, and
    `plotting.md` gained/amended requirements to describe the flat list,
    short-name editability, and Primary Measurement (REQ-BROWSER-010–054,
    REQ-FILE-027/029, REQ-PLOT-300–322).
- Workspace/Configuration format extension (#106): saving and loading a
  `.mvc` session now covers the entire workspace, not just the active
  tab and first-loaded measurement.
  - A saved session captures every tab (name, plot|AST divider width,
    Active Signals Table column widths), every tab's plot-stripe layout
    (stripe names/sizes/active stripe), every active signal's stripe and
    measurement placement, and the full loaded-measurement pool (path,
    short name, time offset, Primary designation, Synchronize
    Measurements state) — restoring a session replaces the entire
    application state, the same way opening a `.mvc` file already
    replaced the single active tab's state before.
  - "Save Config" / "Save Config As…" renamed to "Save Workspace" /
    "Save Workspace As…" to reflect the broader scope; the `.mvc` file
    extension is unchanged.
  - A session referencing more than one measurement, where one or more
    can't be found, shows a single combined dialog listing every missing
    file with the option to continue without them or cancel the whole
    load, rather than prompting to locate each one individually — a
    session with exactly one measurement keeps the existing
    locate-file-interactively behavior.
  - A session saved before this extension (a single tab, single
    measurement, flat shape) still loads correctly into one default tab
    and stripe.
  - `docs/requirements/file-handling.md` gained a new "Session Scope:
    Stripes, Tabs, and Multi-Measurement" section (REQ-FILE-090–098,
    amended after live-testing to also cover the AST divider/column
    widths and to extend measurement-disambiguation to zoom ranges and
    axis groups, not just channel resolution).
- Two new tab-context-menu actions for viewing the same signals a
  different way without rebuilding the selection from scratch (#119):
  - **"Duplicate Tab"** makes a full copy of a tab — every active signal
    (color, line style, and every other display property preserved),
    stripe layout, cursor mode/positions, current zoom/pan view, and axis
    grouping (merged/synced Y-axis groups) — sharing only the underlying
    loaded measurement(s), not any plot object. The copy starts with no
    signal selected and an empty zoom undo/redo history.
  - **"Copy Signals to new Tab"** (disabled when the source tab has no
    active signals) instead opens a new tab with a single stripe holding
    every signal from the source, flattened across all of its stripes,
    keeping each signal's display properties but none of the source's
    stripe layout, zoom, cursor, or axis grouping.
  - Both insert the new tab immediately after the source tab, name it
    "Copy of \<source name\>", and continue the source tab's color
    sequence for any signal added to the new tab afterward.
  - `docs/requirements/plotting.md` gained a new "Duplicating and Copying
    Tabs" section (REQ-PLOT-262 through 269).
- Replacing a loaded measurement's file no longer requires discarding every
  other loaded measurement (#122): a new **File ▸ Replace Measurement**
  submenu, and a matching **"Replace…"** button on that measurement's own
  tab in the Measurement Info Box, swap just that one measurement's
  underlying file in place.
  - The replaced measurement keeps its short name, load-order position,
    X-axis offset, Primary status, and Synchronized membership — every
    other loaded measurement is completely untouched.
  - The replaced measurement's own active signals follow the existing
    "keep active signals on replace" preference (always/ask/never) and
    by-name/near-match resolution, scoped to just that measurement.
  - If the newly selected file fails to open, the measurement being
    replaced (and everything else) is left exactly as it was.
  - A matching **"Close"** button was also added to the Measurement Info
    Box tab, alongside "Replace…" — an additional entry point for the
    existing File ▸ Close Measurement behavior, not a behavior change.
  - `docs/requirements/file-handling.md` gained a new "Replacing a Single
    Measurement" section (REQ-FILE-100 through 108).
- A saved workspace (`.mvc`) can now be applied onto measurements that are
  already loaded, instead of always re-opening the files it records (#105):
  a new **File ▸ Apply Config…** menu item opens a file dialog filtered to
  `.mvc` files.
  - Before anything is applied, a dialog maps each of the saved workspace's
    measurement slots onto an already-loaded measurement (or "None" to
    drop it) — every slot always offers every loaded measurement, and
    picking one already assigned elsewhere reassigns it here, resetting
    the other slot to "None".
  - The applied workspace's tabs, stripes, and signal selections replace
    the current ones entirely, the same as opening a `.mvc` normally does;
    signals resolve against whichever measurement each slot was mapped to,
    using the existing by-name/near-match resolution and "signal not
    found" reporting.
  - The currently loaded measurement pool itself — including which
    measurement is Primary and whether Synchronize Measurements is
    active — is left completely untouched; no measurement file is ever
    opened by this action.
  - A "Save Workspace As…" dialog opens automatically afterward so the
    result can be saved as a new file; the original applied `.mvc` is
    never silently overwritten by a later plain "Save Workspace".
  - `docs/requirements/file-handling.md` gained a new "Applying a Config
    to Already-Loaded Measurements" section (REQ-FILE-110 through 119).
- An active signal can now be temporarily hidden — curve and its own
  Y-axis both disappear — without removing it from the Active Signals
  Table or losing any of its display settings (#133).
  - A new eye-icon button, leftmost in each Active Signals Table row,
    toggles it; so does a new "Toggle Visibility" entry in the table's
    right-click context menu, and the **Ctrl+W** shortcut for whichever
    row(s) are currently selected — each selected signal toggles its own
    state independently, never forced to one shared state.
  - A signal sharing a Merged or Synced Y-axis group with at least one
    still-visible signal keeps that shared axis visible; it disappears
    only once every member of the group is hidden.
  - Zoom to Fit, Zoom Y to View, and Swimlanes all ignore a hidden
    signal's data range.
  - A hidden signal stays fully selectable and editable (Properties,
    recolor, etc.), and its Cursor 1/2/Delta values keep updating live.
  - Hidden/visible state is saved and restored per signal as part of a
    workspace (`.mvc`), the same as its color/line-style/display-mode.
  - `docs/requirements/plotting.md` gained a new "Signal Visibility"
    section (REQ-PLOT-330 through 339).

### Changed
- Renamed the "Share Y-axis" / "Link Y-axes" context menu actions in the
  Active Signals Table to "Merge Y-Axis" / "Sync Y-Axis" for clearer,
  more predictive naming (#90). "Merge" implies becoming one axis;
  "Sync" implies staying separate but moving together.
  `docs/requirements/plotting.md` (REQ-PLOT-030 through REQ-PLOT-037)
  updated to match.
- Renamed the internal Share/Link identifiers left in place by #90 to
  match: Qt signals, controller/handler methods, `PlotArea` internals
  (`_shared_groups`/`_linked_groups`, `share_signals`/`link_signals`,
  `get_shared_signals`/`get_linked_signals`, etc.), `ViewerConfig` fields,
  and the `.mvc` session file's `"shared"`/`"linked"` JSON keys — all now
  `merged`/`synced` (#95). Since negligible real-world `.mvc` usage
  existed at the time, this was a straight rename with no migration: a
  `.mvc` file saved with the old JSON keys still loads without error, but
  its axis grouping silently comes back empty (everything else in the
  session restores normally).

### Fixed
- The "All Stripes" toolbar toggle sat between "Zoom Y to View" and
  "Swimlanes," leaving it ambiguous which actions it actually governed
  (#114). Moved next to "Load File," ahead of "Zoom to Fit"/"Zoom Y to
  View" (the two actions it controls), with a new separator after "Zoom Y
  to View" bracketing them off from "Swimlanes" and the cursor actions.
- "New Tab" and "New Stripe" lived in the File menu; moved to the Edit
  menu, which fits their workspace-creation purpose better (#115).
- Using Swimlanes after splitting signals across multiple stripes could
  crash the whole application with a native segfault, no Python traceback
  (#120). Root cause: three separate places in `plot_stripe.py`
  (`_destroy_vb_and_axis`, `set_measurement_axes`, `set_axis_padding`'s
  alignment spacer) tore down a `ViewBox`/`AxisItem` via `removeItem()`/
  `hide()` alone, which only detaches it from layout/scene/visibility —
  never destroying the underlying Qt object. The orphaned-but-alive item
  stayed wired into cross-stripe X-range-sync signals and eventually
  crashed when something else touched it. All three now `deleteLater()`
  properly. While scanning for the same leak class elsewhere, also found
  and fixed: closing a tab never destroyed its widgets or ran its
  still-active signals through the normal removal pipeline first,
  silently leaking the whole tab's plot and Active Signals Table.
  `docs/architecture.md`'s "PyQtGraph/Qt Teardown Pitfall" decision-log
  entry has the full technical detail.
- A follow-up architecture review found the same #120-class teardown gap
  in the cursor value labels (#134): four sites in `CursorStripesView`
  removed a label from its ViewBox without ever destroying it, the same
  orphaned-but-alive risk as above. Not confirmed to have caused a crash
  in practice, but fixed the same way regardless.
- A short tab name (e.g. "DTI") shrank the whole tab down to barely more
  than its own close ("×") button, making it easy to click Close instead
  of switching tabs (#140). Every tab now has a minimum width regardless
  of name length; the pinned "+" new-tab tab stays compact as before.
- Dragging a signal row in the Active Signals Table between two stripes'
  segments moved the table row but left the signal's curve behind in its
  old stripe's plot; dragging a row onto a stripe's plot area directly
  (rather than onto another AST segment) was rejected outright with a
  blocked cursor (#116). The cross-segment row drag now also relocates the
  signal in the plot (REQ-PLOT-279), and dropping onto a stripe's plot area
  now moves the signal there too, appended after that stripe's existing
  signals (REQ-PLOT-281) — both paths reuse the same
  `AppController.move_signals_to_stripe` the "Move to Stripe" context-menu
  action already used, which worked correctly the whole time.
- The File menu's "Load MDF…" action (and its "Load MDF File (Ctrl+O)"
  tooltip) named only MDF files, even though it always accepted `.mvc`
  config files too. Renamed to "Open…" / "Open File (Ctrl+O)" (#113),
  matching the wording the requirements doc already used for it.
- Loading a `.mvc` config with a maximized window state, while the app was
  already maximized, left the window merely windowed instead of staying
  maximized (#107). `resize()`/`move()` on an already-maximized window can
  drop that state at the OS level, making the following `showMaximized()`
  call a no-op against Qt's stale cached window state; the window is now
  normalized first if it's currently maximized.
- A newly created tab always showed a single generic "Time" X-axis instead
  of one per loaded measurement, unlike every other tab (#124).
  `AppController.create_tab()` registered the new tab's `TabWorkspace` but
  never pushed the current measurement pool/sync state to it — that only
  happened on pool-mutation events (load/close/rename/sync-toggle/primary
  change), which a brand-new tab hadn't been part of. It now pushes that
  state immediately on creation.
- Closing the very last open tab, then creating a new one (or loading
  another measurement), could crash with `RuntimeError: wrapped C/C++
  object of type AxisItem has been deleted` (#130, found live-testing
  #124's fix). `AppController.remove_tab()` deliberately keeps the sole
  remaining `TabWorkspace` alive rather than removing it (`current_workspace`
  must never resolve to nothing), but `MainWindow` always `deleteLater()`'d
  the closed tab's widgets regardless — destroying Qt objects the
  controller still held a live reference to. Closing the last tab now
  parks its page instead of deleting it, and reuses that exact page on the
  next "New Tab" rather than registering a duplicate, orphaned workspace.
  Also fixed: a parked page left un-consumed until the app closes is now
  explicitly `deleteLater()`'d in `closeEvent()` — otherwise it stayed
  alive and wired into its signal/slot connections past its own window's
  teardown, the same orphaned-Qt-object class as #120.
- A newly created tab's Active Signals Table always showed full, unshortened,
  un-measurement-prefixed channel names, ignoring the global display-name
  shortening preference (REQ-PLOT-160) every other tab already respected
  (#131, found live-testing #119). Same root cause and same fix shape as
  #124: `AppController.create_tab()` never pushed the current display-name
  formatter to the newly registered tab — only tabs that already existed
  when the setting was last toggled got it. `create_tab()` now pushes it
  immediately, alongside #124's measurement-axis push.
- `docs/requirements/plotting.md`'s REQ-PLOT-121 incorrectly stated that
  "line only" display mode disables the line style control. It doesn't —
  only the marker shape control is disabled in that mode, which is what
  the code (`signal_info_box.py`) already did. Wording corrected to match
  the implementation; no code change.
- `MdfLoader.channel_tree()` always showed a blank unit and comment for
  channels in MDF3 files, since it read those fields directly off the
  raw channel block (correct for MDF4) instead of falling back to the
  conversion block's unit and the channel's separate description field
  the way MDF3 stores them — violating REQ-MDF-022. Found while adding the
  MDF3 test fixture from #91; `load_signal()` was unaffected since it
  reads through `mdf.get()`, which already handles this correctly.

### Test Coverage
- Added an MDF3 fixture and regression tests exercising open/channel-tree/
  load-signal for both MDF versions (#91), assertions for
  `measurement_info()`'s `author`/`comment` fields plus a metadata-read-failure
  resilience test (#92), tests for `channel_tree()`'s per-channel-skip and
  whole-hierarchy-failure paths (#93), and a test wiring the known-corrupt
  `data/faultfile.mf4` fixture into the automated suite (#94).
- Tagged all existing tests with `@pytest.mark.requirement(REQ-ID)` per
  CLAUDE.md's Requirements Workflow traceability convention, then closed
  the 9 real gaps the resulting coverage audit surfaced (#96): recent
  files list mixing `.mvc`/measurement paths (REQ-FILE-051), display-name
  shortening not affecting lookup (REQ-PLOT-162), the Active Signals
  Table's per-signal enum-display toggles (REQ-PLOT-130/131), Y-axis enum
  labels (REQ-PLOT-014), nearest-to-mouse cursor label visibility
  (REQ-PLOT-081), arrow-key stepping's reference-signal selection
  (REQ-PLOT-091), the delta-time line's midpoint tracking (REQ-PLOT-103),
  the startup update-check's background/silent-vs-reported behavior
  (REQ-NFR-031/032), the per-user settings path convention
  (REQ-NFR-041), and curve downsampling on large recordings
  (REQ-NFR-050/051). Also fixed a dead test
  (`test_single_item_label`) with no assertion, found in passing.

## [2.1.1] - 2026-07-02

### Added
- `.mvc` config files now also capture and restore the window's size,
  position, and maximized state, plus every splitter's sizes (left, right,
  content, and outer splitters) and the left panel's pinned-vs-drawer state
  and width (#77). Restoring a saved session now returns the whole window
  layout, not just the signals and axes. Captured and applied entirely by
  `MainWindow`; `ViewerConfig`/`ConfigManager` treat the data as an opaque
  blob so the Controller never needs to know what a splitter is. Older
  `.mvc` files without this data still load cleanly and keep the app's
  default window size.

### Fixed
- Splash screen icon was very blurry (#85). `QPixmap(path)` on the
  multi-resolution app icon `.ico` (16/32/48/128/256 px frames embedded)
  picked the 16x16 frame with no way to request a bigger one, then upscaled
  it ~6x to 96x96. Now uses `QIcon(path).pixmap(QSize(256, 256))` to grab
  the largest embedded frame and downscale from there instead. Also fixed
  a related HiDPI issue: the splash pixmap never set a `devicePixelRatio`,
  so on scaled displays Qt stretched the whole thing a second time; it's
  now built at the screen's actual device pixel ratio.
- The "Shorten Signal Names" preference had no effect after restarting the
  app — the checkbox showed the correct saved state once you opened
  Preferences again, but names weren't actually shortened until you
  re-toggled it (#89). `Settings.display_name_rule_enabled` was already
  being persisted and loaded correctly; nothing ever *applied* it at
  startup. `app.py` now calls `AppController.refresh_display_names()` and
  syncs the Active Signals Table's checkbox right after wiring the
  controller, before the window is shown.
  - Also added a place to remember shortening-rule *parameters*
    (separator, direction, segment count) per saved session: `.mvc` config
    files now capture and restore them via new fields on `ViewerConfig`.
    Restoring a session applies its saved rule and — since every `Settings`
    setter auto-persists — that also becomes the new global default. The
    on/off toggle itself is intentionally not part of the `.mvc` format; it
    stays governed solely by Preferences. Old `.mvc` files without these
    fields still load with the same defaults `Settings` itself uses.
- Swimlane layout, "Zoom Y to View", and "Zoom to Fit" didn't collapse a
  Linked Y-axes group into one lane/unit (#84). All three grouped active
  signals into units by unique `ViewBox` identity, which correctly
  collapses Shared groups (one literal ViewBox) but not Linked groups
  (each member keeps its own ViewBox, externally forced to match by the
  Link sync handler) — so each linked member's own `setYRange()`/
  `autoRange()` call clobbered the others, leaving whichever was processed
  last as the "winner" and wasting the layout space computed for the rest.
  Added `PlotArea._display_units()`, a shared helper that treats an entire
  Linked group as one unit (sized from the combined data of all its
  members), and rewrote `swimlanes()`, `zoom_y_to_view()`, and
  `zoom_to_fit()` to use it.
  - Along the way, found that a signal could end up in both a Shared and a
    Linked group simultaneously — nothing prevented it, though nothing was
    designed to handle it either. Closed the gap: `AppController` now
    rejects a Share/Link request if any target signal is already in the
    other group type, and `ActiveSignalsTable`'s context menu hides the
    corresponding action instead of offering something that would silently
    no-op.
- Three related Z-order/hit-testing bugs shared one root cause: click
  selection (`PlotArea._hit_test`) and native mouse routing depended on Qt's
  real scene Z-order, which doesn't compare consistently between per-signal
  `ViewBox`es and `pi.vb` (host of the cursor/delta-time lines), and collapses
  entirely when signals share one `ViewBox`.
  - The horizontal delta-time line (and, defensively, the vertical cursor
    lines) were undraggable (#78). `PlotArea` now exposes
    `register_drag_claimant()`: `CursorView` claims a left-button press via
    each line's own `sceneBoundingRect()` — sidestepping the Z-order
    comparison entirely — and drives the line's value directly instead of
    relying on pyqtgraph's native drag, which never sees a claimed press.
    This alone wasn't sufficient to fix the delta line, though: `pi.vb`
    (the ViewBox hosting these lines) auto-ranges by default, and the lines
    were added via `addItem()` without `ignoreBounds=True` — unlike the
    labels/chevrons, which already had it. Each line's own bounding box was
    feeding back into `pi.vb`'s Y auto-fit, so the view re-centered on the
    delta line's value every time it changed, cancelling out any visible
    movement and snapping it back to the vertical middle after any range
    recompute (e.g. a zoom). Cursor lines only looked fine because X kept
    getting explicitly overridden elsewhere, masking the same defect.
  - Z-order was ineffective when signals shared a Y-axis (#80): all members
    of a shared group use the *same* `ViewBox`, so stamping Z only on the
    `ViewBox` couldn't distinguish between them. Selection Z is now tracked
    per-signal (`PlotArea._z_by_signal`) and also applied to each curve, not
    just the `ViewBox`.
  - Some signals — reported after switching a signal to "Marker only" — became
    unselectable in the plot view (though still selectable in the Active
    Signals table), along with every signal ranked below it in Z-order (#81).
    Two issues, the second masking the first: `ScatterPlotItem.pointsAt()`
    requires a pixel-exact hit, far stricter than a line curve's stroked
    `mouseShape()`, so a near-miss on a marker was common; `_hit_test` now
    falls back to a small pixel-tolerance check (`_near_any_point`) around
    each rendered marker. But the near-miss case itself was crashing:
    `pointsAt()` returns a numpy array, and `if spd.curve.scatter.pointsAt(...)`
    raised `ValueError: The truth value of an empty array is ambiguous`
    whenever it returned empty — silently aborting `_hit_test`'s loop before
    it ever reached signals ranked below the marker-only one, exactly matching
    the reported symptom. Fixed by checking `.size > 0` explicitly.
- Step mode line jumped to the next sample's value one timestamp early,
  causing markers to sit at the end of their held segment instead of the
  start (#83). pyqtgraph's `stepMode` was set to `"left"` while passing
  equal-length x/y arrays; switched to `"right"` to match the zero-order-hold
  convention already used by the cursor readout in `model/interpolate.py`.
- Cursor value labels for signals in a shared-Y-axis group disappeared —
  permanently, surviving even a cursor drag — and ungrouping afterward
  lost the labels for all signals in the group, not just the ones that
  were already broken (#82). Sharing/ungrouping replaces a signal's
  ViewBox, but `CursorView.update_labels()` kept reusing the cached
  label tied to the old (now scene-detached) ViewBox instead of noticing
  the change. It now recreates the label in the signal's current
  ViewBox whenever the two no longer match. Also added the missing
  cursor refresh after Share/Link/Ungroup Y-axis actions so labels
  update immediately instead of waiting for the next cursor interaction.
- Activating Enum Display for a signal's Y-axis didn't redraw the axis
  with the enum labels until the user panned or zoomed it (#79).
  `_SignalAxisItem.set_enum_display()` called `update()`, which only
  repaints pyqtgraph's cached tick-label picture — it doesn't regenerate
  it. Now also clears the cache (`self.picture = None`) so the next
  paint rebuilds the tick strings with the new setting.

## [2.1] - 2026-06-28

### Added
- Save and load viewer configuration files (#37). The current view — active
  signals with all display state, axis grouping (shared/linked), zoom, cursor
  state, and the path to the measurement file — can be saved as a `.mvc` file
  (MDF Viewer Config, JSON format) and restored later.
  - **File → Save Config** (Ctrl+S) and **File → Save Config As…** write the
    current session to a `.mvc` file.
  - The **Open** dialog now accepts both MDF files and `.mvc` files; `.mvc`
    files also appear in the recent files list.
  - On load: if the measurement file is not found at its stored path a file
    dialog prompts the user to locate it; signals missing from the file are
    listed in a warning dialog.
  - On exit: if active signals are loaded the app prompts **Save / Don't Save /
    Cancel** (option in Preferences → General, default on).
  - Measurement path is stored as absolute or relative (Preferences → General).
  - Signal matching uses name **and** channel group name to disambiguate
    signals that share a name across multiple channel groups.
- Keep active signals when loading a new file (#36). When a new file is
  opened (via File menu or drag-and-drop), previously active signals are
  looked up by name in the new measurement and re-added with their full
  display state preserved (color, line width/style, display mode, marker
  shape, step mode, enum display options). Three behaviours are selectable
  in Preferences → General: **Always keep** (default), **Ask each time**
  (Yes/No prompt), or **Always discard**. If a signal name is found in
  multiple channel groups the user is asked to pick which group to use.
  Signals that cannot be matched are listed in a dialog with a
  "Copy to Clipboard" button.
- Shared and linked Y-axes (#16). Two or more active signals can be grouped
  from the Active Signals Table context menu (multi-select required):
  - **Share Y-axis** — all selected signals share one ViewBox and one Y-axis
    (same Y scale, zoomed together). The shared axis uses a neutral grey colour;
    shared groups count as a single swimlane.
  - **Link Y-axes** — selected signals keep their own ViewBox and axis but
    pan/zoom together to the exact same absolute Y range whenever any member's
    axis is touched.
  Both options block mismatched-unit combinations (checked in MainWindow before
  calling the controller). Selecting a member of a shared group while
  "Show only selected Y-axis" is on keeps the shared axis visible. A third
  context-menu action, "Remove from shared/linked axis", dissolves a signal
  back to its own axis; removing the last two members of a group also dissolves
  it automatically.
- Enum signal support (#40). Signals with an MDF4 value-to-text conversion
  (conversion type 7) are now recognised as enum signals. Their integer raw
  values are loaded and stored alongside a label map extracted from the
  conversion block. Three independent per-signal display options are exposed
  in the Signal Info Box → Properties tab (visible only for enum signals):
  "Value table" shows `"LABEL (n)"` in the Active Signals Table cursor-value
  columns (on by default); "Cursor label" applies the same format to the
  floating plot label near the cursor (off by default); "Y-axis" replaces
  raw integer tick values with their label text on the signal's Y-axis (off
  by default). The delta column always shows a plain numeric difference.
- Option to show only the selected signal's Y-axis (#69). When enabled in
  Preferences → Signals, all Y-axes except those belonging to the currently
  selected signal(s) are hidden and their layout columns removed, giving the
  plot more horizontal space. All axes reappear when the toggle is off or when
  no signal is selected.
- Measurement raster shown in Signal Info Box (#44). A "Raster" row appears
  in the Info tab for any signal with at least two samples. Fixed-rate signals
  show the mean interval (ms up to 500 ms, seconds above); variable-rate
  signals show "variable". Fixed-rate detection uses the 99th-percentile
  interval deviation with a 5 % tolerance, so occasional ECU jitter or
  timestamp quantization does not misclassify fixed-rate signals.
- Per-signal display mode and marker shapes (#45). Each signal can be shown as
  a line only (default), a line with markers at each sample, or markers only
  (scatter plot). Four marker shapes are available: circle, square, diamond,
  cross. Marker size scales with line thickness. Settings are per-signal and
  controlled via a new "Properties" tab in the Signal Info Box. With multiple
  signals selected, changes apply to all selected signals; mismatched values
  are shown as blank fields.
- Multi-select in the Active Signals Table (#56). Ctrl+click and Shift+click
  select multiple rows. Remove, color change, and step-mode toggle all apply
  to the entire selection. Right-click on a selected row keeps the selection
  intact and shows a context menu with "Remove Signal(s)", "Enable Step Mode",
  and "Disable Step Mode". Row drag-and-drop reordering now moves the entire
  selected block as a unit.
- Zoom undo/redo (#39). `Ctrl+Z` / `Ctrl+Shift+Z` step through zoom history;
  also available under the new Edit menu. Covers all pan, scroll, drag-rect,
  and toolbar zoom actions. Continuous gestures are coalesced into a single
  step. History depth is configurable in Preferences → General → "Undo steps"
  (default: 1).
- Arrow-key cursor stepping (#29). Left/Right keys move the most-recently-
  touched cursor by a configurable step. Step unit (Samples / Pixels / Time)
  and amount are set in Preferences → Cursors. Keys have no effect when
  cursors are hidden.
- "Persistent cursors" setting in Preferences → Cursors tab (default: on).
  When on, cursors reappear at their last position; when off, they are placed
  at 25 % and 75 % of the current viewport on every show (#59, #62).
- "Cursor L / R" mode in Preferences → Cursors tab. In this mode the left
  cursor is always yellow and reports to the "Cursor L" column; the right
  cursor is always blue and reports to "Cursor R". Colors swap dynamically
  when one cursor crosses the other. Delta is always R − L. The default
  "Cursor 1 / 2" mode keeps C1 yellow, C2 orange, and delta as C2 − C1
  regardless of position (#62).

### Fixed
- Cursors are now placed at 25 % and 75 % of the current viewport on first
  activation, instead of at the leftmost edge of the full time range (#59).
- `__version__` in `src/mdf_viewer/__init__.py` was not bumped alongside
  `pyproject.toml`, so the update checker, splash screen, and About dialog
  all reported `2.0.1` instead of `2.1`. Corrected; release artifacts
  rebuilt.

## [2.0.1] - 2026-06-22

### Fixed
- Update check now succeeds in environments with a corporate SSL inspection CA
  (e.g. company proxies). `python-certifi-win32` is added as a Windows
  dependency; it bridges the Windows certificate store into Python's SSL
  layer so internal CAs are trusted automatically (#57).

## [2.0] - 2026-06-21

### Added
- License management system (#19): Ed25519-signed `.lic` files, three tiers
  (Personal, Team 5 seats, Enterprise unlimited), perpetual license with a
  2-year update coverage window. Purely offline verification; license file
  copied to app data on import.
- `Help > Enter License Key…` / `Help > View/Change License Key…` menu action
  opens a dialog to browse for or drag-and-drop a `.lic` file (import mode)
  or view current license details including an expiry notice (view mode).
- "Retrieve License…" button in the license view dialog: opens a Save As dialog
  to export a copy of the stored `.lic` file; default filename derived from the
  licensee name (`First_Last.lic`) (#54).
- Title bar shows "MDF-Viewer — unregistered" when no valid license is present;
  clean "MDF-Viewer" when licensed.
- About dialog shows license status (licensee name, tier, updates-until date,
  or "Unregistered").
- `Help > About MDF-Viewer` moved to last position in the Help menu, with the
  license action first.
- `Help > Check for Update…`: checks the GitHub releases API and shows an
  update-available dialog (with an "Open Release Page" button) or an "up to
  date" dialog. Network errors shown as a warning dialog (#10).
- Automatic update check on startup: runs in a background thread, silent if
  up to date or on network error; shows the update-available dialog if a newer
  version is found. Can be disabled in Preferences (#10).
- `File > Preferences…`: opens the Preferences dialog. Currently contains one
  setting — "Check for updates on startup" — on the General tab. The dialog
  uses a tab layout to accommodate future preference groups (#10).

## [1.5] - 2026-06-18

### Changed
- Replaced the Swimlanes toolbar icon with a cleaner, purpose-built icon (#42).
- Collapsible left panel: the pin/unpin chevron button is now smaller and
  positioned in the top-right corner of the panel, making it less intrusive
  while remaining easy to click; font size of the `‹`/`›` glyph increased for
  readability (#41).

## [1.4] - 2026-06-18

### Added
- New toolbar button "Swimlanes" (shortcut `B`): arranges active signals in
  equal horizontal lanes, each zoomed to the data visible in the current X
  span (5 % top + 5 % bottom padding). Lane order matches the Active Signals
  Table top-to-bottom. One-shot action — interact freely after; press `B`
  again to re-apply after reordering (#15).
- Rows in the Active Signals Table can now be reordered by drag-and-drop.
  The new order is applied to the controller's signal list immediately and is
  picked up by the next Swimlanes action (#15).
- Measurement Info Box moved below the Signal Browser; Signal Info Box moved
  below the Active Signals Table. Both panels have a vertical splitter so the
  user can resize the two halves. The plot area now fills the full center
  height (#33).
- Left panel (Signal Browser + Measurement Info) is now collapsible. A `‹`
  button near the top collapses it into a drawer; in drawer mode the panel
  slides out when the mouse is within 10 px of the left window edge and
  slides back when the mouse moves away. Clicking `›` re-pins the panel into
  the layout. The slide animation uses `QPropertyAnimation` (#33).
- New toolbar button "Zoom to Cursors" (shortcut `C`): sets the X range to
  span exactly between the two active cursors. Enabled only when both cursors
  are visible; disabled otherwise (#28).

### Fixed
- Scroll wheel over a signal's Y-axis no longer zooms X; it now zooms that
  signal's Y-axis as expected. The regression was introduced in v1.3.1 when
  `_ViewBox.wheelEvent` began forcing `axis=0` unconditionally (#34).
- Right-drag zoom rectangle now zooms every signal's Y-axis to match the
  rectangle's Y extent, not just the signal whose ViewBox received the drag
  event. Each signal's undo history is also updated so the zoom participates
  in PyQtGraph's view-history stack (#35).

## [1.3.1] - 2026-06-16

### Added
- Signal browser filter now supports `*` and `?` wildcards (#5). Plain
  text still does a substring match; wildcards switch to full-pattern glob
  matching. The filter placeholder hints at this.
- Keyboard shortcuts: `f` zoom to fit, `y` zoom Y to current X span,
  `.` toggle cursor 1, `,` toggle cursor 2 (#14). The `.` and `,` keys
  each follow their own state machine rather than cycling the shared
  toolbar state.
- New toolbar button "Zoom Y to View" (shortcut `y`): rescales each
  signal's Y-axis to fit the data visible in the current X span (#22).
  Shows a status bar message when no signals are active.
- Mouse controls (#21): left drag pans, right drag opens a zoom rectangle,
  scroll wheel zooms the X axis only. The "Mouse Mode" item has been
  removed from the plot context menu since the mode is now fixed.

### Fixed
- Removing a signal left its Y-axis visible as an orphan in the plot.
  `QGraphicsGridLayout.removeItem` only detaches the axis from layout
  management; `axis.hide()` is now called explicitly to remove it from
  view (#32).
- Constant-zero signals jumped to the top edge of the plot when cursors
  were activated. Cursor value labels were added to the signal's ViewBox
  without `ignoreBounds=True`, corrupting the auto-range of the degenerate
  `[0, 0]` Y range (#32).
- Installer: creating a desktop shortcut failed with "IPersistFile::Save
  failed; code 0x80070005 / Access denied" on per-user installs (#31).
  The shortcut now uses `{autodesktop}` instead of `{commondesktop}`,
  which resolves to the current user's desktop for per-user installs.
- Installer: file associations for `.mf4`/`.mdf` now notify Explorer via
  `SHChangeNotify` so the application icon for those file types appears
  immediately, without requiring a logoff/reboot.

## [1.3] - 2026-06-11

### Added
- Toolbar icons now adapt to the OS color scheme: a dark-gray "light mode"
  variant is used unless the OS reports a dark theme, in which case the
  existing light-gray icons are used.
- A custom application icon, used for the main window, the packaged EXE,
  and the installer.
- A splash screen showing the application icon, name, and version while
  the application starts up.
- A Help > About dialog with the version, author, and a link to the
  GitHub repository.

### Fixed
- The taskbar showed `python.exe`'s icon instead of the application icon
  when running unfrozen (e.g. from a debugger); fixed by setting an
  explicit Windows AppUserModelID at startup.

## [1.2] - 2026-06-11

### Changed
- Default branch renamed from `master` to `main`; adopted a lazy
  release-branch policy (#20) — see `CLAUDE.md`.

### Fixed
- Plot performance: pan/zoom and cursor dragging were dominated by PyQtGraph
  redrawing full-resolution curves on every frame (~13s for 60 pan/zoom
  steps with 6 signals at ~77k samples each). Enabled `clipToView` and
  automatic peak-mode downsampling on each signal curve, cutting this to
  ~2.3s.
- Fixed a crash (`IndexError: list index out of range`) in the Active
  Signals Table when removing a signal (or "Remove All") while a row was
  selected.
- Signal Browser filter (#9): typing in the filter field no longer triggers
  an immediate recursive re-filter of the channel tree on every keystroke;
  filtering is now debounced (250ms after the user stops typing).
- Loading an MDF file (#9) now shows a wait cursor and a "Loading <file>…"
  status bar message for the duration of the load, so the application no
  longer appears to freeze on large measurements.

## [1.1]

- Drag-and-drop signals from the Signal Browser onto the Plot Area or
  Active Signals Table; drag-and-drop MDF files onto the Plot Area.
- Multi-select in the Signal Browser (Ctrl+click, Shift+click).
- Status bar with transient messages (e.g. duplicate-signal notifications).
- Fixed unreadable selection highlight in the Active Signals Table.
- Fixed color picker highlighting white when a signal's color is not a
  basic color.

## [1.0]

- Initial release.
