# MDF-Viewer – Project Context for Claude Code

## Project Overview

MDF-Viewer is a desktop application for visualizing ASAM MDF measurement data files (MDF3 and MDF4). It is a greenfield rewrite based on the author's prior experience with a working prototype. The goal is a clean, maintainable architecture from the start – the prototype suffered from tight coupling between data, UI, and plotting components.

The application is developed as a free, open-source project, targeting individual engineers and automotive measurement professionals.

**GitHub:** https://github.com/andalf-74/MDF-Viewer (public)

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
- **SignalMetadata** – Descriptive information about a signal: name, unit, min/max, sample count, raster, comment, and any other MDF metadata fields.
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

See [`docs/ui.md`](docs/ui.md) for full UI layout (menus, toolbar, panels, info boxes).  
See [`docs/api.md`](docs/api.md) for per-module API reference and implemented module table.  
See [`docs/architecture.md`](docs/architecture.md) for architectural decision log.  
See [`docs/release.md`](docs/release.md) for release build instructions.

---

## File Handling

- **Single file only (MVP)** – loading a new file replaces the current one
- **Recently opened files** – up to 4 entries persisted in `settings.json`; shown in File menu; stale paths pruned silently on menu open; failed loads are not recorded
- **No session persistence (MVP)** – application always starts fresh; saving/restoring active signals, colors, and window state is planned for a future version
- **Robust error handling is mandatory** – the application must never crash on malformed, incomplete, or unexpected MDF content; errors must be caught and communicated to the user gracefully

---

## MDF Support

- MDF3 and MDF4 via the `asammdf` library
- All available channel groups and signals must be represented in the Signal Browser TreeView

### Known asammdf bug — `__del__` on corrupt files

When `asammdf.MDF(path)` fails to open a corrupt file, it raises an exception midway through `MDF4.__init__` before assigning `self._file`. Python's GC later calls `MDF4.__del__`, which calls `close()`, which unconditionally accesses `self._file` — triggering:

```
Exception ignored while calling deallocator <function MDF4.__del__ ...>:
AttributeError: 'MDF4' object has no attribute '_file'
```

This is printed to stderr but does **not** affect app behaviour — `MdfLoader.open()` correctly raises `MdfLoadError` and the error dialog is shown. **Do not chase this as our bug.** The fix belongs in asammdf's `close()` method (guard with `getattr(self, '_file', None)`). We have no clean way to suppress it from our side without redirecting stderr.

---

## Todo / Future Features (not MVP)

- Multi-file support with multiple X-axes and synchronization (by timestamp overlap, manual time offset, or signal-based alignment)
- Session persistence (active signals, colors, window layout)
- Additional toolbar and menu items (TBD)

---

## Development Workflow

### Reviewing Issues
When asked to look at / check / review the GitHub issues, always fetch and display them grouped by milestone so the current development priority is immediately visible.

### Grill-Me Skill
When the user says **"grill me"** about a feature or topic, Claude should enter interview mode: ask focused, one-at-a-time questions to surface requirements, edge cases, and design decisions before writing any code. Summarize findings before proceeding.

### Plugin vs. Built-in Decision Rule
Before implementing any new feature, ask: **does this belong in the base app, or should it be a plugin?**

A feature belongs in the base app if it is core to the viewing experience — without it, the app cannot fulfil its primary purpose (open a file, browse signals, plot them).

A feature should be a plugin if it is optional, self-contained, and adds capability on top of the core without the core needing to know about it. Ask:
- Can the base app still function usefully without this feature? → plugin
- Does implementing it require the `PluginContext` API to grow substantially to accommodate it? → probably built-in (the API complexity cost is too high)
- Is it something a user might reasonably want to disable or replace? → plugin

### General Rules
- **Always check the codebase first** – before making assumptions or proposing solutions, check whether the answer already exists in the codebase
- Always propose architecture and structure before writing code
- Ask clarifying questions when requirements are ambiguous
- Write tests alongside implementation, not after
- Prefer explicit, readable code over clever one-liners
- All user-facing strings should be in English (internationalization not in scope for MVP)
- Commit messages should be clear and descriptive

### Verifying Mouse/Interaction Changes (#78 postmortem)

Synthetic Qt mouse-event tests (`QTest.mousePress/mouseMove/mouseRelease`, or directly calling `eventFilter(...)` with a hand-built event) are **not sufficient evidence** that a fix touching mouse routing, event filters, or Z-order/stacking actually works. They inject events below the real OS input pipeline and can pass while the real interactive app does not — confirmed during the #78 (delta-time line undraggable) investigation, where two separate fixes each passed dedicated regression tests and a full-app `QTest`-based repro, yet failed in a live debug session. Swapping `QT_QPA_PLATFORM=offscreen` for the real platform plugin did **not** close that gap either — `QTest` bypasses real OS-level input regardless of platform.

The project does not have OS-level GUI automation (e.g. `pywinauto`) and isn't investing in it for now — that decision can be revisited if this class of bug keeps recurring. Until then: **for any change touching mouse interaction, drag handling, event filters, or Z-order/stacking in `view/plot_area.py` or `view/cursors.py`, remind the user to manually test the live app before considering the change verified** — do not rely on automated tests alone for these areas, even when they pass. Logic/data tests remain valuable and should still be written as usual; this only applies to the "does the interaction actually reach the right widget" layer.

**Resolution (2026-07-01):** #78 is fixed — along with #80 (Z-order broken on shared Y-axis) and #81 (some signals not selectable), which turned out to share related causes. What finally worked, after two more theoretical fixes still failed live: temporary `print()` diagnostics added directly to `PlotArea.eventFilter`/`CursorView`, with the user reproducing in their real running app and pasting console output. That ruled out the event-routing plumbing as broken and pointed to the actual (unrelated) cause — `pi.vb`'s autoRange tracking the cursor/delta lines' own bounding boxes because they were added without `ignoreBounds=True`. Lesson reinforced, not just theorized: when a live-only mouse bug resists two rounds of "looks right in tests," add print statements to the real code path and get real console output before trying a third theoretical fix — don't remove that logging until the user has personally confirmed the fix live, even after you're confident you've root-caused it.

### Branching & Release Policy (#20)

**Lazy release-branch model** — chosen for low overhead given infrequent releases and a small team:

- **`main`** is the trunk. All bugfixes and features land here (directly or via PR), and each release is tagged `vX.Y` on `main`.
- A **`release/X.Y`** branch is created only when it's actually needed: you've started work on a feature for the *next* release on `main`, but still need to ship a bugfix to the *currently released* version (which must not receive that in-progress feature). Cut `release/X.Y` from the `vX.Y` tag at that point.
- Bugfixes to a released version go to its `release/X.Y` branch, get tagged `vX.Y.Z`, and must be cherry-picked forward to `main` so the fix isn't lost in the next release.
- If no feature work is in flight on `main` when a bugfix is needed, just commit the fix directly to `main` and re-tag/patch-release from there — no branch needed.

`master` was renamed to `main` as part of adopting this policy.

### Version Bump Checklist

`pyproject.toml` reads its version dynamically from `__init__.py`, so only **two** files need updating at release time:

1. `src/mdf_viewer/__init__.py` — `__version__ = "X.Y"`
2. `installer/mdf_viewer.iss` — `#define AppVersion "X.Y"` (line 8)

See `docs/release.md` for the full build and publish steps.

---

## Current Status

**As of 2026-07-02:** v2.1 released — 965 tests passing. Cursor Stuff (#59, #62, #63, #25, #26, #29, #39) and Signal Stuff (#56, #65, #66, #45, #44) merged to main; #30 (line width), #38 (line style), #24 (selected signal highlight), #69 (show only selected signal Y-axis), #40 (enum signal display), #16 (shared/linked Y-axes), #36 (keep signals on new file load), #37 (save/load configuration) implemented.

Since the 2026-06-30 status: #83, #82, #79 (already fixed by then), plus #78/#80/#81 (one shared root-cause fix — drag-claimant routing in `PlotArea`/`CursorView`, per-signal Z tracking, and a numpy-truthiness crash in `_hit_test`), #84 (swimlanes/zoom not collapsing Linked Y-axis groups — new `PlotArea._display_units()` helper), and #89 (shorten-signal-names preference not applied on startup) have all been fixed, verified live, and closed.

Two active milestones on GitHub:
- **2.1.1 Bugfixing** — 2 open bugs remain: #85 (blurry splash-screen icon), #77 (config doesn't save widget sizes).
- **2.2 Plugins** — new plugin architecture effort: #43 (umbrella), #70 (event bus on AppController), #71 (PluginContext API facade), #72 (Plugin base class/lifecycle), #73 (UI extension points in MainWindow), #74 (plugin loader/discovery), #75 (proof-of-concept built-in plugin), #76 (convert update checker into a first-party plugin).

#17 (multi-file support) has been moved to the **Backlog** milestone (due 2028-12-31, i.e. unscheduled), along with #55, #57, #58, #60, #61.

### Changelog
Notable changes are tracked in `CHANGELOG.md` (Keep a Changelog style). Update it alongside `CLAUDE.md` when shipping a fix or feature.

---

## Environment

- `.venv` exists with deps installed (`pip install -e ".[dev]"`). Python 3.14.5. asammdf resolved to 8.x.
- Activate with `.venv\Scripts\activate`, then `pytest` (965 passing) and `python -m mdf_viewer` both work.
- `cryptography` must be installed separately on macOS: `.venv/bin/pip install cryptography`

---

## Security — secrets that must never be committed

The Ed25519 private key and `generate_license.py` are saved at `C:\Users\andal\Documents\mdf-viewer-private\` — **never commit either to any repo**. `.gitignore` blocks `generate_license.py`, `*.lic`, and `*.pem`. See `docs/architecture.md` for full license system design decisions.
