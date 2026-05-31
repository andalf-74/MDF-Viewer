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

from mdf_viewer.controller.cursor_controller import CursorMode

if TYPE_CHECKING:
    from mdf_viewer.view_model.active_signal import ActiveSignal

# Cursor line style
_CURSOR_PEN = pg.mkPen(color=(220, 220, 50), width=1, style=Qt.PenStyle.DashLine)


class CursorView(QObject):
    """Manages the draggable cursor InfiniteLines and their value labels."""

    cursor_moved = pyqtSignal(int, float)  # (cursor_index, x_position)

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
                lambda l, idx=i: self.cursor_moved.emit(idx, l.value())
            )
            self._lines.append(line)

        # (cursor_index, ActiveSignal) → (TextItem, ViewBox)
        # Labels are owned by the signal's ViewBox so they track Y pan/zoom.
        self._labels: dict[tuple[int, ActiveSignal], tuple[pg.TextItem, pg.ViewBox]] = {}

        # Mouse tracking to determine nearest cursor
        self._mouse_proxy = pg.SignalProxy(
            self._pi.scene().sigMouseMoved,
            rateLimit=30,
            slot=self._on_mouse_moved,
        )

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
        self._refresh_label_visibility()

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
                if key not in self._labels:
                    lbl = pg.TextItem(
                        text="",
                        color=active.color,
                        anchor=(0.0, 1.0),
                    )
                    vb.addItem(lbl)
                    self._labels[key] = (lbl, vb)
                lbl, _ = self._labels[key]
                unit = active.metadata.unit
                lbl.setText(f"{y:.4g}{(' ' + unit) if unit else ''}")
                lbl.setPos(x, y)

        # Remove labels for keys no longer needed
        stale = set(self._labels) - current_keys
        for key in stale:
            lbl, vb = self._labels.pop(key)
            vb.removeItem(lbl)

        self._refresh_label_visibility()

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


# ---------------------------------------------------------------------------
# Shared helper (also used by CursorController)
# ---------------------------------------------------------------------------

def _interpolate(active: ActiveSignal, x: float) -> float | None:
    """Linearly interpolate the signal value at timestamp *x*."""
    import numpy as np
    ts = active.data.timestamps
    ys = active.data.samples
    if len(ts) == 0 or x < ts[0] or x > ts[-1]:
        return None
    idx = int(np.searchsorted(ts, x))
    if idx == 0:
        return float(ys[0])
    if idx >= len(ts):
        return float(ys[-1])
    t0, t1 = float(ts[idx - 1]), float(ts[idx])
    y0, y1 = float(ys[idx - 1]), float(ys[idx])
    alpha = (x - t0) / (t1 - t0) if t1 != t0 else 0.0
    return y0 + alpha * (y1 - y0)
