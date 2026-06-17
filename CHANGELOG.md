# Changelog

All notable changes to MDF-Viewer are documented in this file.

## [Unreleased]

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
