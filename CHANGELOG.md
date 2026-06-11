# Changelog

All notable changes to MDF-Viewer are documented in this file.

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
