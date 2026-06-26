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

### General Rules
- **Always check the codebase first** – before making assumptions or proposing solutions, check whether the answer already exists in the codebase
- Always propose architecture and structure before writing code
- Ask clarifying questions when requirements are ambiguous
- Write tests alongside implementation, not after
- Prefer explicit, readable code over clever one-liners
- All user-facing strings should be in English (internationalization not in scope for MVP)
- Commit messages should be clear and descriptive

### Branching & Release Policy (#20)

**Lazy release-branch model** — chosen for low overhead given infrequent releases and a small team:

- **`main`** is the trunk. All bugfixes and features land here (directly or via PR), and each release is tagged `vX.Y` on `main`.
- A **`release/X.Y`** branch is created only when it's actually needed: you've started work on a feature for the *next* release on `main`, but still need to ship a bugfix to the *currently released* version (which must not receive that in-progress feature). Cut `release/X.Y` from the `vX.Y` tag at that point.
- Bugfixes to a released version go to its `release/X.Y` branch, get tagged `vX.Y.Z`, and must be cherry-picked forward to `main` so the fix isn't lost in the next release.
- If no feature work is in flight on `main` when a bugfix is needed, just commit the fix directly to `main` and re-tag/patch-release from there — no branch needed.

`master` was renamed to `main` as part of adopting this policy.

---

## Current Status

**As of 2026-06-26:** v2.0.1 released — 686 tests passing. Cursor Stuff (#59, #62, #63, #25, #26, #29, #39) and Signal Stuff (#56, #65, #66, #45, #44) merged to main; #30 (line width), #38 (line style), #24 (selected signal highlight) implemented; next release will be v2.1.1.

Cursor Stuff features are merged to main; version stays at 2.0.1 until a release build can be produced (requires Windows). Next milestone is v2.1.1 — keep adding features to main.

### Changelog
Notable changes are tracked in `CHANGELOG.md` (Keep a Changelog style). Update it alongside `CLAUDE.md` when shipping a fix or feature.

---

## Environment

- `.venv` exists with deps installed (`pip install -e ".[dev]"`). Python 3.14.5. asammdf resolved to 8.x.
- Activate with `.venv\Scripts\activate`, then `pytest` (638 passing) and `python -m mdf_viewer` both work.
- `cryptography` must be installed separately on macOS: `.venv/bin/pip install cryptography`

---

## Security — secrets that must never be committed

The Ed25519 private key and `generate_license.py` are saved at `C:\Users\andal\Documents\mdf-viewer-private\` — **never commit either to any repo**. `.gitignore` blocks `generate_license.py`, `*.lic`, and `*.pem`. See `docs/architecture.md` for full license system design decisions.
