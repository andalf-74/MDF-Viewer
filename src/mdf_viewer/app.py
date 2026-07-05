"""Application bootstrap: creates the QApplication and wires Model, View, Controller.

This module is the only place where the three MVC layers are assembled. Keeping
the wiring here means no layer needs to import the others' construction logic.
"""

from __future__ import annotations


def run(argv: list[str]) -> int:
    """Create the QApplication, build the MVC graph, and start the event loop.

    Returns the application's exit code.
    """
    import sys
    from pathlib import Path

    from PyQt6.QtCore import QSize, Qt
    from PyQt6.QtGui import QFont, QIcon, QPainter, QPixmap
    from PyQt6.QtWidgets import QApplication, QMessageBox, QSplashScreen

    from mdf_viewer import __version__
    from mdf_viewer.controller.app_controller import AppController
    from mdf_viewer.controller.cursor_controller import CursorController
    from mdf_viewer.controller.zoom_controller import ZoomController
    from mdf_viewer.errors import MdfLoadError
    from mdf_viewer.license.license_manager import LicenseManager
    from mdf_viewer.model.mdf_loader import MdfLoader
    from mdf_viewer.settings import Settings
    from mdf_viewer.view.cursors import CursorStripesView
    from mdf_viewer.view.main_window import MainWindow

    if sys.platform == "win32":
        # Without an explicit AppUserModelID, Windows shows python.exe's icon
        # in the taskbar (instead of the window icon) when run unfrozen.
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "mdf-viewer.mdf-viewer"
        )

    def _build_splash_pixmap() -> QPixmap:
        # QPixmap(path) on a multi-resolution .ico picks the *smallest* embedded
        # frame (16x16 here) with no way to request a bigger one; scaling that up
        # to 96x96 is what made the splash icon blurry (#85). QIcon lets us ask
        # for the icon at its largest embedded size (256x256) and downscale from
        # there instead. The whole pixmap is also built at the screen's actual
        # device pixel ratio so it renders crisply on HiDPI displays too.
        icons_dir = Path(__file__).parent / "resources" / "icons"
        dpr = QApplication.primaryScreen().devicePixelRatio()

        icon_logical = 96
        icon_physical = round(icon_logical * dpr)
        icon = (
            QIcon(str(icons_dir / "app_icon.ico"))
            .pixmap(QSize(256, 256))
            .scaled(
                icon_physical,
                icon_physical,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
        )
        icon.setDevicePixelRatio(dpr)

        logical_w, logical_h = 360, 140
        pixmap = QPixmap(round(logical_w * dpr), round(logical_h * dpr))
        pixmap.setDevicePixelRatio(dpr)
        pixmap.fill(Qt.GlobalColor.white)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(22, 22, icon)

        text_x = 22 + round(icon.width() / dpr) + 20
        painter.setFont(QFont(painter.font().family(), 16, QFont.Weight.Bold))
        painter.drawText(text_x, 60, "MDF-Viewer")
        painter.setFont(QFont(painter.font().family(), 10))
        painter.drawText(text_x, 82, f"Version {__version__}")
        painter.end()

        return pixmap

    app = QApplication(argv)

    splash = QSplashScreen(_build_splash_pixmap())
    splash.show()
    app.processEvents()

    window = MainWindow()
    settings = Settings()

    license_manager = LicenseManager()
    license_info = license_manager.load_stored()
    window.set_license(license_info, license_manager)

    loader = MdfLoader()
    controller = AppController(
        loader=loader,
        signal_browser=window.signal_browser,
        plot_area=window.plot_area,
        active_signals_table=window.active_signals_table,
        measurement_info_box=window.measurement_info_box,
        signal_info_box=window.signal_info_box,
        settings=settings,
    )
    window.set_recent_files_provider(settings.get_and_prune)

    cursor_view = CursorStripesView()
    for stripe in window.plot_area.get_stripes():
        cursor_view.add_stripe(stripe)
    window.plot_area.stripe_created.connect(cursor_view.add_stripe)
    window.plot_area.stripe_deleted.connect(cursor_view.remove_stripe)
    cursor_ctrl = CursorController(
        cursor_view=cursor_view,
        get_x_range=lambda: tuple(window.plot_area.plot_item.vb.viewRange()[0]),
        active_signals_table=window.active_signals_table,
        get_active_signals=lambda: controller.active_signals,
        get_cursor_persistent=lambda: settings.cursor_persistent,
        get_cursor_mode=lambda: settings.cursor_mode,
        get_cursor_colors=lambda: (
            settings.cursor_color_c1,
            settings.cursor_color_c2,
            settings.cursor_color_cl,
            settings.cursor_color_cr,
        ),
        get_y_range=lambda: tuple(window.plot_area.get_active_stripe().plot_item.vb.viewRange()[1]),
        get_show_delta_time=lambda: settings.show_delta_time_in_plot,
        get_delta_time_color=lambda: settings.delta_time_color,
        get_selected_signal=lambda: controller.selected_signal,
        get_cursor_step_unit=lambda: settings.cursor_step_unit,
        get_cursor_step_samples=lambda: settings.cursor_step_samples,
        get_cursor_step_pixels=lambda: settings.cursor_step_pixels,
        get_cursor_step_time_ms=lambda: settings.cursor_step_time_ms,
        get_x_per_pixel=lambda: window.plot_area.get_active_stripe().plot_item.vb.viewPixelSize()[0],
        get_active_stripe=lambda: window.plot_area.get_active_stripe(),
    )
    controller.set_cursor_controller(cursor_ctrl)
    # Order matters: the view's own active-stripe bookkeeping must update
    # before CursorController re-triggers update_delta_time() off of it.
    window.plot_area.active_stripe_changed.connect(cursor_view.set_active_stripe)
    window.plot_area.active_stripe_changed.connect(cursor_ctrl.on_active_stripe_changed)

    zoom_ctrl = ZoomController(
        plot_area=window.plot_area,
        get_active_signals=lambda: controller.active_signals,
        get_max_steps=lambda: settings.max_undo_steps,
    )
    controller.set_zoom_controller(zoom_ctrl)

    window.set_settings(settings)
    window.set_controller(controller)

    # Apply the persisted display-name-shortening setting — set_settings()/
    # set_controller() only store references, they don't sync it in (#89).
    controller.refresh_display_names()
    window.active_signals_table.set_shorten_names_enabled(settings.display_name_rule_enabled)
    window.set_zoom_all_stripes(settings.zoom_scope == "all_stripes")

    window.show()
    splash.finish(window)

    if settings.check_for_updates:
        window.trigger_startup_update_check()

    # Load a file passed on the command line (e.g. via file association).
    if len(argv) > 1:
        path = Path(argv[1])
        if path.is_file():
            if path.suffix.lower() == ".mvc":
                window.open_config(path)
            else:
                try:
                    controller.load_file(path)
                except MdfLoadError as exc:
                    QMessageBox.critical(window, "Load Error", str(exc))

    return app.exec()
