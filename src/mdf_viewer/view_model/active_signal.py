"""ActiveSignal — a signal that has been added to the plot.

The bridge between Model and View: it pairs the model data
(SignalData + SignalMetadata) with the view objects that render it (the
PyQtGraph curve, its dedicated ViewBox, and its color). Living in the
``view_model`` package keeps these UI references out of the pure-data model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from PyQt6.QtGui import QColor

from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata

if TYPE_CHECKING:
    import numpy as np

    from mdf_viewer.model.loaded_measurement import LoadedMeasurement


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
    ``view_box`` are filled in by PlotStripe.add_signal() once a rendering
    context exists.

    ``color`` accepts either a ``QColor`` or a plain ``(r, g, b)`` tuple;
    ``__post_init__`` normalises tuples to ``QColor`` so all consumers always
    see a ``QColor``.
    """

    data: SignalData
    metadata: SignalMetadata
    color: QColor | tuple[int, int, int]
    # The measurement this signal was added from (#101). A live reference,
    # not a copied offset — None outside multi-measurement contexts (e.g.
    # tests constructing an ActiveSignal directly), in which case
    # display_timestamps falls back to the signal's own raw timestamps.
    measurement: "LoadedMeasurement | None" = None
    step_mode: bool = False
    enum_display_table: bool = True    # cursor-value columns in the Active Signals Table
    enum_display_cursor: bool = False  # floating cursor label on the plot
    enum_display_yaxis: bool = False   # Y-axis tick labels
    display_mode: str = "line"    # "line" | "line_marker" | "marker"
    marker_shape: str = "circle"  # "circle" | "square" | "diamond" | "cross"
    line_width: int = 1           # 1–8
    line_style: str = "solid"     # "solid" | "dashes" | "dots" | "dash-dot"
    visible: bool = True          # #133 — curve/axis hidden while False, stays active/selectable
    curve: Any = field(default=None)     # pyqtgraph.PlotDataItem
    view_box: Any = field(default=None)  # pyqtgraph.ViewBox

    def __post_init__(self) -> None:
        if isinstance(self.color, tuple):
            self.color = QColor(*self.color)

    @property
    def display_timestamps(self) -> "np.ndarray":
        """Timestamps shifted by this signal's measurement offset (#101).

        Used everywhere a signal's X position is rendered or measured
        (curve data, zoom-to-fit range, visible-range masks) so that
        panning one measurement's axis row shifts its curves without
        touching the shared X-zoom. Falls back to the raw timestamps when
        no measurement is set (REQ-PLOT-304).
        """
        if self.measurement is None:
            return self.data.timestamps
        return self.data.timestamps + self.measurement.offset_s
