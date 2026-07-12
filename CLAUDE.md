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
- **Session persistence is manual, not automatic** – the app always starts fresh (no auto-restore of the last session), but a full workspace session — every tab (name, plot|AST divider width, Active Signals Table column widths), every tab's plot-stripe layout, every active signal's placement/colors/axis grouping/zoom/cursor/selection, and the full loaded-measurement pool (paths, short names, offsets, Primary, Sync state) — can be saved to and restored from a `.mvc` file via File → Save Workspace / Save Workspace As… (#37, #77, extended to the full workspace by #106). Auto-restore-on-startup is not implemented.
- **Robust error handling is mandatory** – the application must never crash on malformed, incomplete, or unexpected MDF content; errors must be caught and communicated to the user gracefully

---

## MDF Support

- MDF3 and MDF4 via the `asammdf` library
- All available channel groups and signals must be represented in the Signal Browser (a flat, cross-measurement list as of #103 — see `docs/ui.md`/`docs/api.md`; every channel is still shown, channel-group membership is now a hover tooltip rather than list structure)

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
- Auto-restore last session on startup (manual save/load via `.mvc` files already implemented, see File Handling above)
- Additional toolbar and menu items (TBD)

---

## Development Workflow

### Reviewing Issues
When asked to look at / check / review the GitHub issues, always fetch and display them grouped by milestone so the current development priority is immediately visible.

### Grill-Me Skill
When the user says **"grill me"** about a feature or topic, Claude should enter interview mode: ask focused, one-at-a-time questions to surface requirements, edge cases, and design decisions before writing any code. Summarize findings before proceeding — and write that summary into the relevant `docs/requirements/*.md` file(s), not just into the conversation. For a Feature issue, this *is* the "write requirements before implementation" step from Issue Triage below, not a separate later task.

### Requirements Workflow

`docs/requirements/` is the single source of truth for **what the app does** — distinct from GitHub issues (a bug/idea reservoir where anything gets jotted down) and from `docs/architecture.md` / `docs/ui.md` (the **how**, i.e. MVC/View implementation detail). Put another way: **the code is the source of truth for what the app currently does; the requirements docs are the source of truth for what it should do.** When the two disagree, that disagreement is a Bug (see Issue Triage below) — either the requirements doc was silent, or the code drifted from a requirement that was correct.

- **Structure** – one file per capability/domain (e.g. `file-handling.md`, `mdf-support.md`), not one monolithic file, and not split by UI-vs-non-UI — that split is an architecture-stage decision, not a requirements-stage one.
- **Style** – prose per section; each individually-testable sentence is tagged inline with a stable ID, `REQ-<DOMAIN>-NNN` (e.g. `REQ-FILE-010`), numbered in steps of 10 per sub-topic so new requirements can be inserted later without renumbering. Every tagged sentence must be: **positive** (state what the system does, not what it doesn't — a negative phrasing usually means it hasn't been pinned to an actual observable behavior yet), **clear** (stands on its own without the reader having to untangle it), and **testable** (corresponds to something a test can assert). A sentence that's purely explanatory or cross-references other REQ-IDs without making its own independent claim is not a requirement — leave the prose in place but don't give it a REQ-ID.
- **Traceability** – tests cite the requirement they verify via `@pytest.mark.requirement("REQ-FILE-010")`. Not every requirement needs one, though: a `REQ-ID` with no citing test isn't automatically a coverage gap — some requirement classes are legitimately verified by a repeatable *process* instead of an automated test (e.g. `REQ-NFR-040`, "runs on Windows," is verified by the fact that every release goes through a real build, a real installer, and the user running the resulting binary — the same "only a human running the real thing proves it" pattern as the mouse-interaction live-testing rule above). Before treating an untested `REQ-ID` as a gap, check whether it's actually one of these, a wording problem (see Style above), or a genuine missing test.

First file drafted: `docs/requirements/file-handling.md`.

### Issue Triage

GitHub issues are the only backlog and arrive in different flavors. **Before starting work on an issue, state which flavor it is and get the user's agreement** — don't silently assume it, since the flavor decides which docs must stay in sync. Then follow that flavor's rule below — this is what keeps `docs/requirements/`, `docs/architecture.md`, the user manual, and `CHANGELOG.md` from going stale as issues get closed:

- **Feature** → write or update the relevant `docs/requirements/*.md` file(s) *before* implementation starts.
- **Bug** → after root-causing, check whether a requirements doc needs updating too: either the requirement was silent on this case, or the code deviated from a requirement that was correct. If the fix is purely a wording correction to a requirements/architecture/ui doc with no code change (e.g. the REQ-PLOT-121 case), that edit *is* the fix — there's no separate "Documentation" flavor for this, it's a Bug variant.
- **Test-coverage** → tag the new/existing test(s) with the REQ-ID(s) they verify (`@pytest.mark.requirement("REQ-...")`). No requirements doc change unless writing the test surfaces an actual behavior gap — if it does, that part follows the Bug rule above (e.g. #91's MDF3 fixture surfacing a real `channel_tree()` unit/comment bug).
- **Investigation / Spike** → no doc changes during the investigation itself. Must close by either filing a follow-up Feature/Bug issue, or an explicit no-action note on the issue explaining why nothing further is needed — never leave it closed with no trace of the conclusion.
- **Documentation** → means the end-user manual (not `docs/requirements/`, `docs/architecture.md`, or `docs/ui.md`, which are internal). Tracked starting with #55, which will establish where it lives. No requirements/architecture doc changes, since app behavior isn't changing.
- **Refactor / Tech debt** → no requirements doc change (behavior is unchanged by definition). Add a `docs/architecture.md` decision-log entry if the restructuring reflects a real architectural decision worth recording.
- **Chore / Maintenance** → dependency bumps, CI, packaging. No requirements impact; update `docs/release.md` if it changes the release/build process.
- **Design / Architecture question** → resolve into a `docs/architecture.md` decision-log entry.

**`docs/ui.md`** update is not gated to one flavor the way requirements/architecture are — whichever flavor (Feature or Bug) actually adds, removes, or moves a menu item, toolbar button, dialog, or panel must update the relevant section of `docs/ui.md` too, in the same commit as the code change. It's the map of what the user currently sees; unlike requirements (stable invariants) it's pure current-state documentation, so it goes stale the moment a layout change lands without a matching edit — which is exactly what happened across #97/#99/#100/#101/#102 before this rule existed.

**`docs/api.md`** gets the same treatment — same reasoning, same risk of drift, just mapping the codebase's module/class structure instead of the visible UI. Whichever flavor adds a new module, or changes a class's public methods/signals/fields enough that the existing entry no longer matches, updates the relevant `api.md` entry in the same commit. A pure-internal change with no altered public surface (most Refactor/Tech debt work) doesn't need an edit.

**CHANGELOG.md** is reserved for user-visible changes only (Keep a Changelog style) — Feature and Bug entries. Test-coverage, Investigation, Refactor/Tech debt, Chore, and Design-question issues do not get a CHANGELOG entry unless they also produce a user-visible side effect.

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

### PyQtGraph/Qt Object Teardown Pitfall (#120, 2026-07-10 postmortem)

A native segfault (`EXCEPTION_ACCESS_VIOLATION`, zero Python traceback) was chased down to a recurring pattern: code that tears down a `ViewBox`/`AxisItem`/curve called `layout.removeItem()` / `scene.removeItem()` / `.hide()` and stopped there — none of those destroy the underlying Qt object. The item stays alive, orphaned, still wired into whatever signal/slot connections it had (e.g. cross-stripe X-range sync), and can crash much later when something unrelated touches it. Found three separate instances of this in `plot_stripe.py` (`_destroy_vb_and_axis`, `set_measurement_axes`, `set_axis_padding`'s spacer) plus a fourth, different-shaped leak in tab-close (`AppController.remove_tab` never ran a closed tab's still-active signals through `remove_signal`, and `MainWindow._on_tab_close_requested` never `deleteLater()`'d the closed tab's page widget — `QTabWidget.removeTab()` does not delete the widget). See `docs/architecture.md`'s "PyQtGraph/Qt Teardown Pitfall" decision-log entry for the full technical detail (including the `getViewBox()`/`viewRangeChanged()` crash mechanism) and what to check for in new code.

**How it was actually found — a different technique than the #78 postmortem above:** synthetic reproduction wasn't possible (this needed real signal data, real multi-stripe layout, and a specific sequence of user actions to trigger), and the crash left no Python traceback for print-instrumentation to directly bracket at first. What worked: (1) launching the real app repeatedly and matching Windows' own crash dumps (`%LOCALAPPDATA%\CrashDumps\python.exe.<pid>.dmp` — no WinDbg/cdb installed, so parsed with the pure-Python `minidump` pip package) against the *timing* of the user's live reproduction, using `ProcessCreateTime` from the dump to confirm which dump actually corresponded to which repro attempt (an early assumption that a dump was from an unrelated crash turned out to be wrong once the user gave a precise timestamp to check against); (2) once the exact exception (null-pointer read, same code offset every time) was confirmed as the real target, adding synchronous `print(..., flush=True)` statements immediately before *and* after each suspect call, so the crash's exact location could be narrowed to "ran the before-print but never the after-print for call N" across several rounds of live reproduction; (3) getting the user to vary the *exact sequence* of UI actions (not just "click the same button again") surfaced the real trigger condition, which turned out to be a specific state transition (a stripe's computed axis padding dropping to exactly 0 for the first time in the session) that three prior code-reading passes had missed.

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

**As of 2026-07-12:** v2.1.1 is still the last released version (https://github.com/andalf-74/MDF-Viewer/releases/tag/v2.1.1). 1719 tests passing. The **2.1.1 Bugfixing milestone is fully resolved**, all bugs closed. Fix-by-fix detail lives in `CHANGELOG.md`'s `[2.1.1]` entry, not repeated here.

GitHub milestone numbering was reshuffled: **#17 (multi-file support) was pulled out of Backlog, broken into 10 sub-issues, and assigned version 2.2** as milestone **"2.2 Multiview/Multimeasurement"** (due 2026-07-31). The former "2.2 Plugins" effort was renumbered to **"2.3 Plugins"**. This is a version-number assignment only, not a release — 2.2 has not shipped.

Two active milestones remain on GitHub:
- **2.2 Multiview/Multimeasurement** — #17 (umbrella, epic), #97 Plot Stripes (done), #98 Bottom Drawer for Signal Info/Properties (done), #99 Main Widget Tabs (done), #100 Per-Stripe Active Signal Table (done), #101 Multi-Measurement Loading (done), #102 Measurement Synchronization (done), #103 Signal Browser multi-measurement support (done — flat cross-measurement list, Primary Measurement, editable short names, Close Measurement menu), #104 color/line-style convention (rejected by user directly on GitHub — "user can do this himself" — not implemented), #106 Workspace/Config format extension (done, committed `de66462`), #119 Duplicate Tab / Copy Signals to new Tab (implemented, tested, documented, live-verified 2026-07-12; not yet committed), #124 new-tab-missing-axes bug (fixed, committed `2535564`), #130 zombie-workspace-on-last-tab-close bug (found live-testing #124, fixed same commit), #131 new-tab-missing-display-name-formatter bug (found live-testing #119, fixed; not yet committed), #122 Replace a single specific measurement (done, live-verified 2026-07-12 via grill-me → requirements → architecture → plan-mode milestones; File ▸ Replace Measurement submenu + Measurement Info Box "Replace…"/"Close" buttons), #105 Apply Config to Already-Loaded Measurements (done, live-verified 2026-07-12; File ▸ Apply Config… + `MeasurementMappingDialog`, reused #106's own restore pipeline almost entirely unchanged), #133 Signal Visibility (done, live-verified 2026-07-12; per-row eye-icon toggle + "Toggle Visibility" context-menu entry + Ctrl+W, composed into the pre-existing Show-Only-Selected-Y-Axis mechanism rather than a parallel one — a late addition to the milestone, filed and shipped same day). Every 2.2 sub-issue is now done except #17 itself, which stays open as the umbrella tracker.
- **2.3 Plugins** — new plugin architecture effort: #43 (umbrella), #70 (event bus on AppController, done), #71 (PluginContext API facade), #72 (Plugin base class/lifecycle), #73 (UI extension points in MainWindow), #74 (plugin loader/discovery), #75 (proof-of-concept built-in plugin), #76 (convert update checker into a first-party plugin).

There's also a **2.X Artificial Signals** milestone (#58, #86) not yet assigned a version number, and a **Backlog** milestone (due 2028-12-31, unscheduled) holding #55, #57, #60, #61.

### Changelog
Notable changes are tracked in `CHANGELOG.md` (Keep a Changelog style). Update it alongside `CLAUDE.md` when shipping a fix or feature.

---

## Environment

- `.venv` exists with deps installed (`pip install -e ".[dev]"`). Python 3.14.5. asammdf resolved to 8.x.
- Activate with `.venv\Scripts\activate`, then `pytest` and `python -m mdf_viewer` both work. Current test count is tracked in Current Status below, not duplicated here.
- `cryptography` must be installed separately on macOS: `.venv/bin/pip install cryptography`

---

## Security — secrets that must never be committed

The Ed25519 private key and `generate_license.py` are saved at `C:\Users\andal\Documents\mdf-viewer-private\` — **never commit either to any repo**. `.gitignore` blocks `generate_license.py`, `*.lic`, and `*.pem`. See `docs/architecture.md` for full license system design decisions.
