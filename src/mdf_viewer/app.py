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

    app = QApplication(argv)

    # Wiring is added as the layers are implemented:
    #   controller = AppController()
    #   window = MainWindow(controller)
    #   window.show()
    from mdf_viewer.view.main_window import MainWindow

    window = MainWindow()
    window.show()

    return app.exec()
