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
    QDialog,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTabBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)


def _candidate_indices(candidate, measurement_aware: bool) -> tuple:
    """Unpack one `_classify_signal_name()` candidate into the trailing
    fields of a resolved-signal tuple (#106 M5 shared-helper extraction).

    `measurement_aware=False` candidates are plain `SignalMetadata` →
    `(group_index, channel_index)`. `measurement_aware=True` candidates
    are `(LoadedMeasurement, SignalMetadata)` pairs →
    `(group_index, channel_index, measurement)`.
    """
    if measurement_aware:
        measurement, meta = candidate
        return meta.group_index, meta.channel_index, measurement
    return candidate.group_index, candidate.channel_index


from mdf_viewer import __version__
from mdf_viewer.errors import MdfLoadError
from mdf_viewer.license.license_info import LicenseInfo
from mdf_viewer.license.license_manager import LicenseManager
from mdf_viewer.settings import Settings
from mdf_viewer.model.viewer_config import StripeConfig
from mdf_viewer.view.active_signals_table import ActiveSignalsTable
from mdf_viewer.view.dockable_panel import DockablePanel
from mdf_viewer.view.license_dialog import LicenseDialog
from mdf_viewer.view.measurement_info_box import MeasurementInfoBox
from mdf_viewer.view.plot_stripes_area import PlotStripesArea
from mdf_viewer.view.signal_browser import SignalBrowser
from mdf_viewer.view.signal_info_box import SignalInfoBox
from mdf_viewer.view.widgets import busy_cursor, make_splitter
from mdf_viewer.view.widgets.icons import _ICONS_DIR, _icon_suffix, _load_icon
from mdf_viewer.view.workspace_session_controller import WorkspaceSessionController

if TYPE_CHECKING:
    from mdf_viewer.controller.app_controller import AppController
    from mdf_viewer.plugin_api.registry import (
        DockWidgetRegistration,
        MenuActionRegistration,
        PluginRegistry,
    )

_PANEL_W = 260         # left panel default width in pixels
_INFO_DRAWER_W = 260   # info/properties drawer default width in pixels
_MIN_REAL_TAB_WIDTH = 110  # px — REQ-PLOT-255


class _TabBar(QTabBar):
    """`QTabBar` enforcing a minimum width on every real tab (REQ-PLOT-255).

    A short tab name (e.g. "DTI") otherwise shrinks the whole tab down to
    barely more than its own close ("×") button, making the close control
    disproportionately easy to hit by accident instead of the tab itself
    (#140). The pinned "+" new-tab tab is exempt — identified by having no
    close button at all (`MainWindow` clears both button positions for it),
    it should stay compact like a button, not stretch to the same minimum.
    """

    def tabSizeHint(self, index: int) -> QSize:
        hint = super().tabSizeHint(index)
        has_close_button = (
            self.tabButton(index, QTabBar.ButtonPosition.LeftSide) is not None
            or self.tabButton(index, QTabBar.ButtonPosition.RightSide) is not None
        )
        if not has_close_button:
            return hint
        return QSize(max(hint.width(), _MIN_REAL_TAB_WIDTH), hint.height())



_MDF_FILE_FILTER = "MDF Files (*.mf4 *.mdf *.dat);;All Files (*)"
_ALL_FILE_FILTER = "All Supported Files (*.mf4 *.mdf *.dat *.mvc);;MDF Files (*.mf4 *.mdf *.dat);;MDF Viewer Config (*.mvc);;All Files (*)"
_MVC_FILE_FILTER = "MDF Viewer Config (*.mvc);;All Files (*)"
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
        self._plugins_menu: QMenu | None = None
        self._plugin_dialogs: dict["DockWidgetRegistration", QDialog] = {}
        self.setWindowTitle("MDF-Viewer — unregistered")
        self.setWindowIcon(QIcon(str(_ICONS_DIR / "app_icon.ico")))
        self.resize(1280, 800)
        self._build_actions()
        self._build_menu()
        self._build_toolbar()
        self._build_layout()
        self.statusBar()  # pre-create so its height is always reserved
        # Every callable below is a lambda that looks up the target method on
        # `self` at CALL time, not a bound method captured here at __init__
        # time — tests patch these via patch.object(window, "_method_name")
        # *after* construction, which only shadows the instance attribute;
        # a bound method captured up front would keep pointing at the
        # original unpatched function forever (confirmed the hard way: an
        # early draft passed `save_config_as=self._on_save_config_as`
        # directly, and a test patching `_on_save_config_as` away had no
        # effect, so the real QFileDialog.getSaveFileName ran and hung the
        # test process waiting for a dialog nothing could close).
        self._session = WorkspaceSessionController(
            parent=self,
            tab_widget=self._tab_widget,
            get_controller=lambda: self._controller,
            get_settings=lambda: self._settings,
            on_new_tab=lambda: self._on_new_tab(),
            resolve_and_confirm_snapshots=lambda snaps: self._resolve_and_confirm_snapshots(
                snaps, use_group_name=True
            ),
            capture_window_geometry=lambda: self._capture_window_geometry(),
            capture_splitter_sizes=lambda: self._capture_splitter_sizes(),
            apply_window_geometry=lambda g: self._apply_window_geometry(g),
            apply_splitter_sizes=lambda s: self._apply_splitter_sizes(s),
            tab_names=lambda: self._tab_names(),
            tab_page_splitter_sizes=lambda: self._tab_page_splitter_sizes(),
            save_config_as=lambda: self._on_save_config_as(),
            show_status=lambda msg, ms: self.show_status(msg, ms),
            clear_status=lambda: self.statusBar().clearMessage(),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def set_controller(self, controller: AppController) -> None:
        """Wire the controller after it has been constructed with this window's views."""
        self._controller = controller
        controller.set_cursor_mode_callback(self._on_cursor_mode_changed)
        self.signal_browser.add_signals_requested.connect(self._on_add_signals)
        self.measurement_info_box.primary_change_requested.connect(
            controller.set_primary_measurement
        )
        self.measurement_info_box.rename_requested.connect(controller.rename_measurement)
        self.measurement_info_box.replace_requested.connect(self._replace_single_measurement)
        self.measurement_info_box.close_requested.connect(
            self._on_close_measurement_requested
        )
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
        self._build_plugins_menu(controller.plugin_registry)
        self._build_plugin_dock_sections(controller.plugin_registry)

    def _build_plugin_dock_sections(self, registry: "PluginRegistry") -> None:
        """Add every docked-mode plugin widget to the Info/Properties drawer (#73).

        Read once, here in set_controller() — same one-time-snapshot
        reasoning as _build_plugins_menu (REQ-PLUGIN-200).
        """
        for dock_reg in registry.dock_widgets:
            if dock_reg.mode != "docked":
                continue
            widget = dock_reg.build()
            if widget is None:
                continue
            self.signal_info_box.add_plugin_section(dock_reg.title, widget)

    def _build_plugins_menu(self, registry: "PluginRegistry") -> None:
        """Build the Plugins menu from *registry*'s current contents (#73).

        Read once, here in set_controller() — MainWindow is constructed
        before AppController exists (see app.py), so this is the earliest
        point a real PluginRegistry is available. No plugin loader (#74)
        exists yet to change the registry afterward, so this never needs
        to run again (REQ-PLUGIN-200). Not shown at all if there's nothing
        to put in it (REQ-PLUGIN-211).
        """
        has_dialog_widget = any(d.mode == "dialog" for d in registry.dock_widgets)
        if not registry.menu_actions and not has_dialog_widget:
            return

        self._plugins_menu = QMenu("&Plugins", self)
        for action_reg in registry.menu_actions:
            action = QAction(action_reg.label, self)
            action.triggered.connect(lambda checked, r=action_reg: self._on_plugin_menu_action(r))
            self._plugins_menu.addAction(action)

        if registry.menu_actions and has_dialog_widget:
            self._plugins_menu.addSeparator()

        for dock_reg in registry.dock_widgets:
            if dock_reg.mode != "dialog":
                continue
            action = QAction(f"{dock_reg.title}…", self)
            action.triggered.connect(lambda checked, r=dock_reg: self._on_plugin_dialog_action(r))
            self._plugins_menu.addAction(action)

        self.menuBar().insertMenu(self._help_menu.menuAction(), self._plugins_menu)

    def _on_plugin_menu_action(self, registration: "MenuActionRegistration") -> None:
        if not registration.invoke():
            self.show_status(f"Plugin action '{registration.label}' failed — see log for detail.", 5000)

    def _on_plugin_dialog_action(self, registration: "DockWidgetRegistration") -> None:
        """Show *registration*'s dialog, building it lazily on first open and
        reusing the same instance afterward — rebuilding on every open would
        silently discard whatever plugin-owned state the widget holds (#73)."""
        dialog = self._plugin_dialogs.get(registration)
        if dialog is None:
            widget = registration.build()
            if widget is None:
                return
            dialog = QDialog(self)
            dialog.setWindowTitle(registration.title)
            layout = QVBoxLayout(dialog)
            layout.addWidget(widget)
            self._plugin_dialogs[registration] = dialog
        dialog.exec()

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
        plot_area.synchronize_toggled.connect(self._on_sync_button_clicked)
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
        active_signals_table.visibility_toggle_requested.connect(
            controller.toggle_signal_visibility
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

        self._apply_config_action = QAction("Apply Config…", self)
        self._apply_config_action.setToolTip(
            "Apply a saved workspace's tabs/stripes/signals onto the "
            "currently loaded measurement(s), without opening its file(s)"
        )
        self._apply_config_action.triggered.connect(self._on_apply_config)

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

        self._sync_measurements_action = QAction("Sync Measurements", self)
        self._sync_measurements_action.setCheckable(True)
        self._sync_measurements_action.setEnabled(False)
        self._sync_measurements_action.setToolTip(
            "Collapse every loaded measurement's own time axis into one shared ruler"
        )
        self._sync_measurements_action.toggled.connect(self._on_sync_action_toggled)

        self._save_config_action = QAction("Save Workspace", self)
        self._save_config_action.setShortcut(QKeySequence("Ctrl+S"))
        self._save_config_action.triggered.connect(self._on_save_config)

        self._save_config_as_action = QAction("Save Workspace As…", self)
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
        self._file_menu.addAction(self._apply_config_action)
        self._file_menu.addAction(self._save_config_action)
        self._file_menu.addAction(self._save_config_as_action)
        self._replace_measurement_menu = QMenu("Replace Measurement", self)
        self._file_menu.addMenu(self._replace_measurement_menu)
        self._close_measurement_menu = QMenu("Close Measurement", self)
        self._file_menu.addMenu(self._close_measurement_menu)
        self._file_menu.addSeparator()
        self._exit_action = QAction("Exit", self)
        self._exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        self._exit_action.triggered.connect(self.close)
        self._file_menu.addAction(self._preferences_action)
        self._file_menu.addSeparator()
        self._file_menu.addAction(self._exit_action)
        self._file_menu.aboutToShow.connect(self._rebuild_recent_files)
        self._file_menu.aboutToShow.connect(self._update_apply_config_enabled)
        self._file_menu.aboutToShow.connect(self._rebuild_replace_measurement_menu)
        self._file_menu.aboutToShow.connect(self._rebuild_close_measurement_menu)

        self._edit_menu = self.menuBar().addMenu("&Edit")
        self._edit_menu.addAction(self._new_tab_action)
        self._edit_menu.addAction(self._new_stripe_action)
        self._edit_menu.addSeparator()
        self._edit_menu.addAction(self._undo_action)
        self._edit_menu.addAction(self._redo_action)
        self._edit_menu.addSeparator()
        self._edit_menu.addAction(self._sync_measurements_action)

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
        toolbar.addAction(self._zoom_all_stripes_action)
        toolbar.addAction(self._zoom_fit_action)
        toolbar.addAction(self._zoom_y_action)
        toolbar.addSeparator()
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
        self._parked_page: QSplitter | None = None
        self._tab_widget = QTabWidget()
        self._tab_widget.setTabBar(_TabBar())
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

    def _on_new_tab(self) -> int:
        """Create a new tab: a fresh plot area + Active Signals Table pair (#99).

        If a page was parked by closing the previous last tab (#130), reuse
        it instead of building a fresh pair — AppController keeps that
        parked page's TabWorkspace alive rather than removing it (since
        current_workspace must never be empty), so building a fresh pair
        here would register a second, unrelated workspace and leave the
        parked one as a permanent, never-shown orphan.

        Returns the new tab's index in the tab bar (always inserted right
        before the "+" placeholder) — used by _on_duplicate_tab()/
        _on_copy_signals_to_new_tab() (#119) to reposition it afterward.
        """
        if self._parked_page is not None:
            page = self._parked_page
            self._parked_page = None
        else:
            plot_area = PlotStripesArea()
            active_signals_table = ActiveSignalsTable()
            if self._tab_factory is not None:
                self._tab_factory(plot_area, active_signals_table)
            page = self._make_tab_page(plot_area, active_signals_table)
            self._wire_tab_view(plot_area, active_signals_table)
        self._tab_counter += 1
        index = self._placeholder_index()  # insert right before the "+" tab
        self._tab_widget.insertTab(index, page, f"Tab {self._tab_counter}")
        self._tab_widget.setCurrentIndex(index)
        if self._content_stack.currentWidget() is not self._tab_widget:
            self._content_stack.setCurrentWidget(self._tab_widget)
        return index

    def _on_new_stripe(self) -> None:
        """Create a new empty stripe in the currently active tab (REQ-PLOT-196, #112)."""
        if self._controller is not None:
            self._controller.create_stripe()

    def _on_copy_signals_to_new_tab(self, source_index: int) -> None:
        """Copy every active signal from the tab at *source_index* into a
        fresh tab's single stripe — no stripe layout or view state carried
        over (REQ-PLOT-267/268, #119).

        The new tab is built via _on_new_tab() (always appended at the
        end) then repositioned immediately after the source tab with one
        moveTab() call, which re-triggers _on_tab_bar_tab_moved()'s
        existing drag-reorder resync (#99) — no separate "insert at index"
        path needed. moveTab() is a no-op (and doesn't fire tabMoved) when
        source_index is already the last real tab, since the new tab was
        already appended right after it; the controller resync is skipped
        in that case because nothing needs resyncing.
        """
        source_name = self._tab_widget.tabText(source_index)
        new_index = self._on_new_tab()
        dest_index = source_index + 1
        if new_index != dest_index:
            self._tab_widget.tabBar().moveTab(new_index, dest_index)
        self._tab_widget.setTabText(dest_index, "Copy of " + source_name)
        if self._controller is not None:
            self._controller.copy_signals_to_new_tab(source_index, dest_index)

    def _on_duplicate_tab(self, source_index: int) -> None:
        """Full copy of the tab at *source_index*: stripe layout, signals,
        cursor, zoom, and axis grouping — sharing only the underlying
        measurement(s), not any plot object (REQ-PLOT-265, #119).

        Positions/names the new tab exactly like
        _on_copy_signals_to_new_tab() (create at the end, reposition via
        moveTab()), then additionally builds its stripe skeleton from the
        source's *live* stripes — freshly constructed StripeConfigs, never
        touching JSON/disk — before handing off to the controller for
        signal cloning and zoom/grouping/cursor restore.
        """
        source_page = self._tab_widget.widget(source_index)
        source_name = self._tab_widget.tabText(source_index)
        new_index = self._on_new_tab()
        dest_index = source_index + 1
        if new_index != dest_index:
            self._tab_widget.tabBar().moveTab(new_index, dest_index)
        self._tab_widget.setTabText(dest_index, "Copy of " + source_name)

        dest_page = self._tab_widget.widget(dest_index)
        source_plot = source_page.plot_area
        source_stripes = source_plot.get_stripes()
        stripe_configs = [
            StripeConfig(name=stripe.name, size=size)
            for stripe, size in zip(source_stripes, source_plot.get_stripe_sizes())
        ]
        active_stripe_index = source_stripes.index(source_plot.get_active_stripe())
        self._build_stripe_skeleton(dest_page, stripe_configs, active_stripe_index)
        dest_page.setSizes(source_page.sizes())
        dest_page.active_signals_table.set_column_widths(
            source_page.active_signals_table.column_widths()
        )

        if self._controller is not None:
            self._controller.duplicate_tab_signals(source_index, dest_index)

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
        #
        # Exception: closing the very last real tab. AppController.remove_tab()
        # deliberately keeps that one TabWorkspace alive (current_workspace
        # must never be empty) instead of dropping it, so deleteLater()-ing
        # its widgets here would leave the controller holding a reference to
        # already-destroyed Qt objects — the next thing that touched it
        # crashed with "wrapped C/C++ object ... has been deleted" (#130).
        # Park it instead so _on_new_tab() can reuse the very same widgets.
        was_last_real_tab = self._real_tab_count() == 1
        page = self._tab_widget.widget(index)
        self._tab_widget.removeTab(index)
        if was_last_real_tab:
            self._parked_page = page
        else:
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
        duplicate_action = menu.addAction("Duplicate Tab")
        copy_signals_action = menu.addAction("Copy Signals to new Tab")
        copy_signals_action.setEnabled(
            self._controller is not None and self._controller.tab_has_signals(index)
        )
        close_action = menu.addAction("Close")
        action = menu.exec(tab_bar.mapToGlobal(pos))
        if action is rename_action:
            self._rename_tab(index)
        elif action is duplicate_action:
            self._on_duplicate_tab(index)
        elif action is copy_signals_action:
            self._on_copy_signals_to_new_tab(index)
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

    def _on_add_signals(self, locations: list) -> None:
        """A Signal Browser add-signal request — double-click or "Add Signal"
        button (#103, REQ-BROWSER-031). *locations* is a list of
        (measurement_index, group_index, channel_index) triples; a single
        request can span multiple measurements since the browser is now one
        unified cross-measurement list, so each item resolves its own
        measurement rather than sharing one for the whole batch.
        """
        if self._controller is None:
            return
        skipped = 0
        for mi, gi, ci in locations:
            measurement = self._controller.measurement_at(mi)
            try:
                if not self._controller.add_signal(gi, ci, measurement=measurement):
                    skipped += 1
            except MdfLoadError as exc:
                QMessageBox.critical(self, "Error Loading Signal", str(exc))
        if skipped:
            noun = "signal" if skipped == 1 else "signals"
            self.show_status(f"{skipped} {noun} already active, skipped.")

    def _on_add_signals_to_stripe(self, locations: list, stripe) -> None:
        """A drag-and-drop of one or more channels from the Signal Browser
        onto *stripe* (#103). *locations* is a list of (measurement_index,
        group_index, channel_index) triples — a single drag gesture can
        legally span rows from different measurements, so each item
        resolves its own measurement rather than sharing one for the whole
        drop.
        """
        if self._controller is None:
            return
        skipped = 0
        for mi, gi, ci in locations:
            measurement = self._controller.measurement_at(mi)
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

    def _on_sync_button_clicked(self) -> None:
        """A bottom stripe's Synchronize/Un-sync button was clicked (#102),
        in any tab. Flips the controller's global synchronized flag and
        pushes the new state into the Edit-menu checkbox, which mirrors it
        (blocked from re-triggering the controller by
        _on_sync_action_toggled's own equality guard below)."""
        if self._controller is None:
            return
        self._controller.toggle_measurements_synchronized()
        self._sync_measurements_action.setChecked(self._controller.is_measurements_synchronized)

    def _on_sync_action_toggled(self, checked: bool) -> None:
        """The Edit-menu action's checked state changed — either a real user
        click, or _on_sync_button_clicked mirroring the button's own click
        back into this checkbox. Only the former should ask the controller
        to toggle; the latter already reflects the controller's current
        state, so re-toggling would immediately revert it."""
        if self._controller is None:
            return
        if checked == self._controller.is_measurements_synchronized:
            return
        self._controller.toggle_measurements_synchronized()

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
        with busy_cursor(
            f"Loading {names}…", show_status=self.show_status,
            clear_status=lambda: self.statusBar().clearMessage(),
        ):
            if mode == "replace":
                result = self._controller.replace_measurements(paths)
            else:
                result = self._controller.add_measurements(paths)

        self._sync_measurements_action.setEnabled(self._controller.measurement_count >= 2)

        if result.failed:
            lines = "\n".join(f"{Path(p).name}: {err}" for p, err in result.failed)
            QMessageBox.critical(self, "Load Error", lines)

        if mode == "replace" and result.succeeded and snapshots:
            self._restore_snapshots(snapshots)

    def _classify_signal_name(
        self, name: str, group_name: str = "", *,
        measurement_aware: bool = False,
        measurement: "object | None" = None,
    ) -> tuple[str, list]:
        """Classify *name* against the loaded file(s) for signal-restore purposes.

        Tries an exact match first, falling back to a near match
        (REQ-FILE-032/033) only when there's no exact match at all — a
        near match is never preferred over an exact one. Returns
        (status, candidates) where status is one of "exact_single",
        "exact_multiple", "near_single", "near_multiple", or "not_found".

        *measurement*, if given, scopes the search to that one
        `LoadedMeasurement`'s own channel tree only (#106 M6, REQ-FILE-093
        — a saved session's signal resolves against the same measurement
        it was captured from, not an arbitrary one), regardless of
        *measurement_aware*'s value; candidates are still returned as
        (LoadedMeasurement, SignalMetadata) tuples (always this fixed
        *measurement*), matching the measurement_aware=True shape.

        Otherwise, *measurement_aware* selects between two candidate
        shapes: False (default) returns plain SignalMetadata, searching
        only against `.mvc` restore's pre-M6 single-measurement scope.
        True returns (LoadedMeasurement, SignalMetadata) tuples, searched
        across every loaded measurement — used by the multi-file Replace
        carry-over flow (#101) to disambiguate a name matching in more
        than one loaded measurement, which a bare SignalMetadata result
        can't express.
        """
        if measurement is not None:
            candidates = [
                (measurement, meta) for meta in measurement.loader.find_signal_by_name(name)
            ]
            is_near = False
            if not candidates:
                candidates = [
                    (measurement, meta)
                    for meta in measurement.loader.find_similar_signal_by_name(name)
                ]
                is_near = True
            if group_name and candidates:
                narrowed = [c for c in candidates if c[1].group_name == group_name]
                if narrowed:
                    candidates = narrowed
        elif measurement_aware:
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

    def _collect_measurement_snapshots_if_keeping(self, measurement) -> dict[int, list]:
        """Same three keep_signals_on_load branches as _collect_snapshots_if_keeping()
        above, scoped to one measurement's own active signals (REQ-FILE-104)
        rather than every tab's — used by single-measurement Replace, not the
        whole-pool Replace flow that method serves."""
        if self._controller is None or self._settings is None:
            return {}
        setting = self._settings.keep_signals_on_load
        if setting == "never":
            return {}
        if not self._controller.measurement_has_signals(measurement):
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
        return self._controller.snapshot_measurement_signals(measurement)

    def _resolve_and_confirm_snapshots(
        self,
        snapshots_by_tab: dict[int, list],
        *,
        use_group_name: bool,
    ) -> tuple[dict[int, list], list[str]]:
        """Classify every tab's snapshots by name (REQ-FILE-032/033),
        batching every near-match across every tab into ONE
        NearMatchDialog at the end rather than one per tab (REQ-FILE-036)
        — the shared logic behind both `_restore_snapshots()` (file-reload's
        "keep signals", already multi-tab, #99 M8) and
        `_resolve_config_signals()` (session restore, #106); extracted
        since the two were structurally near-identical (#106 M5).

        Always resolves with `_classify_signal_name(measurement_aware=True)`
        — resolved tuples gain a trailing `measurement` element (both real
        callers need this shape; #136 dropped the `measurement_aware`
        parameter after confirming it was always `True` in practice).
        *use_group_name* controls whether each snapshot's `group_name`
        narrows ambiguous matches — a genuine behavioral difference between
        the two callers, not accidental: session-restore's saved
        `SignalConfig.group_name` should narrow matches (`use_group_name=True`),
        while reload's live snapshot resolution never narrows by group
        (`use_group_name=False`).

        Returns (resolved_by_tab, not_found) — resolved_by_tab maps
        tab_index to a list of (snapshot, group_index, channel_index,
        measurement) tuples; not_found is every signal name that
        couldn't be resolved at all (including a declined picker/near-match).
        Showing `SignalsNotFoundDialog` is each caller's own job, since
        the two existing callers do it slightly differently (one
        dedupes/sorts first, one doesn't).
        """
        from mdf_viewer.view.near_match_dialog import NearMatchDialog
        from mdf_viewer.view.signal_group_picker_dialog import SignalGroupPickerDialog

        not_found: list[str] = []
        resolved_by_tab: dict[int, list] = {}
        pending_near_matches: list[tuple[int, object, object, bool]] = []

        for tab_index, snapshots in snapshots_by_tab.items():
            for snap in snapshots:
                group_name = snap.group_name if use_group_name else ""
                snap_measurement = getattr(snap, "measurement", None)
                status, candidates = self._classify_signal_name(
                    snap.name, group_name,
                    measurement_aware=True, measurement=snap_measurement,
                )
                if status == "exact_single":
                    resolved_by_tab.setdefault(tab_index, []).append(
                        (snap, *_candidate_indices(candidates[0], True))
                    )
                elif status == "exact_multiple":
                    dlg = SignalGroupPickerDialog(snap.name, candidates, self)
                    if dlg.exec():
                        resolved_by_tab.setdefault(tab_index, []).append(
                            (snap, *_candidate_indices(dlg.selected(), True))
                        )
                    else:
                        not_found.append(snap.name)
                elif status == "near_single":
                    pending_near_matches.append((tab_index, snap, candidates[0], True))
                elif status == "near_multiple":
                    dlg = SignalGroupPickerDialog(snap.name, candidates, self)
                    if dlg.exec():
                        pending_near_matches.append((tab_index, snap, dlg.selected(), True))
                    else:
                        not_found.append(snap.name)
                else:  # not_found
                    not_found.append(snap.name)

        if pending_near_matches:
            dlg = NearMatchDialog(
                [(snap.name, candidate) for _, snap, candidate, _ in pending_near_matches], self
            )
            checked = dlg.checked_mask() if dlg.exec() else [False] * len(pending_near_matches)
            for (tab_index, snap, candidate, item_aware), accepted in zip(pending_near_matches, checked):
                if accepted:
                    resolved_by_tab.setdefault(tab_index, []).append(
                        (snap, *_candidate_indices(candidate, item_aware))
                    )
                else:
                    not_found.append(snap.name)

        return resolved_by_tab, not_found

    def _restore_snapshots(self, snapshots_by_tab: dict[int, list]) -> None:
        """Resolve each tab's snapshots against the new file and re-add matched signals.

        Near-matches (REQ-FILE-032/033) across every tab are confirmed in
        one NearMatchDialog after all tabs have been classified, rather
        than resolving them inline per tab — see REQ-FILE-036 and
        docs/architecture.md "Near-Match Signal Resolution (#109)".
        """
        from mdf_viewer.view.signals_not_found_dialog import SignalsNotFoundDialog

        # measurement_aware=True: a multi-file Replace (#101) can load more
        # than one measurement at once, so candidates must say which
        # measurement each came from to disambiguate a name matching in
        # more than one. use_group_name=False preserves this call site's
        # long-standing behavior unchanged (see _resolve_and_confirm_snapshots'
        # own docstring for why this is an explicit switch, not a silent
        # improvement bundled into the #106 M5 refactor that extracted this).
        resolved_by_tab, not_found = self._resolve_and_confirm_snapshots(
            snapshots_by_tab, use_group_name=False,
        )

        for tab_index, resolved in resolved_by_tab.items():
            self._controller.restore_tab_signals(tab_index, resolved)

        if not_found:
            dlg = SignalsNotFoundDialog(sorted(set(not_found)), self)
            dlg.exec()

    def _replace_single_measurement(self, measurement) -> None:
        """Replace *measurement*'s underlying file only, leaving every other
        loaded measurement untouched (REQ-FILE-100..107).

        Entry point for both the File ▸ Replace Measurement submenu and the
        Measurement Info Box's "Replace…" button.
        """
        if self._controller is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Replace Measurement", "", _MDF_FILE_FILTER
        )
        if not path:
            return

        snapshots = self._collect_measurement_snapshots_if_keeping(measurement)

        with busy_cursor(
            f"Loading {Path(path).name}…", show_status=self.show_status,
            clear_status=lambda: self.statusBar().clearMessage(),
        ):
            result = self._controller.replace_single_measurement(measurement, path)

        if result.failed:
            lines = "\n".join(f"{Path(p).name}: {err}" for p, err in result.failed)
            QMessageBox.critical(self, "Load Error", lines)
            return

        if snapshots:
            self._restore_snapshots(snapshots)

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
        from mdf_viewer.enums import CursorMode
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
        with busy_cursor():
            try:
                release = fetch_latest_release()
            except UpdateCheckError as exc:
                QMessageBox.warning(self, "Update Check Failed", str(exc))
                return
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
                msg = f"Save updated workspace '{path.name}'?"
            else:
                msg = "Save current view as a workspace file?"
            reply = QMessageBox.question(
                self,
                "Save Workspace?",
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
        # A parked page (#130) left over from closing the last tab without a
        # following "New Tab" is unparented and was never deleteLater()'d —
        # left alone it's exactly the orphaned-but-alive Qt object #120
        # warns about, still wired into whatever signal/slot connections it
        # had, surviving past this window's own teardown.
        if self._parked_page is not None:
            self._parked_page.deleteLater()
            self._parked_page = None
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
            self, "Save Workspace As", "", _MVC_FILE_FILTER
        )
        if not path_str:
            return
        self._save_config_to(Path(path_str))

    def _tab_names(self) -> list[str]:
        """Every real tab's current title, in workspace order (#106) —
        excludes the pinned "+" placeholder tab."""
        placeholder_index = self._placeholder_index()
        return [
            self._tab_widget.tabText(i)
            for i in range(self._tab_widget.count())
            if i != placeholder_index
        ]

    def _tab_page_splitter_sizes(self) -> list[tuple[int, int]]:
        """Every real tab's plot|AST divider widths, in workspace order
        (#106) — `AppController` has no access to these QSplitters
        (`MainWindow` owns the tab pages), same reasoning as `_tab_names()`."""
        placeholder_index = self._placeholder_index()
        return [
            tuple(self._tab_widget.widget(i).sizes())
            for i in range(self._tab_widget.count())
            if i != placeholder_index
        ]

    def _save_config_to(self, path: Path) -> None:
        self._session.save_config_to(path)

    def _reset_to_single_tab(self) -> None:
        self._session.reset_to_single_tab()

    def _build_tab_skeletons(self, tab_configs: list) -> None:
        self._session.build_tab_skeletons(tab_configs)

    def _build_stripe_skeleton(self, page, stripes: list, active_stripe_index: int) -> None:
        self._session.build_stripe_skeleton(page, stripes, active_stripe_index)

    def _resolve_saved_measurements(
        self, measurement_configs: list, config_path: Path
    ) -> tuple[list, list[str]]:
        return self._session.resolve_saved_measurements(measurement_configs, config_path)

    def _confirm_missing_measurements(self, missing_paths: list[str]) -> bool:
        return self._session.confirm_missing_measurements(missing_paths)

    def open_config(self, path: Path) -> None:
        """Public entry point for opening a .mvc config file (e.g. from app.py)."""
        self._load_config(path)

    def _load_config(self, path: Path) -> None:
        self._session.load_config(path)

    def _signal_config_to_snapshot(
        self, sig, stripe_name: str = "", measurement: "object | None" = None,
    ) -> "ActiveSignalSnapshot":
        return self._session.signal_config_to_snapshot(sig, stripe_name, measurement)

    def _resolve_config_signals_for_tabs(
        self, tab_configs: list, measurements: list,
    ) -> tuple[dict[int, list], list[str]]:
        return self._session.resolve_config_signals_for_tabs(tab_configs, measurements)

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

    def _rebuild_replace_measurement_menu(self) -> None:
        """Rebuild the File ▸ Replace Measurement submenu (REQ-FILE-100).

        Rebuilt every time the File menu opens, the same way
        _rebuild_close_measurement_menu() is, so a rename (#103) is always
        reflected and a just-closed measurement never lingers as a stale
        entry.
        """
        self._replace_measurement_menu.clear()
        measurements = [] if self._controller is None else self._controller.measurements
        self._replace_measurement_menu.setEnabled(bool(measurements))
        for measurement in measurements:
            action = self._replace_measurement_menu.addAction(measurement.label)
            action.triggered.connect(
                lambda checked=False, m=measurement: self._replace_single_measurement(m)
            )

    def _rebuild_close_measurement_menu(self) -> None:
        """Rebuild the File ▸ Close Measurement submenu (REQ-FILE-029).

        Rebuilt every time the File menu opens, the same way
        _rebuild_recent_files() is, so a rename (#103) is always reflected
        and a just-closed measurement never lingers as a stale entry.
        """
        self._close_measurement_menu.clear()
        measurements = [] if self._controller is None else self._controller.measurements
        self._close_measurement_menu.setEnabled(bool(measurements))
        for measurement in measurements:
            action = self._close_measurement_menu.addAction(measurement.label)
            action.triggered.connect(
                lambda checked=False, m=measurement: self._on_close_measurement_requested(m)
            )

    def _on_close_measurement_requested(self, measurement) -> None:
        """Close *measurement*, warning first if it still has active signals
        (REQ-FILE-028), mirroring the tab/stripe-close confirmation pattern."""
        if self._controller is None:
            return
        if self._controller.measurement_has_signals(measurement):
            reply = QMessageBox.question(
                self,
                "Close Measurement",
                f'"{measurement.label}" still has signals in it. Close anyway?',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        self._controller.close_measurement(measurement)

    def _update_apply_config_enabled(self) -> None:
        """Enable File ▸ Apply Config… only once at least one measurement
        is loaded (REQ-FILE-110) — recomputed lazily on the File menu's
        aboutToShow, the same lazy-refresh pattern (and the same
        controller.measurements read) used for the Replace/Close
        Measurement submenus above, rather than threading an enabled-state
        update through every measurement-pool-mutating call site."""
        measurements = [] if self._controller is None else self._controller.measurements
        self._apply_config_action.setEnabled(bool(measurements))

    def _on_apply_config(self) -> None:
        self._session.apply_config()

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
