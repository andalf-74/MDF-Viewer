"""WorkspaceSessionController — owns MainWindow's `.mvc` save/load/apply
orchestration (#136).

Despite the "-Controller" suffix (kept to match issue #136's own wording),
this class lives in `view/`, NOT `controller/`. It constructs and shows
concrete `QDialog`s (`SignalGroupPickerDialog`, `NearMatchDialog`,
`MeasurementMappingDialog`, `SignalsNotFoundDialog`, `QMessageBox`,
`QFileDialog`) and manipulates live `QTabWidget` pages directly — both of
which `controller/` classes are prohibited from doing by this project's
MVC rule (see `docs/architecture.md`'s "Layers" table and "View imports in
controller: TYPE_CHECKING-only").

Constructor dependencies are narrow callables/direct objects rather than a
full `MainWindow`/`AppController` reference, mirroring the pattern already
used by `controller/cursor_controller.py`/`controller/zoom_controller.py`
for stateful collaborators: read state you don't own via an injected
callable instead of caching a second copy.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

from PyQt6.QtWidgets import QFileDialog, QMessageBox

from mdf_viewer.view.widgets.busy_cursor import busy_cursor

if TYPE_CHECKING:
    from mdf_viewer.controller.app_controller import ActiveSignalSnapshot, AppController
    from mdf_viewer.model.loaded_measurement import LoadedMeasurement
    from mdf_viewer.model.viewer_config import ViewerConfig
    from mdf_viewer.settings import Settings
    from PyQt6.QtWidgets import QTabWidget, QWidget

# Duplicated from main_window.py's own module-level constants (not imported
# from there — main_window.py imports this module, so the reverse import
# would be circular). Keep the two literal strings in sync if either changes.
_MDF_FILE_FILTER = "MDF Files (*.mf4 *.mdf *.dat);;All Files (*)"
_MVC_FILE_FILTER = "MDF Viewer Config (*.mvc);;All Files (*)"


class WorkspaceSessionController:
    def __init__(
        self,
        parent: "QWidget",
        tab_widget: "QTabWidget",
        get_controller: "Callable[[], AppController | None]",
        get_settings: "Callable[[], Settings | None]",
        on_new_tab: Callable[[], int],
        resolve_and_confirm_snapshots: Callable[
            [dict[int, list]], tuple[dict[int, list], list[str]]
        ],
        capture_window_geometry: Callable[[], dict],
        capture_splitter_sizes: Callable[[], dict],
        apply_window_geometry: Callable[[dict | None], None],
        apply_splitter_sizes: Callable[[dict | None], None],
        tab_names: Callable[[], list[str]],
        tab_page_splitter_sizes: Callable[[], list[tuple[int, int]]],
        save_config_as: Callable[[], None],
        show_status: Callable[[str, int], None],
        clear_status: Callable[[], None],
        is_plot_page: Callable[[object], bool],
        discard_non_plot_page: Callable[[object], None],
        find_tab_type: Callable[[str], object | None],
        create_non_plot_tab: Callable[[object, str], int],
        tab_specs: Callable[[], list[tuple[str, str, object | None]]],
    ) -> None:
        self._parent = parent
        self._tab_widget = tab_widget
        self._get_controller = get_controller
        self._get_settings = get_settings
        self._on_new_tab = on_new_tab
        self._resolve_and_confirm_snapshots = resolve_and_confirm_snapshots
        self._capture_window_geometry = capture_window_geometry
        self._capture_splitter_sizes = capture_splitter_sizes
        self._apply_window_geometry = apply_window_geometry
        self._apply_splitter_sizes = apply_splitter_sizes
        self._tab_names = tab_names
        self._tab_page_splitter_sizes = tab_page_splitter_sizes
        self._save_config_as = save_config_as
        self._show_status = show_status
        self._clear_status = clear_status
        # #148 — pluggable tab types.
        self._is_plot_page = is_plot_page
        self._discard_non_plot_page = discard_non_plot_page
        self._find_tab_type = find_tab_type
        self._create_non_plot_tab = create_non_plot_tab
        self._tab_specs = tab_specs

    # ------------------------------------------------------------------
    # Save path
    # ------------------------------------------------------------------

    def save_config_to(self, path: Path) -> None:
        import dataclasses
        from mdf_viewer.config_manager import ConfigManager
        controller = self._get_controller()
        settings = self._get_settings()
        if controller is None or settings is None:
            return
        try:
            config = controller.capture_config(
                path, self._tab_names(), self._tab_page_splitter_sizes(),
                tab_specs=self._tab_specs(), active_tab_bar_index=self._tab_widget.currentIndex(),
            )
            config = dataclasses.replace(
                config,
                window_geometry=self._capture_window_geometry(),
                splitter_sizes=self._capture_splitter_sizes(),
            )
            ConfigManager.save(config, path, settings.config_path_mode)
        except Exception as exc:
            QMessageBox.critical(self._parent, "Save Workspace Error", str(exc))
            return
        controller.current_config_path = path
        settings.add_recent(path)
        self._show_status(f"Workspace saved to {path.name}", 3000)

    # ------------------------------------------------------------------
    # Load / apply path
    # ------------------------------------------------------------------

    def resolve_saved_measurements(
        self, measurement_configs: list, config_path: Path
    ) -> tuple[list, list[str]]:
        """Resolve every saved measurement's path against *config_path*'s
        directory (REQ-FILE-063/064, generalized to N measurements, #106).

        Returns (resolved_configs, missing_paths) — resolved_configs has
        one entry per input, in the same order: resolved ones get their
        path replaced with the found absolute path, unresolved ones keep
        their original (raw, still-unresolved) path string so
        `AppController.restore_measurements()` fails them again at the
        same index rather than the list silently shrinking and losing
        alignment with the saved signals' `measurement_index` (REQ-FILE-093).
        missing_paths lists the raw saved paths that couldn't be found,
        for `confirm_missing_measurements()`.
        """
        import dataclasses
        from mdf_viewer.config_manager import ConfigManager

        resolved = []
        missing: list[str] = []
        for mc in measurement_configs:
            found = ConfigManager.resolve_measurement_path(mc.path, config_path)
            if found is None:
                missing.append(mc.path)
                resolved.append(mc)
            else:
                resolved.append(dataclasses.replace(mc, path=str(found)))
        return resolved, missing

    def confirm_missing_measurements(self, missing_paths: list[str]) -> bool:
        """Ask whether to continue without measurements that couldn't be
        found (REQ-FILE-097/098) — one combined dialog listing every
        missing path, not an interactive locate-prompt per file (that
        stays REQ-FILE-065's behavior, unchanged, for a session with
        exactly one measurement). Returns True to proceed (continuing
        drops them — `restore_measurements()` will produce `None` at
        their index regardless, so there's nothing to "undo" here),
        False to abort the whole session load.
        """
        if not missing_paths:
            return True
        listing = "\n".join(missing_paths)
        reply = QMessageBox.question(
            self._parent,
            "Measurements Not Found",
            f"The following measurement(s) could not be found:\n\n{listing}\n\n"
            "Continue loading the session without them?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        return reply == QMessageBox.StandardButton.Yes

    def reset_to_single_tab(self) -> None:
        """Tear down every tab but one, before a full session restore
        replaces everything (#106 Phase 0; extended #148 for non-plot tabs).

        `AppController.remove_tab()` only cleans up controller-side state
        (signals, the `TabWorkspace` itself) — it does not touch the
        `QTabWidget` page at all. Mirrors `_on_tab_close_requested`'s full
        teardown (view-side `removeTab()` + `deleteLater()`, #120) for
        every tab removed here too; neither half alone is safe.

        Keeps the *first plot page found* (not always index 0 once a
        non-plot tab can precede it) — guaranteed to exist, since M4's
        corrected parking decision never lets the last plot page
        disappear during normal closing. Every other real tab, plot or
        non-plot, is torn down via its own kind's teardown path. Removed
        in descending index order so removing a later tab never shifts
        the identity of an earlier, not-yet-processed one.
        """
        controller = self._get_controller()
        if controller is None:
            return
        placeholder_index = self._tab_widget.count() - 1
        real_indices = list(range(placeholder_index))
        keep_index = next(
            (i for i in real_indices if self._is_plot_page(self._tab_widget.widget(i))), None,
        )
        for index in reversed(real_indices):
            if index == keep_index:
                continue
            page = self._tab_widget.widget(index)
            if self._is_plot_page(page):
                wi = controller.tab_index_for_plot(page.plot_area)
                self._tab_widget.removeTab(index)
                page.deleteLater()
                if wi is not None:
                    controller.remove_tab(wi)
            else:
                self._discard_non_plot_page(page)
                self._tab_widget.removeTab(index)
                page.deleteLater()
        if self._tab_widget.currentIndex() != 0:
            self._tab_widget.setCurrentIndex(0)
        controller.remove_all()

    def build_tab_skeletons(self, tab_configs: list) -> list:
        """Build every saved tab's skeleton — the tab itself (renamed)
        and, for a plot tab, its stripe layout (renamed/resized) — with
        no signals yet (#106 Phase 2; extended #148 for non-plot tabs).

        Processes *tab_configs* as one single ordered pass (plot and
        non-plot interleaved in saved order, not plot-first-then-non-plot)
        — REQ-PLUGIN-351's "same relative position" depends on this.
        Assumes `reset_to_single_tab()` already ran, so exactly one plot
        tab exists. Reused for the *first* `"plot"` entry found (renamed,
        not recreated, then relocated to its correct position via
        `moveTab()` once every other tab has been built); every other
        `"plot"` entry drives `on_new_tab()`'s own tab-creation factory —
        a deliberate simplification (see `docs/architecture.md`): each
        call fires `switch_tab()` as a side effect and doesn't reconcile
        `_tab_counter` against restored names, accepted for this rare
        bulk operation rather than building a separate non-interactive
        tab-creation path. A non-plot entry looks its `view_type` up in
        the plugin registry and builds it via `create_non_plot_tab()`,
        titled from the *saved* name (so a user's rename survives); an
        unregistered type is skipped entirely (REQ-PLUGIN-352). If
        *tab_configs* has zero `"plot"` entries, the surviving tab is
        left exactly where it is — an implicit, unsaved extra Plot tab,
        since `AppController` structurally always keeps >=1 workspace
        alive — and every entry is simply appended after it.

        Returns `resolved_workspaces: list[TabWorkspace | None]`, one
        entry per *tab_configs* position — the `TabWorkspace` for a
        (re)used/created plot tab, `None` for a non-plot or skipped
        entry — threaded to `AppController.restore_config()` (#148).
        """
        controller = self._get_controller()
        if controller is None or not tab_configs:
            return []

        survivor_page = self._tab_widget.widget(0)
        first_plot_index = next(
            (i for i, tc in enumerate(tab_configs) if tc.view_type == "plot"), None,
        )
        resolved_workspaces: list = [None] * len(tab_configs)

        for index, tab_config in enumerate(tab_configs):
            if tab_config.view_type == "plot":
                if index == first_plot_index:
                    page = survivor_page
                else:
                    page = self._tab_widget.widget(self._on_new_tab())
                self._tab_widget.setTabText(self._tab_widget.indexOf(page), tab_config.name)
                self.build_stripe_skeleton(page, tab_config.stripes, tab_config.active_stripe_index)
                page.setSizes(list(tab_config.page_splitter_sizes))
                wi = controller.tab_index_for_plot(page.plot_area)
                if wi is not None:
                    resolved_workspaces[index] = controller.all_workspaces()[wi]
            else:
                registration = self._find_tab_type(tab_config.view_type)
                if registration is not None:
                    self._create_non_plot_tab(registration, tab_config.name)
                # else: unregistered type — skipped (REQ-PLUGIN-352);
                # resolved_workspaces[index] stays None either way, a
                # non-plot tab never has a workspace to begin with.

        if first_plot_index is not None:
            current_survivor_index = self._tab_widget.indexOf(survivor_page)
            if current_survivor_index != first_plot_index:
                self._tab_widget.tabBar().moveTab(current_survivor_index, first_plot_index)

        return resolved_workspaces

    def build_stripe_skeleton(self, page, stripes: list, active_stripe_index: int) -> None:
        """Build one tab's stripe layout from saved `StripeConfig`s (#106
        Phase 2), with no signals placed yet.

        `PlotStripesArea` already creates one stripe unconditionally in
        its own `__init__` — reused as `stripes[0]` (renamed) rather than
        creating an extra, un-renamed empty stripe alongside it (a real
        bug the #106 Plan-review pass caught: `create_stripe()` isn't a
        no-op to call "just in case", it always appends). Sizes are set
        once, only after every stripe for this tab exists, since
        `create_stripe()` itself resets every stripe's size on every call.
        """
        plot_area = page.plot_area
        ast = page.active_signals_table
        existing = plot_area.get_stripes()
        for _ in range(len(stripes) - len(existing)):
            plot_area.create_stripe()
        all_stripes = plot_area.get_stripes()
        for stripe, stripe_config in zip(all_stripes, stripes):
            ast.rename_stripe_segment(stripe, stripe_config.name)
        plot_area.set_stripe_sizes([s.size for s in stripes])
        if 0 <= active_stripe_index < len(all_stripes):
            plot_area.set_active_stripe(all_stripes[active_stripe_index])

    def resolve_config_signals_for_tabs(
        self, tab_configs: list, measurements: list,
    ) -> tuple[dict[int, list], list[str]]:
        """Match every saved tab's SignalConfig entries to channels in the
        resolved measurement pool (#106 M6, full multi-tab replacement for
        the old single-tab `_resolve_config_signals`).

        *measurements* is `AppController.restore_measurements()`'s
        index-aligned result (a `None` entry means that measurement failed
        to load, per Phase 1) — a signal whose `measurement_index` points
        at a `None` slot is folded straight into `not_found` without
        attempting resolution at all, since there's nothing to search
        (REQ-FILE-098). Every other signal's search is scoped to its own
        saved measurement (REQ-FILE-093), not the whole pool.

        Returns (resolved_by_tab, not_found) — resolved_by_tab maps tab
        index to a list of (ActiveSignalSnapshot, group_index,
        channel_index, measurement) tuples, ready for
        `AppController.restore_config()`.
        """
        snapshots_by_tab: dict[int, list] = {}
        not_found: list[str] = []
        for tab_index, tab_config in enumerate(tab_configs):
            stripe_names = [s.name for s in tab_config.stripes]
            for sig in tab_config.signals:
                measurement = (
                    measurements[sig.measurement_index]
                    if 0 <= sig.measurement_index < len(measurements) else None
                )
                if measurement is None:
                    not_found.append(sig.name)
                    continue
                stripe_name = (
                    stripe_names[sig.stripe_index]
                    if 0 <= sig.stripe_index < len(stripe_names) else ""
                )
                snapshots_by_tab.setdefault(tab_index, []).append(
                    self.signal_config_to_snapshot(sig, stripe_name, measurement=measurement)
                )

        # use_group_name=True preserves the old single-tab
        # _resolve_config_signals' long-standing behavior unchanged (see
        # _resolve_and_confirm_snapshots' own docstring for why this is an
        # explicit switch) — baked into the injected callable at
        # construction time (MainWindow._session wiring).
        resolved_by_tab, more_not_found = self._resolve_and_confirm_snapshots(snapshots_by_tab)
        return resolved_by_tab, not_found + more_not_found

    def signal_config_to_snapshot(
        self, sig, stripe_name: str = "", measurement: "object | None" = None,
    ) -> "ActiveSignalSnapshot":
        """Convert a saved `SignalConfig` into the `ActiveSignalSnapshot`
        currency `MainWindow._resolve_and_confirm_snapshots()` operates on
        (#106) — `_restore_snapshots()`'s snapshots instead come from
        already-active `ActiveSignal`s (`AppController._snapshot_signals`),
        since that caller runs on a live session, not saved JSON data.

        *measurement*, when given, is the live `LoadedMeasurement` this
        signal was saved against (#106 M6, resolved via `SignalConfig.
        measurement_index` against `AppController.restore_measurements()`'s
        result) — scopes this snapshot's later resolution to that one
        measurement (REQ-FILE-093) instead of the whole pool.
        """
        from mdf_viewer.controller.app_controller import ActiveSignalSnapshot
        return ActiveSignalSnapshot(
            name=sig.name,
            color=tuple(sig.color),  # type: ignore[arg-type]
            line_width=sig.line_width,
            line_style=sig.line_style,
            display_mode=sig.display_mode,
            marker_shape=sig.marker_shape,
            step_mode=sig.step_mode,
            enum_display_table=sig.enum_display_table,
            enum_display_cursor=sig.enum_display_cursor,
            enum_display_yaxis=sig.enum_display_yaxis,
            group_name=sig.group_name,
            stripe_name=stripe_name,
            measurement=measurement,
            visible=sig.visible,
        )

    # ------------------------------------------------------------------
    # Unified restore pipeline (#136) — load_config()/apply_config() share
    # this method for everything from "obtain measurements" onward (build
    # skeletons -> resolve signals -> restore_config), differing only in
    # how `measurements: list[LoadedMeasurement | None]` is obtained.
    # Window geometry/splitter-size application is each caller's own
    # responsibility, at its own correct point relative to its own
    # cancellable dialog(s) — not shared here (see obtain_measurements'
    # own docstring note below on REQ-FILE-114).
    # ------------------------------------------------------------------

    def _restore_saved_workspace(
        self,
        config: "ViewerConfig",
        *,
        obtain_measurements: "Callable[[ViewerConfig], list[LoadedMeasurement | None] | None]",
        require_at_least_one_loaded: bool,
        finalize: Callable[[Path], None],
        source_path: Path,
    ) -> None:
        from mdf_viewer.view.signals_not_found_dialog import SignalsNotFoundDialog

        # *obtain_measurements* is responsible for calling
        # self.reset_to_single_tab() itself, at whatever point its own
        # caller-specific logic today calls it (load_config: after path
        # resolution, before restore_measurements, both busy-cursor-wrapped;
        # apply_config: after the mapping dialog). It must NOT be called
        # unconditionally here — both callers today leave the workspace
        # completely untouched when their own dialog is cancelled, and
        # hoisting the reset out of the cancel path would destroy the
        # user's open tabs even on a cancelled Load/Apply.
        #
        # Window geometry/splitter sizes are NOT applied by this shared
        # method at all — each caller applies them at its own correct
        # point (load_config: unconditionally, before its own
        # locate-prompt/missing-measurement dialog, matching its
        # long-standing tested behavior; apply_config: only once
        # obtain_measurements() below has already succeeded, per
        # REQ-FILE-114's "cancelling this dialog aborts with nothing
        # changed" — a live-testing report caught apply_config visibly
        # resizing the window even on a cancelled mapping dialog, a bug
        # that predates #136 but was never actually correct).
        measurements = obtain_measurements(config)
        if measurements is None:
            return  # cancelled partway through — workspace untouched

        if (
            require_at_least_one_loaded
            and measurements
            and not any(m is not None for m in measurements)
        ):
            QMessageBox.critical(self._parent, "Load Error", "No measurements could be loaded.")
            return

        resolved_workspaces = self.build_tab_skeletons(list(config.tabs))

        resolved_by_tab, not_found = self.resolve_config_signals_for_tabs(
            list(config.tabs), measurements,
        )
        if not_found:
            SignalsNotFoundDialog(sorted(set(not_found)), self._parent).exec()

        controller = self._get_controller()
        controller.restore_config(config, resolved_by_tab, measurements, resolved_workspaces)

        # build_tab_skeletons() reproduces config.tabs' exact order in the
        # tab bar *except* in the "zero plot entries" case (#148), where
        # the surviving implicit extra Plot tab occupies position 0 and
        # every restored (non-plot) tab is shifted one position later.
        has_plot_entry = any(ws is not None for ws in resolved_workspaces)
        target_index = config.active_tab_index + (0 if has_plot_entry else 1)
        if 0 <= target_index < self._tab_widget.count() - 1:  # -1 excludes the "+" placeholder
            self._tab_widget.setCurrentIndex(target_index)

        finalize(source_path)

    def load_config(self, path: Path) -> None:
        import dataclasses
        from mdf_viewer.config_manager import ConfigManager
        from mdf_viewer.errors import ConfigLoadError
        from mdf_viewer.model.viewer_config import MeasurementConfig

        controller = self._get_controller()
        settings = self._get_settings()
        if controller is None or settings is None:
            return

        try:
            config = ConfigManager.load(path)
        except ConfigLoadError as exc:
            QMessageBox.critical(self._parent, "Config Load Error", str(exc))
            return

        self._apply_window_geometry(config.window_geometry)
        self._apply_splitter_sizes(config.splitter_sizes)

        def obtain(cfg: "ViewerConfig"):
            measurement_configs = list(cfg.measurements)
            if len(measurement_configs) <= 1:
                # REQ-FILE-065: a session with zero or one measurement still
                # gets an interactive locate-prompt for a missing file, not
                # the combined continue/cancel dialog used for 2+ (REQ-FILE-097).
                mc = measurement_configs[0] if measurement_configs else None
                raw_path = mc.path if mc is not None else ""
                found = ConfigManager.resolve_measurement_path(raw_path, path)
                if found is None:
                    mdf_path_str, _ = QFileDialog.getOpenFileName(
                        self._parent,
                        f"Locate Measurement File for '{path.name}'",
                        "",
                        _MDF_FILE_FILTER,
                    )
                    if not mdf_path_str:
                        return None
                    found = Path(mdf_path_str)
                if mc is not None:
                    resolved_measurement_configs = [dataclasses.replace(mc, path=str(found))]
                else:
                    resolved_measurement_configs = [
                        MeasurementConfig(path=str(found), label="M1", offset_s=0.0)
                    ]
            else:
                resolved_configs, missing = self.resolve_saved_measurements(
                    measurement_configs, path,
                )
                if not self.confirm_missing_measurements(missing):
                    return None
                resolved_measurement_configs = resolved_configs

            with busy_cursor(
                "Loading session…", show_status=self._show_status, clear_status=self._clear_status,
            ):
                self.reset_to_single_tab()
                return controller.restore_measurements(
                    resolved_measurement_configs, cfg.primary_measurement_index,
                    cfg.measurements_synchronized,
                )

        def finalize(p: Path) -> None:
            controller.current_config_path = p
            settings.add_recent(p)

        self._restore_saved_workspace(
            config, obtain_measurements=obtain, require_at_least_one_loaded=True,
            finalize=finalize, source_path=path,
        )

    def apply_config(self) -> None:
        """Apply a saved .mvc workspace's tabs/stripes/signals onto the
        currently loaded measurement(s), without opening any file the
        config records (#105, REQ-FILE-110..119).

        Reuses the normal session-restore pipeline (`_restore_saved_workspace`)
        unchanged — the only new step is the measurement-mapping dialog,
        which replaces `restore_measurements()`'s file-opening entirely
        with a pure selection from measurements already loaded.
        """
        from mdf_viewer.config_manager import ConfigManager
        from mdf_viewer.errors import ConfigLoadError

        controller = self._get_controller()
        settings = self._get_settings()
        if controller is None or settings is None:
            return

        path_str, _ = QFileDialog.getOpenFileName(
            self._parent, "Apply Config", "", _MVC_FILE_FILTER
        )
        if not path_str:
            return
        path = Path(path_str)

        try:
            config = ConfigManager.load(path)
        except ConfigLoadError as exc:
            QMessageBox.critical(self._parent, "Config Load Error", str(exc))
            return

        def obtain(cfg: "ViewerConfig"):
            measurement_configs = list(cfg.measurements)
            if measurement_configs:
                from mdf_viewer.view.measurement_mapping_dialog import MeasurementMappingDialog
                dlg = MeasurementMappingDialog(
                    measurement_configs, controller.measurements, self._parent
                )
                if not dlg.exec():
                    return None
                mapped = dlg.mapping()
            else:
                mapped = []
            # Only apply geometry/splitter sizes once we know we're actually
            # proceeding (REQ-FILE-114: cancelling the mapping dialog above
            # must leave "nothing changed" — caught live, this used to run
            # unconditionally before the dialog even showed).
            self._apply_window_geometry(cfg.window_geometry)
            self._apply_splitter_sizes(cfg.splitter_sizes)
            self.reset_to_single_tab()
            return mapped

        def finalize(p: Path) -> None:
            settings.add_recent(p)
            # Deliberately not setting controller.current_config_path here
            # (REQ-FILE-119) — a later plain "Save Workspace" must not
            # silently overwrite the applied template with a different
            # measurement mapping. Prompt for a new save location instead.
            self._save_config_as()

        self._restore_saved_workspace(
            config, obtain_measurements=obtain, require_at_least_one_loaded=False,
            finalize=finalize, source_path=path,
        )
