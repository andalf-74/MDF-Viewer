"""AppController — central coordinator between Model and View.

Owns application state that is not specific to a single widget:
  * the loaded MeasurementInfo and channel hierarchy
  * the list of ActiveSignal objects currently on the plot
  * the current selection in the Active Signals Table

It calls into the model (MdfLoader) to load data and tells the view what to
display, without either layer importing the other.
"""

from __future__ import annotations


class AppController:
    """Coordinates loading, active-signal management, and selection state."""

    # To be implemented:
    #   load_file(path) -> uses MdfLoader, populates the Signal Browser
    #   add_signal(group_index, channel_index) -> creates an ActiveSignal
    #   remove_signal(active_signal) / remove_all()
    #   set_selected_signal(active_signal) -> drives the Signal Info Box
