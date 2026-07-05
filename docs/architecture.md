# MDF-Viewer Architecture

Strict MVC separation is mandatory. The prototype this project replaces failed
because data, UI, and plotting were tightly coupled; every decision here exists
to keep those concerns apart.

## Layers

| Layer | Package | May import | Must NOT import |
|-------|---------|------------|-----------------|
| Model | `mdf_viewer.model` | numpy, asammdf | PyQt6, pyqtgraph, view, controller |
| View | `mdf_viewer.view` | PyQt6, pyqtgraph | model-loading logic, asammdf |
| Controller | `mdf_viewer.controller` | model, view_model | — |
| View-model | `mdf_viewer.view_model` | model, PyQt6, pyqtgraph | — |

The **model** is pure data and never imports Qt. The **view** is pure UI and
holds no business logic. The **controller** coordinates the two and owns
cross-widget state. The **view-model** holds the few bridge objects that must
reference both a model object and its on-screen representation.

## Signal classes

- **`model.signal_data.SignalData`** — raw timestamps + sample arrays. Pure data.
- **`model.signal_metadata.SignalMetadata`** — name, unit, min/max, sample
  count, comment, and other MDF fields. Pure data, no samples.
- **`view_model.active_signal.ActiveSignal`** — a signal placed on the plot.
  Pairs `SignalData` + `SignalMetadata` with its PyQtGraph curve, ViewBox, and
  color. This is the Model↔View bridge, which is why it lives in `view_model`
  rather than `model` (it references Qt/PyQtGraph types).

## File I/O isolation

`model.mdf_loader.MdfLoader` is the **only** module that imports `asammdf`. It
translates a file on disk into the plain data classes above and raises
`MdfLoadError` on malformed or unreadable content, so the rest of the app never
touches the asammdf API and never crashes on bad input.

## Assembly

`app.run()` is the single place that constructs and wires the three layers
together. No layer constructs another's object graph.

## Module map

```
model/        signal_data, signal_metadata, measurement, mdf_loader
view_model/   active_signal
controller/   app_controller, cursor_controller, interfaces
view/         main_window, signal_browser, active_signals_table, plot_area,
              cursors, measurement_info_box, signal_info_box, widgets/
```

---

## Decision log

Decisions are recorded here when the "why" is not obvious from reading the code.
Grouped by topic; most-recent entries at the bottom of each group.

### Foundation

- **Qt binding:** PyQt6, licensed GPL-3.0-only by Riverbank (not LGPL — earlier misconception); PyQtGraph supports it.
- **Project license (1.x):** GPL-3.0-only (`LICENSE`, `pyproject.toml`), required by PyQt6's GPL terms for the combined work. Replaces the earlier `Proprietary` placeholder.
- **Build:** `pyproject.toml` (src-layout, entry point `mdf-viewer`) + `requirements.txt` / `requirements-dev.txt`.
- **`__version__`:** defined in `src/mdf_viewer/__init__.py` — the single source of truth. `pyproject.toml` uses `dynamic = ["version"]` with `[tool.setuptools.dynamic] version = {attr = "mdf_viewer.__version__"}` so it reads from `__init__.py` at install/build time rather than hardcoding a second copy. The installer `.iss` still requires a manual bump at release time (Inno Setup cannot read Python). Python code imports `__version__` directly rather than via `importlib.metadata` (editable installs cache stale metadata until reinstalled).

### Data model

- **`ActiveSignal` location:** `src/mdf_viewer/view_model/` (not `model/`), to keep the data layer free of Qt/PyQtGraph imports.
- **`ActiveSignal.__eq__ = object.__eq__`:** list `in` and `remove` also use `__eq__`, which the dataclass version raises on numpy arrays. Identity equality is set alongside `__hash__` so both dict and list operations are consistent.
- **`SignalMetadata.data_type` / `is_integer`:** `MdfLoader.load_signal` captures the raw asammdf dtype before the mandatory float64 conversion. `is_integer` is used by `PlotArea._SignalAxisItem` to suppress fractional ticks on discrete/integer signals. `data_type` (e.g. `"uint8"`) is displayed in `SignalInfoBox`.
- **Enum/string signal fallback:** `load_signal` retries with `raw=True` when physical values are non-numeric byte strings (common for CAN enum signals like gear position or state flags); raw integer encoding is numeric and plots correctly with the existing integer-tick axis.
- **`MdfLoadError` in `errors.py` (#46):** moved from `model/mdf_loader.py` so that `view/main_window.py` can import it without creating a view→model dependency. Both `mdf_loader.py` and `main_window.py` import from `mdf_viewer.errors`.
- **MDF4 `header.author`** does not round-trip via asammdf (stored in XML comment block). The `MeasurementInfo.extra` dict is available for raw fields if needed later.

### MVC wiring

- **View imports in controller:** `TYPE_CHECKING`-only — no runtime view imports; all views are injected as constructor parameters.
- **Protocol contracts in `controller/interfaces.py` (#50):** seven `typing.Protocol` classes declare every method each controller calls on its view dependencies. Interface segregation applied to `ActiveSignalsTable`: `SignalTableProtocol` (add/remove/clear rows — `AppController`) and `CursorValueSinkProtocol` (cursor value columns — `CursorController`) are separate. All protocols live under `TYPE_CHECKING` — no runtime cost.
- **MVC assembly:** `MainWindow` creates view widgets; `app.py` reads them to construct `AppController`; `set_controller` completes the wiring. No layer constructs another's object graph.
- **Signal color palette:** 8-color cycling tuple defined in `app_controller.py`; resets on `load_file()`.
- **Duplicate signal prevention:** `AppController.add_signal` checks `(group_index, channel_index)` against active signals' metadata before loading; returns `False` on duplicates (callers use the return value to count skips for the status bar message).
- **Single controller contact point for `MainWindow` (#48):** `MainWindow` no longer holds a reference to `CursorController`. All cursor actions (`toggle_cursor`, `press_cursor1`, `press_cursor2`, `zoom_to_cursors`, `set_cursor_mode_callback`) are proxy methods on `AppController`, which delegates to `_cursor_ctrl`. `set_controller(ctrl)` has no `cursor_ctrl` parameter.

### Plot area

- **`PlotArea` multi-axis pattern:** `pi.vb` (main ViewBox) is the X-axis host only — no curves added to it. Each signal gets its own `ViewBox` with `setXLink(pi)` for shared X, and an `AxisItem('right')` placed at the next layout column. `pi.vb.sigResized` → `_update_view_geometries()` keeps extra ViewBoxes geometrically aligned.
- **`PlotArea` zoom_to_fit:** computes X bounds from `active.data.timestamps` across all signals, calls `pi.vb.setXRange` (propagates via XLink), then `vb.autoRange()` per signal for independent Y reset.
- **Curve downsampling:** each `PlotDataItem` in `PlotArea.add_signal` has `setClipToView(True)` and `setDownsampling(auto=True, method="peak")`. The curve is constructed without data, added to its `ViewBox` via `vb.addItem(curve)`, and only then given data via `curve.setData(...)` — calling `setData` before the curve has a parent `ViewBox` made pyqtgraph fall back to the `PlotWidget` for `getViewBox()`, which raised `AttributeError: autoRangeEnabled` once downsampling was enabled.
- **Y-axis tick formatting:** `_SignalAxisItem` subclasses `pg.AxisItem`; float signals use `:.6g` (strips floating-point noise like "256.000000007"); integer signals snap ticks to integer positions and format as plain integers.
- **Drag-and-drop MIME type:** `application/x-mdf-viewer-signals` (defined in `view/_mime.py`); payload is a JSON-encoded list of `[group_index, channel_index]` pairs. Event filters installed on `_pw.viewport()` (PlotArea) and `_table.viewport()` (ActiveSignalsTable) handle DragEnter/DragMove/Drop without subclassing PyQtGraph or QTableWidget.

### Plot Stripes (#97)

- **Container structure:** each stripe is a separate `pg.PlotWidget`/`PlotItem` (not multiple rows in one shared `GraphicsLayoutWidget`), stacked in a `QSplitter(Qt.Vertical)`. Stripe-height resizing is the splitter's native drag-handle behavior rather than hand-built divider painting. Every stripe's own `pi.vb` continues to be X-linked across all stripes (not just within one), so the existing per-signal `ViewBox`/axis pattern (see "Plot area" above) is unchanged within a stripe — a stripe is just another `PlotArea`-like host.
- **Why not one shared `GraphicsLayoutWidget`:** a single shared scene would let one cursor `InfiniteLine` visually span every stripe without duplication, but PyQtGraph gives no splitter-equivalent for resizing `PlotItem` rows inside one layout — that would mean hand-rolling drag handles and manual `QGraphicsLayout` stretch-factor updates. Separate `PlotWidget`s get resize handles for free and keep each stripe's X-axis-tick visibility (only the bottom-most stripe shows ticks, REQ-PLOT-181) and active-stripe marker independent and easy to reason about.
- **Cursor lines vs. the delta-time line:** because each stripe is its own `QGraphicsScene`, a single `InfiniteLine` can't span stripes — cursor lines are duplicated one-per-stripe and kept in lockstep (REQ-PLOT-182). The delta-time line is different: it isn't tied to any curve's data, so it only needs to exist in the currently active stripe's `pi.vb` at a time, reparented (or recreated) on active-stripe change, with its vertical position remembered independently per stripe (REQ-PLOT-105).

### Cursor system

- **`CursorController` wiring:** optional dependency injected via `AppController.set_cursor_controller()`; all notify calls are guarded by `None` check so the cursor system can be omitted without touching `AppController`.
- **`CursorController` reads signals on demand (#49):** the controller receives a `get_active_signals: Callable[[], list]` at construction (`app.py` passes `lambda: controller.active_signals`). This eliminates a second authoritative list. `AppController.add_signal` calls `cursor_ctrl.refresh()` after appending; `remove_signal` calls `on_signal_removed` (label cleanup only, before ViewBox destruction) then `refresh()`.
- **CursorView lifetime:** `CursorView` is a `QObject` constructed in `app.py` after `MainWindow` so the PlotItem scene already exists. Tests keep the parent `PlotWidget` alive via a separate pytest fixture to prevent C++ object deletion.
- **Nearest-cursor label logic:** uses identity-based label keys `(cursor_index, active)` to avoid numpy `__eq__` ambiguity (same pitfall as `ActiveSignalsTable._find_row`).
- **Cursor label Y-tracking:** labels are added to the signal's own `ViewBox` so `setPos(x, y)` is in the signal's Y coordinate space and the label tracks Y pan/zoom automatically. `_labels` stores `(TextItem, ViewBox)` tuples. Cursor cleanup is called in `AppController` *before* `plot_area.remove_signal` so the ViewBox is still in the scene when `vb.removeItem(lbl)` runs.
- **Cursor labels show value only:** no unit suffix — the unit is already on the Y-axis and in the Signal Info Box.

### UI details

- **Identity-based row lookup in `ActiveSignalsTable`:** `ActiveSignal` is a mutable dataclass with numpy-array fields; `__eq__` raises `ValueError` on boolean coercion. All lookups use `is` via `_find_row()`.
- **`ActiveSignalsTable.remove_row` / `clear` ordering:** the table widget is mutated first (`removeRow` / `setRowCount(0)`), then `_signals` — `removeRow`/`setRowCount(0)` can synchronously emit `itemSelectionChanged` before returning, and the handler indexes into `_signals`. Mutating `_signals` first left it shorter than the row indices Qt reported, raising `IndexError`. `_on_selection_changed` also has a bounds check as a defensive fallback.
- **Recent files persistence:** plain JSON (no `QSettings`/registry) for transparency and portability; written immediately on successful load so a crash doesn't lose the entry; failed loads are never recorded; stale entries pruned silently when the File menu opens.
- **Recent files menu wiring:** `MainWindow` takes a provider callable (`settings.get_and_prune`) rather than a direct `Settings` reference, keeping the view layer free of settings knowledge; `File.aboutToShow` triggers the rebuild so the list is always fresh.
- **Signal Browser filter debounce (#9):** `_filter_edit.textChanged` (re)starts a single-shot `QTimer` (`_FILTER_DELAY_MS = 250`); `_apply_filter()` runs on timeout. Recursive filtering over a large channel tree is expensive so per-keystroke filtering felt sluggish. `populate()`/`clear()` stop the timer and apply the empty filter immediately.
- **Load busy feedback (#9):** `MainWindow._load_file()` is the single entry point for all three load paths. It sets a wait cursor and a persistent "Loading…" status message for the duration of `controller.load_file()`, restoring both in a `finally` block.
- **File drop confirmation:** `MainWindow._on_file_dropped` checks `controller.is_file_loaded` before replacing an open file; uses `QMessageBox.question` so the user can cancel.
- **Status bar skip notification:** `MainWindow._on_add_signals` counts duplicates via `add_signal`'s `bool` return value and calls `show_status` with a singular/plural message.
- **Toolbar icons:** custom PNGs in `src/mdf_viewer/resources/icons/`; 32×32 px 1× and 64×64 px `@2x` HiDPI variants; `_load_icon(name)` helper wires both sizes into one `QIcon`.
- **Theme-aware toolbar icons:** each icon has a light-gray variant (dark backgrounds) and a dark-gray `_light` variant (light backgrounds). `_icon_suffix()` reads `QApplication.styleHints().colorScheme()` once at startup. Detected once; no live theme-change handling.
- **Application icon:** `src/mdf_viewer/resources/icons/app_icon.ico`; set via `MainWindow.setWindowIcon()`, baked into the EXE via `icon=` in `mdf_viewer.spec`, and used as the installer icon via `SetupIconFile` in `mdf_viewer.iss`.
- **Windows taskbar icon (unfrozen run):** `app.py` calls `SetCurrentProcessExplicitAppUserModelID` on `sys.platform == "win32"` before creating the `QApplication`. Without it Windows shows `python.exe`'s icon in the taskbar when run via the debugger.
- **Splash screen:** `app.py` builds a `QSplashScreen` pixmap from `app_icon.ico` plus version text, shown before the heavier view/controller imports and closed via `splash.finish(window)`. Not unit-tested (consistent with the rest of `app.py`).
- **Help > About:** `MainWindow` has a `Help` menu with an "About MDF-Viewer" action that calls `QMessageBox.about()` with version, description, author, and GitHub link.

### License system

- **v2.0 direction:** v1.5 is the last free/GPL-3.0 feature release. v2.0 stays GPL-3.0 and adds an honor-based license-key system: a cosmetic "Licensed to: …" display with no hard enforcement. GPL does not prohibit charging money, only requires distributing source.
- **Feature-gating model (Option A):** paid features ship as normal GPL code gated by a license-key check; the gate can be removed by anyone building from source — acceptable under the honor model.
- **File format:** JSON with a `payload` block (fields inside are signed) and a `signature` field (base64 Ed25519). `format_version` lives inside the payload so it cannot be tampered with post-signing.
- **Canonical signing:** `json.dumps(payload, sort_keys=True, separators=(',', ':'))` — deterministic, no whitespace.
- **Tiers:** Personal (1 seat), Team (5 seats fixed, `TEAM_SEATS = 5`), Enterprise (0 = unlimited).
- **Perpetual + 2-year updates:** license never expires; `updates_until` date is signed into payload. After expiry the app keeps working but shows a notice.
- **Backwards compatibility:** new payload fields must always be optional with defaults — old licenses remain valid. Only key rotation invalidates old licenses (avoid rotating the key pair).
- **`load_stored()` never raises** — returns `None` on missing or corrupt file so a bad license file never prevents the app from starting.

### Plugin groundwork (#70)

- **`EventBus` is a separate `QObject` owned by `AppController`, not `AppController` itself:** keeps `AppController`'s own class hierarchy free of Qt inheritance, and lets #71 (`PluginContext`) hand plugins `context.events` — a small, fixed surface — rather than a reference to all of `AppController`.
- **Event payloads are per-event dataclasses (`FileLoadedEvent`, `SignalAddedEvent`, ...) carried via `pyqtSignal(object)`, not positional typed args:** upcoming multi-measurement/stripe work (#100/#101/#106) will want to add fields like `measurement_id`/`stripe_id` to these events later. A dataclass field addition doesn't require any existing `.connect()` callback to change; a positional signal signature only stays compatible if new args are strictly appended and never inserted — the dataclass removes that footgun instead of just documenting around it.
- **Purely additive, not a rewiring of internal coordination:** `AppController` keeps every direct call it already makes to `_cursor_ctrl`/`_table`/`_plot`; it also emits an event alongside. No existing internal module was migrated to subscribe instead of being called directly — that direct-call structure is already well-tested and explicit, and there's no current subscriber to justify the swap.
- **`cursor_moved` wiring uses callback injection, not a Qt signal on `CursorController` itself:** `CursorController.set_position_changed_callback()` matches the existing `set_mode_changed_callback` pattern, keeping `CursorController` testable without a `QApplication` and decoupled from `AppController` (its own stated design goal). `AppController.set_cursor_controller()` wires the callback to `self.events.cursor_moved.emit(...)`. Fires on drag, chevron-fetch, and arrow-key step, and once from `_commit_mode` (covers initial cursor placement and `restore()`); suppressed while `HIDDEN`.
- **Help menu order:** License Key action first, separator, About last.
- **License state read once at startup; restart required after import (#51):** `app.py` calls `license_manager.load_stored()` once; `window.set_license(info, manager)` is called once and never again. `MainWindow._on_license()` opens the dialog and does nothing on accept — the dialog's own "restart required" message is the canonical flow.
- **Repo/secrets:** the Ed25519 private key and `generate_license.py` are saved at `C:\Users\andal\Documents\mdf-viewer-private\` — never commit either to any repo. `.gitignore` blocks `generate_license.py`, `*.lic`, and `*.pem`.
