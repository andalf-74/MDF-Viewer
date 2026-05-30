"""ActiveSignalsTable — right panel table of signals currently on the plot.

Columns: color swatch | name | cursor 1 value | cursor 2 value | delta.
Buttons: Remove Signal, Remove All. Selection here drives the Signal Info Box.
Cursor-value columns are shown only when a cursor is active.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget


class ActiveSignalsTable(QWidget):
    """Table of active signals with color, cursor values, and delta."""

    # To be implemented:
    #   QTableWidget/QTableView with the five columns
    #   color-swatch click -> color picker -> recolor curve + Y axis
    #   "Remove Signal" / "Remove All" buttons
    #   signals: remove_requested, remove_all_requested, selection_changed,
    #            color_change_requested
