"""MainWindow — top-level window: menu bar, toolbar, and the splitter layout.

Layout (per CLAUDE.md):

    +-----------------------------------------------------------------+
    | Menu bar (File: Load MDF / Exit)                                |
    | Toolbar (Load File | Zoom to Fit | Cursor Toggle)               |
    +------------+------------------------+----------+---------------+
    | Signal     |                        | Active   | Signal Info / |
    | Browser /  | Plot Stripes Area      | Signals  | Properties    |
    | Meas. Info | (one or more stripes)  | Table    | (drawer)      |
    | (drawer)   |                        |          |               |
    +------------+------------------------+----------+---------------+

The Signal Browser/Measurement Info panel (left) and the Signal Info/
Properties panel (right) are each a `DockablePanel` (#98): pinned as a
docked column by default, or collapsible into a hover-reveal overlay.

This module only assembles widgets and exposes signals/slots; it contains no
data-loading or plotting logic.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Callable

from PyQt6.QtCore import (
    QEvent,
    QSize,
    Qt,
    QThread,
    QUrl,
    pyqtSignal,
)
from PyQt6.QtGui import QAction, QDesktopServices, QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

_ICONS_DIR = Path(__file__).parent.parent / "resources" / "icons"


def _load_icon(name: str) -> QIcon:
    icon = QIcon()
    icon.addFile(str(_ICONS_DIR / f"{name}.png"), QSize(32, 32))
    icon.addFile(str(_ICONS_DIR / f"{name}@2x.png"), QSize(64, 64))
    return icon


def _icon_suffix() -> str:
    """Return "_light" unless the OS explicitly reports a dark color scheme.

    The unsuffixed icons are light-gray and meant for dark backgrounds; the
    "_light" variants are dark-gray and meant for light backgrounds. Detected
    once at startup; an "Unknown" report (e.g. on platforms without theme
    support) falls back to the light-mode icons, since light mode is the more
    common default.
    """
    scheme = QApplication.styleHints().colorScheme()
    return "" if scheme == Qt.ColorScheme.Dark else "_light"


from mdf_viewer import __version__
from mdf_viewer.errors import MdfLoadError
from mdf_viewer.license.license_info import LicenseInfo
from mdf_viewer.license.license_manager import LicenseManager
from mdf_viewer.settings import Settings
from mdf_viewer.view.active_signals_table import ActiveSignalsTable
from mdf_viewer.view.dockable_panel import DockablePanel
from mdf_viewer.view.license_dialog import LicenseDialog
from mdf_viewer.view.measurement_info_box import MeasurementInfoBox
from mdf_viewer.view.plot_stripes_area import PlotStripesArea
from mdf_viewer.view.signal_browser import SignalBrowser
from mdf_viewer.view.signal_info_box import SignalInfoBox
from mdf_viewer.view.widgets import make_splitter

if TYPE_CHECKING:
    from mdf_viewer.controller.app_controller import AppController

_PANEL_W = 260         # left panel default width in pixels
_INFO_DRAWER_W = 260   # info/properties drawer default width in pixels



_MDF_FILE_FILTER = "MDF Files (*.mf4 *.mdf *.dat);;All Files (*)"
_ALL_FILE_FILTER = "All Supported Files (*.mf4 *.mdf *.dat *.mvc);;MDF Files (*.mf4 *.mdf *.dat);;MDF Viewer Config (*.mvc);;All Files (*)"
_GITHUB_URL = "https://github.com/andalf-74/MDF-Viewer"


class MainWindow(QMainWindow):
    """Assembles the menu bar, toolbar, and nested-splitter main layout."""

    def __init__(self) -> None:
        super().__init__()
        self._controller: AppController | None = None
        self._recent_provider: Callable[[], list[Path]] | None = None
        self._recent_actions: list[QAction] = []
        self._recent_sep: QAction | None = None
        self._license_info: LicenseInfo | None = None
        self._license_manager: LicenseManager | None = None
        self._settings: Settings | None = None
        self._update_thread: _UpdateCheckThread | None = None
        self.setWindowTitle("MDF-Viewer — unregistered")
        self.setWindowIcon(QIcon(str(_ICONS_DIR / "app_icon.ico")))
        self.resize(1280, 800)
        self._build_actions()
        self._build_menu()
        self._build_toolbar()
        self._build_layout()
        self.statusBar()  # pre-create so its height is always reserved

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_controller(self, controller: AppController) -> None:
        """Wire the controller after it has been constructed with this window's views."""
        self._controller = controller
        controller.set_cursor_mode_callback(self._on_cursor_mode_changed)
        self.signal_browser.add_signals_requested.connect(self._on_add_signals)
        self.plot_area.signals_dropped_on_stripe.connect(self._on_add_signals_to_stripe)
        self.plot_area.file_dropped.connect(self._on_file_dropped)
        self.plot_area.delete_stripe_requested.connect(self._on_delete_stripe_requested)
        self.active_signals_table.signals_dropped.connect(self._on_add_signals)
        self.active_signals_table.remove_requested.connect(controller.remove_signals)
        self.active_signals_table.remove_all_requested.connect(controller.remove_all)
        self.active_signals_table.selection_changed.connect(
            controller.set_selected_signal
        )
        self.active_signals_table.multi_selection_active.connect(
            controller.on_multi_selection
        )
        self.active_signals_table.multi_selection_changed.connect(
            controller.set_multi_selected
        )
        self.signal_info_box.display_mode_requested.connect(
            controller.on_display_mode_requested
        )
        self.signal_info_box.marker_shape_requested.connect(
            controller.on_marker_shape_requested
        )
        self.signal_info_box.line_width_requested.connect(
            controller.on_line_width_requested
        )
        self.signal_info_box.line_style_requested.connect(
            controller.on_line_style_requested
        )
        self.signal_info_box.enum_table_requested.connect(
            controller.on_enum_table_requested
        )
        self.signal_info_box.enum_cursor_requested.connect(
            controller.on_enum_cursor_requested
        )
        self.signal_info_box.enum_yaxis_requested.connect(
            controller.on_enum_yaxis_requested
        )
        self.active_signals_table.color_change_requested.connect(
            controller.recolor_signals
        )
        self.active_signals_table.step_mode_set_requested.connect(
            controller.set_step_modes
        )
        self.active_signals_table.order_changed.connect(controller.reorder_signals)
        self.plot_area.y_grid_toggled.connect(controller.on_y_grid_toggled)
        self.plot_area.signal_clicked.connect(self.active_signals_table.select_signal)
        self.active_signals_table.configure_display_names_requested.connect(
            self._on_configure_display_names
        )
        self.active_signals_table.shorten_names_toggled.connect(
            self._on_shorten_names_toggled
        )
        self.active_signals_table.merge_y_axis_requested.connect(
            self._on_merge_y_axis_requested
        )
        self.active_signals_table.sync_y_axis_requested.connect(
            self._on_sync_y_axis_requested
        )
        self.active_signals_table.ungroup_y_axis_requested.connect(
            controller.on_ungroup_y_axis_requested
        )
        self.active_signals_table.move_to_stripe_requested.connect(
            controller.move_signals_to_stripe
        )
        self.active_signals_table.move_to_new_stripe_requested.connect(
            controller.move_signals_to_new_stripe
        )
        self.active_signals_table.set_stripe_providers(
            controller.get_stripes, controller.get_stripe_for_signal
        )

    def show_status(self, message: str, timeout_ms: int = 3000) -> None:
        """Show a transient status bar message."""
        self.statusBar().showMessage(message, timeout_ms)

    def set_recent_files_provider(
        self, provider: Callable[[], list[Path]]
    ) -> None:
        """Supply a callable that returns the current recent files list."""
        self._recent_provider = provider

    def set_license(
        self, info: LicenseInfo | None, manager: LicenseManager | None = None
    ) -> None:
        """Apply license state to title bar and Help menu."""
        self._license_info = info
        self._license_manager = manager
        if info is not None:
            self.setWindowTitle("MDF-Viewer")
            self._license_action.setText("View/Change License Key…")
        else:
            self.setWindowTitle("MDF-Viewer — unregistered")
            self._license_action.setText("Enter License Key…")

    def set_settings(self, settings: Settings) -> None:
        """Store the Settings instance (needed by Preferences dialog)."""
        self._settings = settings

    def trigger_startup_update_check(self) -> None:
        """Run an update check in the background; silently show a dialog if newer."""
        self._update_thread = _UpdateCheckThread(__version__, self)
        self._update_thread.update_available.connect(self._on_update_available)
        self._update_thread.start()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_actions(self) -> None:
        suffix = _icon_suffix()

        self._load_action = QAction(_load_icon(f"folder{suffix}"), "Load MDF…", self)
        self._load_action.setShortcut(QKeySequence.StandardKey.Open)
        self._load_action.setToolTip("Load MDF File (Ctrl+O)")
        self._load_action.triggered.connect(self._on_load_file)

        self._zoom_fit_action = QAction(
            _load_icon(f"zoom_to_fit{suffix}"), "Zoom to Fit", self
        )
        self._zoom_fit_action.setShortcuts(
            [QKeySequence("Ctrl+0"), QKeySequence("f")]
        )
        self._zoom_fit_action.setToolTip("Zoom to fit all active signals (Ctrl+0 / F)")
        self._zoom_fit_action.triggered.connect(self._on_zoom_to_fit)

        self._zoom_y_action = QAction(
            _load_icon(f"zoom_y_to_fit{suffix}"), "Zoom Y to View", self
        )
        self._zoom_y_action.setShortcut(QKeySequence("y"))
        self._zoom_y_action.setToolTip("Zoom Y axes to current X span (Y)")
        self._zoom_y_action.triggered.connect(self._on_zoom_y_to_view)

        self._swimlanes_action = QAction(
            _load_icon(f"swimlanes{suffix}"), "Swimlanes", self
        )
        self._swimlanes_action.setShortcut(QKeySequence("b"))
        self._swimlanes_action.setToolTip("Arrange signals in swimlanes (B)")
        self._swimlanes_action.triggered.connect(self._on_swimlanes)

        self._zoom_all_stripes_action = QAction("All Stripes", self)
        self._zoom_all_stripes_action.setCheckable(True)
        self._zoom_all_stripes_action.setChecked(True)
        self._zoom_all_stripes_action.setToolTip(
            "Whether Zoom to Fit / Zoom Y to View apply to every stripe "
            "or only the active one"
        )
        self._zoom_all_stripes_action.toggled.connect(self._on_zoom_scope_toggled)

        self._zoom_cursors_action = QAction(
            _load_icon(f"zoom_to_cursors{suffix}"), "Zoom to Cursors", self
        )
        self._zoom_cursors_action.setShortcut(QKeySequence("c"))
        self._zoom_cursors_action.setToolTip("Zoom X to cursor range (C)")
        self._zoom_cursors_action.setEnabled(False)
        self._zoom_cursors_action.triggered.connect(self._on_zoom_to_cursors)

        self._cursor_action = QAction(_load_icon(f"cursors{suffix}"), "Cursors", self)
        self._cursor_action.setToolTip("Toggle cursors (off → 1 → 2 → off)")
        self._cursor_action.triggered.connect(self._on_cursor_toggle)

        self._cursor1_shortcut = QShortcut(QKeySequence("."), self)
        self._cursor1_shortcut.activated.connect(self._on_cursor1)
        self._cursor2_shortcut = QShortcut(QKeySequence(","), self)
        self._cursor2_shortcut.activated.connect(self._on_cursor2)

        self._cursor_left_shortcut = QShortcut(QKeySequence("Left"), self)
        self._cursor_left_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._cursor_left_shortcut.activated.connect(self._on_cursor_left)
        self._cursor_right_shortcut = QShortcut(QKeySequence("Right"), self)
        self._cursor_right_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._cursor_right_shortcut.activated.connect(self._on_cursor_right)

        self._undo_action = QAction("Undo", self)
        self._undo_action.setShortcut(QKeySequence("Ctrl+Z"))
        self._undo_action.triggered.connect(self._on_undo)

        self._redo_action = QAction("Redo", self)
        self._redo_action.setShortcut(QKeySequence("Ctrl+Shift+Z"))
        self._redo_action.triggered.connect(self._on_redo)

        self._save_config_action = QAction("Save Config", self)
        self._save_config_action.setShortcut(QKeySequence("Ctrl+S"))
        self._save_config_action.triggered.connect(self._on_save_config)

        self._save_config_as_action = QAction("Save Config As…", self)
        self._save_config_as_action.triggered.connect(self._on_save_config_as)

        self._preferences_action = QAction("Preferences…", self)
        self._preferences_action.triggered.connect(self._on_preferences)

        self._check_update_action = QAction("Check for Update…", self)
        self._check_update_action.triggered.connect(self._on_check_for_update)

        self._about_action = QAction("About MDF-Viewer", self)
        self._about_action.triggered.connect(self._on_about)

        self._license_action = QAction("Enter License Key…", self)
        self._license_action.triggered.connect(self._on_license)

    def _build_menu(self) -> None:
        self._file_menu = self.menuBar().addMenu("&File")
        self._file_menu.addAction(self._load_action)
        self._file_menu.addAction(self._save_config_action)
        self._file_menu.addAction(self._save_config_as_action)
        self._file_menu.addSeparator()
        self._exit_action = QAction("Exit", self)
        self._exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        self._exit_action.triggered.connect(self.close)
        self._file_menu.addAction(self._preferences_action)
        self._file_menu.addSeparator()
        self._file_menu.addAction(self._exit_action)
        self._file_menu.aboutToShow.connect(self._rebuild_recent_files)

        self._edit_menu = self.menuBar().addMenu("&Edit")
        self._edit_menu.addAction(self._undo_action)
        self._edit_menu.addAction(self._redo_action)

        self._help_menu = self.menuBar().addMenu("&Help")
        self._help_menu.addAction(self._check_update_action)
        self._help_menu.addSeparator()
        self._help_menu.addAction(self._license_action)
        self._help_menu.addSeparator()
        self._help_menu.addAction(self._about_action)

    def _build_toolbar(self) -> None:
        toolbar = self.addToolBar("Main")
        toolbar.setMovable(False)
        toolbar.addAction(self._load_action)
        toolbar.addSeparator()
        toolbar.addAction(self._zoom_fit_action)
        toolbar.addAction(self._zoom_y_action)
        toolbar.addAction(self._zoom_all_stripes_action)
        toolbar.addAction(self._swimlanes_action)
        toolbar.addAction(self._zoom_cursors_action)
        toolbar.addAction(self._cursor_action)

    def _build_layout(self) -> None:
        self.signal_browser = SignalBrowser()
        self.plot_area = PlotStripesArea()
        self.active_signals_table = ActiveSignalsTable()
        self.measurement_info_box = MeasurementInfoBox()
        self.signal_info_box = SignalInfoBox()

        # ── Left panel content (Signal Browser / Measurement Info) ───────
        self._left_splitter = make_splitter(Qt.Orientation.Vertical)
        left_splitter = self._left_splitter
        left_splitter.addWidget(self.signal_browser)
        left_splitter.addWidget(self.measurement_info_box)
        left_splitter.setStretchFactor(0, 3)
        left_splitter.setStretchFactor(1, 1)

        # ── Central container ─────────────────────────────────────────────
        # In pinned mode the outer splitter fills it. Unpinned DockablePanels
        # re-parent themselves here as floating overlays.
        self._central = QWidget()
        self.setCentralWidget(self._central)
        self._central.installEventFilter(self)

        # ── Content splitter (plot area | Active Signals Table | info drawer)
        self._info_dock = DockablePanel(
            content=self.signal_info_box,
            edge=Qt.Edge.RightEdge,
            overlay_parent=self._central,
            dock_callback=self._dock_info_panel,
            default_width=_INFO_DRAWER_W,
        )
        self._content_splitter = make_splitter(Qt.Orientation.Horizontal)
        self._content_splitter.addWidget(self.plot_area)
        self._content_splitter.addWidget(self.active_signals_table)
        self._content_splitter.addWidget(self._info_dock)
        self._content_splitter.setStretchFactor(0, 1)
        self._content_splitter.setStretchFactor(1, 0)
        self._content_splitter.setStretchFactor(2, 0)
        self._content_splitter.setSizes([500, _PANEL_W, _INFO_DRAWER_W])

        # ── Outer splitter (pinned mode: left panel + content) ───────────
        self._left_dock = DockablePanel(
            content=self._left_splitter,
            edge=Qt.Edge.LeftEdge,
            overlay_parent=self._central,
            dock_callback=self._dock_left_panel,
            default_width=_PANEL_W,
        )
        self._outer_splitter = make_splitter(Qt.Orientation.Horizontal)
        self._outer_splitter.addWidget(self._left_dock)
        self._outer_splitter.addWidget(self._content_splitter)
        self._outer_splitter.setStretchFactor(0, 0)
        self._outer_splitter.setStretchFactor(1, 1)
        self._outer_splitter.setSizes([_PANEL_W, 760])
        self._outer_splitter.setParent(self._central)

        self._content_splitter.show()
        self._left_dock.show()
        self._info_dock.show()

    def _dock_left_panel(self, panel: DockablePanel) -> None:
        """Re-insert the left DockablePanel into _outer_splitter on re-pin."""
        self._outer_splitter.insertWidget(0, panel)
        w = self._central.width()
        self._outer_splitter.setSizes([panel.width_px, max(0, w - panel.width_px)])

    def _dock_info_panel(self, panel: DockablePanel) -> None:
        """Re-append the info DockablePanel into _content_splitter on re-pin."""
        sizes_before = self._content_splitter.sizes()  # [plot_w, ast_w]
        plot_w = sizes_before[0] if sizes_before else self._content_splitter.width()
        ast_w = sizes_before[1] if len(sizes_before) > 1 else 0
        self._content_splitter.addWidget(panel)
        self._content_splitter.setSizes(
            [max(0, plot_w - panel.width_px), ast_w, panel.width_px]
        )

    # ------------------------------------------------------------------
    # Geometry management
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event) -> bool:
        if obj is self._central and event.type() == QEvent.Type.Resize:
            self._update_child_geometries()
        return super().eventFilter(obj, event)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if hasattr(self, '_central'):
            self._update_child_geometries()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if hasattr(self, '_central'):
            self._update_child_geometries()

    def _update_child_geometries(self) -> None:
        w = self._central.width()
        h = self._central.height()
        if w == 0 or h == 0:
            return
        self._outer_splitter.setGeometry(0, 0, w, h)
        self._left_dock.update_geometry(w, h)
        self._info_dock.update_geometry(w, h)

    # ------------------------------------------------------------------
    # Layout persistence (.mvc window/splitter state)
    # ------------------------------------------------------------------

    def _capture_window_geometry(self) -> dict:
        geo = self.normalGeometry()
        return {
            "x": geo.x(),
            "y": geo.y(),
            "width": geo.width(),
            "height": geo.height(),
            "maximized": self.isMaximized(),
        }

    def _capture_splitter_sizes(self) -> dict:
        return {
            "left": self._left_splitter.sizes(),
            "content": self._content_splitter.sizes(),
            "outer": self._outer_splitter.sizes(),
            "left_panel": {
                "pinned": self._left_dock.pinned,
                "width": self._left_dock.width_px,
            },
            "info_drawer": {
                "pinned": self._info_dock.pinned,
                "width": self._info_dock.width_px,
                "inner": self.signal_info_box.splitter_sizes(),
            },
        }

    def _apply_window_geometry(self, geometry: dict | None) -> None:
        if not geometry:
            return
        # Normalize first (#107): resizing/moving an already-maximized window
        # forces Windows to drop the maximized state at the OS level, after
        # which showMaximized() below becomes a no-op against Qt's stale
        # cached window state — always start the restore from a clean,
        # non-maximized state regardless of the window's current state.
        if self.isMaximized():
            self.showNormal()
        w, h = geometry.get("width"), geometry.get("height")
        if isinstance(w, int) and isinstance(h, int) and w > 0 and h > 0:
            self.resize(w, h)
            x, y = geometry.get("x"), geometry.get("y")
            if isinstance(x, int) and isinstance(y, int):
                self.move(x, y)
        if geometry.get("maximized"):
            self.showMaximized()

    def _apply_splitter_sizes(self, sizes: dict | None) -> None:
        if not sizes:
            return
        for attr, key in (
            ("_left_splitter", "left"),
            ("_content_splitter", "content"),
            ("_outer_splitter", "outer"),
        ):
            values = sizes.get(key)
            if isinstance(values, list) and all(isinstance(v, int) for v in values):
                getattr(self, attr).setSizes(values)

        for dock, key in (
            (self._left_dock, "left_panel"),
            (self._info_dock, "info_drawer"),
        ):
            entry = sizes.get(key)
            if not isinstance(entry, dict):
                continue
            # Toggle first: unpinning captures the dock's *current* on-screen
            # width into width_px, which the width override below must win
            # over — reversing this order would let toggle_pin() clobber an
            # explicitly saved width with whatever the widget happened to be
            # rendered at.
            if entry.get("pinned") is False and dock.pinned:
                dock.toggle_pin()
            width = entry.get("width")
            if isinstance(width, int) and width > 0:
                dock.set_width(width)

        info_drawer = sizes.get("info_drawer")
        if isinstance(info_drawer, dict):
            inner = info_drawer.get("inner")
            if isinstance(inner, list) and all(isinstance(v, int) for v in inner):
                self.signal_info_box.set_splitter_sizes(inner)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_add_signals(self, locations: list) -> None:
        if self._controller is None:
            return
        skipped = 0
        for gi, ci in locations:
            try:
                if not self._controller.add_signal(gi, ci):
                    skipped += 1
            except MdfLoadError as exc:
                QMessageBox.critical(self, "Error Loading Signal", str(exc))
        if skipped:
            noun = "signal" if skipped == 1 else "signals"
            self.show_status(f"{skipped} {noun} already active, skipped.")

    def _on_add_signals_to_stripe(self, locations: list, stripe) -> None:
        if self._controller is None:
            return
        skipped = 0
        for gi, ci in locations:
            try:
                if not self._controller.add_signal(gi, ci, stripe=stripe):
                    skipped += 1
            except MdfLoadError as exc:
                QMessageBox.critical(self, "Error Loading Signal", str(exc))
        if skipped:
            noun = "signal" if skipped == 1 else "signals"
            self.show_status(f"{skipped} {noun} already active, skipped.")

    def _on_delete_stripe_requested(self, stripe) -> None:
        if self._controller is None:
            return
        if not self._controller.get_signals_in_stripe(stripe):
            if not self._controller.delete_stripe(stripe):
                self.show_status("Cannot delete the last remaining stripe.")
            return
        reply = QMessageBox.question(
            self,
            "Delete Stripe",
            "This stripe still has signals in it. Delete anyway?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.Cancel,
        )
        if reply == QMessageBox.StandardButton.Yes:
            self._controller.delete_stripe(stripe, force=True)

    def _on_file_dropped(self, path) -> None:
        if self._controller is None:
            return
        if Path(path).suffix.lower() == ".mvc":
            self._load_config(Path(path))
            return
        if self._controller.is_file_loaded:
            reply = QMessageBox.question(
                self,
                "Replace File",
                f"Replace the currently loaded file with\n{Path(path).name}?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self._load_file(path)

    def _on_load_file(self) -> None:
        if self._controller is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Open File", "", _ALL_FILE_FILTER
        )
        if not path:
            return
        if Path(path).suffix.lower() == ".mvc":
            self._load_config(Path(path))
        else:
            self._load_file(path)

    def _load_file(self, path: str | Path) -> None:
        """Load *path* via the controller, showing busy feedback meanwhile.

        Loading a large MDF file can take noticeable time; without this the
        application appears to freeze. Show a wait cursor and a persistent
        status message for the duration of the call.
        """
        if self._controller is None:
            return

        snapshots = self._collect_snapshots_if_keeping()

        self.show_status(f"Loading {Path(path).name}…", timeout_ms=0)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        load_ok = True
        try:
            self._controller.load_file(path)
        except MdfLoadError as exc:
            QMessageBox.critical(self, "Load Error", str(exc))
            load_ok = False
        finally:
            QApplication.restoreOverrideCursor()
            self.statusBar().clearMessage()

        if load_ok and snapshots:
            self._restore_snapshots(snapshots)

    def _collect_snapshots_if_keeping(self) -> list:
        """Return snapshots of active signals if the user wants to keep them, else []."""
        if self._controller is None or self._settings is None:
            return []
        if not self._controller.active_signals:
            return []
        setting = self._settings.keep_signals_on_load
        if setting == "never":
            return []
        if setting == "always":
            return self._controller.snapshot_active_signals()
        # "ask"
        reply = QMessageBox.question(
            self,
            "Keep Active Signals?",
            "Keep the currently active signals in the new measurement?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            return self._controller.snapshot_active_signals()
        return []

    def _restore_snapshots(self, snapshots: list) -> None:
        """Resolve each snapshot against the new file and re-add matched signals."""
        from mdf_viewer.view.signal_group_picker_dialog import SignalGroupPickerDialog
        from mdf_viewer.view.signals_not_found_dialog import SignalsNotFoundDialog

        resolved: list[tuple] = []
        not_found: list[str] = []

        for snap in snapshots:
            candidates = self._controller.find_signal_by_name(snap.name)
            if not candidates:
                not_found.append(snap.name)
            elif len(candidates) == 1:
                meta = candidates[0]
                resolved.append((snap, meta.group_index, meta.channel_index))
            else:
                dlg = SignalGroupPickerDialog(snap.name, candidates, self)
                if dlg.exec():
                    meta = dlg.selected()
                    resolved.append((snap, meta.group_index, meta.channel_index))
                else:
                    not_found.append(snap.name)

        if resolved:
            self._controller.restore_signals(resolved)

        if not_found:
            dlg = SignalsNotFoundDialog(not_found, self)
            dlg.exec()

    def _on_zoom_to_fit(self) -> None:
        if self._controller is not None:
            self._controller.zoom_to_fit()

    def _on_zoom_y_to_view(self) -> None:
        if self._controller is None:
            return
        if not self._controller.zoom_y_to_view():
            self.show_status("No active signals to zoom.")

    def _on_swimlanes(self) -> None:
        if self._controller is None:
            return
        if not self._controller.swimlanes():
            self.show_status("No active signals to arrange.")

    def _on_zoom_to_cursors(self) -> None:
        if self._controller is not None:
            self._controller.zoom_to_cursors()

    def _on_undo(self) -> None:
        if self._controller is not None:
            self._controller.undo()

    def _on_redo(self) -> None:
        if self._controller is not None:
            self._controller.redo()

    def _on_cursor_mode_changed(self, mode) -> None:
        from mdf_viewer.controller.cursor_controller import CursorMode
        self._zoom_cursors_action.setEnabled(mode == CursorMode.TWO)

    def _on_cursor_toggle(self) -> None:
        if self._controller is not None:
            self._controller.toggle_cursor()

    def _on_cursor1(self) -> None:
        if self._controller is not None:
            self._controller.press_cursor1()

    def _on_cursor2(self) -> None:
        if self._controller is not None:
            self._controller.press_cursor2()

    def _on_cursor_left(self) -> None:
        if self._controller is not None and not self._focus_in_text_widget():
            self._controller.press_left()

    def _on_cursor_right(self) -> None:
        if self._controller is not None and not self._focus_in_text_widget():
            self._controller.press_right()

    @staticmethod
    def _focus_in_text_widget() -> bool:
        from PyQt6.QtWidgets import QAbstractSpinBox, QLineEdit
        w = QApplication.focusWidget()
        return isinstance(w, (QLineEdit, QAbstractSpinBox))

    def _on_preferences(self) -> None:
        if self._settings is None:
            return
        from mdf_viewer.view.preferences_dialog import PreferencesDialog
        preview = None
        if self._controller is not None and self._controller.selected_signal is not None:
            preview = self._controller.selected_signal.metadata.name
        dlg = PreferencesDialog(self._settings, self, preview_name=preview)
        if dlg.exec() and self._controller is not None:
            self._controller.refresh_cursors()
            self._controller.refresh_z_order()
            self._controller.refresh_display_names()
            self.active_signals_table.set_shorten_names_enabled(
                self._settings.display_name_rule_enabled
            )

    def _on_configure_display_names(self, preview_name: str) -> None:
        if self._settings is None or self._controller is None:
            return
        from mdf_viewer.view.signal_display_name_dialog import SignalDisplayNameDialog
        dlg = SignalDisplayNameDialog(self._settings, preview_name, self)
        if dlg.exec():
            self._controller.refresh_display_names()
            self.active_signals_table.set_shorten_names_enabled(
                self._settings.display_name_rule_enabled
            )

    def _on_shorten_names_toggled(self, enabled: bool) -> None:
        if self._settings is None or self._controller is None:
            return
        self._settings.display_name_rule_enabled = enabled
        self._controller.refresh_display_names()
        self.active_signals_table.set_shorten_names_enabled(enabled)

    def _on_zoom_scope_toggled(self, checked: bool) -> None:
        if self._settings is None:
            return
        self._settings.zoom_scope = "all_stripes" if checked else "active_stripe"

    def set_zoom_all_stripes(self, enabled: bool) -> None:
        """Set the toolbar toggle's initial state from a persisted setting."""
        self._zoom_all_stripes_action.setChecked(enabled)

    def _on_merge_y_axis_requested(self, signals: list) -> None:
        if self._controller is None:
            return
        units = {s.metadata.unit for s in signals}
        if len(units) > 1:
            self.show_status("Cannot merge axis: selected signals have different units.")
            return
        self._controller.on_merge_y_axis_requested(signals)

    def _on_sync_y_axis_requested(self, signals: list) -> None:
        if self._controller is None:
            return
        units = {s.metadata.unit for s in signals}
        if len(units) > 1:
            self.show_status("Cannot sync axes: selected signals have different units.")
            return
        self._controller.on_sync_y_axis_requested(signals)

    def _on_check_for_update(self) -> None:
        from mdf_viewer.update_checker import UpdateCheckError, fetch_latest_release, is_newer
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        try:
            release = fetch_latest_release()
        except UpdateCheckError as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(self, "Update Check Failed", str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
        if is_newer(release.tag, __version__):
            self._on_update_available(release.tag, release.url)
        else:
            QMessageBox.information(
                self,
                "Up to Date",
                f"MDF-Viewer {__version__} is the latest version.",
            )

    def _on_update_available(self, tag: str, url: str) -> None:
        msg = QMessageBox(self)
        msg.setWindowTitle("Update Available")
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText(f"Version <b>{tag}</b> is available.")
        msg.setInformativeText(f"You are running version {__version__}.")
        open_btn = msg.addButton("Open Release Page", QMessageBox.ButtonRole.ActionRole)
        msg.addButton(QMessageBox.StandardButton.Close)
        msg.exec()
        if msg.clickedButton() is open_btn:
            QDesktopServices.openUrl(QUrl(url))

    def _on_about(self) -> None:
        info = self._license_info
        if info is not None:
            expired_note = (
                f"<br><i>Update coverage expired {info.updates_until.isoformat()}</i>"
                if info.updates_expired
                else ""
            )
            license_line = (
                f"<p><b>Licensed to:</b> {info.licensee_name} "
                f"({info.tier_display}){expired_note}</p>"
            )
        else:
            license_line = "<p><i>Unregistered</i></p>"

        QMessageBox.about(
            self,
            "About MDF-Viewer",
            f"<h3>MDF-Viewer {__version__}</h3>"
            "<p>A free, open-source viewer for ASAM MDF "
            "(MDF3/MDF4) measurement data files.</p>"
            "<p>By Andreas Maus</p>"
            f'<p><a href="{_GITHUB_URL}">{_GITHUB_URL}</a></p>'
            f"{license_line}",
        )

    def _on_license(self) -> None:
        if self._license_manager is None:
            return
        dlg = LicenseDialog(self._license_manager, self._license_info, self)
        dlg.exec()  # dialog shows "restart required" on success; no state update needed here

    def closeEvent(self, event) -> None:
        if self._should_prompt_save_on_close():
            path = self._controller.current_config_path if self._controller else None
            if path is not None:
                msg = f"Save updated config '{path.name}'?"
            else:
                msg = "Save current view as a config file?"
            reply = QMessageBox.question(
                self,
                "Save Config?",
                msg,
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
            )
            if reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return
            if reply == QMessageBox.StandardButton.Save:
                if path is not None:
                    self._save_config_to(path)
                else:
                    self._on_save_config_as()
        event.accept()

    def _should_prompt_save_on_close(self) -> bool:
        return (
            self._settings is not None
            and self._settings.prompt_save_config_on_close
            and self._controller is not None
            and bool(self._controller.active_signals)
        )

    def _on_save_config(self) -> None:
        if self._controller is None:
            return
        path = self._controller.current_config_path
        if path is None:
            self._on_save_config_as()
        else:
            self._save_config_to(path)

    def _on_save_config_as(self) -> None:
        if self._controller is None:
            return
        path_str, _ = QFileDialog.getSaveFileName(
            self, "Save Config As", "", "MDF Viewer Config (*.mvc);;All Files (*)"
        )
        if not path_str:
            return
        self._save_config_to(Path(path_str))

    def _save_config_to(self, path: Path) -> None:
        import dataclasses
        from mdf_viewer.config_manager import ConfigManager
        if self._controller is None or self._settings is None:
            return
        try:
            config = self._controller.capture_config(path)
            config = dataclasses.replace(
                config,
                window_geometry=self._capture_window_geometry(),
                splitter_sizes=self._capture_splitter_sizes(),
            )
            ConfigManager.save(config, path, self._settings.config_path_mode)
        except Exception as exc:
            QMessageBox.critical(self, "Save Config Error", str(exc))
            return
        self._controller.current_config_path = path
        self._settings.add_recent(path)
        self.show_status(f"Config saved to {path.name}")

    def open_config(self, path: Path) -> None:
        """Public entry point for opening a .mvc config file (e.g. from app.py)."""
        self._load_config(path)

    def _load_config(self, path: Path) -> None:
        from mdf_viewer.config_manager import ConfigManager
        from mdf_viewer.errors import ConfigLoadError
        if self._controller is None or self._settings is None:
            return

        try:
            config = ConfigManager.load(path)
        except ConfigLoadError as exc:
            QMessageBox.critical(self, "Config Load Error", str(exc))
            return

        self._apply_window_geometry(config.window_geometry)
        self._apply_splitter_sizes(config.splitter_sizes)

        mdf_path = ConfigManager.resolve_measurement_path(config.measurement_path, path)
        if mdf_path is None:
            mdf_path_str, _ = QFileDialog.getOpenFileName(
                self,
                f"Locate Measurement File for '{path.name}'",
                "",
                _MDF_FILE_FILTER,
            )
            if not mdf_path_str:
                return
            mdf_path = Path(mdf_path_str)

        self.show_status(f"Loading {mdf_path.name}…", timeout_ms=0)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        load_ok = True
        try:
            self._controller.load_file(mdf_path)
        except MdfLoadError as exc:
            QMessageBox.critical(self, "Load Error", str(exc))
            load_ok = False
        finally:
            QApplication.restoreOverrideCursor()
            self.statusBar().clearMessage()

        if not load_ok:
            return

        resolved, not_found = self._resolve_config_signals(config)

        if not_found:
            from mdf_viewer.view.signals_not_found_dialog import SignalsNotFoundDialog
            SignalsNotFoundDialog(not_found, self).exec()

        if resolved:
            self._controller.restore_config(config, resolved)

        self._controller.current_config_path = path
        self._settings.add_recent(path)

    def _resolve_config_signals(self, config) -> tuple[list, list[str]]:
        """Match SignalConfig entries in *config* to channels in the loaded file.

        Returns (resolved, not_found) where resolved is a list of
        (ActiveSignalSnapshot, group_index, channel_index) tuples.
        """
        from mdf_viewer.controller.app_controller import ActiveSignalSnapshot
        from mdf_viewer.view.signal_group_picker_dialog import SignalGroupPickerDialog

        resolved: list = []
        not_found: list[str] = []

        for sig in config.signals:
            candidates = self._controller.find_signal_by_name(sig.name)
            if not candidates:
                not_found.append(sig.name)
                continue

            # Narrow by group_name when stored
            if sig.group_name:
                group_match = [c for c in candidates if c.group_name == sig.group_name]
                if group_match:
                    candidates = group_match

            snap = ActiveSignalSnapshot(
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
            )

            if len(candidates) == 1:
                meta = candidates[0]
                resolved.append((snap, meta.group_index, meta.channel_index))
            else:
                dlg = SignalGroupPickerDialog(sig.name, candidates, self)
                if dlg.exec():
                    meta = dlg.selected()
                    resolved.append((snap, meta.group_index, meta.channel_index))
                else:
                    not_found.append(sig.name)

        return resolved, not_found

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

        for path in paths:
            action = QAction(Path(path).name, self)
            action.setToolTip(str(path))
            action.triggered.connect(lambda checked, p=path: self._on_open_recent(p))
            self._file_menu.insertAction(self._preferences_action, action)
            self._recent_actions.append(action)
        self._recent_sep = self._file_menu.insertSeparator(self._preferences_action)

    def _on_open_recent(self, path: Path) -> None:
        if Path(path).suffix.lower() == ".mvc":
            self._load_config(Path(path))
        else:
            self._load_file(path)


class _UpdateCheckThread(QThread):
    update_available = pyqtSignal(str, str)  # tag, url

    def __init__(self, current_version: str, parent=None) -> None:
        super().__init__(parent)
        self._current = current_version

    def run(self) -> None:
        from mdf_viewer.update_checker import UpdateCheckError, fetch_latest_release, is_newer
        try:
            release = fetch_latest_release()
            if is_newer(release.tag, self._current):
                self.update_available.emit(release.tag, release.url)
        except UpdateCheckError:
            pass
