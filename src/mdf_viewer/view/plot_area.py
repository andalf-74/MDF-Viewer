"""PlotArea — center-top plotting widget built on PyQtGraph.

A shared X-axis (time) is panned/zoomed across all signals simultaneously.
Each active signal gets its own ViewBox and right-side Y-axis, colored to match
the signal, allowing independent per-signal Y pan/zoom.

Architecture note: the main PlotItem ViewBox (pi.vb) is used only as the X-axis
host — no curves are placed in it. Every signal gets its own ViewBox whose X is
linked to pi.vb, so panning or zooming X anywhere propagates to all signals.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import pyqtgraph as pg
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from mdf_viewer.view_model.active_signal import ActiveSignal

if TYPE_CHECKING:
    pass


class _SignalAxisItem(pg.AxisItem):
    """AxisItem that formats tick labels to 6 significant figures.

    PyQtGraph's default tickStrings can produce floating-point noise
    (e.g. "256.000000007"). :.6g strips trailing zeros and limits
    precision to 6 significant figures.
    """

    def tickStrings(self, values, scale, spacing):
        return [f"{v * scale:.6g}" for v in values]


@dataclass
class _SignalPlotData:
    """Internal per-signal rendering objects."""
    curve: object   # pg.PlotDataItem
    view_box: object  # pg.ViewBox
    axis: object    # pg.AxisItem


class PlotArea(QWidget):
    """PyQtGraph plot with a shared X-axis and one ViewBox/Y-axis per signal."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._pw = pg.PlotWidget()
        self._pi: pg.PlotItem = self._pw.getPlotItem()

        # Hide default axes; each signal provides its own right-side axis.
        self._pi.hideAxis('left')
        self._pi.hideAxis('right')
        self._pi.showGrid(x=True, y=False)
        self._pi.setLabel('bottom', 'Time', units='s')

        # Maps ActiveSignal → its rendering objects (identity-based, see __hash__).
        self._data: dict[ActiveSignal, _SignalPlotData] = {}

        self._pi.vb.sigResized.connect(self._update_view_geometries)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._pw)

    # ------------------------------------------------------------------
    # Public API (called by AppController)
    # ------------------------------------------------------------------

    def add_signal(self, active: ActiveSignal) -> None:
        """Add a signal curve with its own ViewBox and right Y-axis.

        Sets active.curve and active.view_box so callers can inspect them.
        No-op if the signal is already displayed.
        """
        if active in self._data:
            return

        color = active.color
        pen = pg.mkPen(color=color, width=2)

        vb = pg.ViewBox()
        self._pi.scene().addItem(vb)
        vb.setXLink(self._pi)

        # Place a new right axis in the next available layout column.
        col = self._pi.layout.columnCount()
        axis = _SignalAxisItem(
            'right',
            linkView=vb,
            pen=pg.mkPen(color=color),
            textPen=pg.mkPen(color=color),
        )
        self._pi.layout.addItem(axis, 2, col)

        curve = pg.PlotDataItem(
            active.data.timestamps,
            active.data.samples,
            pen=pen,
        )
        vb.addItem(curve)

        active.curve = curve
        active.view_box = vb
        self._data[active] = _SignalPlotData(curve=curve, view_box=vb, axis=axis)

        self._update_view_geometries()
        vb.enableAutoRange()

    def remove_signal(self, active: ActiveSignal) -> None:
        """Remove a signal's curve, ViewBox, and axis. No-op if not present."""
        if active not in self._data:
            return
        spd = self._data.pop(active)
        spd.view_box.removeItem(spd.curve)
        self._pi.layout.removeItem(spd.axis)
        self._pi.scene().removeItem(spd.view_box)
        active.curve = None
        active.view_box = None
        self._update_view_geometries()

    def recolor_signal(self, active: ActiveSignal, color) -> None:
        """Update curve pen, Y-axis pen, and active.color. No-op if not present."""
        if active not in self._data:
            return
        spd = self._data[active]
        pen = pg.mkPen(color=color, width=2)
        spd.curve.setPen(pen)
        spd.axis.setPen(pg.mkPen(color=color))
        spd.axis.setTextPen(pg.mkPen(color=color))
        active.color = color

    def zoom_to_fit(self) -> None:
        """Reset viewport: full X range across all signals, auto Y per signal."""
        if not self._data:
            return

        # Compute full X range from all active signal timestamps.
        t_min = min(float(a.data.timestamps[0]) for a in self._data if len(a.data.timestamps))
        t_max = max(float(a.data.timestamps[-1]) for a in self._data if len(a.data.timestamps))
        self._pi.vb.setXRange(t_min, t_max, padding=0.02)

        # Auto-range Y independently per signal.
        for spd in self._data.values():
            spd.view_box.autoRange()

    @property
    def plot_item(self) -> pg.PlotItem:
        return self._pi

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _update_view_geometries(self) -> None:
        """Keep extra ViewBoxes aligned with the main ViewBox after resize."""
        rect = self._pi.vb.sceneBoundingRect()
        for spd in self._data.values():
            spd.view_box.setGeometry(rect)
            spd.view_box.linkedViewChanged(self._pi.vb, spd.view_box.XAxis)
