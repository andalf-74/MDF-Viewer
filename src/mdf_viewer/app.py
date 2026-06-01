"""Application bootstrap: creates the QApplication and wires Model, View, Controller.

This module is the only place where the three MVC layers are assembled. Keeping
the wiring here means no layer needs to import the others' construction logic.
"""

from __future__ import annotations


def run(argv: list[str]) -> int:
    """Create the QApplication, build the MVC graph, and start the event loop.

    Returns the application's exit code.
    """
    from pathlib import Path

    from PyQt6.QtWidgets import QApplication, QMessageBox

    from mdf_viewer.controller.app_controller import AppController
    from mdf_viewer.controller.cursor_controller import CursorController
    from mdf_viewer.model.mdf_loader import MdfLoadError, MdfLoader
    from mdf_viewer.settings import Settings
    from mdf_viewer.view.cursors import CursorView
    from mdf_viewer.view.main_window import MainWindow

    app = QApplication(argv)

    window = MainWindow()
    settings = Settings()

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

    # Load a file passed on the command line (e.g. via .mf4 file association).
    if len(argv) > 1:
        path = Path(argv[1])
        if path.is_file():
            try:
                controller.load_file(path)
            except MdfLoadError as exc:
                QMessageBox.critical(window, "Load Error", str(exc))

    return app.exec()
