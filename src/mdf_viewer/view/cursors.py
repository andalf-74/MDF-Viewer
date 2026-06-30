"""CursorView — draggable vertical cursor lines and their value labels.

Rendered inside the PlotArea. Manages one or two InfiniteLine items and
per-signal TextItem value labels. The toggle cycle and position memory live
in CursorController; this class only handles the visual representation.

Label visibility rule: with ONE cursor, its labels are always shown; with
TWO cursors, only the cursor nearest the mouse pointer shows its labels.

Each label is parented to the signal's own ViewBox (not the main PlotItem),
so it lives in that signal's Y coordinate space. This means the label
automatically tracks Y panning and zooming without any extra update calls.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pyqtgraph as pg
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtCore import QObject
from PyQt6.QtGui import QFont

from mdf_viewer.controller.cursor_controller import CursorMode
from mdf_viewer.model.interpolate import interpolate as _interpolate

if TYPE_CHECKING:
    from mdf_viewer.view_model.active_signal import ActiveSignal

# Cursor line style
_CURSOR_PEN = pg.mkPen(color=(220, 220, 50), width=1, style=Qt.PenStyle.DashLine)


_DELTA_PEN = pg.mkPen(color=(200, 200, 200), width=1, style=Qt.PenStyle.DashLine)


class _ChevronItem(pg.TextItem):
    """Clickable edge-indicator chevron for an off-screen cursor or delta-time line."""

    def __init__(self) -> None:
        super().__init__(text="", color=(220, 220, 50), anchor=(0.0, 0.5))
        font = QFont()
        font.setPointSize(12)
        font.setBold(True)
        self.setFont(font)
        self.setZValue(100)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._clicked_cb = None

    def set_clicked_callback(self, cb) -> None:
        self._clicked_cb = cb

    def mousePressEvent(self, event) -> None:  # type: ignore[override]
        if self._clicked_cb is not None:
            self._clicked_cb(event.scenePos())
        event.accept()


class CursorView(QObject):
    """Manages the draggable cursor InfiniteLines and their value labels."""

    cursor_moved = pyqtSignal(int, float)            # (cursor_index, x_position)
    cursor_clicked = pyqtSignal(int)                 # (cursor_index) — clicked without drag
    delta_line_moved = pyqtSignal(float)             # (y_position)
    cursor_fetch_requested = pyqtSignal(int, float)  # (cursor_index, x_data) — chevron clicked
    delta_fetch_requested = pyqtSignal(float)        # (y_data) — delta-time chevron clicked

    def __init__(self, plot_item: pg.PlotItem, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pi = plot_item
        self._mode = CursorMode.HIDDEN
        self._nearest_cursor: int = 0

        # Two InfiniteLines, both hidden initially.
        self._lines: list[pg.InfiniteLine] = []
        for i in range(2):
            line = pg.InfiniteLine(angle=90, movable=True, pen=_CURSOR_PEN)
            line.setVisible(False)
            self._pi.addItem(line)
            line.sigPositionChanged.connect(
                lambda ln, idx=i: self.cursor_moved.emit(idx, ln.value())
            )
            line.sigClicked.connect(
                lambda ln, ev, idx=i: self.cursor_clicked.emit(idx)
            )
            self._lines.append(line)

        # Horizontal delta-time line (angle=0), hidden until TWO mode.
        self._delta_line = pg.InfiniteLine(angle=0, movable=True, pen=_DELTA_PEN)
        self._delta_line.setVisible(False)
        self._pi.addItem(self._delta_line)
        self._delta_line.sigPositionChanged.connect(self._on_delta_line_pos_changed)

        # Delta-time label, parented to the main ViewBox.
        self._delta_label = pg.TextItem(text="", color=(200, 200, 200), anchor=(0.5, 1.0))
        self._delta_label.setVisible(False)
        self._pi.vb.addItem(self._delta_label, ignoreBounds=True)
        self._delta_label_x: float = 0.0  # last known midpoint X, updated in update_delta_time

        # (cursor_index, ActiveSignal) → (TextItem, ViewBox)
        # Labels are owned by the signal's ViewBox so they track Y pan/zoom.
        self._labels: dict[tuple[int, ActiveSignal], tuple[pg.TextItem, pg.ViewBox]] = {}

        # Off-screen edge chevrons — two for cursors, one for the delta-time line.
        self._c_chevrons: list[_ChevronItem] = []
        for i in range(2):
            chev = _ChevronItem()
            chev.setVisible(False)
            self._pi.vb.addItem(chev, ignoreBounds=True)
            chev.set_clicked_callback(
                lambda scene_pos, idx=i: self.cursor_fetch_requested.emit(
                    idx, self._pi.vb.mapSceneToView(scene_pos).x()
                )
            )
            self._c_chevrons.append(chev)

        self._dt_chevron = _ChevronItem()
        self._dt_chevron.setVisible(False)
        self._dt_chevron.setToolTip("Fetch ∆t line")
        self._pi.vb.addItem(self._dt_chevron, ignoreBounds=True)
        self._dt_chevron.set_clicked_callback(
            lambda scene_pos: self.delta_fetch_requested.emit(
                self._pi.vb.mapSceneToView(scene_pos).y()
            )
        )

        # Cached state used by _update_chevrons on view-range change.
        self._line_colors: list[tuple] = [(220, 220, 50), (255, 140, 0)]
        self._cursor_names: list[str] = ["Cursor 1", "Cursor 2"]
        self._cached_delta_y: float | None = None
        self._cached_delta_show: bool = False
        self._cached_delta_color: tuple = (200, 200, 200)

        # Mouse tracking to determine nearest cursor
        self._mouse_proxy = pg.SignalProxy(
            self._pi.scene().sigMouseMoved,
            rateLimit=30,
            slot=self._on_mouse_moved,
        )

        # Reposition chevrons whenever the view range is panned or zoomed.
        self._pi.vb.sigRangeChanged.connect(lambda *_: self._update_chevrons())

    # ------------------------------------------------------------------
    # Public API (called by CursorController)
    # ------------------------------------------------------------------

    def apply_mode(self, mode: CursorMode, positions: list[float]) -> None:
        """Show/hide lines and set their positions."""
        self._mode = mode
        self._lines[0].setVisible(mode in (CursorMode.ONE, CursorMode.TWO))
        self._lines[1].setVisible(mode == CursorMode.TWO)
        if mode != CursorMode.HIDDEN:
            self._lines[0].setValue(positions[0])
        if mode == CursorMode.TWO:
            self._lines[1].setValue(positions[1])
        if mode != CursorMode.TWO:
            self._delta_line.setVisible(False)
            self._delta_label.setVisible(False)
        self._refresh_label_visibility()
        self._update_chevrons()

    def update_delta_time(
        self,
        x1: float,
        x2: float,
        delta_t_str: str,
        y_pos: float | None,
        show: bool,
        color: tuple,
    ) -> None:
        """Show or hide the horizontal delta-time line and its label.

        If *y_pos* is None the line is placed at 10 % from the top of the
        current view range.  The caller is notified of the chosen position
        via the ``delta_line_moved`` signal so it can persist it.
        """
        if not show:
            self._delta_line.setVisible(False)
            self._delta_label.setVisible(False)
            self._cached_delta_show = False
            self._cached_delta_y = None
            self._update_chevrons()
            return

        pen = pg.mkPen(color=color, width=1, style=Qt.PenStyle.DashLine)
        self._delta_line.setPen(pen)
        self._delta_label.setColor(color)

        if y_pos is None:
            try:
                y_min, y_max = self._pi.vb.viewRange()[1]
            except Exception:
                y_min, y_max = 0.0, 1.0
            y_pos = y_max - 0.1 * (y_max - y_min)

        mid_x = (x1 + x2) / 2.0
        self._delta_label_x = mid_x  # must be set before setValue fires sigPositionChanged
        self._delta_line.setValue(y_pos)  # fires _on_delta_line_pos_changed → updates label
        self._delta_line.setVisible(True)

        self._delta_label.setText(delta_t_str)
        self._delta_label.setPos(mid_x, y_pos)
        self._delta_label.setVisible(True)

        self._cached_delta_y = y_pos
        self._cached_delta_show = True
        self._cached_delta_color = color
        self._update_chevrons()

    def update_labels(
        self,
        active_signals: list[ActiveSignal],
        positions: list[float],
        mode: CursorMode,
    ) -> None:
        """Create or reposition value labels for all signal × cursor pairs.

        Each label is parented to the signal's own ViewBox so it stays
        anchored to the correct Y position even when the Y axis is panned
        or zoomed independently.
        """
        self._mode = mode
        current_keys: set[tuple[int, ActiveSignal]] = set()

        for ci in range(2):
            if ci == 1 and mode != CursorMode.TWO:
                continue
            x = positions[ci]
            for active in active_signals:
                vb = active.view_box
                if vb is None:
                    continue
                key = (ci, active)
                current_keys.add(key)
                y = _interpolate(active, x)
                if y is None:
                    if key in self._labels:
                        self._labels[key][0].setVisible(False)
                    continue
                cached = self._labels.get(key)
                if cached is None or cached[1] is not vb:
                    # No label yet, or the signal's ViewBox changed (axis
                    # sharing/linking/ungrouping can destroy or replace it) —
                    # detach from the stale ViewBox and recreate in the new one.
                    if cached is not None:
                        cached[1].removeItem(cached[0])
                    lbl = pg.TextItem(
                        text="",
                        color=active.color,
                        anchor=(0.0, 1.0),
                    )
                    vb.addItem(lbl, ignoreBounds=True)
                    self._labels[key] = (lbl, vb)
                lbl, _ = self._labels[key]
                em = active.metadata.enum_map
                if em and active.enum_display_cursor:
                    iv = int(round(y))
                    label = em.get(iv)
                    text = f"{label} ({iv})" if label is not None else f"{y:.4g}"
                else:
                    text = f"{y:.4g}"
                lbl.setText(text)
                lbl.setPos(x, y)

        # Remove labels for keys no longer needed
        stale = set(self._labels) - current_keys
        for key in stale:
            lbl, vb = self._labels.pop(key)
            vb.removeItem(lbl)

        self._refresh_label_visibility()
        self._update_chevrons()

    def set_line_colors(self, color0: tuple, color1: tuple) -> None:
        """Update the pen color of each cursor line (RGB tuples)."""
        for line, color in zip(self._lines, (color0, color1)):
            line.setPen(pg.mkPen(color=color, width=1, style=Qt.PenStyle.DashLine))
        self._line_colors = [color0, color1]
        self._update_chevrons()

    def set_cursor_names(self, name0: str, name1: str) -> None:
        """Update the cursor names used in chevron tooltips."""
        self._cursor_names = [name0, name1]
        self._update_chevrons()

    def recolor_labels(self, active: ActiveSignal, color) -> None:
        """Update the color of all existing labels for a specific signal."""
        for (_, sig), (lbl, _) in self._labels.items():
            if sig is active:
                lbl.setColor(color)

    def remove_labels_for(self, active: ActiveSignal) -> None:
        """Remove all labels for a specific signal.

        Must be called before the signal's ViewBox is destroyed.
        """
        stale = [k for k in self._labels if k[1] is active]
        for key in stale:
            lbl, vb = self._labels.pop(key)
            vb.removeItem(lbl)

    def clear_labels(self) -> None:
        """Remove all value labels from the plot.

        Must be called before signal ViewBoxes are destroyed.
        """
        for lbl, vb in self._labels.values():
            vb.removeItem(lbl)
        self._labels.clear()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_delta_line_pos_changed(self, line: pg.InfiniteLine) -> None:
        y = line.value()
        self._cached_delta_y = y
        if self._delta_label.isVisible():
            self._delta_label.setPos(self._delta_label_x, y)
        self._update_chevrons()
        self.delta_line_moved.emit(y)

    def _refresh_label_visibility(self) -> None:
        for (ci, _), (lbl, _) in self._labels.items():
            lbl.setVisible(self._should_show(ci))

    def _should_show(self, cursor_idx: int) -> bool:
        if self._mode == CursorMode.HIDDEN:
            return False
        if self._mode == CursorMode.ONE:
            return cursor_idx == 0
        # TWO: show only the cursor nearest the mouse
        return cursor_idx == self._nearest_cursor

    def _on_mouse_moved(self, event: tuple) -> None:
        if self._mode != CursorMode.TWO:
            return
        pos = event[0]
        if not self._pi.vb.sceneBoundingRect().contains(pos):
            return
        mouse_x = self._pi.vb.mapSceneToView(pos).x()
        d0 = abs(mouse_x - self._lines[0].value())
        d1 = abs(mouse_x - self._lines[1].value())
        nearest = 0 if d0 <= d1 else 1
        if nearest != self._nearest_cursor:
            self._nearest_cursor = nearest
            self._refresh_label_visibility()

    def _update_chevrons(self) -> None:
        """Reposition and show/hide edge chevrons for off-screen elements."""
        if self._mode == CursorMode.HIDDEN:
            for chev in self._c_chevrons:
                chev.setVisible(False)
            self._dt_chevron.setVisible(False)
            return

        try:
            x_min, x_max = self._pi.vb.viewRange()[0]
            y_min, y_max = self._pi.vb.viewRange()[1]
        except Exception:
            return

        y_span = y_max - y_min
        y_center = (y_min + y_max) / 2.0
        n_cursors = 2 if self._mode == CursorMode.TWO else 1

        # Classify each active cursor as off-screen left, right, or on-screen.
        left_idxs: list[int] = []
        right_idxs: list[int] = []
        on_idxs: list[int] = []
        for i in range(n_cursors):
            x = self._lines[i].value()
            if x < x_min:
                left_idxs.append(i)
            elif x > x_max:
                right_idxs.append(i)
            else:
                on_idxs.append(i)

        def _y_positions(group: list[int]) -> list[float]:
            if len(group) <= 1:
                return [y_center]
            return [y_center + 0.07 * y_span, y_center - 0.07 * y_span]

        def _apply(idxs: list[int], text: str, anchor: tuple, edge_x: float) -> None:
            ys = _y_positions(idxs)
            for j, i in enumerate(idxs):
                chev = self._c_chevrons[i]
                chev.setColor(self._line_colors[i])
                chev.setText(text)
                chev.setAnchor(anchor)
                chev.setPos(edge_x, ys[j])
                chev.setToolTip(f"Fetch {self._cursor_names[i]}")
                chev.setVisible(True)

        _apply(left_idxs, "<", (0.0, 0.5), x_min)
        _apply(right_idxs, ">", (1.0, 0.5), x_max)
        for i in on_idxs:
            self._c_chevrons[i].setVisible(False)
        if self._mode == CursorMode.ONE:
            self._c_chevrons[1].setVisible(False)

        # Delta-time chevron — only visible in TWO mode when enabled.
        if self._cached_delta_show and self._cached_delta_y is not None:
            x_center = (x_min + x_max) / 2.0
            dy = self._cached_delta_y
            if dy > y_max:
                self._dt_chevron.setColor(self._cached_delta_color)
                self._dt_chevron.setText("^")
                self._dt_chevron.setAnchor((0.5, 0.0))
                self._dt_chevron.setPos(x_center, y_max)
                self._dt_chevron.setVisible(True)
            elif dy < y_min:
                self._dt_chevron.setColor(self._cached_delta_color)
                self._dt_chevron.setText("v")
                self._dt_chevron.setAnchor((0.5, 1.0))
                self._dt_chevron.setPos(x_center, y_min)
                self._dt_chevron.setVisible(True)
            else:
                self._dt_chevron.setVisible(False)
        else:
            self._dt_chevron.setVisible(False)

