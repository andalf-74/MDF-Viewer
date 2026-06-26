"""PlotArea — center-top plotting widget built on PyQtGraph.

A shared X-axis (time) is panned/zoomed across all signals simultaneously.
Each active signal gets its own ViewBox and right-side Y-axis, colored to match
the signal, allowing independent per-signal Y pan/zoom.

Architecture note: the main PlotItem ViewBox (pi.vb) is used only as the X-axis
host — no curves are placed in it. Every signal gets its own ViewBox whose X is
linked to pi.vb, so panning or zooming X anywhere propagates to all signals.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pyqtgraph as pg
from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QPen
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from mdf_viewer.view._mime import SIGNAL_MIME_TYPE
from mdf_viewer.view_model.active_signal import ActiveSignal
from mdf_viewer.view_model.zoom_state import ZoomState

if TYPE_CHECKING:
    pass

_MDF_SUFFIXES = {'.mf4', '.mdf', '.dat'}

_PG_SYMBOL: dict[str, str] = {
    "circle": "o",
    "square": "s",
    "diamond": "d",
    "cross": "+",
}

_QT_PEN_STYLE: dict[str, Qt.PenStyle] = {
    "solid":    Qt.PenStyle.SolidLine,
    "dashes":   Qt.PenStyle.DashLine,
    "dots":     Qt.PenStyle.DotLine,
    "dash-dot": Qt.PenStyle.DashDotLine,
}


_SELECTION_Z = 10   # Z-value base for selected signals; unselected signals stay at 0


def _symbol_size(line_width: int) -> int:
    return max(6, line_width * 4)


def _make_pen(color, width: int, style: str) -> QPen:
    pen = pg.mkPen(color=color, width=width)
    pen.setStyle(_QT_PEN_STYLE.get(style, Qt.PenStyle.SolidLine))
    return pen


class _ViewBox(pg.ViewBox):
    """ViewBox with fixed mouse behaviour for MDF-Viewer.

    Left drag: pan. Right drag: rectangle zoom. Wheel: X-axis zoom only,
    except when the mouse is over a Y-axis (axis=1), which zooms Y.
    The 'Mouse Mode' context-menu item is removed since the mode is fixed.
    """

    # Emitted with the scene-space QRectF when a right-drag zoom rect finishes.
    zoom_rect_finished = pyqtSignal(object)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMouseMode(pg.ViewBox.PanMode)

    def getMenu(self, ev=None):
        menu = super().getMenu(ev)
        if menu is not None:
            for action in menu.actions():
                if 'mouse' in action.text().lower():
                    menu.removeAction(action)
                    break
        return menu

    def mouseDragEvent(self, ev, axis=None):
        if ev.button() == Qt.MouseButton.RightButton and axis is None:
            if ev.isFinish():
                self.rbScaleBox.hide()
                local_rect = QRectF(pg.Point(ev.buttonDownPos()), pg.Point(ev.pos()))
                data_rect = self.childGroup.mapRectFromParent(local_rect)
                self.showAxRect(data_rect)
                self.axHistoryPointer += 1
                self.axHistory = self.axHistory[:self.axHistoryPointer] + [data_rect]
                # Emit scene-space rect so other ViewBoxes can map it correctly.
                scene_rect = QRectF(
                    self.mapToScene(QPointF(ev.buttonDownPos())),
                    self.mapToScene(QPointF(ev.pos())),
                )
                self.zoom_rect_finished.emit(scene_rect)
            else:
                self.updateScaleBox(ev.buttonDownPos(), ev.pos())
            ev.accept()
        else:
            super().mouseDragEvent(ev, axis=axis)

    def wheelEvent(self, ev, axis=None):
        # axis=1 means the wheel is over a linked Y-axis — let it zoom Y.
        # All other cases (interior, X-axis, None) zoom X only.
        super().wheelEvent(ev, axis=1 if axis == 1 else 0)


class _SignalAxisItem(pg.AxisItem):
    """AxisItem with improved tick formatting.

    For float signals: labels use :.6g (6 significant figures, no trailing
    zeros — eliminates floating-point noise like "256.000000007").

    For integer signals (discrete values such as gear, enum, flag):
    - tickValues snaps all ticks to integer positions, suppressing
      fractional ticks like 7.5 on a gear axis.
    - tickStrings formats values as plain integers ("7" not "7.0").
    """

    def __init__(self, *args, integer_ticks: bool = False, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._integer_ticks = integer_ticks

    def tickValues(self, minVal, maxVal, size):
        ticks = super().tickValues(minVal, maxVal, size)
        if not self._integer_ticks:
            return ticks
        # Snap every proposed tick to the nearest integer and deduplicate.
        seen: set[int] = set()
        result = []
        for spacing, values in ticks:
            int_vals = []
            for v in values:
                iv = int(round(v))
                if iv not in seen and minVal - 0.5 <= iv <= maxVal + 0.5:
                    seen.add(iv)
                    int_vals.append(float(iv))
            if int_vals:
                result.append((max(spacing, 1.0), int_vals))
        return result

    def tickStrings(self, values, scale, spacing):
        if self._integer_ticks:
            return [str(int(round(v * scale))) for v in values]
        return [f"{v * scale:.6g}" for v in values]


@dataclass
class _SignalPlotData:
    """Internal per-signal rendering objects."""
    curve: object   # pg.PlotDataItem
    view_box: object  # pg.ViewBox
    axis: object    # pg.AxisItem


class PlotArea(QWidget):
    """PyQtGraph plot with a shared X-axis and one ViewBox/Y-axis per signal."""

    # Emitted when the user toggles the Y-grid checkbox in the plot context menu.
    y_grid_toggled = pyqtSignal(bool)
    # Emitted when an MDF file is dropped onto the plot.
    file_dropped = pyqtSignal(object)  # Path
    # Emitted when signals are dragged from the Signal Browser and dropped.
    signals_dropped = pyqtSignal(list)  # list of (group_index, channel_index)
    # Emitted whenever the X or any signal Y range changes (for zoom undo/redo).
    range_changed = pyqtSignal()
    # Emitted on a left-click in the plot: the topmost hit ActiveSignal, or None on a miss.
    signal_clicked = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._pw = pg.PlotWidget(viewBox=_ViewBox())
        self._pi: pg.PlotItem = self._pw.getPlotItem()

        # Hide default axes; each signal provides its own right-side axis.
        self._pi.hideAxis('left')
        self._pi.hideAxis('right')
        self._pi.showGrid(x=True, y=False)
        self._pi.setLabel('bottom', 'Time', units='s')

        # Maps ActiveSignal → its rendering objects (identity-based, see __hash__).
        self._data: dict[ActiveSignal, _SignalPlotData] = {}
        # Signals currently highlighted (selection boost); ordered earliest→latest.
        self._selected_signals: list[ActiveSignal] = []
        self._selected_line_boost: int = 1

        self._pi.vb.sigResized.connect(self._update_view_geometries)
        self._pi.ctrl.yGridCheck.toggled.connect(self._on_y_grid_toggled)
        self._pi.vb.zoom_rect_finished.connect(self._on_zoom_rect_finished)
        self._pi.vb.sigRangeChanged.connect(self._on_vb_range_changed)

        self._pw.viewport().setAcceptDrops(True)
        self._pw.viewport().installEventFilter(self)

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
        line_width = active.line_width
        pen = _make_pen(color, line_width, active.line_style) if active.display_mode != "marker" else None

        vb = _ViewBox()
        self._pi.scene().addItem(vb)
        vb.setXLink(self._pi)
        vb.zoom_rect_finished.connect(self._on_zoom_rect_finished)

        # Place a new right axis in the next available layout column.
        col = self._pi.layout.columnCount()
        integer_ticks = active.metadata.is_integer
        axis = _SignalAxisItem(
            'right',
            linkView=vb,
            pen=pg.mkPen(color=color),
            textPen=pg.mkPen(color=color),
            integer_ticks=integer_ticks,
        )
        self._pi.layout.addItem(axis, 2, col)

        if active.display_mode != "line":
            sym = _PG_SYMBOL.get(active.marker_shape, "o")
            sym_size = _symbol_size(line_width)
            sym_pen = pg.mkPen(color=color)
            sym_brush = pg.mkBrush(color=color)
        else:
            sym = sym_pen = sym_brush = None
            sym_size = 0

        curve = pg.PlotDataItem(
            pen=pen,
            stepMode="left" if active.step_mode else False,
            symbol=sym,
            symbolPen=sym_pen,
            symbolBrush=sym_brush,
            symbolSize=sym_size,
        )
        curve.setClipToView(True)
        curve.setDownsampling(auto=True, method="peak")
        vb.addItem(curve)
        curve.setData(active.data.timestamps, active.data.samples)

        active.curve = curve
        active.view_box = vb
        self._data[active] = _SignalPlotData(curve=curve, view_box=vb, axis=axis)

        self._update_view_geometries()
        vb.enableAutoRange()
        # Connect after enableAutoRange so the initial auto-range isn't captured
        # as a zoom undo step.
        vb.sigRangeChanged.connect(self._on_vb_range_changed)

    def remove_signal(self, active: ActiveSignal) -> None:
        """Remove a signal's curve, ViewBox, and axis. No-op if not present."""
        if active not in self._data:
            return
        spd = self._data.pop(active)
        spd.view_box.zoom_rect_finished.disconnect(self._on_zoom_rect_finished)
        spd.view_box.sigRangeChanged.disconnect(self._on_vb_range_changed)
        spd.view_box.removeItem(spd.curve)
        self._pi.layout.removeItem(spd.axis)
        spd.axis.hide()
        self._pi.scene().removeItem(spd.view_box)
        active.curve = None
        active.view_box = None
        self._update_view_geometries()

    def set_selected_signals(
        self,
        selected: list[ActiveSignal],
        all_signals: list[ActiveSignal] | None = None,
        top_first: bool = True,
    ) -> None:
        """Update pen boost and Z-order for all signals.

        *selected* — signals to highlight (+1px, raised above unselected).
        *all_signals* — full ordered signal list (table order, index 0 = top row).
            When provided, every signal gets a base Z from its position; omit to
            leave unselected signals at Z=0 (backward-compatible).
        *top_first* — when True the top row has the highest base Z-value.
        """
        self._selected_signals = list(selected)
        selected_set = set(selected)
        n = len(all_signals) if all_signals else 0

        for active, spd in self._data.items():
            # Base Z from table position
            if all_signals is not None and active in all_signals:
                pos = all_signals.index(active)
                base_z = (n - pos) if top_first else (pos + 1)
            else:
                base_z = 0

            if active in selected_set:
                idx = selected.index(active)
                spd.view_box.setZValue(n + _SELECTION_Z + idx)
            else:
                spd.view_box.setZValue(base_z)

            if active.display_mode != "marker":
                spd.curve.setPen(_make_pen(active.color, self._effective_width(active), active.line_style))

    def recolor_signal(self, active: ActiveSignal, color) -> None:
        """Update curve pen, Y-axis pen, and active.color. No-op if not present."""
        if active not in self._data:
            return
        spd = self._data[active]
        pen = _make_pen(color, self._effective_width(active), active.line_style) if active.display_mode != "marker" else None
        spd.curve.setPen(pen)
        if active.display_mode != "line":
            spd.curve.setSymbolPen(pg.mkPen(color=color))
            spd.curve.setSymbolBrush(pg.mkBrush(color=color))
        spd.axis.setPen(pg.mkPen(color=color))
        spd.axis.setTextPen(pg.mkPen(color=color))
        active.color = color
        spd.view_box.update()

    def set_display_mode(self, active: ActiveSignal, mode: str, shape: str) -> None:
        """Switch a signal between line / line+marker / marker rendering. No-op if not present."""
        if active not in self._data:
            return
        spd = self._data[active]
        color = active.color
        eff_width = self._effective_width(active)
        pen = _make_pen(color, eff_width, active.line_style) if mode != "marker" else None
        if mode == "line":
            symbol = sym_pen = sym_brush = None
            sym_size = 0
        else:
            symbol = _PG_SYMBOL.get(shape, "o")
            sym_size = _symbol_size(eff_width)
            sym_pen = pg.mkPen(color=color)
            sym_brush = pg.mkBrush(color=color)
        spd.curve.setPen(pen)
        spd.curve.setSymbol(symbol)
        spd.curve.setSymbolPen(sym_pen)
        spd.curve.setSymbolBrush(sym_brush)
        spd.curve.setSymbolSize(sym_size)

    def set_line_width(self, active: ActiveSignal, width: int) -> None:
        """Update the curve line width. No-op if not present."""
        if active not in self._data:
            return
        active.line_width = width
        spd = self._data[active]
        if active.display_mode != "marker":
            spd.curve.setPen(_make_pen(active.color, self._effective_width(active), active.line_style))
        if active.display_mode != "line":
            spd.curve.setSymbolSize(_symbol_size(self._effective_width(active)))

    def set_line_style(self, active: ActiveSignal, style: str) -> None:
        """Update the curve line style. No-op if not present or in marker-only mode."""
        if active not in self._data:
            return
        active.line_style = style
        if active.display_mode != "marker":
            self._data[active].curve.setPen(_make_pen(active.color, self._effective_width(active), style))

    def set_selected_line_boost(self, value: int) -> None:
        """Set the line-width boost applied to selected signals."""
        self._selected_line_boost = value

    def _effective_width(self, active: ActiveSignal) -> int:
        """Return line_width + boost if the signal is currently selected, else line_width."""
        return active.line_width + (self._selected_line_boost if active in self._selected_signals else 0)

    def set_y_grid(self, active: ActiveSignal, enabled: bool) -> None:
        """Enable or disable the Y-grid on a signal's axis. No-op if not present."""
        if active not in self._data:
            return
        self._data[active].axis.setGrid(160 if enabled else False)

    def set_step_mode(self, active: ActiveSignal, enabled: bool) -> None:
        """Switch a signal curve between step and linear rendering. No-op if not present."""
        if active not in self._data:
            return
        spd = self._data[active]
        spd.curve.opts["stepMode"] = "left" if enabled else False
        spd.curve.setData(active.data.timestamps, active.data.samples)

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

    def zoom_to_x_range(self, x_min: float, x_max: float) -> None:
        """Set the shared X range to [x_min, x_max] with standard padding."""
        self._pi.vb.setXRange(x_min, x_max, padding=0.02)

    def swimlanes(self, ordered_signals: list) -> bool:
        """Arrange signals in equal horizontal lanes by adjusting each Y range.

        Each signal's Y-axis is panned and zoomed so the signal occupies its
        1/N horizontal band, top-to-bottom matching *ordered_signals*.  Only
        setYRange is used — ViewBox geometries are unchanged — so the result
        participates in the normal Y-axis view history and is reversible.

        Returns True if applied, False if there are no active signals.
        """
        if not self._data or not ordered_signals:
            return False

        n = len(ordered_signals)
        x_min, x_max = self._pi.vb.viewRange()[0]

        for i, active in enumerate(ordered_signals):
            if active not in self._data:
                continue
            spd = self._data[active]

            ts = active.data.timestamps
            ys = active.data.samples
            mask = (ts >= x_min) & (ts <= x_max)
            visible_ys = ys[mask]

            if len(visible_ys) == 0:
                y_min = float(ys.min()) if len(ys) else -1.0
                y_max = float(ys.max()) if len(ys) else 1.0
            else:
                y_min = float(visible_ys.min())
                y_max = float(visible_ys.max())

            data_span = y_max - y_min
            if data_span == 0:
                data_span = 2.0
                y_min -= 1.0
                y_max += 1.0

            # Add 5 % padding within each lane, then compute the ViewBox Y range
            # that maps this signal's padded data band to lane i (i=0 → top).
            # In PyQtGraph Y increases upward, so band 0 (top screen) = high Y.
            pad = 0.05 * data_span
            adj_min = y_min - pad
            adj_span = data_span + 2 * pad   # padded lane height in data units

            vb_y_min = adj_min - (n - 1 - i) * adj_span
            vb_y_max = adj_min + (i + 1) * adj_span

            spd.view_box.setYRange(vb_y_min, vb_y_max, padding=0)
        return True

    def zoom_y_to_view(self) -> bool:
        """Rescale each signal's Y-axis to fit the currently visible X range.

        Returns True if any signals are active, False if there is nothing to zoom.
        """
        if not self._data:
            return False
        x_min, x_max = self._pi.vb.viewRange()[0]
        for active, spd in self._data.items():
            ts = active.data.timestamps
            ys = active.data.samples
            mask = (ts >= x_min) & (ts <= x_max)
            visible_ys = ys[mask]
            if len(visible_ys) == 0:
                continue
            y_min = float(visible_ys.min())
            y_max = float(visible_ys.max())
            if y_min == y_max:
                y_min -= 1.0
                y_max += 1.0
            spd.view_box.setYRange(y_min, y_max, padding=0.05)
        return True

    def get_zoom_state(self, active_signals: list) -> ZoomState:
        """Snapshot the current X range and each active signal's Y range."""
        x_range = tuple(self._pi.vb.viewRange()[0])
        y_ranges = {
            active: tuple(active.view_box.viewRange()[1])
            for active in active_signals
            if active.view_box is not None
        }
        return ZoomState(x_range=x_range, y_ranges=y_ranges)

    def set_zoom_state(self, state: ZoomState, active_signals: list) -> None:
        """Restore X and Y ranges from a previously captured ZoomState.

        Signals present in active_signals but absent from state.y_ranges (added
        after the snapshot) keep their current Y range.  Signals that were in
        the snapshot but have since been removed are silently skipped.
        """
        self._pi.vb.setXRange(*state.x_range, padding=0)
        for active in active_signals:
            if active in state.y_ranges and active.view_box is not None:
                active.view_box.setYRange(*state.y_ranges[active], padding=0)

    @property
    def plot_item(self) -> pg.PlotItem:
        return self._pi

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _hit_test(self, viewport_pos: QPointF) -> "ActiveSignal | None":
        """Return the topmost ActiveSignal whose curve/markers contain viewport_pos, or None."""
        scene_pos = self._pw.mapToScene(viewport_pos.toPoint())
        ordered = sorted(self._data.items(), key=lambda kv: kv[1].view_box.zValue(), reverse=True)
        for active, spd in ordered:
            if active.display_mode != "marker":
                data_pos = spd.view_box.mapSceneToView(scene_pos)
                if spd.curve.curve.mouseShape().contains(data_pos):
                    return active
            if active.display_mode != "line":
                local_pos = spd.curve.scatter.mapFromScene(scene_pos)
                if spd.curve.scatter.pointsAt(local_pos):
                    return active
        return None

    def eventFilter(self, watched, event):
        if watched is self._pw.viewport():
            t = event.type()
            if t == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                hit = self._hit_test(QPointF(event.pos()))
                self.signal_clicked.emit(hit)
                return hit is not None  # True (consume) on hit, False (pass through) on miss
            if t == QEvent.Type.DragEnter:
                if self._accepts_drag(event.mimeData()):
                    event.acceptProposedAction()
                else:
                    event.ignore()
                return True
            elif t == QEvent.Type.DragMove:
                if self._accepts_drag(event.mimeData()):
                    event.acceptProposedAction()
                else:
                    event.ignore()
                return True
            elif t == QEvent.Type.Drop:
                self._on_drop(event)
                return True
        return super().eventFilter(watched, event)

    def _accepts_drag(self, mime_data) -> bool:
        if mime_data.hasFormat(SIGNAL_MIME_TYPE):
            return True
        if mime_data.hasUrls():
            return any(
                u.isLocalFile()
                and Path(u.toLocalFile()).suffix.lower() in _MDF_SUFFIXES
                for u in mime_data.urls()
            )
        return False

    def _on_drop(self, event) -> None:
        mime = event.mimeData()
        if mime.hasFormat(SIGNAL_MIME_TYPE):
            data = bytes(mime.data(SIGNAL_MIME_TYPE))
            locs = [tuple(item) for item in json.loads(data)]
            self.signals_dropped.emit(locs)
            event.acceptProposedAction()
        elif mime.hasUrls():
            for url in mime.urls():
                if url.isLocalFile():
                    path = Path(url.toLocalFile())
                    if path.suffix.lower() in _MDF_SUFFIXES:
                        self.file_dropped.emit(path)
                        event.acceptProposedAction()
                        return
            event.ignore()
        else:
            event.ignore()

    def _on_vb_range_changed(self, *_) -> None:
        self.range_changed.emit()

    def _on_zoom_rect_finished(self, scene_rect: QRectF) -> None:
        """Apply zoom rect Y extent to every signal ViewBox and update their undo history."""
        for spd in self._data.values():
            mapped = spd.view_box.childGroup.mapRectFromScene(scene_rect)
            y_min = min(mapped.top(), mapped.bottom())
            y_max = max(mapped.top(), mapped.bottom())
            spd.view_box.setYRange(y_min, y_max, padding=0)
            spd.view_box.axHistoryPointer += 1
            spd.view_box.axHistory = (
                spd.view_box.axHistory[:spd.view_box.axHistoryPointer] + [mapped]
            )

    def _on_y_grid_toggled(self, checked: bool) -> None:
        self.y_grid_toggled.emit(checked)

    def _update_view_geometries(self) -> None:
        """Keep extra ViewBoxes aligned with the main ViewBox after resize."""
        rect = self._pi.vb.sceneBoundingRect()
        for spd in self._data.values():
            spd.view_box.setGeometry(rect)
            spd.view_box.linkedViewChanged(self._pi.vb, spd.view_box.XAxis)
