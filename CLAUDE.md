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
    plugin_api/     # PluginContext facade — the only thing a plugin may import (#71)
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

**As of 2026-07-12: v2.2 is the latest released version** (https://github.com/andalf-74/MDF-Viewer/releases/tag/v2.2, tag `v2.2` on `main`). 1722 tests passing. Ships `MDF-Viewer-2.2-Setup.exe` (installer) and `MDF-Viewer-2.2-Windows.zip` (portable) — see `docs/release.md`. Fix/feature-by-feature detail lives in `CHANGELOG.md`'s `[2.2]` entry, not repeated here.

2.2 combines two closed GitHub milestones, both reshuffled from earlier planning (see git history for the full renumbering story if needed): **"2.2 Multiview/Multimeasurement"** (#17 umbrella + #97–#106, #119, #122, #124, #130, #131, #133 — multi-file support, Plot Stripes, tabs, per-stripe AST, workspace/config extension, etc.; #104 rejected by user directly) and **"2.2 Additional Bugfixing"** (#134–#140 — a later architecture review's findings plus two more issues added afterward; #139 closed as duplicate/already-implemented, #140 fixed). Both milestones and their umbrella issues are closed on GitHub.

One other active milestone remains on GitHub:
- **2.3 Plugins** — new plugin architecture effort: #43 (umbrella), #70 (event bus on AppController, done), #71 (PluginContext API facade, done), #72 (Plugin base class/lifecycle, done), #73 (UI extension points in MainWindow, done), #74 (plugin loader/discovery, done), #75 (proof-of-concept built-in plugin, done — see below), #76 (convert update checker into a first-party plugin), #147 (virtual measurements/signals — plugin groundwork for artificial-signal and custom-file-format plugins, implemented — see below), #148 (register_tab_type — pluggable tab types, implemented — see below), #118 (OpenStreetMap View, first real consumer of #148, not yet started).

**#71 (PluginContext API facade) implemented, committed (`eb63eee`), pushed, and closed 2026-07-13** via a 6-milestone plan (types → registry → AppController additions → read surface → registration/event surface → e2e harness + docs), full grill-me → requirements (`docs/requirements/plugin-api.md` REQ-PLUGIN-060–150) → architecture (Plan-agent-reviewed, `docs/architecture.md`) workflow. New top-level `src/mdf_viewer/plugin_api/` package (`types.py`/`registry.py`/`context.py`) — `PluginContext` is the only object a plugin will ever import; read-only signal/measurement/cursor projections, `register_menu_action`/`register_dock_widget` (stubs, rendered by #73), event subscription (`subscribe`/`unsubscribe_all`). `AppController` gained `all_workspaces()`, `active_tab_index`, and an opaque per-signal token (`token_for_signal`/`find_active_signal_by_id`) — not `id(active_signal)`, which would be unsafe for a handle a plugin can hold indefinitely. Filed follow-up [#147](https://github.com/andalf-74/MDF-Viewer/issues/147) for a future "virtual measurement" capability (artificial-signal and custom-file-format plugins), out of #71's scope. No CHANGELOG entry (no user-visible surface yet, matching the #70 precedent).

**#72 (Plugin base class and lifecycle) implemented 2026-07-13** via a 4-milestone plan (base class → PluginContext._teardown() → start()/stop() lifecycle+auto-wiring → docs), same full grill-me → requirements (REQ-PLUGIN-160–190) → architecture (Plan-agent-reviewed) workflow, extending #71's package with `plugin_api/plugin.py`. `Plugin` is what a plugin author implements against (`PluginContext` is what it *receives*): class-attribute metadata (`name` enforced non-empty via `__init_subclass__`, not `__init__`, so a subclass that forgets `super().__init__()` can't skip it), mandatory `activate(context)`/optional `deactivate()`, five no-op event handler methods auto-wired to `PluginContext.subscribe()` only when overridden (no manual subscribe call needed), and framework-facing `start()`/`stop()` lifecycle methods (idempotent, called by the future loader #74) — `start()`'s failure path tears down via a new `PluginContext._teardown()` before returning `False`, so a plugin whose `activate()` registers something then raises never leaks that registration forever. 1781 tests passing (up from 1762 at #71). No CHANGELOG entry (same reasoning as #71). Committed (`91372a3`), pushed, and closed.

**#73 (UI extension points in MainWindow) implemented 2026-07-13** via a 4-milestone plan (AppController.plugin_registry → Plugins menu → docked-widget sections → docs), same grill-me → requirements (REQ-PLUGIN-200–231) → architecture (Plan-agent-reviewed) → plan-mode milestones workflow. Makes #71's registration stubs visible: a "Plugins" menu (between Edit and Help, hidden entirely when the registry is empty — today's actual state) built once in `MainWindow.set_controller()`; docked-mode dock widgets stack into #98's existing Info/Properties splitter as another titled pane; dialog-mode widgets get an auto-added "*Title*…" Plugins-menu entry, built once and cached. Plan review caught a fatal wiring bug before implementation (`MainWindow` is constructed before `AppController` in `app.py`, so the registry can't be read from `__init__` — moved to `set_controller()`), and that very fix then silently invalidated an unrelated placement assumption from the same review (plain `addMenu()` no longer lands between Edit/Help once built later — fixed with `QMenuBar.insertMenu()`), caught during implementation itself. `MenuActionRegistration.invoke()`'s return type widened from `None` to `bool` (#71's shipped code) so a failed menu action can show a status-bar message. 1794 tests passing (up from 1781 at #72). `docs/ui.md`/`docs/api.md` updated. No CHANGELOG entry (registry stays empty until #74/#75 exist).

**#74 (plugin loader and discovery) implemented 2026-07-13** via a 4-milestone plan (Settings.plugins_dir → loader import machinery → load_all/deactivate_all → app.py wiring + docs), same grill-me → requirements (REQ-PLUGIN-240–280) → architecture (Plan-agent-reviewed) → plan-mode milestones workflow. New `plugin_api/loader.py`: `PluginLoader` scans a plugins directory (one subfolder per plugin, each declaring an explicit `PLUGINS: list[type[Plugin]]` — no introspection, cleanly supports single-plugin and "toolsuite" packages alike), imports each via `importlib.util.spec_from_file_location`, activates every declared class, and deactivates them all on shutdown. Plugins directory defaults to next to the running app (installer/portable — travels with a portable copy) or relative to the source checkout in dev mode, overridable via new `Settings.plugins_dir`. Wired into `app.py` between `AppController` construction and `window.set_controller()` (the hard ordering constraint #73 imposed), with `deactivate_all()` after `app.exec()` returns. Plan review caught a correctness bug that would have broken every multi-file plugin package: `importlib`'s module must be registered in `sys.modules` *before* `exec_module()` runs, or a package's own `from . import sibling` fails — confirmed fixed via a dedicated regression test. 1818 tests passing (up from 1794 at #73). Also fixed, mid-implementation, a second recurrence of the "truncated Read splices into existing code" mistake (this time silently removing `Settings.check_for_updates`'s `_save()` call) — caught by the full test suite, not by inspection; see `docs/architecture.md`/memory for detail. No CHANGELOG entry (no real plugin ships until #75).

**Bug #149 found and fixed 2026-07-13, while scoping #75** (before writing any plugin code — checking whether the Signal Statistics PoC example would receive what #71's own requirements already promised). `PluginContext.subscribe()` forwarded the raw `EventBus` payload to plugin handlers completely untransformed: every event's `tab` field is the raw `TabWorkspace` (exposing that tab's actual `plot`/`cursor_ctrl`/`zoom_ctrl`), and `signal_added`/`signal_removed`/`selection_changed` carry the live, mutable `ActiveSignal`(s) — a plugin could corrupt real in-memory sample data in place, desync the app's rendered state, or manipulate live PyQtGraph objects directly (risking the exact native-crash class #120 already fixed once). Fixed by adding 5 read-only `Plugin*Event` dataclasses (`tab_index: int | None` instead of the raw tab; `PluginSignalView` instead of the raw `ActiveSignal`), an explicit `_translate_event()` with a loud `AssertionError` fallback (never a silent passthrough), and a structural guard test cross-checking `_KNOWN_EVENTS` against `EventBus`'s real `pyqtSignal` attributes — so a future new event without a matching translator fails a test immediately. Also reordered `AppController`'s 4 signal-removal sites so `signal_removed` fires *before* the plugin-facing token is dropped, closing a related leak. 1821 tests passing (up from 1818). Full detail in `docs/architecture.md`'s "Event Payload Leak (#149)" entry.

**#75 (proof-of-concept built-in plugin, Signal Statistics) implemented 2026-07-13.** New `plugins/signal_statistics/__init__.py`: subscribes to `selection_changed`, shows Min/Max/Mean of the selected signal in a docked widget via `context.get_samples()`. Deliberately dev-mode-only, not packaged into the release build — lives directly at `<repo root>/plugins/`, which is already #74's own default dev-mode discovery directory, so it's auto-discovered with zero extra wiring; shipping it in the installer/portable build was considered and dropped since none of the PoC's actual goals (validate the lifecycle, surface API gaps, serve as a reference example) need it to reach an end user's installed copy. Tests load it through the real `PluginLoader` pointed at the real repo `plugins/` directory, not a direct import — proving the actual committed file works via the actual discovery mechanism. 1824 tests passing (up from 1821 at #149). **Live-tested in the real running app — user confirmed it opens normally and the panel shows and updates correctly** — the first time the full pipeline (#71→#74, #149) has been exercised end-to-end with a real plugin, not just mocked-piece unit tests.

**#147 (virtual measurements/signals, plugin groundwork) implemented 2026-07-14** via a 5-milestone plan (core model-layer types → AppController/EventBus wiring → `.mvc` capture_config() rework → PluginContext/Plugin surface → UI badges/guards), full grill-me → requirements (`docs/requirements/virtual-measurements.md` REQ-VMEAS-010–440, `docs/requirements/plugin-api.md` REQ-PLUGIN-290–310) → architecture (two Plan-agent review passes — one on the technical design, 7 real gaps found and folded in; one on the milestone breakdown itself) → plan-mode milestones workflow. The grill-me reframed the issue from "a plugin registers a measurement" into a general `VirtualSignal`/`VirtualMeasurement` abstraction: new `model/measurement_loader.py` (`MeasurementLoader` `Protocol`, satisfied by both `MdfLoader` and the new `VirtualMeasurementLoader`), `model/virtual_signal.py`/`model/virtual_measurement_loader.py`, and `LoadedMeasurement.owner_plugin: str | None` (sole source of truth for "is this measurement virtual"). New `PluginContext` methods `create_virtual_signal`/`create_virtual_measurement`/`attach_virtual_signal`/`register_virtual_measurement`, a new `measurement_closed` EventBus event/`Plugin.on_measurement_closed` handler, and a `(virtual)` badge in the Signal Browser and Measurement Info Box (Replace… disabled for a virtual measurement, REQ-VMEAS-440). The most serious gap the first Plan review caught: `.mvc` save computed `primary_index`/signal indices against the *unfiltered* pool while filtering only the saved measurement list — would have silently corrupted any save containing a virtual measurement; fixed by consistently filtering to `real_measurements` throughout `capture_config()`/`_capture_tab()`, widening `primary_measurement_index` to `int | None`. Also fixed, discovered during implementation: `ConfigManager.load()`'s `int(data.get("primary_measurement_index", 0))` would have raised on a saved `null` rather than restoring "no real Primary" — caught before it could ever ship. Downsampling/lazy-loading of real signals and full `.mvc` serialization of virtual measurements are explicitly deferred to future issues; no PoC/reference plugin ships in #147 itself (matches the #71–#74 precedent). Committed (`d2211fe`), pushed, and closed on GitHub; follow-up PoC issue filed as [#152](https://github.com/andalf-74/MDF-Viewer/issues/152), the same way #75 followed #71–#74. 1887 tests passing (up from 1824 at #75). `docs/api.md`/`docs/ui.md` updated. No CHANGELOG entry (no end-user-visible surface until a real plugin uses this, same reasoning as #71–#74).

**#148 (pluggable tab types, `register_tab_type`) implemented 2026-07-15** via a 5-milestone plan (foundations → minimal test-fixture plugin → tab creation UI → existing tab-lifecycle fixes → `.mvc` persistence), full grill-me (lighter than #147's — the issue body already recorded real design decisions from prior discussion) → requirements (`docs/requirements/plugin-api.md` REQ-PLUGIN-320–352) → architecture (**three** Plan-agent review passes — two on the technical design, one on the milestone breakdown; 17 real gaps found total and folded in) → plan-mode milestones workflow. Extends #71–#73's UI extension points: `PluginContext.register_tab_type(type_id, display_name, view_factory)` lets a plugin register a whole tab *template*, not just a menu action or dock widget — `AppController`'s `TabWorkspace`/`_workspaces` stays completely plot-tabs-only and unaware non-plot tabs exist, matching the boundary #73 already established for dialog-mode dock widgets. New dev-mode-only `plugins/tab_type_fixture/` (mirrors #75's precedent) exists purely to make the tab-lifecycle bug surface live-testable, since unit tests alone weren't sufficient here (unlike #147). The first design draft's approach — computing a workspace index by *counting* plot pages up to a `QTabWidget` position, redone ad hoc per call site — turned out to have 12 gaps across the first review, several serious (a `restore_config()` bug that would have silently misapplied one tab's saved axis-grouping/zoom/cursor state onto an unrelated tab; a reintroduction of the #130 native-crash class in the tab-close parking decision; `AttributeError` crashes in Preferences with any non-plot tab open). The redesign replaced all counting with **identity-based lookup** (new `AppController.tab_index_for_plot(plot_area)`, mirroring the existing `reorder_tabs()`/`_measurement_index()` identity-search idioms already in the codebase) plus an explicit `resolved_workspaces` correspondence built once during `.mvc` restore's Phase 2 and threaded through to Phase 4 — a second review found 5 more loose ends in that redesign (all folded in), and the milestone-breakdown review found 2 more call sites needing the same treatment (tab-bar drag-reordering; confirmed Ctrl+Tab needed no change). 1937 tests passing (up from 1887 at #147). Live-tested in the real running app at two checkpoints — tab creation/switch/close/duplicate/copy/reorder/Preferences with mixed plot and non-plot tabs (M4), and a full `.mvc` save→reload round-trip with a non-plot tab positioned between two plot tabs, confirming each plot tab's signals/axis-grouping/zoom/cursor state landed on the correct tab and the focused non-plot tab was restored correctly (M5) — both user-confirmed. Serialization of a non-plot tab's own internal content is explicitly deferred to a future issue (v1 persists only existence/name/view_type, recreating an empty instance on restore); #118 (OpenStreetMap View) remains the first real consumer, not yet started. `docs/api.md`/`docs/ui.md` updated. No CHANGELOG entry (no end-user-visible surface until #118 or another real plugin ships a tab type, same reasoning as #71–#75/#147).

The **2.X Artificial Signals** milestone was renamed/versioned to **2.4 Artificial Signals** (#58 umbrella, #86, #110, #121, #123, #143) on GitHub. A **Backlog** milestone (unscheduled) holds #55, #57, #60, #61, #108, #111, #118, #125, #126, #127, #128, #129, #132, #144.

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
