"""Application bootstrap: creates the QApplication and wires Model, View, Controller.

This module is the only place where the three MVC layers are assembled. Keeping
the wiring here means no layer needs to import the others' construction logic.
"""

from __future__ import annotations


def run(argv: list[str]) -> int:
    """Create the QApplication, build the MVC graph, and start the event loop.

    Returns the application's exit code.
    """
    from PyQt6.QtWidgets import QApplication

    from mdf_viewer.controller.app_controller import AppController
    from mdf_viewer.model.mdf_loader import MdfLoader
    from mdf_viewer.view.main_window import MainWindow

    app = QApplication(argv)

    window = MainWindow()

    loader = MdfLoader()
    controller = AppController(
        loader=loader,
        signal_browser=window.signal_browser,
        plot_area=window.plot_area,
        active_signals_table=window.active_signals_table,
        measurement_info_box=window.measurement_info_box,
        signal_info_box=window.signal_info_box,
    )
    window.set_controller(controller)

    window.show()
    return app.exec()
