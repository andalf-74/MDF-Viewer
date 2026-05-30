"""PlotArea — center-top plotting widget built on PyQtGraph.

A shared X-axis (time) is panned/zoomed across all signals simultaneously.
Each active signal gets its own ViewBox and right-side Y-axis, colored to match
the signal, allowing independent per-signal Y pan/zoom.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget


class PlotArea(QWidget):
    """PyQtGraph plot with a shared X-axis and one ViewBox/Y-axis per signal."""

    # To be implemented:
    #   pyqtgraph PlotWidget/GraphicsLayout with a shared bottom (time) axis
    #   add_signal(active_signal) -> new ViewBox + right Y axis, linked X
    #   remove_signal(active_signal)
    #   zoom_to_fit() -> full X range, auto Y per signal
    #   host the cursor items (see cursors.py)
