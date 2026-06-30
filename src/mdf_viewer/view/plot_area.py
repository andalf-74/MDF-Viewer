"""PlotArea — center-top plotting widget built on PyQtGraph.

A shared X-axis (time) is panned/zoomed across all signals simultaneously.
Each active signal normally gets its own ViewBox and right-side Y-axis. Signals
can also be grouped: a *shared* group puts all member curves into one ViewBox
with one neutral-coloured Y-axis (same Y scale); a *linked* group keeps each
signal's own ViewBox but syncs their Y ranges absolutely when any one is
panned or zoomed.

Architecture note: the main PlotItem ViewBox (pi.vb) is used only as the X-axis
host — no curves are placed in it. Every signal gets its own ViewBox whose X is
linked to pi.vb, so panning or zooming X anywhere propagates to all signals.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
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
_NEUTRAL_AXIS_COLOR = (160, 160, 160)  # shared-axis colour (neither signal's colour)


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

    def __init__(self, *args, integer_ticks: bool = False,
                 enum_map: dict | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._integer_ticks = integer_ticks
        self._enum_map: dict[int, str] = enum_map or {}
        self._enum_display: bool = False

    def set_enum_display(self, enabled: bool) -> None:
        self._enum_display = enabled
        self.update()

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
            if self._enum_map and self._enum_display:
                result = []
                for v in values:
                    key = int(round(v * scale))
                    result.append(self._enum_map.get(key, str(key)))
                return result
            return [str(int(round(v * scale))) for v in values]
        return [f"{v * scale:.6g}" for v in values]


@dataclass
class _SignalPlotData:
    """Internal per-signal rendering objects."""
    curve: object           # pg.PlotDataItem
    view_box: object        # pg.ViewBox
    axis: object            # pg.AxisItem
    owns_axis: bool = True  # False for non-first members of a shared group


class PlotArea(QWidget):
    """PyQtGraph plot with a shared X-axis and one ViewBox/Y-axis per signal.

    Signals can be grouped for coordinated Y-axis behaviour:
    - *shared*: all members render into one ViewBox with one neutral Y-axis.
    - *linked*: each member keeps its own ViewBox/axis; Y-range changes are
      mirrored absolutely across all members of the group.
    """

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
        self._show_only_selected_y_axis: bool = False

        # Axis grouping state
        self._shared_groups: list[list[ActiveSignal]] = []
        self._linked_groups: list[list[ActiveSignal]] = []
        self._linked_handlers: dict[int, object] = {}  # id(vb) → handler
        self._syncing_y: bool = False

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
            enum_map=active.metadata.enum_map or None,
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
            stepMode="right" if active.step_mode else False,
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

        self._update_axis_visibility()
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

        # Always remove the curve from its ViewBox.
        spd.view_box.removeItem(spd.curve)
        active.curve = None
        active.view_box = None

        # Handle linked group cleanup before the ViewBox is destroyed.
        linked_grp = self._find_linked_group(active)
        if linked_grp is not None:
            self._disconnect_linked_handler(active)
            linked_grp.remove(active)
            if len(linked_grp) <= 1:
                if linked_grp:
                    self._disconnect_linked_handler(linked_grp[0])
                self._linked_groups.remove(linked_grp)

        # Handle shared group / ViewBox lifecycle.
        shared_grp = self._find_shared_group(active)
        if shared_grp is not None:
            shared_grp.remove(active)
            if spd.owns_axis:
                if shared_grp:
                    # Transfer ViewBox+axis ownership to the next remaining member.
                    self._transfer_ownership(spd.view_box, spd.axis, shared_grp[0])
                else:
                    # Last member — destroy.
                    self._destroy_vb_and_axis(spd.view_box, spd.axis)
            if len(shared_grp) == 1:
                # Group shrinks to one — dissolve: give the last member its own axis.
                last = shared_grp[0]
                old_vb = self._data[last].view_box
                old_axis = self._data[last].axis
                self._restore_signal_axis(last)
                self._destroy_vb_and_axis(old_vb, old_axis)
                self._shared_groups.remove(shared_grp)
            elif len(shared_grp) == 0:
                self._shared_groups.remove(shared_grp)
        elif spd.owns_axis:
            # Standard removal — signal was not in any shared group.
            self._destroy_vb_and_axis(spd.view_box, spd.axis)

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
        self._update_axis_visibility()
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
        # Only recolor the axis if this signal is the sole user (not in a shared group).
        if self._find_shared_group(active) is None:
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

    def set_show_only_selected_y_axis(self, enabled: bool) -> None:
        """Toggle whether only the selected signal's Y-axis is shown."""
        self._show_only_selected_y_axis = enabled
        self._update_axis_visibility()

    def _effective_width(self, active: ActiveSignal) -> int:
        """Return line_width + boost if the signal is currently selected, else line_width."""
        return active.line_width + (self._selected_line_boost if active in self._selected_signals else 0)

    def set_y_grid(self, active: ActiveSignal, enabled: bool) -> None:
        """Enable or disable the Y-grid on a signal's axis. No-op if not present."""
        if active not in self._data:
            return
        self._data[active].axis.setGrid(160 if enabled else False)

    def set_enum_display_yaxis(self, active: ActiveSignal, enabled: bool) -> None:
        """Show enum labels (or raw integers) on this signal's Y-axis. No-op if not present."""
        if active not in self._data:
            return
        grp = self._find_shared_group(active)
        if grp is not None:
            # Shared axis: any-on rule across all group members.
            any_enum = any(a.enum_display_yaxis for a in grp if a.metadata.enum_map)
            self._data[active].axis.set_enum_display(any_enum)
        else:
            self._data[active].axis.set_enum_display(enabled)

    def set_step_mode(self, active: ActiveSignal, enabled: bool) -> None:
        """Switch a signal curve between step and linear rendering. No-op if not present."""
        if active not in self._data:
            return
        spd = self._data[active]
        spd.curve.opts["stepMode"] = "right" if enabled else False
        spd.curve.setData(active.data.timestamps, active.data.samples)

    def zoom_to_fit(self) -> None:
        """Reset viewport: full X range across all signals, auto Y per signal."""
        if not self._data:
            return

        # Compute full X range from all active signal timestamps.
        t_min = min(float(a.data.timestamps[0]) for a in self._data if len(a.data.timestamps))
        t_max = max(float(a.data.timestamps[-1]) for a in self._data if len(a.data.timestamps))
        self._pi.vb.setXRange(t_min, t_max, padding=0.02)

        # Auto-range Y per unique ViewBox (shared groups share one ViewBox).
        seen: set[int] = set()
        for spd in self._data.values():
            if id(spd.view_box) not in seen:
                seen.add(id(spd.view_box))
                spd.view_box.autoRange()

    def zoom_to_x_range(self, x_min: float, x_max: float) -> None:
        """Set the shared X range to [x_min, x_max] with standard padding."""
        self._pi.vb.setXRange(x_min, x_max, padding=0.02)

    def swimlanes(self, ordered_signals: list) -> bool:
        """Arrange signals in equal horizontal lanes by adjusting each Y range.

        Shared-axis groups count as one lane: their combined visible Y extent
        fills a single band. Each signal (or group) occupies 1/N of the viewport.

        Returns True if applied, False if there are no active signals.
        """
        if not self._data or not ordered_signals:
            return False

        # Build ordered list of unique (ViewBox, [signals]) units.
        seen_vb_ids: set[int] = set()
        units: list[tuple] = []
        for active in ordered_signals:
            if active not in self._data:
                continue
            spd = self._data[active]
            vb_id = id(spd.view_box)
            if vb_id not in seen_vb_ids:
                seen_vb_ids.add(vb_id)
                # All signals sharing this ViewBox, in ordered_signals order.
                grp = [s for s in ordered_signals if s in self._data and id(self._data[s].view_box) == vb_id]
                units.append((spd.view_box, grp))

        n = len(units)
        x_min, x_max = self._pi.vb.viewRange()[0]

        for i, (vb, unit_signals) in enumerate(units):
            ys_all: list[float] = []
            for active in unit_signals:
                ts = active.data.timestamps
                ys = active.data.samples
                mask = (ts >= x_min) & (ts <= x_max)
                visible = ys[mask]
                if len(visible):
                    ys_all.extend(visible.tolist())

            if not ys_all:
                all_ys = [y for a in unit_signals for y in a.data.samples.tolist()]
                y_min = min(all_ys) if all_ys else -1.0
                y_max = max(all_ys) if all_ys else 1.0
            else:
                y_min = min(ys_all)
                y_max = max(ys_all)

            data_span = y_max - y_min
            if data_span == 0:
                data_span = 2.0
                y_min -= 1.0
                y_max += 1.0

            # Add 5 % padding within each lane, then compute the ViewBox Y range
            # that maps this unit's padded data band to lane i (i=0 → top).
            # In PyQtGraph Y increases upward, so band 0 (top screen) = high Y.
            pad = 0.05 * data_span
            adj_min = y_min - pad
            adj_span = data_span + 2 * pad

            vb_y_min = adj_min - (n - 1 - i) * adj_span
            vb_y_max = adj_min + (i + 1) * adj_span

            vb.setYRange(vb_y_min, vb_y_max, padding=0)
        return True

    def zoom_y_to_view(self) -> bool:
        """Rescale each signal's Y-axis to fit the currently visible X range.

        For shared groups, the combined visible extent of all members fills the axis.
        Returns True if any signals are active, False if there is nothing to zoom.
        """
        if not self._data:
            return False
        x_min, x_max = self._pi.vb.viewRange()[0]
        for vb, signals in self._unique_vb_signals().items():
            ys_all: list[float] = []
            for active in signals:
                ts = active.data.timestamps
                ys = active.data.samples
                mask = (ts >= x_min) & (ts <= x_max)
                visible = ys[mask]
                if len(visible):
                    ys_all.extend(visible.tolist())
            if not ys_all:
                continue
            y_min = min(ys_all)
            y_max = max(ys_all)
            if y_min == y_max:
                y_min -= 1.0
                y_max += 1.0
            vb.setYRange(y_min, y_max, padding=0.05)
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
    # Axis grouping — public API
    # ------------------------------------------------------------------

    def share_signals(self, signals: list[ActiveSignal]) -> None:
        """Merge signals into one shared ViewBox and a single neutral Y-axis.

        If any of the signals are already in a shared group, their whole group
        is merged in. Mismatched-unit validation is done by the caller.
        """
        signals = [s for s in signals if s in self._data]
        if len(signals) < 2:
            return

        # Expand to include all members of any existing shared groups.
        merged_ids: set[int] = set()
        existing_grps: list[list[ActiveSignal]] = []
        for s in signals:
            grp = self._find_shared_group(s)
            if grp is not None:
                for m in grp:
                    merged_ids.add(id(m))
                if grp not in existing_grps:
                    existing_grps.append(grp)
            else:
                merged_ids.add(id(s))

        # Preserve _data insertion order.
        merged = [a for a in self._data if id(a) in merged_ids]
        if len(merged) < 2:
            return

        # Choose canonical ViewBox: prefer an existing group's owner, else first.
        canonical: ActiveSignal | None = None
        for grp in existing_grps:
            for s in grp:
                if s in self._data and self._data[s].owns_axis:
                    canonical = s
                    break
            if canonical:
                break
        if canonical is None:
            canonical = merged[0]

        canonical_vb = self._data[canonical].view_box
        canonical_axis = self._data[canonical].axis

        # Collect non-canonical ViewBoxes to destroy after all migrations.
        vbs_to_destroy: list[tuple] = []
        seen_vb_ids: set[int] = {id(canonical_vb)}
        for active in merged:
            spd = self._data[active]
            vb_id = id(spd.view_box)
            if vb_id not in seen_vb_ids:
                seen_vb_ids.add(vb_id)
                vbs_to_destroy.append((spd.view_box, spd.axis))

        # Migrate all member curves to the canonical ViewBox.
        for active in merged:
            spd = self._data[active]
            if id(spd.view_box) == id(canonical_vb):
                # Already in canonical VB — just update owns_axis.
                self._data[active] = _SignalPlotData(
                    curve=spd.curve,
                    view_box=canonical_vb,
                    axis=canonical_axis,
                    owns_axis=(active is canonical),
                )
                continue
            # Move curve from old VB to canonical VB in a single reparent step.
            # Using removeItem+addItem creates an intermediate state where the
            # curve's parentItem is None; PyQtGraph then caches the PlotWidget as
            # the view, causing autoRangeEnabled() to crash (PlotWidget != ViewBox).
            self._reparent_curve(spd.curve, spd.view_box, canonical_vb)
            self._data[active] = _SignalPlotData(
                curve=spd.curve,
                view_box=canonical_vb,
                axis=canonical_axis,
                owns_axis=False,
            )
            active.view_box = canonical_vb

        # Destroy non-canonical ViewBoxes (all curves have already been moved).
        for old_vb, old_axis in vbs_to_destroy:
            self._destroy_vb_and_axis(old_vb, old_axis)

        # Update group registry.
        for grp in existing_grps:
            self._shared_groups.remove(grp)
        self._shared_groups.append(list(merged))

        # Set shared axis to neutral color.
        neutral = pg.mkPen(color=_NEUTRAL_AXIS_COLOR)
        canonical_axis.setPen(neutral)
        canonical_axis.setTextPen(neutral)

        # Enum display: any-on across all members.
        any_enum = any(a.enum_display_yaxis for a in merged if a.metadata.enum_map)
        canonical_axis.set_enum_display(any_enum)

        self._update_axis_visibility()
        self._update_view_geometries()

    def ungroup_signal(self, active: ActiveSignal) -> None:
        """Remove active from its shared or linked group.

        For shared groups: the signal gets its own fresh ViewBox and Y-axis.
        If the group shrinks to one member, that member is also restored to its
        own axis and the group is dissolved.
        For linked groups: the signal's Y-range handler is disconnected.
        """
        # Linked group first.
        linked_grp = self._find_linked_group(active)
        if linked_grp is not None:
            self._disconnect_linked_handler(active)
            linked_grp.remove(active)
            if len(linked_grp) <= 1:
                if linked_grp:
                    self._disconnect_linked_handler(linked_grp[0])
                self._linked_groups.remove(linked_grp)
            return

        shared_grp = self._find_shared_group(active)
        if shared_grp is None:
            return

        # Capture state before any modification.
        active_was_owner = self._data[active].owns_axis
        old_shared_vb = self._data[active].view_box
        old_shared_axis = self._data[active].axis

        shared_grp.remove(active)

        # Give the leaving signal its own axis (removes curve from shared VB).
        self._restore_signal_axis(active)

        if len(shared_grp) == 0:
            # active was the only member (degenerate); clean up orphaned VB.
            self._shared_groups.remove(shared_grp)
            self._destroy_vb_and_axis(old_shared_vb, old_shared_axis)

        elif len(shared_grp) == 1:
            # Dissolve: give the last remaining member its own axis too.
            last = shared_grp[0]
            self._restore_signal_axis(last)
            self._destroy_vb_and_axis(old_shared_vb, old_shared_axis)
            self._shared_groups.remove(shared_grp)

        else:
            # Group continues with ≥ 2 members.
            if active_was_owner:
                new_owner = shared_grp[0]
                ns = self._data[new_owner]
                self._data[new_owner] = _SignalPlotData(
                    curve=ns.curve, view_box=ns.view_box,
                    axis=ns.axis, owns_axis=True,
                )
            # Refresh enum display on the remaining shared axis.
            any_enum = any(a.enum_display_yaxis for a in shared_grp if a.metadata.enum_map)
            old_shared_axis.set_enum_display(any_enum)

        self._update_axis_visibility()
        self._update_view_geometries()

    def link_signals(self, signals: list[ActiveSignal]) -> None:
        """Link Y-axes: when one signal's Y range changes, all linked peers follow.

        If any of the signals are already in a linked group, the groups are merged.
        Mismatched-unit validation is done by the caller.
        """
        signals = [s for s in signals if s in self._data]
        if len(signals) < 2:
            return

        # Expand any existing linked groups that overlap with the requested set.
        merged_ids: set[int] = set()
        existing_grps: list[list[ActiveSignal]] = []
        for s in signals:
            grp = self._find_linked_group(s)
            if grp is not None:
                for m in grp:
                    merged_ids.add(id(m))
                if grp not in existing_grps:
                    existing_grps.append(grp)
            else:
                merged_ids.add(id(s))

        merged = [a for a in self._data if id(a) in merged_ids]
        if len(merged) < 2:
            return

        # Disconnect existing handlers before rebuilding.
        for grp in existing_grps:
            for s in grp:
                self._disconnect_linked_handler(s)
            self._linked_groups.remove(grp)

        group: list[ActiveSignal] = list(merged)
        self._linked_groups.append(group)

        # Connect a sync handler on each member's ViewBox.
        for active in group:
            self._connect_linked_handler(active, group)

    def is_in_group(self, active: ActiveSignal) -> bool:
        """Return True if active is in any shared or linked group."""
        return (
            self._find_shared_group(active) is not None
            or self._find_linked_group(active) is not None
        )

    def get_group_type(self, active: ActiveSignal) -> str | None:
        """Return 'shared', 'linked', or None."""
        if self._find_shared_group(active) is not None:
            return "shared"
        if self._find_linked_group(active) is not None:
            return "linked"
        return None

    def get_grouped_signals(self) -> set[ActiveSignal]:
        """Return the set of all signals currently in any group."""
        result: set[ActiveSignal] = set()
        for grp in self._shared_groups:
            result.update(grp)
        for grp in self._linked_groups:
            result.update(grp)
        return result

    def get_axis_grouping(self) -> tuple[list[list[str]], list[list[str]]]:
        """Return current shared and linked groups as signal-name lists.

        Returns (shared_groups, linked_groups) where each inner list contains
        the metadata names of the signals in that group.
        """
        shared = [[a.metadata.name for a in grp] for grp in self._shared_groups]
        linked = [[a.metadata.name for a in grp] for grp in self._linked_groups]
        return shared, linked

    def restore_axis_grouping(
        self,
        shared: list[list[str]],
        linked: list[list[str]],
        active_signals: list,
    ) -> None:
        """Restore shared and linked groups from signal-name lists.

        Names that don't match any active signal are silently skipped.
        """
        name_map = {a.metadata.name: a for a in active_signals}
        for group_names in shared:
            actives = [name_map[n] for n in group_names if n in name_map]
            if len(actives) >= 2:
                self.share_signals(actives)
        for group_names in linked:
            actives = [name_map[n] for n in group_names if n in name_map]
            if len(actives) >= 2:
                self.link_signals(actives)

    # ------------------------------------------------------------------
    # Internal helpers — grouping
    # ------------------------------------------------------------------

    def _find_shared_group(self, active: ActiveSignal) -> list[ActiveSignal] | None:
        for grp in self._shared_groups:
            if active in grp:
                return grp
        return None

    def _find_linked_group(self, active: ActiveSignal) -> list[ActiveSignal] | None:
        for grp in self._linked_groups:
            if active in grp:
                return grp
        return None

    def _connect_linked_handler(self, active: ActiveSignal, group: list[ActiveSignal]) -> None:
        """Connect a Y-range sync handler to active's ViewBox."""
        if active not in self._data:
            return
        vb = self._data[active].view_box
        # sigRangeChanged emits (viewbox, [[xmin,xmax],[ymin,ymax]], ...)
        def handler(*args, _self=self, _source=active, _grp=group):
            if _self._syncing_y:
                return
            if len(args) < 2:
                return
            try:
                y_range = args[1][1]
                if len(y_range) < 2:
                    return
            except (IndexError, TypeError):
                return
            _self._syncing_y = True
            try:
                for peer in list(_grp):
                    if peer is _source or peer not in _self._data:
                        continue
                    peer_vb = _self._data[peer].view_box
                    cur = peer_vb.viewRange()[1]
                    # Skip if peer already has the requested range (float tolerance).
                    # PyQtGraph fires sigRangeChanged twice when a VB has a pending
                    # _autoRangeNeedsUpdate — the second call should be a no-op.
                    if abs(cur[0] - y_range[0]) < 1e-9 and abs(cur[1] - y_range[1]) < 1e-9:
                        continue
                    peer_vb.setYRange(y_range[0], y_range[1], padding=0)
            finally:
                _self._syncing_y = False

        vb.sigRangeChanged.connect(handler)
        self._linked_handlers[id(vb)] = handler

    def _disconnect_linked_handler(self, active: ActiveSignal) -> None:
        """Disconnect the linked Y-range handler from active's ViewBox."""
        if active not in self._data:
            return
        vb = self._data[active].view_box
        handler = self._linked_handlers.pop(id(vb), None)
        if handler is not None:
            try:
                vb.sigRangeChanged.disconnect(handler)
            except TypeError:
                pass

    @staticmethod
    def _reparent_curve(curve, old_vb, new_vb) -> None:
        """Move *curve* from *old_vb* to *new_vb* without an intermediate None-parent state.

        ViewBox.removeItem() calls scene.removeItem() then setParentItem(None). The
        None-parent state causes PyQtGraph's getViewBox() to cache the PlotWidget (the
        QGraphicsView) as the item's view, which then crashes when viewRangeChanged()
        tries to call view.autoRangeEnabled(). Instead we update the ViewBox bookkeeping
        lists manually and do a single setParentItem() call that goes directly from the
        old childGroup to the new childGroup.
        """
        if curve in old_vb.addedItems:
            old_vb.addedItems.remove(curve)
        if hasattr(old_vb, '_itemBoundsCache'):
            old_vb._itemBoundsCache.clear()
        new_vb.addedItems.append(curve)
        if hasattr(new_vb, '_itemBoundsCache'):
            new_vb._itemBoundsCache.clear()
        curve.setParentItem(new_vb.childGroup)

    def _destroy_vb_and_axis(self, vb, axis) -> None:
        """Disconnect and destroy a ViewBox and its associated AxisItem."""
        # Unlink X first — removing an X-linked VB from the scene fires a range-change
        # signal that can cascade into curves' _updateView and crash if the curve has
        # already been relocated to a different ViewBox.
        try:
            vb.setXLink(None)
        except Exception:
            pass
        # Disconnect linked handler if one exists for this VB.
        handler = self._linked_handlers.pop(id(vb), None)
        if handler is not None:
            try:
                vb.sigRangeChanged.disconnect(handler)
            except TypeError:
                pass
        try:
            vb.zoom_rect_finished.disconnect(self._on_zoom_rect_finished)
        except TypeError:
            pass
        try:
            vb.sigRangeChanged.disconnect(self._on_vb_range_changed)
        except TypeError:
            pass
        self._pi.layout.removeItem(axis)
        axis.hide()
        self._pi.scene().removeItem(vb)

    def _transfer_ownership(self, vb, axis, new_owner: ActiveSignal) -> None:
        """Give new_owner owns_axis=True for the shared ViewBox+axis."""
        if new_owner not in self._data:
            return
        spd = self._data[new_owner]
        self._data[new_owner] = _SignalPlotData(
            curve=spd.curve, view_box=vb, axis=axis, owns_axis=True,
        )

    def _restore_signal_axis(self, active: ActiveSignal) -> None:
        """Give active its own independent ViewBox and Y-axis.

        Removes active's curve from whatever ViewBox it is currently in (which
        may be a shared one) and creates a fresh ViewBox+AxisItem for this signal.
        The old ViewBox is NOT destroyed here — callers handle that.
        """
        if active not in self._data:
            return
        old_spd = self._data[active]

        vb = _ViewBox()
        self._pi.scene().addItem(vb)
        vb.setXLink(self._pi)
        vb.zoom_rect_finished.connect(self._on_zoom_rect_finished)
        # Use _reparent_curve to move from old VB to new VB in one step (avoids
        # intermediate None-parent state that crashes PyQtGraph's view lookup).
        self._reparent_curve(old_spd.curve, old_spd.view_box, vb)

        col = self._pi.layout.columnCount()
        axis = _SignalAxisItem(
            'right',
            linkView=vb,
            pen=pg.mkPen(color=active.color),
            textPen=pg.mkPen(color=active.color),
            integer_ticks=active.metadata.is_integer,
            enum_map=active.metadata.enum_map or None,
        )
        axis.set_enum_display(active.enum_display_yaxis)
        self._pi.layout.addItem(axis, 2, col)

        self._data[active] = _SignalPlotData(
            curve=old_spd.curve, view_box=vb, axis=axis, owns_axis=True,
        )
        active.view_box = vb

        vb.sigRangeChanged.connect(self._on_vb_range_changed)
        vb.enableAutoRange()

    def _unique_vb_signals(self) -> dict:
        """Return {viewbox: [active, ...]} grouped by unique ViewBox."""
        result: dict = {}
        for active, spd in self._data.items():
            vb_id = id(spd.view_box)
            if vb_id not in result:
                result[vb_id] = (spd.view_box, [])
            result[vb_id][1].append(active)
        return {vb: sigs for vb, sigs in result.values()}

    # ------------------------------------------------------------------
    # Internal helpers — general
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
        """Apply zoom rect Y extent to every unique signal ViewBox and update their undo history."""
        seen: set[int] = set()
        for spd in self._data.values():
            vb_id = id(spd.view_box)
            if vb_id in seen:
                continue
            seen.add(vb_id)
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

    def _update_axis_visibility(self) -> None:
        """Show or hide Y-axes according to the show-only-selected-Y-axis toggle.

        For shared groups: the axis is shown if ANY member is selected.
        """
        if not self._show_only_selected_y_axis or not self._selected_signals:
            visible_set = set(self._data.keys())
        else:
            visible_set = set(self._selected_signals) & set(self._data.keys())

        # Determine per-axis visibility: an axis is visible if any of its signals is.
        axis_show: dict[int, tuple] = {}  # id(axis) → (axis, should_show)
        for active, spd in self._data.items():
            aid = id(spd.axis)
            should = active in visible_set
            if aid not in axis_show:
                axis_show[aid] = (spd.axis, should)
            elif should:
                axis_show[aid] = (spd.axis, True)

        for _aid, (axis, should_show) in axis_show.items():
            if not should_show and axis.isVisible():
                self._pi.layout.removeItem(axis)
                axis.hide()
            elif should_show and not axis.isVisible():
                col = self._pi.layout.columnCount()
                self._pi.layout.addItem(axis, 2, col)
                axis.show()

    def _update_view_geometries(self) -> None:
        """Keep extra ViewBoxes aligned with the main ViewBox after resize."""
        rect = self._pi.vb.sceneBoundingRect()
        seen: set[int] = set()
        for spd in self._data.values():
            vb_id = id(spd.view_box)
            if vb_id in seen:
                continue
            seen.add(vb_id)
            spd.view_box.setGeometry(rect)
            spd.view_box.linkedViewChanged(self._pi.vb, spd.view_box.XAxis)
