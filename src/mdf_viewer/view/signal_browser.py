"""SignalBrowser — left panel TreeView of the full MDF channel hierarchy.

Emits a request when the user wants to add a signal (double-click a node, or
select + "Add Signal"). Holds no model data itself; it is populated by the
controller and reports user intent back out.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget


class SignalBrowser(QWidget):
    """Channel-group / channel hierarchy tree with an Add Signal button."""

    # To be implemented:
    #   QTreeView + model populated from the channel hierarchy
    #   "Add Signal" button below the tree
    #   signal: add_signal_requested(group_index, channel_index)
