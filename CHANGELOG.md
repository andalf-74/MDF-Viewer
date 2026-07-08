# Changelog

All notable changes to MDF-Viewer are documented in this file.

## [Unreleased]

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
