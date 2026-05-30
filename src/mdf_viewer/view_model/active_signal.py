"""ActiveSignal — a signal that has been added to the plot.

The bridge between Model and View: it pairs the model data
(SignalData + SignalMetadata) with the view objects that render it (the
PyQtGraph curve, its dedicated ViewBox, and its color). Living in the
``view_model`` package keeps these UI references out of the pure-data model.
"""

from __future__ import annotations


class ActiveSignal:
    """Pairs model data with the plot objects that render a single signal.

    Holds (to be implemented):
      * data: SignalData
      * metadata: SignalMetadata
      * curve: pyqtgraph.PlotDataItem
      * view_box: pyqtgraph.ViewBox  (per-signal Y axis)
      * color: QColor
    """
