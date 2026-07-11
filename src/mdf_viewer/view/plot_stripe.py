"""PlotStripe — a single plot stripe widget built on PyQtGraph.

One or more PlotStripes are composed by PlotStripesArea (see
plot_stripes_area.py) into the full multi-stripe plot area, sharing one
X-axis and cursors across stripes while each stripe keeps its own
independent Y-axes. A PlotStripe on its own has no knowledge of sibling
stripes — everything below is scoped to "this stripe's own signals".

A shared X-axis (time) is panned/zoomed across all signals simultaneously.
Each active signal normally gets its own ViewBox and right-side Y-axis. Signals
can also be grouped: a *merged* group puts all member curves into one ViewBox
with one neutral-coloured Y-axis (same Y scale); a *synced* group keeps each
signal's own ViewBox but syncs their Y ranges absolutely when any one is
panned or zoomed.

Architecture note: the main PlotItem ViewBox (pi.vb) is used only as the X-axis
host — no curves are placed in it. Every signal gets its own ViewBox whose X is
linked to pi.vb, so panning or zooming X anywhere propagates to all signals.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

import pyqtgraph as pg
from PyQt6.QtCore import QEvent, QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QPen
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QWidget

from mdf_viewer.view._mime import (
    ROW_MIME_TYPE,
    SIGNAL_MIME_TYPE,
    decode_row_payload,
    decode_signal_payload,
)
from mdf_viewer.view_model.active_signal import ActiveSignal
from mdf_viewer.view_model.zoom_state import ZoomState

if TYPE_CHECKING:
    from typing import Protocol

    class DragClaimant(Protocol):
        """Something that gets first refusal on a left-button press in the plot.

        Registered via PlotStripe.register_drag_claimant(). hit_test() returns an
        opaque token identifying what was hit (e.g. a specific line), or None on
        a miss; the same token is passed back to on_move/on_release for the
        remainder of that gesture.

        This exists so cursor/delta-time lines (owned by CursorView, living in
        pi.vb) can claim a drag before curve-click hit-testing or native
        ViewBox panning ever see the event. Real Qt scene Z-order does not
        compare consistently between pi.vb and each signal's own top-level
        ViewBox (see #78) — routing through one authoritative, coordinate-based
        check here avoids depending on that comparison at all.
        """

        def hit_test(self, scene_pos: QPointF) -> object | None: ...
        def on_press(self, token: object, scene_pos: QPointF) -> None: ...
        def on_move(self, token: object, scene_pos: QPointF) -> None: ...
        def on_release(self, token: object, scene_pos: QPointF) -> None: ...

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
_NEUTRAL_AXIS_COLOR = (160, 160, 160)  # merged-axis colour (neither signal's colour)


def _symbol_size(line_width: int) -> int:
    return max(6, line_width * 4)


def _make_pen(color, width: int, style: str) -> QPen:
    pen = pg.mkPen(color=color, width=width)
    pen.setStyle(_QT_PEN_STYLE.get(style, Qt.PenStyle.SolidLine))
    return pen


class _ViewBox(pg.ViewBox):
    """ViewBox with fixed mouse behaviour for MDF-Viewer.

    Left drag inside the plot interior: pans X only (Y-panning an individual
    signal is only available by dragging that signal's own Y-axis column,
    which pyqtgraph routes here as axis=1 — not a use case for interior
    drags). Right drag: rectangle zoom. Wheel: X-axis zoom only, except when
    the mouse is over a Y-axis (axis=1), which zooms Y.
    The 'Mouse Mode' context-menu item is removed since the mode is fixed.
    """

    # Emitted with the scene-space QRectF when a right-drag zoom rect finishes.
    zoom_rect_finished = pyqtSignal(object)

    def __init__(self, *args, extra_menu_items=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.setMouseMode(pg.ViewBox.PanMode)
        # Appended once here (not in getMenu(), which pyqtgraph calls on every
        # right-click but always returns the same cached self.menu — adding
        # items there would duplicate them on the second click).
        if extra_menu_items and self.menu is not None:
            self.menu.addSeparator()
            for label, callback in extra_menu_items:
                action = self.menu.addAction(label)
                action.triggered.connect(callback)

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
        elif ev.button() == Qt.MouseButton.LeftButton and axis is None:
            # Interior drag: X only. Passing axis=0 masks out Y in the base
            # implementation (see ViewBox.mouseDragEvent's mask[1-axis]=0).
            super().mouseDragEvent(ev, axis=0)
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
        self.picture = None
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


class _MeasurementAxisItem(pg.AxisItem):
    """Bottom-orientation axis row showing one measurement's own recorded
    time under the shared X ruler (#101).

    Linked to the SAME shared ViewBox as every other axis in this stripe —
    not a separate one — so its tick *positions* always track the shared
    X-zoom/range for free (REQ-PLOT-302). Only tickStrings() differs per
    row: it subtracts this row's own measurement.offset_s, so the row
    reads as "this measurement's real recorded time" regardless of how far
    its curves have been panned relative to the others.

    mouseDragEvent is fully overridden and never forwards to the linked
    view's own pan (unlike PyQtGraph's default AxisItem.mouseDragEvent,
    which always calls linkedView().mouseDragEvent — see the #101
    architecture note for why that default can't be reused here). Dragging
    this axis mutates measurement.offset_s directly instead, which is the
    "zoom stays global, only pan is per-measurement" split REQ-PLOT-303
    requires.

    draggable=False (#102) disables the drag entirely — used for the single
    collapsed row shown while measurements are synchronized, since there is
    no way to tell which measurement a drag on that shared row would even
    apply to; re-adjusting requires un-synchronizing first (REQ-PLOT-314).
    """

    def __init__(self, measurement, on_offset_changed=None, draggable: bool = True, *args, **kwargs) -> None:
        kwargs.setdefault('orientation', 'bottom')
        super().__init__(*args, **kwargs)
        self._measurement = measurement
        self._on_offset_changed = on_offset_changed
        self._draggable = draggable
        self._drag_start_offset = 0.0

    def tickStrings(self, values, scale, spacing):
        offset = self._measurement.offset_s
        return [f"{(v * scale) - offset:.6g}" for v in values]

    def mouseDragEvent(self, event):
        if not self._draggable:
            event.ignore()
            return
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return
        lv = self.linkedView()
        if lv is None:
            event.ignore()
            return
        if event.isStart():
            self._drag_start_offset = self._measurement.offset_s
        dx_px = event.scenePos().x() - event.buttonDownScenePos().x()
        px_size_x = lv.viewPixelSize()[0]
        self._measurement.offset_s = self._drag_start_offset + dx_px * px_size_x
        if self._on_offset_changed is not None:
            self._on_offset_changed(self._measurement)
        # Tick positions are unchanged (the shared ViewBox range never
        # moves), but the labels must repaint to reflect the new offset —
        # same forced-repaint pattern as _SignalAxisItem.set_enum_display.
        self.picture = None
        self.update()
        event.accept()


@dataclass
class _SignalPlotData:
    """Internal per-signal rendering objects."""
    curve: object           # pg.PlotDataItem
    view_box: object        # pg.ViewBox
    axis: object            # pg.AxisItem
    owns_axis: bool = True  # False for non-first members of a merged group


class PlotStripe(QWidget):
    """One plot stripe: a shared X-axis and one ViewBox/Y-axis per signal.

    Signals can be grouped for coordinated Y-axis behaviour:
    - *merged*: all members render into one ViewBox with one neutral Y-axis.
    - *synced*: each member keeps its own ViewBox/axis; Y-range changes are
      mirrored absolutely across all members of the group.
    """

    # Emitted when the user toggles the Y-grid checkbox in the plot context menu.
    y_grid_toggled = pyqtSignal(bool)
    # Emitted when an MDF file is dropped onto the plot.
    file_dropped = pyqtSignal(object)  # Path
    # Emitted when signals are dragged from the Signal Browser and dropped:
    # list of (measurement_index, group_index, channel_index) triples (#103)
    # — a single drag can span rows from different loaded measurements, so
    # each item carries its own measurement_index.
    signals_dropped = pyqtSignal(list)
    # Emitted when an already-active signal is dragged from the Active
    # Signals Table and dropped onto this stripe's plot area (#116): the set
    # of id(ActiveSignal) being moved — resolved back to actual ActiveSignal
    # objects by whoever handles the signal, since only they know the full
    # active-signal list.
    active_signals_dropped = pyqtSignal(object)
    # Emitted whenever the X or any signal Y range changes (for zoom undo/redo).
    range_changed = pyqtSignal()
    # Emitted on a left-click in the plot: the topmost hit ActiveSignal, or None on a miss.
    signal_clicked = pyqtSignal(object)
    # Emitted (with self) on any mouse-press in this stripe's viewport, hit or
    # miss — lets PlotStripesArea track which stripe the user last interacted with.
    activated = pyqtSignal(object)
    # Emitted (with self) when "Create new Stripe" is chosen from this stripe's
    # context menu.
    create_stripe_requested = pyqtSignal(object)
    # Emitted (with self) when "Delete this Stripe" is chosen from this stripe's
    # context menu. The caller decides whether that's actually allowed (see
    # PlotStripesArea.delete_stripe).
    delete_stripe_requested = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        # Display name (REQ-PLOT-290/291); PlotStripesArea assigns the
        # default "Stripe N" right after construction, since a stripe has no
        # way to know its own creation index on its own.
        self.name: str = ""

        self._pw = pg.PlotWidget(viewBox=self._new_view_box())
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
        # Authoritative per-signal Z, independent of the ViewBox: merged-axis
        # groups put multiple signals in the *same* ViewBox, so a Z stamped
        # only on the ViewBox can't distinguish between them (#80). This dict
        # is the source of truth for _hit_test's stacking order.
        self._z_by_signal: dict[ActiveSignal, int] = {}

        # Objects that get first refusal on a left-button press (see DragClaimant).
        self._drag_claimants: list["DragClaimant"] = []
        self._active_claimant: tuple["DragClaimant", object] | None = None

        # Axis grouping state
        self._merged_groups: list[list[ActiveSignal]] = []
        self._synced_groups: list[list[ActiveSignal]] = []
        self._synced_handlers: dict[int, object] = {}  # id(vb) → handler
        self._syncing_y: bool = False

        # Blank right-side spacer used by PlotStripesArea to pad this stripe's
        # axis area so its plotting viewport aligns with wider stripes (see
        # content_axis_width/set_axis_padding).
        self._axis_spacer: pg.AxisItem | None = None

        # Per-measurement X-axis rows (#101); only ever non-empty on the
        # bottom-most stripe of a PlotStripesArea (REQ-PLOT-301), stacked
        # below PlotItem's own rows 0-3 (title/top-axis/vb/bottom-axis) —
        # see set_measurement_axes().
        self._measurement_axes: list["_MeasurementAxisItem"] = []

        self._pi.vb.sigResized.connect(self._update_view_geometries)
        self._pi.ctrl.yGridCheck.toggled.connect(self._on_y_grid_toggled)
        self._pi.vb.zoom_rect_finished.connect(self._on_zoom_rect_finished)
        self._pi.vb.sigRangeChanged.connect(self._on_vb_range_changed)

        self._pw.viewport().setAcceptDrops(True)
        self._pw.viewport().installEventFilter(self)
        self._drag_hover_active = False

        # Synchronize/Un-sync measurements button (#102) — parented directly
        # to self._pw (the PlotWidget/QGraphicsView) rather than added to the
        # QHBoxLayout below, since it needs to float *on top of* the plot
        # near the measurement axis rows, not sit *beside* the plot the way
        # _active_marker does. Only ever shown on the bottom-most stripe of a
        # PlotStripesArea, and only with 2+ measurements loaded — see
        # set_measurement_sync_control().
        self._sync_button = QPushButton(self._pw)
        self._sync_button.hide()
        self._sync_button.clicked.connect(self._on_sync_button_clicked)
        self._sync_toggle_cb: Callable[[], None] | None = None

        # Left-edge active-stripe marker (REQ-PLOT-210).
        self._active_marker = QFrame(self)
        self._active_marker.setFixedWidth(3)
        self._active_marker.setStyleSheet("background: transparent;")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._active_marker)
        layout.addWidget(self._pw)

    # ------------------------------------------------------------------
    # Public API (called by AppController / PlotStripesArea)
    # ------------------------------------------------------------------

    def _new_view_box(self) -> "_ViewBox":
        """Construct a _ViewBox wired with this stripe's stripe-management menu items."""
        return _ViewBox(
            extra_menu_items=[
                ("Create new Stripe", lambda: self.create_stripe_requested.emit(self)),
                ("Delete this Stripe", lambda: self.delete_stripe_requested.emit(self)),
            ]
        )

    def set_active(self, active: bool) -> None:
        """Show/hide the colored left-edge marker indicating the active stripe."""
        color = "palette(highlight)" if active else "transparent"
        self._active_marker.setStyleSheet(f"background: {color};")

    def set_show_x_axis_ticks(self, enabled: bool) -> None:
        """Show or hide this stripe's bottom X-axis tick labels and "Time" title.

        Only the bottom-most stripe in a PlotStripesArea shows ticks; other
        stripes hide them since the X value is identical at any horizontal
        position across all stripes (REQ-PLOT-181).
        """
        self._pi.getAxis('bottom').setStyle(showValues=enabled)
        self._pi.showLabel('bottom', enabled)

    # PlotItem's own rows are fixed by PyQtGraph: 0=title, 1=top axis
    # (unused here), 2=ViewBox, 3=bottom 'Time' axis (confirmed by
    # inspecting a real PlotItem's layout — see docs/architecture.md
    # "Multiple Measurements (#101)"). New measurement rows stack below
    # that, starting at row 4, all in column 1 (the same column as the
    # ViewBox and the 'Time' axis, so they align to the plot's own width
    # rather than spanning the extra right-side Y-axis columns).
    _MEASUREMENT_AXIS_BASE_ROW = 4
    _MEASUREMENT_AXIS_COLUMN = 1

    def set_measurement_axes(
        self, measurements: list, on_offset_changed=None, draggable: bool = True,
    ) -> None:
        """Build/tear down one bottom axis row per loaded measurement (#101).

        Only the bottom-most stripe in a PlotStripesArea should ever be
        given a non-empty *measurements* (REQ-PLOT-301); every other
        stripe is called with an empty list to clear its rows. Rows are
        linked to this stripe's shared ViewBox (self._pi.vb) — the same
        one every signal's X and the 'Time' axis already track — so their
        tick positions stay correct for free; see _MeasurementAxisItem.

        *on_offset_changed* is called with the LoadedMeasurement whenever
        the user drags one of these rows, so the caller (PlotStripesArea /
        AppController) can refresh that measurement's curves across every
        stripe and tab.

        *draggable* (#102) applies to every row built by this call — passed
        False for the single collapsed row shown while measurements are
        synchronized (REQ-PLOT-314).
        """
        for axis in self._measurement_axes:
            # Same leak as _destroy_vb_and_axis (#120): removeItem()+hide()
            # only detach from layout/visibility, never destroying the axis —
            # it stays alive, still linked to self._pi.vb, whose X range is
            # kept in sync across every stripe (sync_x_range), so it keeps
            # reacting to range changes indefinitely. Every time a new stripe
            # becomes the bottom one, the previous bottom stripe's axis was
            # leaked this way; deleteLater() actually frees it.
            self._pi.layout.removeItem(axis)
            axis.hide()
            if axis.scene() is not None:
                axis.scene().removeItem(axis)
            axis.deleteLater()
        self._measurement_axes = []

        for i, measurement in enumerate(measurements):
            axis = _MeasurementAxisItem(
                measurement=measurement,
                on_offset_changed=on_offset_changed,
                draggable=draggable,
                linkView=self._pi.vb,
                pen=pg.mkPen(color=_NEUTRAL_AXIS_COLOR),
                textPen=pg.mkPen(color=_NEUTRAL_AXIS_COLOR),
            )
            axis.setLabel(measurement.label)
            row = self._MEASUREMENT_AXIS_BASE_ROW + i
            self._pi.layout.setRowPreferredHeight(row, 0)
            self._pi.layout.setRowMinimumHeight(row, 0)
            self._pi.layout.setRowSpacing(row, 0)
            self._pi.layout.setRowStretchFactor(row, 1)
            self._pi.layout.addItem(axis, row, self._MEASUREMENT_AXIS_COLUMN)
            self._measurement_axes.append(axis)

    def set_measurement_sync_control(
        self, visible: bool, synchronized: bool, on_toggle: Callable[[], None] | None = None,
    ) -> None:
        """Show/hide/relabel this stripe's Synchronize/Un-sync button (#102).

        Only ever called with visible=True on the bottom-most stripe of a
        PlotStripesArea, and only once 2+ measurements are loaded
        (REQ-PLOT-316) — every other stripe (and a bottom stripe with fewer
        than 2 measurements) gets visible=False, hiding it entirely rather
        than showing it disabled.
        """
        self._sync_toggle_cb = on_toggle
        self._sync_button.setVisible(visible)
        if visible:
            self._sync_button.setText("Un-Sync" if synchronized else "Sync")
            self._reposition_sync_button()

    def _on_sync_button_clicked(self) -> None:
        if self._sync_toggle_cb is not None:
            self._sync_toggle_cb()

    def _reposition_sync_button(self) -> None:
        """Pin the sync button to a corner of the plot viewport."""
        margin = 6
        self._sync_button.adjustSize()
        viewport_rect = self._pw.viewport().rect()
        x = viewport_rect.right() - self._sync_button.width() - margin
        y = viewport_rect.bottom() - self._sync_button.height() - margin
        self._sync_button.move(max(0, x), max(0, y))
        self._sync_button.raise_()

    def content_axis_width(self) -> float:
        """Sum of the pixel widths of this stripe's own visible Y-axes.

        Excludes any alignment spacer previously applied via
        set_axis_padding() — this is the "real" content width PlotStripesArea
        compares across stripes to compute each one's needed padding.

        Forces the layout to settle first: an AxisItem's width() reflects a
        pending setStyle()/visibility change only after Qt has run a layout
        pass, which activate() does synchronously rather than waiting for the
        next paint cycle.
        """
        self._pi.layout.activate()
        seen: set[int] = set()
        total = 0.0
        for spd in self._data.values():
            axis = spd.axis
            if id(axis) in seen or not axis.isVisible():
                continue
            seen.add(id(axis))
            total += axis.width()
        return total

    def set_axis_padding(self, px: float) -> None:
        """Reserve *px* extra blank pixels on the right of this stripe's axes.

        Used by PlotStripesArea to align every stripe's plotting viewport to
        the same pixel width, since each stripe's Y-axis columns otherwise
        auto-size independently (different signal counts/tick-label widths
        per stripe would otherwise make the same X value land at a different
        screen position in each stripe — REQ-PLOT-180).
        """
        px = max(0, round(px))
        if px <= 0:
            if self._axis_spacer is not None:
                # Same leak as _destroy_vb_and_axis/set_measurement_axes
                # (#120): removeItem() alone detaches from layout but never
                # destroys the spacer — it stays alive, orphaned. This branch
                # only runs the first time this stripe's needed padding drops
                # to exactly 0, which is what made it easy to miss.
                spacer = self._axis_spacer
                self._pi.layout.removeItem(spacer)
                spacer.hide()
                if spacer.scene() is not None:
                    spacer.scene().removeItem(spacer)
                spacer.deleteLater()
                self._axis_spacer = None
            return
        if self._axis_spacer is None:
            self._axis_spacer = pg.AxisItem('right')
            self._axis_spacer.setPen(pg.mkPen(None))
            self._axis_spacer.setStyle(showValues=False, tickLength=0)
            self._pi.layout.addItem(self._axis_spacer, 2, self._pi.layout.columnCount())
        self._axis_spacer.setWidth(px)
        self._pi.layout.activate()

    def register_drag_claimant(self, claimant: "DragClaimant") -> None:
        """Register an object that gets first refusal on left-button presses.

        Checked in registration order before curve-click hit-testing. Used by
        CursorView so cursor/delta-time line drags are claimed here rather
        than left to native ViewBox panning.
        """
        self._drag_claimants.append(claimant)

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

        vb = self._new_view_box()
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
        curve.setData(active.display_timestamps, active.data.samples)

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
        self._z_by_signal.pop(active, None)

        # Always remove the curve from its ViewBox, then destroy it — not via
        # ViewBox.removeItem() (see _reparent_curve's docstring for the crash
        # that leaves: PyQtGraph's getViewBox() wrongly caches the enclosing
        # QGraphicsView once parentItem is None, which later crashes on
        # viewRangeChanged()). The curve was never destroyed here at all, just
        # detached — deleteLater() is what actually frees it instead of
        # leaving a poisoned zombie curve.
        self._destroy_curve(spd.curve, spd.view_box)
        active.curve = None
        active.view_box = None

        # Handle synced group cleanup before the ViewBox is destroyed.
        synced_grp = self._find_synced_group(active)
        if synced_grp is not None:
            self._disconnect_synced_handler(active)
            synced_grp.remove(active)
            if len(synced_grp) <= 1:
                if synced_grp:
                    self._disconnect_synced_handler(synced_grp[0])
                self._synced_groups.remove(synced_grp)

        # Handle merged group / ViewBox lifecycle.
        merged_grp = self._find_merged_group(active)
        if merged_grp is not None:
            merged_grp.remove(active)
            if spd.owns_axis:
                if merged_grp:
                    # Transfer ViewBox+axis ownership to the next remaining member.
                    self._transfer_ownership(spd.view_box, spd.axis, merged_grp[0])
                else:
                    # Last member — destroy.
                    self._destroy_vb_and_axis(spd.view_box, spd.axis)
            if len(merged_grp) == 1:
                # Group shrinks to one — dissolve: give the last member its own axis.
                last = merged_grp[0]
                old_vb = self._data[last].view_box
                old_axis = self._data[last].axis
                self._restore_signal_axis(last)
                self._destroy_vb_and_axis(old_vb, old_axis)
                self._merged_groups.remove(merged_grp)
            elif len(merged_grp) == 0:
                self._merged_groups.remove(merged_grp)
        elif spd.owns_axis:
            # Standard removal — signal was not in any merged group.
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
                z = n + _SELECTION_Z + idx
            else:
                z = base_z

            self._z_by_signal[active] = z
            spd.view_box.setZValue(z)
            spd.curve.setZValue(z)

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
        # Only recolor the axis if this signal is the sole user (not in a merged group).
        if self._find_merged_group(active) is None:
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
        grp = self._find_merged_group(active)
        if grp is not None:
            # Merged axis: any-on rule across all group members.
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
        spd.curve.setData(active.display_timestamps, active.data.samples)

    def refresh_signal_data(self, active: ActiveSignal) -> None:
        """Re-apply curve data after active.display_timestamps changes (#101).

        Used when a measurement's X-axis offset is dragged — Y data and
        every other display property (color, width, step mode, ...) are
        untouched. No-op if not present.
        """
        if active not in self._data:
            return
        self._data[active].curve.setData(active.display_timestamps, active.data.samples)

    def zoom_to_fit(self) -> None:
        """Reset viewport: full X range across all signals, auto Y per signal."""
        if not self._data:
            return

        # Compute full X range from all active signals' display timestamps.
        t_min = min(float(a.display_timestamps[0]) for a in self._data if len(a.data.timestamps))
        t_max = max(float(a.display_timestamps[-1]) for a in self._data if len(a.data.timestamps))
        self._pi.vb.setXRange(t_min, t_max, padding=0.02)
        self.autorange_y()

    def autorange_y(self) -> None:
        """Auto-range Y independently for every display unit in this stripe.

        A display unit is an ungrouped signal, a Merged group (one shared
        ViewBox), or a Synced group (each member its own ViewBox, ranges
        forced equal). Computes each unit's Y range directly from its
        members' full sample data via setYRange, rather than pyqtgraph's
        generic ViewBox.autoRange() — that also recomputes X from the
        curve's own bounding rect, which would silently overwrite the
        "full data range" X just set by zoom_to_fit() with whichever
        signal's autoRange() call happened to run last.
        """
        for vb, members, _is_synced in self._display_units():
            all_ys = [y for a in members for y in a.data.samples.tolist()]
            if not all_ys:
                continue
            y_min, y_max = min(all_ys), max(all_ys)
            if y_min == y_max:
                y_min -= 1.0
                y_max += 1.0
            vb.setYRange(y_min, y_max, padding=0.05)

    def zoom_to_x_range(self, x_min: float, x_max: float) -> None:
        """Set the shared X range to [x_min, x_max] with standard padding."""
        self._pi.vb.setXRange(x_min, x_max, padding=0.02)

    def sync_x_range(self, x_min: float, x_max: float) -> None:
        """Match another stripe's exact X range, with no added padding.

        Used by PlotStripesArea to keep every stripe's X range in lockstep —
        not a user-facing zoom action, so it must not add zoom_to_x_range()'s
        margin (that would compound outward every time it propagates).
        """
        self._pi.vb.setXRange(x_min, x_max, padding=0)

    def swimlanes(self, ordered_signals: list) -> bool:
        """Arrange signals in equal horizontal lanes by adjusting each Y range.

        Merged-axis groups count as one lane: their combined visible Y extent
        fills a single band. Each signal (or group) occupies 1/N of the viewport.

        Returns True if applied, False if there are no active signals.
        """
        if not self._data or not ordered_signals:
            return False

        units = self._display_units(ordered_signals)

        n = len(units)
        x_min, x_max = self._pi.vb.viewRange()[0]

        for i, (vb, unit_signals, _is_synced) in enumerate(units):
            ys_all: list[float] = []
            for active in unit_signals:
                ts = active.display_timestamps
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

        For merged groups, the combined visible extent of all members fills the axis.
        Returns True if any signals are active, False if there is nothing to zoom.
        """
        if not self._data:
            return False
        x_min, x_max = self._pi.vb.viewRange()[0]
        for vb, signals, _is_synced in self._display_units():
            ys_all: list[float] = []
            for active in signals:
                ts = active.display_timestamps
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

    def merge_signals(self, signals: list[ActiveSignal]) -> None:
        """Merge signals into one shared ViewBox and a single neutral Y-axis.

        If any of the signals are already in a merged group, their whole group
        is merged in. Mismatched-unit validation is done by the caller.
        """
        signals = [s for s in signals if s in self._data]
        if len(signals) < 2:
            return

        # Expand to include all members of any existing merged groups.
        merged_ids: set[int] = set()
        existing_grps: list[list[ActiveSignal]] = []
        for s in signals:
            grp = self._find_merged_group(s)
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
            self._merged_groups.remove(grp)
        self._merged_groups.append(list(merged))

        # Set merged axis to neutral color.
        neutral = pg.mkPen(color=_NEUTRAL_AXIS_COLOR)
        canonical_axis.setPen(neutral)
        canonical_axis.setTextPen(neutral)

        # Enum display: any-on across all members.
        any_enum = any(a.enum_display_yaxis for a in merged if a.metadata.enum_map)
        canonical_axis.set_enum_display(any_enum)

        self._update_axis_visibility()
        self._update_view_geometries()

    def ungroup_signal(self, active: ActiveSignal) -> None:
        """Remove active from its merged or synced group.

        For merged groups: the signal gets its own fresh ViewBox and Y-axis.
        If the group shrinks to one member, that member is also restored to its
        own axis and the group is dissolved.
        For synced groups: the signal's Y-range handler is disconnected.
        """
        # Synced group first.
        synced_grp = self._find_synced_group(active)
        if synced_grp is not None:
            self._disconnect_synced_handler(active)
            synced_grp.remove(active)
            if len(synced_grp) <= 1:
                if synced_grp:
                    self._disconnect_synced_handler(synced_grp[0])
                self._synced_groups.remove(synced_grp)
            return

        merged_grp = self._find_merged_group(active)
        if merged_grp is None:
            return

        # Capture state before any modification.
        active_was_owner = self._data[active].owns_axis
        old_merged_vb = self._data[active].view_box
        old_merged_axis = self._data[active].axis

        merged_grp.remove(active)

        # Give the leaving signal its own axis (removes curve from merged VB).
        self._restore_signal_axis(active)

        if len(merged_grp) == 0:
            # active was the only member (degenerate); clean up orphaned VB.
            self._merged_groups.remove(merged_grp)
            self._destroy_vb_and_axis(old_merged_vb, old_merged_axis)

        elif len(merged_grp) == 1:
            # Dissolve: give the last remaining member its own axis too.
            last = merged_grp[0]
            self._restore_signal_axis(last)
            self._destroy_vb_and_axis(old_merged_vb, old_merged_axis)
            self._merged_groups.remove(merged_grp)

        else:
            # Group continues with ≥ 2 members.
            if active_was_owner:
                new_owner = merged_grp[0]
                ns = self._data[new_owner]
                self._data[new_owner] = _SignalPlotData(
                    curve=ns.curve, view_box=ns.view_box,
                    axis=ns.axis, owns_axis=True,
                )
            # Refresh enum display on the remaining merged axis.
            any_enum = any(a.enum_display_yaxis for a in merged_grp if a.metadata.enum_map)
            old_merged_axis.set_enum_display(any_enum)

        self._update_axis_visibility()
        self._update_view_geometries()

    def sync_signals(self, signals: list[ActiveSignal]) -> None:
        """Sync Y-axes: when one signal's Y range changes, all synced peers follow.

        If any of the signals are already in a synced group, the groups are combined.
        Mismatched-unit validation is done by the caller.
        """
        signals = [s for s in signals if s in self._data]
        if len(signals) < 2:
            return

        # Expand any existing synced groups that overlap with the requested set.
        merged_ids: set[int] = set()
        existing_grps: list[list[ActiveSignal]] = []
        for s in signals:
            grp = self._find_synced_group(s)
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
                self._disconnect_synced_handler(s)
            self._synced_groups.remove(grp)

        group: list[ActiveSignal] = list(merged)
        self._synced_groups.append(group)

        # Connect a sync handler on each member's ViewBox.
        for active in group:
            self._connect_synced_handler(active, group)

    def is_in_group(self, active: ActiveSignal) -> bool:
        """Return True if active is in any merged or synced group."""
        return (
            self._find_merged_group(active) is not None
            or self._find_synced_group(active) is not None
        )

    def get_group_type(self, active: ActiveSignal) -> str | None:
        """Return 'merged', 'synced', or None."""
        if self._find_merged_group(active) is not None:
            return "merged"
        if self._find_synced_group(active) is not None:
            return "synced"
        return None

    def get_grouped_signals(self) -> set[ActiveSignal]:
        """Return the set of all signals currently in any group."""
        result: set[ActiveSignal] = set()
        for grp in self._merged_groups:
            result.update(grp)
        for grp in self._synced_groups:
            result.update(grp)
        return result

    def get_merged_signals(self) -> set[ActiveSignal]:
        """Return the set of all signals currently in a Merged Y-axis group."""
        result: set[ActiveSignal] = set()
        for grp in self._merged_groups:
            result.update(grp)
        return result

    def get_synced_signals(self) -> set[ActiveSignal]:
        """Return the set of all signals currently in a Synced Y-axes group."""
        result: set[ActiveSignal] = set()
        for grp in self._synced_groups:
            result.update(grp)
        return result

    def get_axis_grouping(self) -> tuple[list[list[tuple]], list[list[tuple]]]:
        """Return current merged and synced groups as (name, measurement) pairs.

        Returns (merged_groups, synced_groups) where each inner list contains
        one (metadata name, owning LoadedMeasurement) pair per signal in that
        group — the measurement is included (#106) so a saved/restored group
        can disambiguate the same channel name active from two different
        loaded measurements, which a bare name can't.
        """
        merged = [[(a.metadata.name, a.measurement) for a in grp] for grp in self._merged_groups]
        synced = [[(a.metadata.name, a.measurement) for a in grp] for grp in self._synced_groups]
        return merged, synced

    def restore_axis_grouping(
        self,
        merged: list[list[str]],
        synced: list[list[str]],
        active_signals: list,
    ) -> None:
        """Restore merged and synced groups from signal-name lists.

        Names that don't match any active signal are silently skipped.
        """
        name_map = {a.metadata.name: a for a in active_signals}
        for group_names in merged:
            actives = [name_map[n] for n in group_names if n in name_map]
            if len(actives) >= 2:
                self.merge_signals(actives)
        for group_names in synced:
            actives = [name_map[n] for n in group_names if n in name_map]
            if len(actives) >= 2:
                self.sync_signals(actives)

    # ------------------------------------------------------------------
    # Internal helpers — grouping
    # ------------------------------------------------------------------

    def _find_merged_group(self, active: ActiveSignal) -> list[ActiveSignal] | None:
        for grp in self._merged_groups:
            if active in grp:
                return grp
        return None

    def _find_synced_group(self, active: ActiveSignal) -> list[ActiveSignal] | None:
        for grp in self._synced_groups:
            if active in grp:
                return grp
        return None

    def _connect_synced_handler(self, active: ActiveSignal, group: list[ActiveSignal]) -> None:
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
        self._synced_handlers[id(vb)] = handler

    def _disconnect_synced_handler(self, active: ActiveSignal) -> None:
        """Disconnect the synced Y-range handler from active's ViewBox."""
        if active not in self._data:
            return
        vb = self._data[active].view_box
        handler = self._synced_handlers.pop(id(vb), None)
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

    @staticmethod
    def _destroy_curve(curve, vb) -> None:
        """Remove *curve* from *vb*'s bookkeeping and destroy it (#120).

        Deliberately skips ViewBox.removeItem() (see _reparent_curve's
        docstring above for the exact crash that leaves) — curve is being
        destroyed, not reparented, so instead of ever leaving it in the
        None-parent state, deleteLater() detaches it from the scene as part
        of normal Qt destruction, atomically.
        """
        if curve in vb.addedItems:
            vb.addedItems.remove(curve)
        if hasattr(vb, '_itemBoundsCache'):
            vb._itemBoundsCache.clear()
        curve.deleteLater()

    def _destroy_vb_and_axis(self, vb, axis) -> None:
        """Disconnect and destroy a ViewBox and its associated AxisItem.

        Both are QGraphicsWidgets scoped to this stripe's own scene.
        layout.removeItem()/hide() only detach the axis from grid
        positioning and visibility — the underlying Qt objects stay alive,
        still linked to each other, as orphaned scene members. Left that
        way, every signal moved out of a stripe (#120) leaks a live
        ViewBox+AxisItem pair; deleteLater() is what actually frees them.
        """
        # Unlink X first — removing an X-linked VB from the scene fires a range-change
        # signal that can cascade into curves' _updateView and crash if the curve has
        # already been relocated to a different ViewBox.
        try:
            vb.setXLink(None)
        except Exception:
            pass
        # Disconnect synced handler if one exists for this VB.
        handler = self._synced_handlers.pop(id(vb), None)
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
        if axis.scene() is not None:
            axis.scene().removeItem(axis)
        axis.deleteLater()
        self._pi.scene().removeItem(vb)
        vb.deleteLater()

    def _transfer_ownership(self, vb, axis, new_owner: ActiveSignal) -> None:
        """Give new_owner owns_axis=True for the merged ViewBox+axis."""
        if new_owner not in self._data:
            return
        spd = self._data[new_owner]
        self._data[new_owner] = _SignalPlotData(
            curve=spd.curve, view_box=vb, axis=axis, owns_axis=True,
        )

    def _restore_signal_axis(self, active: ActiveSignal) -> None:
        """Give active its own independent ViewBox and Y-axis.

        Removes active's curve from whatever ViewBox it is currently in (which
        may be a merged one) and creates a fresh ViewBox+AxisItem for this signal.
        The old ViewBox is NOT destroyed here — callers handle that.
        """
        if active not in self._data:
            return
        old_spd = self._data[active]

        vb = self._new_view_box()
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

    def _display_units(
        self, ordered_signals: list[ActiveSignal] | None = None,
    ) -> list[tuple[object, list[ActiveSignal], bool]]:
        """Group active signals into independent Y-display units.

        Returns (view_box, member_signals, is_synced_group) tuples. A unit is
        either a unique ViewBox and everything sharing it (covers ungrouped
        signals and Merged groups, which already collapse onto one ViewBox —
        is_synced_group False), or an entire Synced group treated as a single
        unit even though each member keeps its own ViewBox (is_synced_group
        True). Synced members' Y-ranges are externally forced to match by the
        sync handler in _connect_synced_handler, so treating them as N
        independent units makes each one's setYRange()/autoRange() call
        clobber the others (#84). *view_box* is one representative member's —
        applying a range to it is enough, since the sync handler propagates
        it to the rest of the synced group automatically.

        If *ordered_signals* is given, unit order follows the earliest-
        appearing member; otherwise falls back to internal dict order.
        """
        signals = ordered_signals if ordered_signals is not None else list(self._data)
        seen_vb_ids: set[int] = set()
        seen_synced_ids: set[int] = set()
        units: list[tuple[object, list[ActiveSignal], bool]] = []
        for active in signals:
            if active not in self._data:
                continue
            synced_grp = self._find_synced_group(active)
            if synced_grp is not None:
                grp_id = id(synced_grp)
                if grp_id in seen_synced_ids:
                    continue
                seen_synced_ids.add(grp_id)
                members = [s for s in signals if s in self._data and s in synced_grp]
                units.append((self._data[active].view_box, members, True))
                continue
            vb_id = id(self._data[active].view_box)
            if vb_id in seen_vb_ids:
                continue
            seen_vb_ids.add(vb_id)
            members = [
                s for s in signals
                if s in self._data and id(self._data[s].view_box) == vb_id
            ]
            units.append((self._data[active].view_box, members, False))
        return units

    # ------------------------------------------------------------------
    # Internal helpers — general
    # ------------------------------------------------------------------

    # Pixel tolerance for the marker fallback hit-test below — a few px wider
    # than an exact pointsAt() hit so near-misses on small markers still
    # register instead of falling through to native ViewBox panning (#81).
    _MARKER_HIT_TOLERANCE_PX = 6

    def _hit_test(self, viewport_pos: QPointF) -> "ActiveSignal | None":
        """Return the topmost ActiveSignal whose curve/markers contain viewport_pos, or None."""
        scene_pos = self._pw.mapToScene(viewport_pos.toPoint())
        ordered = sorted(
            self._data.items(), key=lambda kv: self._z_by_signal.get(kv[0], 0), reverse=True
        )
        for active, spd in ordered:
            if active.display_mode != "marker":
                data_pos = spd.view_box.mapSceneToView(scene_pos)
                if spd.curve.curve.mouseShape().contains(data_pos):
                    return active
            if active.display_mode != "line":
                local_pos = spd.curve.scatter.mapFromScene(scene_pos)
                if spd.curve.scatter.pointsAt(local_pos).size > 0:
                    return active
                if self._near_any_point(spd.view_box, spd.curve.scatter, local_pos):
                    return active
        return None

    def _near_any_point(self, view_box, scatter, local_pos: QPointF) -> bool:
        """Generous fallback for marker-only signals: hit if within a few px of any point.

        ScatterPlotItem.pointsAt() only hits if the click lands exactly inside a
        rendered symbol — a much smaller target than a curve's stroked
        mouseShape(). Distance is measured in screen pixels (via
        viewPixelSize()) since local_pos/point positions are in data units.
        """
        try:
            dx, dy = view_box.viewPixelSize()
        except Exception:
            return False
        if not dx or not dy:
            return False
        tol = self._MARKER_HIT_TOLERANCE_PX
        for point in scatter.points():
            pos = point.pos()
            if abs(pos.x() - local_pos.x()) / dx <= tol and abs(pos.y() - local_pos.y()) / dy <= tol:
                return True
        return False

    def eventFilter(self, watched, event):
        if watched is self._pw.viewport():
            t = event.type()
            if t == QEvent.Type.Resize and self._sync_button.isVisible():
                self._reposition_sync_button()
                # Falls through (not returning True) — this is a genuine
                # resize the viewport itself must still process normally,
                # unlike every other branch below which claims/consumes
                # its event.
            if t == QEvent.Type.MouseButtonPress:
                self.activated.emit(self)
            if t == QEvent.Type.MouseButtonPress and event.button() == Qt.MouseButton.LeftButton:
                scene_pos = self._pw.mapToScene(event.pos())
                for claimant in self._drag_claimants:
                    token = claimant.hit_test(scene_pos)
                    if token is not None:
                        self._active_claimant = (claimant, token)
                        claimant.on_press(token, scene_pos)
                        return True
                hit = self._hit_test(QPointF(event.pos()))
                self.signal_clicked.emit(hit)
                return hit is not None  # True (consume) on hit, False (pass through) on miss
            if t == QEvent.Type.MouseMove and self._active_claimant is not None:
                claimant, token = self._active_claimant
                claimant.on_move(token, self._pw.mapToScene(event.pos()))
                return True
            if t == QEvent.Type.MouseButtonRelease and self._active_claimant is not None:
                claimant, token = self._active_claimant
                claimant.on_release(token, self._pw.mapToScene(event.pos()))
                self._active_claimant = None
                return True
            if t == QEvent.Type.DragEnter:
                accepted = self._accepts_drag(event.mimeData())
                self._set_drag_highlight(accepted)
                if accepted:
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
            elif t == QEvent.Type.DragLeave:
                self._set_drag_highlight(False)
                return True
            elif t == QEvent.Type.Drop:
                self._set_drag_highlight(False)
                self._on_drop(event)
                return True
        return super().eventFilter(watched, event)

    def _set_drag_highlight(self, enabled: bool) -> None:
        """Toggle the drop-target highlight shown while a drag hovers this stripe."""
        if enabled == self._drag_hover_active:
            return
        self._drag_hover_active = enabled
        border = "2px solid palette(highlight)" if enabled else "none"
        self._pw.setStyleSheet(f"border: {border};")

    def _accepts_drag(self, mime_data) -> bool:
        if mime_data.hasFormat(SIGNAL_MIME_TYPE) or mime_data.hasFormat(ROW_MIME_TYPE):
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
            locs = decode_signal_payload(data)
            self.signals_dropped.emit(locs)
            event.acceptProposedAction()
        elif mime.hasFormat(ROW_MIME_TYPE):
            data = bytes(mime.data(ROW_MIME_TYPE))
            ids = decode_row_payload(data)
            self.active_signals_dropped.emit(ids)
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

        For merged groups: the axis is shown if ANY member is selected.
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
        # The sync button (#102) is a QWidget parented directly to self._pw,
        # not a scene item — adding/removing a signal changes the axis
        # layout (and therefore the plotted content's on-screen bounds)
        # without necessarily firing a Resize event on the viewport, which
        # was the only other place it got re-raised/repositioned. Qt's own
        # QGraphicsView appears to re-raise its viewport internally on scene
        # changes, burying any sibling widget behind it again — found live
        # (button went invisible after adding a signal), not by inspection.
        if not self._sync_button.isHidden():
            self._reposition_sync_button()
