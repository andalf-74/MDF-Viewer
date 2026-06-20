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

    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QFont, QPainter, QPixmap
    from PyQt6.QtWidgets import QApplication, QMessageBox, QSplashScreen

    from mdf_viewer import __version__
    from mdf_viewer.controller.app_controller import AppController
    from mdf_viewer.controller.cursor_controller import CursorController
    from mdf_viewer.errors import MdfLoadError
    from mdf_viewer.license.license_manager import LicenseManager
    from mdf_viewer.model.mdf_loader import MdfLoader
    from mdf_viewer.settings import Settings
    from mdf_viewer.view.cursors import CursorView
    from mdf_viewer.view.main_window import MainWindow

    if sys.platform == "win32":
        # Without an explicit AppUserModelID, Windows shows python.exe's icon
        # in the taskbar (instead of the window icon) when run unfrozen.
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "mdf-viewer.mdf-viewer"
        )

    def _build_splash_pixmap() -> QPixmap:
        icons_dir = Path(__file__).parent / "resources" / "icons"
        icon = QPixmap(str(icons_dir / "app_icon.ico")).scaled(
            96,
            96,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

        pixmap = QPixmap(360, 140)
        pixmap.fill(Qt.GlobalColor.white)

        painter = QPainter(pixmap)
        painter.drawPixmap(22, 22, icon)

        text_x = 22 + icon.width() + 20
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

    cursor_view = CursorView(window.plot_area.plot_item)
    cursor_ctrl = CursorController(
        cursor_view=cursor_view,
        get_x_range=lambda: tuple(window.plot_area.plot_item.vb.viewRange()[0]),
        active_signals_table=window.active_signals_table,
    )
    controller.set_cursor_controller(cursor_ctrl)

    window.set_controller(controller, cursor_ctrl)
    window.show()
    splash.finish(window)

    # Load a file passed on the command line (e.g. via .mf4 file association).
    if len(argv) > 1:
        path = Path(argv[1])
        if path.is_file():
            try:
                controller.load_file(path)
            except MdfLoadError as exc:
                QMessageBox.critical(window, "Load Error", str(exc))

    return app.exec()
