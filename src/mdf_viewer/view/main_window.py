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

from PyQt6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QEvent,
    QPoint,
    QPropertyAnimation,
    QSize,
    Qt,
    QTimer,
)
from PyQt6.QtGui import QAction, QCursor, QFont, QIcon, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QToolButton,
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
from mdf_viewer.view.active_signals_table import ActiveSignalsTable
from mdf_viewer.view.license_dialog import LicenseDialog
from mdf_viewer.view.measurement_info_box import MeasurementInfoBox
from mdf_viewer.view.plot_area import PlotArea
from mdf_viewer.view.signal_browser import SignalBrowser
from mdf_viewer.view.signal_info_box import SignalInfoBox

if TYPE_CHECKING:
    from mdf_viewer.controller.app_controller import AppController

_PANEL_W = 260       # left panel width in pixels
_HOVER_PX = 10       # distance from left edge that triggers drawer slide-out
_ANIM_MS = 200       # slide animation duration in ms


def _make_splitter(orientation: Qt.Orientation) -> QSplitter:
    """Splitter with a thin visible handle line."""
    s = QSplitter(orientation)
    s.setHandleWidth(3)
    s.setStyleSheet("QSplitter::handle { background: palette(mid); }")
    return s

_MDF_FILE_FILTER = "MDF Files (*.mf4 *.mdf *.dat);;All Files (*)"
_GITHUB_URL = "https://github.com/andalf-74/MDF-Viewer"


class MainWindow(QMainWindow):
    """Assembles the menu bar, toolbar, and nested-splitter main layout."""

    def __init__(self) -> None:
        super().__init__()
        self._controller: AppController | None = None
        self._cursor_ctrl = None
        self._recent_provider: Callable[[], list[Path]] | None = None
        self._recent_actions: list[QAction] = []
        self._recent_sep: QAction | None = None
        self._license_info: LicenseInfo | None = None
        self._license_manager: LicenseManager | None = None
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

    def set_controller(
        self, controller: AppController, cursor_ctrl=None
    ) -> None:
        """Wire the controller after it has been constructed with this window's views."""
        self._controller = controller
        self._cursor_ctrl = cursor_ctrl
        if cursor_ctrl is not None:
            cursor_ctrl.set_mode_changed_callback(self._on_cursor_mode_changed)
        self.signal_browser.add_signals_requested.connect(self._on_add_signals)
        self.plot_area.signals_dropped.connect(self._on_add_signals)
        self.plot_area.file_dropped.connect(self._on_file_dropped)
        self.active_signals_table.signals_dropped.connect(self._on_add_signals)
        self.active_signals_table.remove_requested.connect(controller.remove_signal)
        self.active_signals_table.remove_all_requested.connect(controller.remove_all)
        self.active_signals_table.selection_changed.connect(
            controller.set_selected_signal
        )
        self.active_signals_table.color_change_requested.connect(
            controller.recolor_signal
        )
        self.active_signals_table.step_mode_toggle_requested.connect(
            controller.toggle_step_mode
        )
        self.active_signals_table.order_changed.connect(controller.reorder_signals)
        self.plot_area.y_grid_toggled.connect(controller.on_y_grid_toggled)

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

        self._about_action = QAction("About MDF-Viewer", self)
        self._about_action.triggered.connect(self._on_about)

        self._license_action = QAction("Enter License Key…", self)
        self._license_action.triggered.connect(self._on_license)

    def _build_menu(self) -> None:
        self._file_menu = self.menuBar().addMenu("&File")
        self._file_menu.addAction(self._load_action)
        self._file_menu.addSeparator()
        self._exit_action = QAction("Exit", self)
        self._exit_action.setShortcut(QKeySequence("Ctrl+Q"))
        self._exit_action.triggered.connect(self.close)
        self._file_menu.addAction(self._exit_action)
        self._file_menu.aboutToShow.connect(self._rebuild_recent_files)

        self._help_menu = self.menuBar().addMenu("&Help")
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
        toolbar.addAction(self._swimlanes_action)
        toolbar.addAction(self._zoom_cursors_action)
        toolbar.addAction(self._cursor_action)

    def _build_layout(self) -> None:
        self.signal_browser = SignalBrowser()
        self.plot_area = PlotArea()
        self.active_signals_table = ActiveSignalsTable()
        self.measurement_info_box = MeasurementInfoBox()
        self.signal_info_box = SignalInfoBox()

        # ── Left panel (collapsible / drawer) ────────────────────────────
        self._left_panel = QWidget()
        self._left_panel.setAutoFillBackground(True)  # opaque over content

        self._pin_button = QToolButton()
        self._pin_button.setText("‹")
        self._pin_button.setFixedHeight(32)
        self._pin_button.setAutoRaise(True)
        self._pin_button.setToolTip("Collapse panel")
        self._pin_button.clicked.connect(self._toggle_pin)
        _pin_font = QFont()
        _pin_font.setPointSize(16)
        self._pin_button.setFont(_pin_font)

        left_splitter = _make_splitter(Qt.Orientation.Vertical)
        left_splitter.addWidget(self.signal_browser)
        left_splitter.addWidget(self.measurement_info_box)
        left_splitter.setStretchFactor(0, 3)
        left_splitter.setStretchFactor(1, 1)

        pin_row = QHBoxLayout()
        pin_row.setContentsMargins(0, 0, 0, 0)
        pin_row.addStretch()
        pin_row.addWidget(self._pin_button)

        left_vbox = QVBoxLayout(self._left_panel)
        left_vbox.setContentsMargins(0, 0, 0, 0)
        left_vbox.setSpacing(0)
        left_vbox.addLayout(pin_row)
        left_vbox.addWidget(left_splitter)

        # ── Right panel ───────────────────────────────────────────────────
        right_panel = QWidget()
        right_splitter = _make_splitter(Qt.Orientation.Vertical)
        right_splitter.addWidget(self.active_signals_table)
        right_splitter.addWidget(self.signal_info_box)
        right_splitter.setStretchFactor(0, 3)
        right_splitter.setStretchFactor(1, 1)
        right_vbox = QVBoxLayout(right_panel)
        right_vbox.setContentsMargins(0, 0, 0, 0)
        right_vbox.addWidget(right_splitter)

        # ── Content splitter (plot area + right panel) ────────────────────
        self._content_splitter = _make_splitter(Qt.Orientation.Horizontal)
        self._content_splitter.addWidget(self.plot_area)
        self._content_splitter.addWidget(right_panel)
        self._content_splitter.setStretchFactor(0, 1)
        self._content_splitter.setStretchFactor(1, 0)
        self._content_splitter.setSizes([760, 260])

        # ── Outer splitter (pinned mode: left panel + content) ───────────
        # _panel_w tracks the current panel width so it's preserved across
        # pin/drawer transitions even after the user has resized the panel.
        self._panel_w = _PANEL_W
        self._outer_splitter = _make_splitter(Qt.Orientation.Horizontal)
        self._outer_splitter.addWidget(self._left_panel)
        self._outer_splitter.addWidget(self._content_splitter)
        self._outer_splitter.setStretchFactor(0, 0)
        self._outer_splitter.setStretchFactor(1, 1)
        self._outer_splitter.setSizes([_PANEL_W, 760])

        # ── Central container ─────────────────────────────────────────────
        # In pinned mode the outer splitter fills it.  In drawer mode the
        # left panel is re-parented here as a floating overlay.
        self._central = QWidget()
        self.setCentralWidget(self._central)
        self._central.installEventFilter(self)
        self._outer_splitter.setParent(self._central)

        # ── Collapse/drawer state ─────────────────────────────────────────
        self._pinned = True
        self._drawer_shown = False

        self._hover_timer = QTimer(self)
        self._hover_timer.setInterval(50)
        self._hover_timer.timeout.connect(self._check_hover)

        self._panel_anim = QPropertyAnimation(self._left_panel, b"pos", self)
        self._panel_anim.setDuration(_ANIM_MS)
        self._panel_anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

        self._content_splitter.show()
        self._left_panel.show()

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
        if not self._pinned:
            # In drawer mode the left panel floats as an overlay child of _central
            self._left_panel.resize(self._panel_w, h)
            if self._panel_anim.state() != QAbstractAnimation.State.Running:
                x = 0 if self._drawer_shown else -self._panel_w
                self._left_panel.move(x, 0)

    # ------------------------------------------------------------------
    # Collapse / drawer
    # ------------------------------------------------------------------

    def _toggle_pin(self) -> None:
        if self._pinned:
            # Record current width before removing from splitter
            self._panel_w = self._left_panel.width()
            self._pinned = False
            self._pin_button.setText("›")
            self._pin_button.setToolTip("Pin panel")
            # Re-parent to _central as a floating overlay
            self._left_panel.setParent(self._central)
            self._left_panel.resize(self._panel_w, self._central.height())
            self._left_panel.move(0, 0)
            self._left_panel.show()
            self._left_panel.raise_()
            self._hover_timer.start()
            self._slide_panel(show=False)
        else:
            self._panel_anim.stop()
            self._hover_timer.stop()
            self._pinned = True
            self._drawer_shown = False
            self._pin_button.setText("‹")
            self._pin_button.setToolTip("Collapse panel")
            # Re-insert into the outer splitter at position 0
            self._outer_splitter.insertWidget(0, self._left_panel)
            w = self._central.width()
            self._outer_splitter.setSizes([self._panel_w, max(0, w - self._panel_w)])

    def _slide_panel(self, show: bool) -> None:
        self._panel_anim.stop()
        self._drawer_shown = show
        end = QPoint(0, 0) if show else QPoint(-self._panel_w, 0)
        if self._left_panel.pos() == end:
            return
        self._panel_anim.setStartValue(self._left_panel.pos())
        self._panel_anim.setEndValue(end)
        self._panel_anim.start()

    def _check_hover(self) -> None:
        if self._pinned:
            return
        x = self._central.mapFromGlobal(QCursor.pos()).x()
        if not self._drawer_shown and x < _HOVER_PX:
            self._slide_panel(show=True)
        elif self._drawer_shown and x > self._panel_w + 20:
            self._slide_panel(show=False)

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

    def _on_file_dropped(self, path) -> None:
        if self._controller is None:
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
            self, "Load MDF File", "", _MDF_FILE_FILTER
        )
        if not path:
            return
        self._load_file(path)

    def _load_file(self, path: str | Path) -> None:
        """Load *path* via the controller, showing busy feedback meanwhile.

        Loading a large MDF file can take noticeable time; without this the
        application appears to freeze. Show a wait cursor and a persistent
        status message for the duration of the call.
        """
        if self._controller is None:
            return
        self.show_status(f"Loading {Path(path).name}…", timeout_ms=0)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        QApplication.processEvents()
        try:
            self._controller.load_file(path)
        except MdfLoadError as exc:
            QMessageBox.critical(self, "Load Error", str(exc))
        finally:
            QApplication.restoreOverrideCursor()
            self.statusBar().clearMessage()

    def _on_zoom_to_fit(self) -> None:
        if hasattr(self.plot_area, "zoom_to_fit"):
            self.plot_area.zoom_to_fit()

    def _on_zoom_y_to_view(self) -> None:
        if not self.plot_area.zoom_y_to_view():
            self.show_status("No active signals to zoom.")

    def _on_swimlanes(self) -> None:
        if self._controller is None:
            return
        if not self._controller.swimlanes():
            self.show_status("No active signals to arrange.")

    def _on_zoom_to_cursors(self) -> None:
        if self._cursor_ctrl is None:
            return
        span = self._cursor_ctrl.zoom_to_cursors()
        if span is not None:
            self.plot_area.zoom_to_x_range(*span)

    def _on_cursor_mode_changed(self, mode) -> None:
        from mdf_viewer.controller.cursor_controller import CursorMode
        self._zoom_cursors_action.setEnabled(mode == CursorMode.TWO)

    def _on_cursor_toggle(self) -> None:
        if self._cursor_ctrl is not None:
            self._cursor_ctrl.toggle()

    def _on_cursor1(self) -> None:
        if self._cursor_ctrl is not None:
            self._cursor_ctrl.press_cursor1()

    def _on_cursor2(self) -> None:
        if self._cursor_ctrl is not None:
            self._cursor_ctrl.press_cursor2()

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
        if dlg.exec() == LicenseDialog.DialogCode.Accepted:
            new_info = self._license_manager.load_stored()
            self.set_license(new_info, self._license_manager)

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
        self._load_file(path)
