"""Cursors — draggable vertical cursor lines and their value labels.

Rendered inside the PlotArea. The value label is shown only on the cursor
nearest the mouse pointer, positioned close to its intersection with a curve.
Visual concern only; the toggle cycle and position memory live in the
controller's CursorController.
"""

from __future__ import annotations


class CursorView:
    """Manages the draggable cursor InfiniteLines and their value labels."""

    # To be implemented:
    #   one/two pyqtgraph.InfiniteLine items, draggable on X
    #   value label near the curve intersection of the nearest cursor
    #   emits position changes for the controller to consume
