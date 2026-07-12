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

if TYPE_CHECKING:
    from mdf_viewer.controller.app_controller import AppController
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
