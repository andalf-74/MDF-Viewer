"""CursorView / CursorStripesView — draggable vertical cursor lines and their value labels.

CursorView renders one stripe's worth of cursor/delta-time InfiniteLines and
their off-screen chevrons — it has no knowledge of other stripes. The toggle
cycle and position memory live in CursorController; this class only handles
the visual representation for its own stripe.

CursorStripesView composes one CursorView per stripe into a single object
satisfying the same CursorViewProtocol CursorController talks to, so
CursorController itself needs no stripe-awareness at all. It owns everything
that is NOT inherently per-scene: value labels (already parented to each
signal's own ViewBox, so they're stripe-correct without any extra work),
nearest-cursor tracking (mouse can be over any stripe), and cross-stripe
lockstep propagation of cursor-line drags (REQ-PLOT-182). The delta-time line
is the one exception — it's shown in only the active stripe at a time
(REQ-PLOT-105/183), so CursorStripesView routes update_delta_time() there and
suppresses it everywhere else. See CursorStripesView below for all of this.

Label visibility rule: with ONE cursor, its labels are always shown; with
TWO cursors, only the cursor nearest the mouse pointer shows its labels.
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
    """Manages one stripe's draggable cursor/delta-time InfiniteLines and chevrons.

    Has no knowledge of value labels or other stripes — see CursorStripesView,
    which composes one CursorView per stripe and owns everything cross-stripe.
    """

    cursor_moved = pyqtSignal(int, float)            # (cursor_index, x_position)
    cursor_clicked = pyqtSignal(int)                 # (cursor_index) — clicked without drag
    delta_line_moved = pyqtSignal(float)             # (y_position)
    cursor_fetch_requested = pyqtSignal(int, float)  # (cursor_index, x_data) — chevron clicked
    delta_fetch_requested = pyqtSignal(float)        # (y_data) — delta-time chevron clicked

    def __init__(self, plot_item: pg.PlotItem, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._pi = plot_item
        self._mode = CursorMode.HIDDEN

        # DragClaimant state (see PlotStripe.register_drag_claimant).
        self._drag_line: pg.InfiniteLine | None = None
        self._dragged: bool = False

        # Two InfiniteLines, both hidden initially.
        self._lines: list[pg.InfiniteLine] = []
        for i in range(2):
            line = pg.InfiniteLine(angle=90, movable=True, pen=_CURSOR_PEN)
            line.setVisible(False)
            self._pi.addItem(line, ignoreBounds=True)
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
        self._pi.addItem(self._delta_line, ignoreBounds=True)
        self._delta_line.sigPositionChanged.connect(self._on_delta_line_pos_changed)

        # Delta-time label, parented to the main ViewBox.
        self._delta_label = pg.TextItem(text="", color=(200, 200, 200), anchor=(0.5, 1.0))
        self._delta_label.setVisible(False)
        self._pi.vb.addItem(self._delta_label, ignoreBounds=True)
        self._delta_label_x: float = 0.0  # last known midpoint X, updated in update_delta_time

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

        # Reposition chevrons whenever the view range is panned or zoomed.
        self._pi.vb.sigRangeChanged.connect(lambda *_: self._update_chevrons())

    # ------------------------------------------------------------------
    # DragClaimant protocol (registered with PlotArea.register_drag_claimant)
    # ------------------------------------------------------------------
    #
    # Cursor/delta lines live in pi.vb, while each signal gets its own
    # top-level ViewBox — real Qt scene Z-order does not compare consistently
    # between the two (#78). Rather than fight that comparison, PlotArea gives
    # this claimant first look at every left-button press: hit_test() uses
    # each line's own sceneBoundingRect() (the same margin pyqtgraph's native
    # drag/hover already uses) to decide, independent of Z-order entirely.
    # Once claimed, the drag is driven directly via setValue() instead of
    # pyqtgraph's native mouseDragEvent, which never runs for a claimed press.

    def hit_test(self, scene_pos) -> pg.InfiniteLine | None:
        """Return the topmost visible cursor/delta line under scene_pos, or None."""
        for line in (self._delta_line, *self._lines):
            if line.isVisible() and line.sceneBoundingRect().contains(scene_pos):
                return line
        return None

    def on_press(self, line: pg.InfiniteLine, scene_pos) -> None:
        self._drag_line = line
        self._dragged = False

    def on_move(self, line: pg.InfiniteLine, scene_pos) -> None:
        self._dragged = True
        v = self._pi.vb.mapSceneToView(scene_pos)
        line.setValue(v.x() if line.angle == 90 else v.y())

    def on_release(self, line: pg.InfiniteLine, scene_pos) -> None:
        if not self._dragged and line in self._lines:
            self.cursor_clicked.emit(self._lines.index(line))
        self._drag_line = None

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


class CursorStripesView(QObject):
    """Composes one CursorView per stripe into a single CursorViewProtocol.

    CursorController talks to this exactly as it would a single CursorView —
    it has no idea multiple stripes exist. This class is responsible for:

    - Cross-stripe lockstep cursor-line dragging (REQ-PLOT-182): dragging a
      cursor line in any one stripe's CursorView re-applies the resulting
      position to every other stripe's CursorView, guarded by a
      ``_propagating`` flag against feedback loops (same pattern as
      PlotStripe's own ``_syncing_y`` for Synced Y-axis groups).
    - Routing update_delta_time() to only the active stripe's CursorView,
      hiding it everywhere else (REQ-PLOT-105/183) — the delta-time line is
      not duplicated across stripes.
    - Value labels, lifted verbatim from CursorView: they were always parented
      to each signal's own ViewBox rather than to any one stripe's PlotItem,
      so centralizing them here needs no change to that logic at all.
    - Nearest-cursor tracking for label visibility, listening to mouse-move on
      every stripe's own scene (the user's mouse can be over any of them).
    """

    cursor_moved = pyqtSignal(int, float)
    cursor_clicked = pyqtSignal(int)
    delta_line_moved = pyqtSignal(float)
    cursor_fetch_requested = pyqtSignal(int, float)
    delta_fetch_requested = pyqtSignal(float)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._per_stripe: dict[object, CursorView] = {}
        self._mouse_proxies: dict[object, pg.SignalProxy] = {}
        self._active_stripe: object | None = None

        # Mirrors CursorController's own state so a freshly added stripe (or
        # one whose line echoes a sibling's drag) can be brought up to date
        # immediately rather than waiting for the next unrelated cursor move.
        self._mode = CursorMode.HIDDEN
        self._positions: list[float] = [0.0, 0.0]
        self._line_colors: tuple = ((220, 220, 50), (255, 140, 0))
        self._cursor_names: tuple = ("Cursor 1", "Cursor 2")
        self._propagating = False

        self._nearest_cursor: int = 0
        # (cursor_index, ActiveSignal) → (TextItem, ViewBox) — lifted verbatim
        # from CursorView; labels are parented to the signal's own ViewBox so
        # they're already correct regardless of which stripe that signal is in.
        self._labels: dict[tuple[int, ActiveSignal], tuple[pg.TextItem, pg.ViewBox]] = {}

    # ------------------------------------------------------------------
    # Stripe lifecycle (wired directly to PlotStripesArea in app.py)
    # ------------------------------------------------------------------

    def add_stripe(self, stripe) -> None:
        view = CursorView(stripe.plot_item)
        stripe.register_drag_claimant(view)
        view.cursor_moved.connect(lambda idx, x, v=view: self._on_cursor_moved(v, idx, x))
        view.cursor_clicked.connect(self.cursor_clicked)
        view.delta_line_moved.connect(self.delta_line_moved)
        view.cursor_fetch_requested.connect(self.cursor_fetch_requested)
        view.delta_fetch_requested.connect(self.delta_fetch_requested)

        # Bring the new stripe's own cursor rendering up to the current state.
        view.apply_mode(self._mode, self._positions)
        view.set_line_colors(*self._line_colors)
        view.set_cursor_names(*self._cursor_names)

        self._per_stripe[stripe] = view
        self._mouse_proxies[stripe] = pg.SignalProxy(
            stripe.plot_item.scene().sigMouseMoved,
            rateLimit=30,
            slot=lambda ev, s=stripe: self._on_mouse_moved(s, ev),
        )
        if self._active_stripe is None:
            self._active_stripe = stripe

    def remove_stripe(self, stripe) -> None:
        view = self._per_stripe.pop(stripe, None)
        self._mouse_proxies.pop(stripe, None)
        if view is not None:
            view.deleteLater()
        if self._active_stripe is stripe:
            self._active_stripe = next(iter(self._per_stripe), None)

    def set_active_stripe(self, stripe) -> None:
        """Record the new active stripe.

        Does not by itself move the delta-time line —
        CursorController.on_active_stripe_changed() re-triggers
        update_delta_time() once this has been called, so ordering the two
        connections matters (see app.py).
        """
        self._active_stripe = stripe

    # ------------------------------------------------------------------
    # CursorViewProtocol — called by CursorController
    # ------------------------------------------------------------------

    def apply_mode(self, mode: CursorMode, positions: list[float]) -> None:
        self._mode = mode
        self._positions = list(positions)
        for view in self._per_stripe.values():
            view.apply_mode(mode, positions)
        self._refresh_label_visibility()

    def update_delta_time(
        self,
        x1: float,
        x2: float,
        delta_t_str: str,
        y_pos: float | None,
        show: bool,
        color: tuple,
    ) -> None:
        for stripe, view in self._per_stripe.items():
            if show and stripe is self._active_stripe:
                view.update_delta_time(x1, x2, delta_t_str, y_pos, True, color)
            else:
                view.update_delta_time(x1, x2, delta_t_str, y_pos=None, show=False, color=color)

    def update_labels(
        self,
        active_signals: list[ActiveSignal],
        positions: list[float],
        mode: CursorMode,
    ) -> None:
        """Create or reposition value labels for all signal × cursor pairs.

        Lifted from CursorView unchanged: each label is parented to the
        signal's own ViewBox, which is already correct no matter which
        stripe currently owns that signal.
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

    def set_line_colors(self, color0: tuple, color1: tuple) -> None:
        self._line_colors = (color0, color1)
        for view in self._per_stripe.values():
            view.set_line_colors(color0, color1)

    def set_cursor_names(self, name0: str, name1: str) -> None:
        self._cursor_names = (name0, name1)
        for view in self._per_stripe.values():
            view.set_cursor_names(name0, name1)

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

    def _on_cursor_moved(self, source_view: CursorView, index: int, x: float) -> None:
        if self._propagating:
            # This call is an echo of our own apply_mode() fan-out below
            # (setValue() on a sibling's line re-fires its sigPositionChanged)
            # — not a new, independent drag. Ignore it entirely so
            # CursorController sees exactly one cursor_moved per user action.
            return
        self._positions[index] = x
        self._propagating = True
        try:
            for view in self._per_stripe.values():
                if view is not source_view:
                    view.apply_mode(self._mode, self._positions)
        finally:
            self._propagating = False
        self.cursor_moved.emit(index, x)

    def _on_mouse_moved(self, stripe, event: tuple) -> None:
        if self._mode != CursorMode.TWO:
            return
        pos = event[0]
        vb = stripe.plot_item.vb
        if not vb.sceneBoundingRect().contains(pos):
            return
        mouse_x = vb.mapSceneToView(pos).x()
        d0 = abs(mouse_x - self._positions[0])
        d1 = abs(mouse_x - self._positions[1])
        nearest = 0 if d0 <= d1 else 1
        if nearest != self._nearest_cursor:
            self._nearest_cursor = nearest
            self._refresh_label_visibility()

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

