"""MainWindow — top-level window: menu bar, toolbar, and the splitter layout.

Layout (per CLAUDE.md):

    +-----------------------------------------------------------------+
    | Menu bar (File: Open / Exit)                                    |
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
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTabWidget,
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
        self._tab_factory: Callable[[PlotStripesArea, ActiveSignalsTable], None] | None = None
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
        self.signal_browser.measurement_selected.connect(self._on_measurement_selected)
        self._wire_tab_view(self.plot_area, self.active_signals_table)
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

    def _wire_tab_view(
        self, plot_area: PlotStripesArea, active_signals_table: ActiveSignalsTable
    ) -> None:
        """Connect one tab's plot area + Active Signals Table to the controller.

        Called once per tab: from set_controller() for the first tab, and
        from _on_new_tab() for every tab created afterward (#99). The
        Signal Browser and Signal Info/Properties drawer are shared, single
        instances wired once in set_controller() instead — they aren't
        duplicated per tab.
        """
        controller = self._controller
        plot_area.signals_dropped_on_stripe.connect(self._on_add_signals_to_stripe)
        plot_area.active_signals_dropped_on_stripe.connect(
            self._on_active_signals_dropped_to_stripe
        )
        plot_area.file_dropped.connect(self._on_file_dropped)
        plot_area.delete_stripe_requested.connect(self._on_delete_stripe_requested)
        active_signals_table.signals_dropped_on_stripe.connect(self._on_add_signals_to_stripe)
        active_signals_table.remove_requested.connect(controller.remove_signals)
        active_signals_table.remove_all_requested.connect(controller.remove_all)
        active_signals_table.selection_changed.connect(
            controller.set_selected_signal
        )
        active_signals_table.multi_selection_active.connect(
            controller.on_multi_selection
        )
        active_signals_table.multi_selection_changed.connect(
            controller.set_multi_selected
        )
        active_signals_table.color_change_requested.connect(
            controller.recolor_signals
        )
        active_signals_table.step_mode_set_requested.connect(
            controller.set_step_modes
        )
        active_signals_table.order_changed.connect(controller.reorder_signals)
        plot_area.y_grid_toggled.connect(controller.on_y_grid_toggled)
        plot_area.signal_clicked.connect(active_signals_table.select_signal)
        active_signals_table.configure_display_names_requested.connect(
            self._on_configure_display_names
        )
        active_signals_table.shorten_names_toggled.connect(
            self._on_shorten_names_toggled
        )
        active_signals_table.merge_y_axis_requested.connect(
            self._on_merge_y_axis_requested
        )
        active_signals_table.sync_y_axis_requested.connect(
            self._on_sync_y_axis_requested
        )
        active_signals_table.ungroup_y_axis_requested.connect(
            controller.on_ungroup_y_axis_requested
        )
        active_signals_table.move_to_stripe_requested.connect(
            controller.move_signals_to_stripe
        )
        active_signals_table.move_to_new_stripe_requested.connect(
            controller.move_signals_to_new_stripe
        )
        active_signals_table.set_stripe_providers(
            controller.get_stripes, controller.get_stripe_for_signal
        )

        # Per-stripe Active Signals Table segments (#100): react to stripe
        # lifecycle, plus a bootstrap for the stripe(s) PlotStripesArea.
        # __init__ already created — and already fired stripe_created for —
        # before this connection existed.
        plot_area.stripe_created.connect(active_signals_table.add_stripe_segment)
        plot_area.stripe_deleted.connect(active_signals_table.remove_stripe_segment)
        for stripe in plot_area.get_stripes():
            active_signals_table.add_stripe_segment(stripe)
        # The bootstrapped segment(s) above start with whatever arbitrary
        # size Qt's QSplitter.addWidget() gave them — push the stripe(s)'
        # real sizes now so they match immediately (REQ-PLOT-274), the same
        # way stripe_sizes_changed keeps later-created segments matching.
        active_signals_table.set_segment_sizes(plot_area.get_stripe_sizes())

        # Bidirectional stripe/segment divider sync (REQ-PLOT-274): dragging
        # either splitter's handle resizes the other in lockstep.
        plot_area.stripe_sizes_changed.connect(active_signals_table.set_segment_sizes)
        active_signals_table.segment_sizes_changed.connect(plot_area.set_stripe_sizes)

        # Clicking inside a segment activates its stripe (REQ-PLOT-278),
        # mirroring PlotStripe's own "click anywhere inside it" rule.
        active_signals_table.segment_activated.connect(plot_area.set_active_stripe)

    def set_tab_factory(
        self, factory: Callable[[PlotStripesArea, ActiveSignalsTable], None]
    ) -> None:
        """Supply the callback that builds a new tab's controller-side stack (#99).

        app.py injects this — it calls controller.create_tab() and builds
        the tab's CursorController/ZoomController, mirroring what already
        happens once at startup for the first tab.
        """
        self._tab_factory = factory

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

        self._load_action = QAction(_load_icon(f"folder{suffix}"), "Open…", self)
        self._load_action.setShortcut(QKeySequence.StandardKey.Open)
        self._load_action.setToolTip("Open File (Ctrl+O)")
        self._load_action.triggered.connect(self._on_load_file)

        self._new_tab_action = QAction("New Tab", self)
        self._new_tab_action.triggered.connect(self._on_new_tab)

        self._new_stripe_action = QAction("New Stripe", self)
        self._new_stripe_action.triggered.connect(self._on_new_stripe)

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

        self._next_tab_shortcut = QShortcut(QKeySequence("Ctrl+Tab"), self)
        self._next_tab_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._next_tab_shortcut.activated.connect(lambda: self._cycle_tab(1))
        self._prev_tab_shortcut = QShortcut(QKeySequence("Ctrl+Shift+Tab"), self)
        self._prev_tab_shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._prev_tab_shortcut.activated.connect(lambda: self._cycle_tab(-1))

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
        self._file_menu.addAction(self._new_tab_action)
        self._file_menu.addAction(self._new_stripe_action)
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

        # ── Tabs (#99) — each tab page is one plot area + Active Signals
        # Table pair; the Info/Properties drawer stays outside, shared ──
        self._tab_counter = 1
        self._tab_widget = QTabWidget()
        self._tab_widget.setTabsClosable(True)
        self._tab_widget.setMovable(True)
        self._tab_widget.addTab(
            self._make_tab_page(self.plot_area, self.active_signals_table), "Tab 1"
        )
        # A real "+" tab pinned to the end (browser-style), not a corner
        # widget — a corner widget sits at the far edge of the tab bar with
        # a visible gap after the last tab; this sits immediately next to
        # it and moves as tabs are added/removed.
        self._new_tab_placeholder_widget = QWidget()
        placeholder_index = self._tab_widget.addTab(self._new_tab_placeholder_widget, "+")
        tab_bar = self._tab_widget.tabBar()
        tab_bar.setTabButton(placeholder_index, tab_bar.ButtonPosition.RightSide, None)
        tab_bar.setTabButton(placeholder_index, tab_bar.ButtonPosition.LeftSide, None)
        self._tab_widget.tabCloseRequested.connect(self._on_tab_close_requested)
        self._tab_widget.currentChanged.connect(self._on_tab_changed)
        self._tab_widget.tabBarClicked.connect(self._on_tab_bar_clicked)
        self._tab_widget.tabBarDoubleClicked.connect(self._on_tab_bar_double_clicked)
        tab_bar.tabMoved.connect(self._on_tab_bar_tab_moved)
        tab_bar.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        tab_bar.customContextMenuRequested.connect(self._on_tab_context_menu)

        self._empty_tabs_placeholder = self._build_empty_tabs_placeholder()
        self._content_stack = QStackedWidget()
        self._content_stack.addWidget(self._tab_widget)
        self._content_stack.addWidget(self._empty_tabs_placeholder)

        # ── Content splitter (tabs | info drawer) ────────────────────────
        self._info_dock = DockablePanel(
            content=self.signal_info_box,
            edge=Qt.Edge.RightEdge,
            overlay_parent=self._central,
            dock_callback=self._dock_info_panel,
            default_width=_INFO_DRAWER_W,
        )
        self._content_splitter = make_splitter(Qt.Orientation.Horizontal)
        self._content_splitter.addWidget(self._content_stack)
        self._content_splitter.addWidget(self._info_dock)
        self._content_splitter.setStretchFactor(0, 1)
        self._content_splitter.setStretchFactor(1, 0)
        self._content_splitter.setSizes([500 + _PANEL_W, _INFO_DRAWER_W])

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

    def _make_tab_page(
        self, plot_area: PlotStripesArea, active_signals_table: ActiveSignalsTable
    ) -> QSplitter:
        """Pair one tab's plot area and Active Signals Table side by side.

        Kept as a splitter (not a plain layout) so the divider between them
        stays user-draggable, matching today's single-workspace behavior.
        """
        page = make_splitter(Qt.Orientation.Horizontal)
        page.addWidget(plot_area)
        page.addWidget(active_signals_table)
        page.setStretchFactor(0, 1)
        page.setStretchFactor(1, 0)
        page.setSizes([500, _PANEL_W])
        page.plot_area = plot_area
        page.active_signals_table = active_signals_table
        return page

    def _build_empty_tabs_placeholder(self) -> QWidget:
        """Shown in place of the tab widget when the last tab has been closed."""
        placeholder = QWidget()
        layout = QVBoxLayout(placeholder)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label = QLabel("No tabs open")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        new_tab_button = QPushButton("New Tab")
        new_tab_button.clicked.connect(self._on_new_tab)
        layout.addWidget(label)
        layout.addWidget(new_tab_button)
        return placeholder

    def _placeholder_index(self) -> int:
        """Current position of the pinned "+" tab (usually last, but a drag
        reorder can transiently move it — _on_tab_bar_tab_moved corrects that)."""
        return self._tab_widget.indexOf(self._new_tab_placeholder_widget)

    def _is_placeholder(self, index: int) -> bool:
        return index == self._placeholder_index()

    def _real_tab_count(self) -> int:
        return self._tab_widget.count() - 1

    def _all_active_signals_tables(self) -> list[ActiveSignalsTable]:
        """Every real tab's Active Signals Table, for preferences that apply globally."""
        placeholder_index = self._placeholder_index()
        return [
            self._tab_widget.widget(i).active_signals_table
            for i in range(self._tab_widget.count())
            if i != placeholder_index
        ]

    def _on_new_tab(self) -> None:
        """Create a new tab: a fresh plot area + Active Signals Table pair (#99)."""
        plot_area = PlotStripesArea()
        active_signals_table = ActiveSignalsTable()
        if self._tab_factory is not None:
            self._tab_factory(plot_area, active_signals_table)
        self._tab_counter += 1
        page = self._make_tab_page(plot_area, active_signals_table)
        index = self._placeholder_index()  # insert right before the "+" tab
        self._tab_widget.insertTab(index, page, f"Tab {self._tab_counter}")
        self._wire_tab_view(plot_area, active_signals_table)
        self._tab_widget.setCurrentIndex(index)
        if self._content_stack.currentWidget() is not self._tab_widget:
            self._content_stack.setCurrentWidget(self._tab_widget)

    def _on_new_stripe(self) -> None:
        """Create a new empty stripe in the currently active tab (REQ-PLOT-196, #112)."""
        if self._controller is not None:
            self._controller.create_stripe()

    def _on_tab_changed(self, index: int) -> None:
        if self._controller is not None and index >= 0 and not self._is_placeholder(index):
            self._controller.switch_tab(index)

    def _on_tab_bar_clicked(self, index: int) -> None:
        """Clicking the "+" tab creates a new tab instead of selecting it.

        Uses tabBarClicked (a real mouse click) rather than currentChanged,
        which also fires when Qt's own post-removal reindexing happens to
        land on the "+" tab (e.g. closing the last real tab) — that must
        NOT auto-create a replacement tab (REQ-PLOT-254).
        """
        if index >= 0 and self._is_placeholder(index):
            self._on_new_tab()

    def _on_tab_bar_tab_moved(self, from_index: int, to_index: int) -> None:
        """Keep the "+" tab pinned last after a drag reorder, then resync the
        controller's tab order (REQ-PLOT-243) once the placeholder has settled.

        moveTab() below re-emits tabMoved, re-entering this handler — the
        resync only runs once the placeholder position is already correct,
        so it reads the final settled order rather than an intermediate one.
        """
        tab_bar = self._tab_widget.tabBar()
        last = tab_bar.count() - 1
        placeholder_index = self._placeholder_index()
        if placeholder_index != last:
            tab_bar.moveTab(placeholder_index, last)
            return
        if self._controller is not None:
            pages = [
                self._tab_widget.widget(i)
                for i in range(self._tab_widget.count())
                if i != placeholder_index
            ]
            self._controller.reorder_tabs([page.plot_area for page in pages])

    def _on_tab_close_requested(self, index: int) -> None:
        """Close the tab at *index* (REQ-PLOT-251/252/253).

        Warns before closing a tab that still has active signals, mirroring
        the stripe-deletion warning (_on_delete_stripe_requested,
        REQ-PLOT-194). Activates the tab immediately to the left afterward,
        or the next remaining tab if the closed one was first — QTabBar's
        default post-removal current index picks the opposite neighbor
        (SelectRightTab), so the new index is computed explicitly before
        removal rather than relied on.
        """
        if self._is_placeholder(index):
            return
        has_signals = (
            self._controller is not None and self._controller.tab_has_signals(index)
        )
        if has_signals:
            reply = QMessageBox.question(
                self,
                "Close Tab",
                "This tab still has signals in it. Close anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        new_index = max(0, index - 1)
        # removeTab() only detaches the page from the tab bar — it does not
        # delete the widget (Qt's own docs say so explicitly). Without an
        # explicit deleteLater() here, the closed tab's whole PlotStripesArea
        # (every stripe, curve, ViewBox, axis) and ActiveSignalsTable leak for
        # the rest of the app session, never destroyed (#120).
        page = self._tab_widget.widget(index)
        self._tab_widget.removeTab(index)
        page.deleteLater()
        if self._controller is not None:
            self._controller.remove_tab(index)
        if self._real_tab_count() == 0:
            self._content_stack.setCurrentWidget(self._empty_tabs_placeholder)
        else:
            self._tab_widget.setCurrentIndex(new_index)

    def _cycle_tab(self, delta: int) -> None:
        """Move to the next/previous real tab (Ctrl+Tab / Ctrl+Shift+Tab), wrapping around."""
        count = self._real_tab_count()
        if count == 0:
            return
        placeholder_index = self._placeholder_index()
        real_indices = [i for i in range(self._tab_widget.count()) if i != placeholder_index]
        current = self._tab_widget.currentIndex()
        pos = real_indices.index(current) if current in real_indices else 0
        self._tab_widget.setCurrentIndex(real_indices[(pos + delta) % count])

    def _on_tab_bar_double_clicked(self, index: int) -> None:
        if index >= 0 and not self._is_placeholder(index):
            self._rename_tab(index)

    def _rename_tab(self, index: int) -> None:
        from PyQt6.QtWidgets import QInputDialog
        current_name = self._tab_widget.tabText(index)
        name, ok = QInputDialog.getText(self, "Rename Tab", "Tab name:", text=current_name)
        if ok and name.strip():
            self._tab_widget.setTabText(index, name.strip())

    def _on_tab_context_menu(self, pos) -> None:
        from PyQt6.QtWidgets import QMenu
        tab_bar = self._tab_widget.tabBar()
        index = tab_bar.tabAt(pos)
        if index < 0 or self._is_placeholder(index):
            return
        menu = QMenu(self)
        rename_action = menu.addAction("Rename")
        close_action = menu.addAction("Close")
        action = menu.exec(tab_bar.mapToGlobal(pos))
        if action is rename_action:
            self._rename_tab(index)
        elif action is close_action:
            self._on_tab_close_requested(index)

    def _dock_left_panel(self, panel: DockablePanel) -> None:
        """Re-insert the left DockablePanel into _outer_splitter on re-pin."""
        self._outer_splitter.insertWidget(0, panel)
        w = self._central.width()
        self._outer_splitter.setSizes([panel.width_px, max(0, w - panel.width_px)])

    def _dock_info_panel(self, panel: DockablePanel) -> None:
        """Re-append the info DockablePanel into _content_splitter on re-pin."""
        sizes_before = self._content_splitter.sizes()  # [content_w]
        content_w = sizes_before[0] if sizes_before else self._content_splitter.width()
        self._content_splitter.addWidget(panel)
        self._content_splitter.setSizes(
            [max(0, content_w - panel.width_px), panel.width_px]
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

    def _on_measurement_selected(self, index: int) -> None:
        """The Signal Browser's measurement selector changed (#101, REQ-BROWSER-051)."""
        if self._controller is None:
            return
        self.signal_browser.populate(self._controller.channel_tree_for_measurement(index))

    def _on_add_signals(self, locations: list) -> None:
        if self._controller is None:
            return
        measurement = self._controller.measurement_at(self.signal_browser.current_measurement_index())
        skipped = 0
        for gi, ci in locations:
            try:
                if not self._controller.add_signal(gi, ci, measurement=measurement):
                    skipped += 1
            except MdfLoadError as exc:
                QMessageBox.critical(self, "Error Loading Signal", str(exc))
        if skipped:
            noun = "signal" if skipped == 1 else "signals"
            self.show_status(f"{skipped} {noun} already active, skipped.")

    def _on_add_signals_to_stripe(self, locations: list, stripe, measurement_index: int = 0) -> None:
        if self._controller is None:
            return
        measurement = self._controller.measurement_at(measurement_index)
        skipped = 0
        for gi, ci in locations:
            try:
                if not self._controller.add_signal(gi, ci, stripe=stripe, measurement=measurement):
                    skipped += 1
            except MdfLoadError as exc:
                QMessageBox.critical(self, "Error Loading Signal", str(exc))
        if skipped:
            noun = "signal" if skipped == 1 else "signals"
            self.show_status(f"{skipped} {noun} already active, skipped.")

    def _on_active_signals_dropped_to_stripe(self, ids: set, stripe) -> None:
        """An already-active signal was dragged from the Active Signals Table
        and dropped onto *stripe*'s plot area (#116). Resolves the dragged
        id(ActiveSignal) set back to actual ActiveSignal objects — PlotStripe
        only knows the ids, not the full active-signal list — then moves them
        the same way the AST's own cross-segment drag and "Move to Stripe"
        context menu action already do.
        """
        if self._controller is None:
            return
        signals = [a for a in self._controller.active_signals if id(a) in ids]
        if signals:
            self._controller.move_signals_to_stripe(signals, stripe)

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
        # Replace-vs-Add prompting (when applicable) happens inside
        # _load_files() itself, so drag-drop gets the same choice as
        # File > Open once >=1 measurement is already loaded (REQ-FILE-020).
        self._load_file(path)

    def _on_load_file(self) -> None:
        if self._controller is None:
            return
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Open File", "", _ALL_FILE_FILTER
        )
        if not paths:
            return
        if len(paths) == 1 and Path(paths[0]).suffix.lower() == ".mvc":
            self._load_config(Path(paths[0]))
        else:
            self._load_files(paths)

    def _ask_replace_or_add(self) -> str | None:
        """Prompt Replace vs. Add when >=1 measurement is already loaded (REQ-FILE-020).

        Returns "replace", "add", or None if the user canceled.
        """
        msg = QMessageBox(self)
        msg.setWindowTitle("Load Measurement")
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setText("A measurement is already loaded.")
        msg.setInformativeText(
            "Replace it with the newly selected file(s), or add them alongside it?"
        )
        replace_btn = msg.addButton("Replace", QMessageBox.ButtonRole.AcceptRole)
        add_btn = msg.addButton("Add", QMessageBox.ButtonRole.YesRole)
        msg.addButton(QMessageBox.StandardButton.Cancel)
        msg.exec()
        clicked = msg.clickedButton()
        if clicked is replace_btn:
            return "replace"
        if clicked is add_btn:
            return "add"
        return None

    def _load_file(self, path: str | Path) -> None:
        """Back-compat single-file entry point — see _load_files()."""
        self._load_files([path])

    def _load_files(self, paths: list[str | Path]) -> None:
        """Load *paths* via the controller, showing busy feedback meanwhile.

        Prompts Replace vs. Add whenever at least one measurement is
        already loaded (REQ-FILE-020); with none loaded, loads directly
        with no prompt (REQ-FILE-012). Builds one error dialog naming
        every file that failed to open, rather than surfacing only the
        first failure (REQ-FILE-023).
        """
        if self._controller is None:
            return

        mode = "replace"
        if self._controller.measurement_count > 0:
            mode = self._ask_replace_or_add()
            if mode is None:
                return

        snapshots = self._collect_snapshots_if_keeping() if mode == "replace" else {}

        names = ", ".join(Path(p).name for p in paths)
        self.show_status(f"Loading {names}…", timeout_ms=0)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        try:
            if mode == "replace":
                result = self._controller.replace_measurements(paths)
            else:
                result = self._controller.add_measurements(paths)
        finally:
            QApplication.restoreOverrideCursor()
            self.statusBar().clearMessage()

        if result.failed:
            lines = "\n".join(f"{Path(p).name}: {err}" for p, err in result.failed)
            QMessageBox.critical(self, "Load Error", lines)

        if mode == "replace" and result.succeeded and snapshots:
            self._restore_snapshots(snapshots)

    def _classify_signal_name(
        self, name: str, group_name: str = "", *, measurement_aware: bool = False,
    ) -> tuple[str, list]:
        """Classify *name* against the loaded file(s) for signal-restore purposes.

        Tries an exact match first, falling back to a near match
        (REQ-FILE-032/033) only when there's no exact match at all — a
        near match is never preferred over an exact one. Returns
        (status, candidates) where status is one of "exact_single",
        "exact_multiple", "near_single", "near_multiple", or "not_found".

        *measurement_aware* selects between two candidate shapes: False
        (default) returns plain SignalMetadata, searching only against
        `.mvc` restore's deliberately single-measurement scope (#106).
        True returns (LoadedMeasurement, SignalMetadata) tuples, searched
        across every loaded measurement — used by the multi-file Replace
        carry-over flow (#101) to disambiguate a name matching in more
        than one loaded measurement, which a bare SignalMetadata result
        can't express.
        """
        if measurement_aware:
            candidates = self._controller.find_signal_locations_by_name(name)
            is_near = False
            if not candidates:
                candidates = self._controller.find_similar_signal_locations_by_name(name)
                is_near = True
            if group_name and candidates:
                narrowed = [c for c in candidates if c[1].group_name == group_name]
                if narrowed:
                    candidates = narrowed
        else:
            candidates = self._controller.find_signal_by_name(name)
            is_near = False
            if not candidates:
                candidates = self._controller.find_similar_signal_by_name(name)
                is_near = True
            if group_name and candidates:
                narrowed = [c for c in candidates if c.group_name == group_name]
                if narrowed:
                    candidates = narrowed
        if not candidates:
            return "not_found", []
        prefix = "near" if is_near else "exact"
        suffix = "single" if len(candidates) == 1 else "multiple"
        return f"{prefix}_{suffix}", candidates

    def _collect_snapshots_if_keeping(self) -> dict[int, list]:
        """Return {tab_index: snapshots} for every tab with active signals,
        if the user wants to keep them, else {} (REQ-PLOT-260 — all tabs,
        not just the active one)."""
        if self._controller is None or self._settings is None:
            return {}
        setting = self._settings.keep_signals_on_load
        if setting == "never":
            return {}
        tabs_with_signals = [
            i for i in range(self._controller.tab_count)
            if self._controller.tab_has_signals(i)
        ]
        if not tabs_with_signals:
            return {}
        if setting == "ask":
            reply = QMessageBox.question(
                self,
                "Keep Active Signals?",
                "Keep the currently active signals in the new measurement?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return {}
        return {i: self._controller.snapshot_tab_signals(i) for i in tabs_with_signals}

    def _restore_snapshots(self, snapshots_by_tab: dict[int, list]) -> None:
        """Resolve each tab's snapshots against the new file and re-add matched signals.

        Near-matches (REQ-FILE-032/033) across every tab are confirmed in
        one NearMatchDialog after all tabs have been classified, rather
        than resolving them inline per tab — see REQ-FILE-036 and
        docs/architecture.md "Near-Match Signal Resolution (#109)".
        """
        from mdf_viewer.view.near_match_dialog import NearMatchDialog
        from mdf_viewer.view.signal_group_picker_dialog import SignalGroupPickerDialog
        from mdf_viewer.view.signals_not_found_dialog import SignalsNotFoundDialog

        not_found: list[str] = []
        resolved_by_tab: dict[int, list] = {}
        pending_near_matches: list[tuple[int, object, object]] = []

        for tab_index, snapshots in snapshots_by_tab.items():
            for snap in snapshots:
                # measurement_aware=True: a multi-file Replace (#101) can load
                # more than one measurement at once, so candidates must say
                # which measurement each came from to disambiguate a name
                # matching in more than one — see _classify_signal_name().
                status, candidates = self._classify_signal_name(snap.name, measurement_aware=True)
                if status == "exact_single":
                    measurement, meta = candidates[0]
                    resolved_by_tab.setdefault(tab_index, []).append(
                        (snap, meta.group_index, meta.channel_index, measurement)
                    )
                elif status == "exact_multiple":
                    dlg = SignalGroupPickerDialog(snap.name, candidates, self)
                    if dlg.exec():
                        measurement, meta = dlg.selected()
                        resolved_by_tab.setdefault(tab_index, []).append(
                            (snap, meta.group_index, meta.channel_index, measurement)
                        )
                    else:
                        not_found.append(snap.name)
                elif status == "near_single":
                    pending_near_matches.append((tab_index, snap, candidates[0]))
                elif status == "near_multiple":
                    dlg = SignalGroupPickerDialog(snap.name, candidates, self)
                    if dlg.exec():
                        pending_near_matches.append((tab_index, snap, dlg.selected()))
                    else:
                        not_found.append(snap.name)
                else:  # not_found
                    not_found.append(snap.name)

        if pending_near_matches:
            dlg = NearMatchDialog(
                [(snap.name, candidate) for _, snap, candidate in pending_near_matches], self
            )
            checked = dlg.checked_mask() if dlg.exec() else [False] * len(pending_near_matches)
            for (tab_index, snap, candidate), accepted in zip(pending_near_matches, checked):
                if accepted:
                    measurement, meta = candidate
                    resolved_by_tab.setdefault(tab_index, []).append(
                        (snap, meta.group_index, meta.channel_index, measurement)
                    )
                else:
                    not_found.append(snap.name)

        for tab_index, resolved in resolved_by_tab.items():
            self._controller.restore_tab_signals(tab_index, resolved)

        if not_found:
            dlg = SignalsNotFoundDialog(sorted(set(not_found)), self)
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
            for table in self._all_active_signals_tables():
                table.set_shorten_names_enabled(self._settings.display_name_rule_enabled)

    def _on_configure_display_names(self, preview_name: str) -> None:
        if self._settings is None or self._controller is None:
            return
        from mdf_viewer.view.signal_display_name_dialog import SignalDisplayNameDialog
        dlg = SignalDisplayNameDialog(self._settings, preview_name, self)
        if dlg.exec():
            self._controller.refresh_display_names()
            for table in self._all_active_signals_tables():
                table.set_shorten_names_enabled(self._settings.display_name_rule_enabled)

    def _on_shorten_names_toggled(self, enabled: bool) -> None:
        if self._settings is None or self._controller is None:
            return
        self._settings.display_name_rule_enabled = enabled
        self._controller.refresh_display_names()
        for table in self._all_active_signals_tables():
            table.set_shorten_names_enabled(enabled)

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

        Near-matches (REQ-FILE-032/033) across every signal in *config* are
        confirmed in one NearMatchDialog after all signals have been
        classified, rather than resolving them inline one at a time — see
        REQ-FILE-036.
        """
        from mdf_viewer.controller.app_controller import ActiveSignalSnapshot
        from mdf_viewer.view.near_match_dialog import NearMatchDialog
        from mdf_viewer.view.signal_group_picker_dialog import SignalGroupPickerDialog

        resolved: list = []
        not_found: list[str] = []
        pending_near_matches: list[tuple[object, object]] = []  # (snap, candidate)

        for sig in config.signals:
            status, candidates = self._classify_signal_name(sig.name, sig.group_name)

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

            if status == "exact_single":
                meta = candidates[0]
                resolved.append((snap, meta.group_index, meta.channel_index))
            elif status == "exact_multiple":
                dlg = SignalGroupPickerDialog(sig.name, candidates, self)
                if dlg.exec():
                    meta = dlg.selected()
                    resolved.append((snap, meta.group_index, meta.channel_index))
                else:
                    not_found.append(sig.name)
            elif status == "near_single":
                pending_near_matches.append((snap, candidates[0]))
            elif status == "near_multiple":
                dlg = SignalGroupPickerDialog(sig.name, candidates, self)
                if dlg.exec():
                    pending_near_matches.append((snap, dlg.selected()))
                else:
                    not_found.append(sig.name)
            else:  # not_found
                not_found.append(sig.name)

        if pending_near_matches:
            dlg = NearMatchDialog(
                [(snap.name, candidate) for snap, candidate in pending_near_matches], self
            )
            checked = dlg.checked_mask() if dlg.exec() else [False] * len(pending_near_matches)
            for (snap, candidate), accepted in zip(pending_near_matches, checked):
                if accepted:
                    resolved.append((snap, candidate.group_index, candidate.channel_index))
                else:
                    not_found.append(snap.name)

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
