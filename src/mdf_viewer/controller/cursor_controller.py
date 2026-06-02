"""CursorController — owns cursor toggle state and position memory.

Cursor behaviour is self-contained enough to isolate from AppController:
  * toggle cycle: HIDDEN -> ONE -> TWO -> HIDDEN
  * remembers each cursor's last position across hide/show
  * computes per-signal interpolated values and delta
  * drives ActiveSignalsTable cursor columns and CursorView labels
"""

from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING, Callable

import numpy as np

if TYPE_CHECKING:
    from mdf_viewer.view.cursors import CursorView
    from mdf_viewer.view_model.active_signal import ActiveSignal


class CursorMode(Enum):
    """The three states cycled by the Cursor Toggle toolbar button."""

    HIDDEN = auto()
    ONE = auto()
    TWO = auto()


class CursorController:
    """Manages cursor mode, remembered positions, and value computation.

    Dependencies are injected so the class remains testable without a
    QApplication or real MDF file.
    """

    def __init__(
        self,
        cursor_view: CursorView,
        get_x_range: Callable[[], tuple[float, float]],
        active_signals_table,
    ) -> None:
        """
        Parameters
        ----------
        cursor_view:
            The CursorView that owns the InfiniteLines in the plot.
        get_x_range:
            Callable returning the current plot X range as (x_min, x_max).
            Used to place cursors sensibly on first activation.
        active_signals_table:
            ActiveSignalsTable — receives update_cursor_values calls.
        """
        self._view = cursor_view
        self._get_x_range = get_x_range
        self._table = active_signals_table

        self._mode = CursorMode.HIDDEN
        self._positions: list[float] = [0.0, 0.0]
        self._initialized = False  # False → place at view range on first toggle
        self._active_signals: list[ActiveSignal] = []

        cursor_view.cursor_moved.connect(self._on_cursor_dragged)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def mode(self) -> CursorMode:
        return self._mode

    def toggle(self) -> None:
        """Advance: HIDDEN → ONE → TWO → HIDDEN."""
        if self._mode == CursorMode.HIDDEN:
            if not self._initialized:
                self._place_initial_positions()
                self._initialized = True
            self._mode = CursorMode.ONE
        elif self._mode == CursorMode.ONE:
            self._mode = CursorMode.TWO
        else:
            self._mode = CursorMode.HIDDEN

        self._view.apply_mode(self._mode, self._positions)
        self._table.show_cursor_columns(self._mode != CursorMode.HIDDEN)
        self._refresh(update_labels=True)

    def reset(self) -> None:
        """Called by AppController on file load — next toggle re-places cursors."""
        self._initialized = False
        if self._mode != CursorMode.HIDDEN:
            self._mode = CursorMode.HIDDEN
            self._view.apply_mode(CursorMode.HIDDEN, self._positions)
            self._table.show_cursor_columns(False)

    def recolor_signal(self, active: ActiveSignal, color) -> None:
        """Update cursor label colors when a signal's color changes."""
        self._view.recolor_labels(active, color)

    def on_signal_added(self, active: ActiveSignal) -> None:
        self._active_signals.append(active)
        self._refresh(update_labels=True)

    def on_signal_removed(self, active: ActiveSignal) -> None:
        if active in self._active_signals:
            self._active_signals.remove(active)
        self._view.remove_labels_for(active)
        self._refresh(update_labels=False)

    def on_all_signals_cleared(self) -> None:
        self._active_signals.clear()
        self._view.clear_labels()

    # ------------------------------------------------------------------
    # Slots (private)
    # ------------------------------------------------------------------

    def _on_cursor_dragged(self, index: int, x: float) -> None:
        self._positions[index] = x
        self._refresh(update_labels=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _place_initial_positions(self) -> None:
        if self._active_signals:
            ts_all = [s.data.timestamps for s in self._active_signals if len(s.data.timestamps)]
            if ts_all:
                x_min = float(min(t[0] for t in ts_all))
                x_max = float(max(t[-1] for t in ts_all))
            else:
                x_min, x_max = 0.0, 1.0
        else:
            try:
                x_min, x_max = self._get_x_range()
            except Exception:
                x_min, x_max = 0.0, 1.0
        span = max(x_max - x_min, 0.0)
        self._positions[0] = x_min
        self._positions[1] = x_min + span * 0.1

    def _refresh(self, *, update_labels: bool) -> None:
        """Update table values and (optionally) plot labels."""
        if self._mode == CursorMode.HIDDEN:
            return

        c1_x = self._positions[0]
        c2_x = self._positions[1] if self._mode == CursorMode.TWO else None

        for active in self._active_signals:
            c1_val = _interpolate(active, c1_x)
            c2_val = _interpolate(active, c2_x) if c2_x is not None else None

            delta: float | None = None
            if c1_val is not None and c2_val is not None:
                delta = c2_val - c1_val

            self._table.update_cursor_values(
                active,
                _fmt(c1_val),
                _fmt(c2_val),
                _fmt(delta),
            )

        if update_labels:
            self._view.update_labels(
                self._active_signals, self._positions, self._mode
            )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _interpolate(active: ActiveSignal, x: float) -> float | None:
    """Linearly interpolate the signal value at timestamp *x*."""
    ts = active.data.timestamps
    ys = active.data.samples
    if len(ts) == 0 or x < ts[0] or x > ts[-1]:
        return None
    idx = int(np.searchsorted(ts, x))
    if idx == 0:
        return float(ys[0])
    if idx >= len(ts):
        return float(ys[-1])
    y0 = float(ys[idx - 1])
    if active.step_mode:
        return y0
    t0, t1 = float(ts[idx - 1]), float(ts[idx])
    y1 = float(ys[idx])
    alpha = (x - t0) / (t1 - t0) if t1 != t0 else 0.0
    return y0 + alpha * (y1 - y0)


def _fmt(value: float | None) -> str:
    """Format a cursor value for display in the table."""
    if value is None:
        return ""
    return f"{value:.6g}"
