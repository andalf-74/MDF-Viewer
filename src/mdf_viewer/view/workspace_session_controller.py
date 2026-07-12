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

from PyQt6.QtWidgets import QMessageBox

if TYPE_CHECKING:
    from mdf_viewer.controller.app_controller import ActiveSignalSnapshot, AppController
    from mdf_viewer.model.loaded_measurement import LoadedMeasurement
    from mdf_viewer.settings import Settings
    from PyQt6.QtWidgets import QTabWidget, QWidget


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
        """Tear down every tab but the first, before a full session
        restore replaces everything (#106 Phase 0).

        `AppController.remove_tab()` only cleans up controller-side state
        (signals, the `TabWorkspace` itself) — it does not touch the
        `QTabWidget` page at all. Mirrors `_on_tab_close_requested`'s full
        teardown (view-side `removeTab()` + `deleteLater()`, #120) for
        every tab removed here too; neither half alone is safe.

        Relies on the same invariant `_on_tab_close_requested` already
        assumes: real tab positions in `_tab_widget` align 1:1 with
        `AppController._workspaces` indices (the pinned "+" placeholder
        sits after all of them once any transient drag-reorder settles).
        """
        controller = self._get_controller()
        if controller is None:
            return
        for index in range(controller.tab_count - 1, 0, -1):
            page = self._tab_widget.widget(index)
            self._tab_widget.removeTab(index)
            page.deleteLater()
            controller.remove_tab(index)
        if self._tab_widget.currentIndex() != 0:
            self._tab_widget.setCurrentIndex(0)
        controller.remove_all()

    def build_tab_skeletons(self, tab_configs: list) -> None:
        """Build every saved tab's skeleton — the tab itself (renamed)
        and its stripe layout (renamed/resized) — with no signals yet
        (#106 Phase 2).

        Assumes `reset_to_single_tab()` already ran, so exactly one tab
        exists. Reuses that tab as `tab_configs[0]` (renamed, not
        recreated) and drives `on_new_tab()`'s own tab-creation factory
        for each further `TabConfig` — a deliberate simplification (see
        `docs/architecture.md`): each call fires `switch_tab()` as a side
        effect and doesn't reconcile `_tab_counter` against restored
        names, accepted for this rare bulk operation rather than
        building a separate non-interactive tab-creation path.
        """
        controller = self._get_controller()
        if controller is None or not tab_configs:
            return
        for _ in range(len(tab_configs) - 1):
            self._on_new_tab()
        for index, tab_config in enumerate(tab_configs):
            self._tab_widget.setTabText(index, tab_config.name)
            page = self._tab_widget.widget(index)
            self.build_stripe_skeleton(page, tab_config.stripes, tab_config.active_stripe_index)
            page.setSizes(list(tab_config.page_splitter_sizes))

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
