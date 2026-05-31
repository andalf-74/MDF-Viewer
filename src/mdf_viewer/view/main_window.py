"""MainWindow — top-level window: menu bar, toolbar, and the splitter layout.

Layout (per CLAUDE.md):

    +-----------------------------------------------------------+
    | Menu bar (File: Load MDF / Exit)                          |
    | Toolbar (Load File | Zoom to Fit | Cursor Toggle)         |
    +------------+--------------------------------+-------------+
    |            | Plot Area                      |             |
    | Signal     +--------------------------------+ Active      |
    | Browser    | Measurement Info | Signal Info | Signals     |
    | (tree)     |                                | Table       |
    +------------+--------------------------------+-------------+

This module only assembles widgets and exposes signals/slots; it contains no
data-loading or plotting logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QSplitter,
    QStyle,
)

from mdf_viewer.model.mdf_loader import MdfLoadError
from mdf_viewer.view.active_signals_table import ActiveSignalsTable
from mdf_viewer.view.measurement_info_box import MeasurementInfoBox
from mdf_viewer.view.plot_area import PlotArea
from mdf_viewer.view.signal_browser import SignalBrowser
from mdf_viewer.view.signal_info_box import SignalInfoBox

if TYPE_CHECKING:
    from mdf_viewer.controller.app_controller import AppController

_MDF_FILE_FILTER = "MDF Files (*.mf4 *.mdf *.dat);;All Files (*)"


class MainWindow(QMainWindow):
    """Assembles the menu bar, toolbar, and nested-splitter main layout."""

    def __init__(self) -> None:
        super().__init__()
        self._controller: AppController | None = None
        self._cursor_ctrl = None
        self._recent_provider: Callable[[], list[Path]] | None = None
        self._recent_actions: list[QAction] = []
        self._recent_sep: QAction | None = None
        self.setWindowTitle("MDF-Viewer")
        self.resize(1280, 800)
        self._build_actions()
        self._build_menu()
        self._build_toolbar()
        self._build_layout()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_controller(
        self, controller: AppController, cursor_ctrl=None
    ) -> None:
        """Wire the controller after it has been constructed with this window's views."""
        self._controller = controller
        self._cursor_ctrl = cursor_ctrl
        self.signal_browser.add_signal_requested.connect(self._on_add_signal)
        self.active_signals_table.remove_requested.connect(controller.remove_signal)
        self.active_signals_table.remove_all_requested.connect(controller.remove_all)
        self.active_signals_table.selection_changed.connect(
            controller.set_selected_signal
        )
        self.active_signals_table.color_change_requested.connect(
            self._on_color_changed
        )

    def set_recent_files_provider(
        self, provider: Callable[[], list[Path]]
    ) -> None:
        """Supply a callable that returns the current recent files list."""
        self._recent_provider = provider

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_actions(self) -> None:
        load_icon = self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon)
        self._load_action = QAction(load_icon, "Load MDF…", self)
        self._load_action.setShortcut(QKeySequence.StandardKey.Open)
        self._load_action.setToolTip("Load MDF File (Ctrl+O)")
        self._load_action.triggered.connect(self._on_load_file)

        self._zoom_fit_action = QAction("Zoom to Fit", self)
        self._zoom_fit_action.setShortcut(QKeySequence("Ctrl+0"))
        self._zoom_fit_action.setToolTip("Zoom to fit all active signals")
        self._zoom_fit_action.triggered.connect(self._on_zoom_to_fit)

        self._cursor_action = QAction("Cursors", self)
        self._cursor_action.setToolTip("Toggle cursors (off → 1 → 2 → off)")
        self._cursor_action.triggered.connect(self._on_cursor_toggle)

    def _build_menu(self) -> None:
        self._file_menu = self.menuBar().addMenu("&File")
        self._file_menu.addAction(self._load_action)
        self._file_menu.addSeparator()
        self._exit_action = QAction("Exit", self)
        self._exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        self._exit_action.triggered.connect(self.close)
        self._file_menu.addAction(self._exit_action)
        self._file_menu.aboutToShow.connect(self._rebuild_recent_files)

    def _build_toolbar(self) -> None:
        toolbar = self.addToolBar("Main")
        toolbar.setMovable(False)
        toolbar.addAction(self._load_action)
        toolbar.addSeparator()
        toolbar.addAction(self._zoom_fit_action)
        toolbar.addAction(self._cursor_action)

    def _build_layout(self) -> None:
        self.signal_browser = SignalBrowser()
        self.plot_area = PlotArea()
        self.active_signals_table = ActiveSignalsTable()
        self.measurement_info_box = MeasurementInfoBox()
        self.signal_info_box = SignalInfoBox()

        bottom_splitter = QSplitter(Qt.Orientation.Horizontal)
        bottom_splitter.addWidget(self.measurement_info_box)
        bottom_splitter.addWidget(self.signal_info_box)
        bottom_splitter.setStretchFactor(0, 1)
        bottom_splitter.setStretchFactor(1, 1)

        center_splitter = QSplitter(Qt.Orientation.Vertical)
        center_splitter.addWidget(self.plot_area)
        center_splitter.addWidget(bottom_splitter)
        center_splitter.setStretchFactor(0, 3)
        center_splitter.setStretchFactor(1, 1)

        outer_splitter = QSplitter(Qt.Orientation.Horizontal)
        outer_splitter.addWidget(self.signal_browser)
        outer_splitter.addWidget(center_splitter)
        outer_splitter.addWidget(self.active_signals_table)
        outer_splitter.setStretchFactor(0, 0)
        outer_splitter.setStretchFactor(1, 1)
        outer_splitter.setStretchFactor(2, 0)
        outer_splitter.setSizes([260, 760, 260])

        self.setCentralWidget(outer_splitter)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_load_file(self) -> None:
        if self._controller is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Load MDF File", "", _MDF_FILE_FILTER
        )
        if not path:
            return
        try:
            self._controller.load_file(path)
        except MdfLoadError as exc:
            QMessageBox.critical(self, "Load Error", str(exc))

    def _on_add_signal(self, group_index: int, channel_index: int) -> None:
        if self._controller is None:
            return
        try:
            self._controller.add_signal(group_index, channel_index)
        except MdfLoadError as exc:
            QMessageBox.critical(self, "Error Loading Signal", str(exc))

    def _on_color_changed(self, active, new_color) -> None:
        self.plot_area.recolor_signal(active, new_color)

    def _on_zoom_to_fit(self) -> None:
        if hasattr(self.plot_area, "zoom_to_fit"):
            self.plot_area.zoom_to_fit()

    def _on_cursor_toggle(self) -> None:
        if self._cursor_ctrl is not None:
            self._cursor_ctrl.toggle()

    def _rebuild_recent_files(self) -> None:
        for action in self._recent_actions:
            self._file_menu.removeAction(action)
        if self._recent_sep is not None:
            self._file_menu.removeAction(self._recent_sep)
        self._recent_actions = []
        self._recent_sep = None

        if self._recent_provider is None:
            return
        paths = self._recent_provider()
        if not paths:
            return

        self._recent_sep = self._file_menu.insertSeparator(self._exit_action)
        for path in paths:
            action = QAction(Path(path).name, self)
            action.setToolTip(str(path))
            action.triggered.connect(lambda checked, p=path: self._on_open_recent(p))
            self._file_menu.insertAction(self._exit_action, action)
            self._recent_actions.append(action)

    def _on_open_recent(self, path: Path) -> None:
        if self._controller is None:
            return
        try:
            self._controller.load_file(path)
        except MdfLoadError as exc:
            QMessageBox.critical(self, "Load Error", str(exc))
