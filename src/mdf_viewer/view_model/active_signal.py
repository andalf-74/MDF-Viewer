"""ActiveSignal — a signal that has been added to the plot.

The bridge between Model and View: it pairs the model data
(SignalData + SignalMetadata) with the view objects that render it (the
PyQtGraph curve, its dedicated ViewBox, and its color). Living in the
``view_model`` package keeps these UI references out of the pure-data model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from PyQt6.QtGui import QColor

from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata


@dataclass
class ActiveSignal:
    # Mutable dataclass: auto-generated __eq__ and __hash__ compare all fields,
    # including numpy arrays whose boolean coercion raises ValueError.
    # Use identity semantics throughout — two ActiveSignal instances represent
    # distinct plot objects even if they wrap the same channel data.
    __eq__ = object.__eq__
    __hash__ = object.__hash__
    """Pairs model data with the plot objects that render a single signal.

    ``data`` and ``metadata`` are set at construction. ``curve`` and
    ``view_box`` are filled in by PlotArea.add_signal() once a rendering
    context exists.
    """

    data: SignalData
    metadata: SignalMetadata
    color: QColor
    step_mode: bool = False
    curve: Any = field(default=None)     # pyqtgraph.PlotDataItem
    view_box: Any = field(default=None)  # pyqtgraph.ViewBox
