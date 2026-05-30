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

from PyQt6.QtWidgets import QMainWindow


class MainWindow(QMainWindow):
    """Assembles the menu bar, toolbar, and nested-splitter main layout."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("MDF-Viewer")
        self.resize(1280, 800)
        # To be implemented:
        #   _build_menu(), _build_toolbar(), _build_layout()
        #   left: SignalBrowser
        #   center splitter (vertical): PlotArea over a horizontal splitter of
        #     (MeasurementInfoBox | SignalInfoBox)
        #   right: ActiveSignalsTable
