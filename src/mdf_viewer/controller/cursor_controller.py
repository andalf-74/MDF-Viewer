"""CursorController — owns cursor toggle state and position memory.

Cursor behaviour is self-contained enough to isolate from AppController:
  * toggle cycle: HIDDEN -> ONE -> TWO -> HIDDEN
  * remembers each cursor's last position across hide/show
  * computes per-signal interpolated values and delta
  * drives ActiveSignalsTable cursor columns and CursorView labels

The active signal list is *not* stored here — it is read on demand via
the ``get_active_signals`` callable injected at construction, so there is
a single authoritative list (owned by AppController).
"""

from __future__ import annotations

from enum import Enum, auto
from typing import TYPE_CHECKING, Callable

import numpy as np

if TYPE_CHECKING:
    from mdf_viewer.controller.interfaces import CursorValueSinkProtocol, CursorViewProtocol
    from mdf_viewer.view_model.active_signal import ActiveSignal

_ModeCallback = Callable[["CursorMode"], None]


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
        cursor_view: CursorViewProtocol,
        get_x_range: Callable[[], tuple[float, float]],
        active_signals_table: CursorValueSinkProtocol,
        get_active_signals: Callable[[], list] | None = None,
        get_cursor_persistent: Callable[[], bool] | None = None,
    ) -> None:
        """
        Parameters
        ----------
        cursor_view:
            The CursorView that owns the InfiniteLines in the plot.
        get_x_range:
            Callable returning the current plot X range as (x_min, x_max).
            Used to place cursors on first activation.
        active_signals_table:
            ActiveSignalsTable — receives update_cursor_values calls.
        get_active_signals:
            Callable returning the current list of ActiveSignal objects.
            AppController passes ``lambda: controller.active_signals``.
            Defaults to an empty-list callable when omitted (useful in tests
            that only exercise toggle/mode behaviour).
        get_cursor_persistent:
            Callable returning whether cursors should remember their last
            position across hide/show cycles.  Defaults to ``lambda: True``.
        """
        self._view = cursor_view
        self._get_x_range = get_x_range
        self._table = active_signals_table
        self._get_active_signals: Callable[[], list] = (
            get_active_signals if get_active_signals is not None else (lambda: [])
        )
        self._get_cursor_persistent: Callable[[], bool] = (
            get_cursor_persistent if get_cursor_persistent is not None else (lambda: True)
        )

        self._mode = CursorMode.HIDDEN
        self._positions: list[float] = [0.0, 0.0]
        self._initialized = False
        self._mode_changed_cb: _ModeCallback | None = None

        cursor_view.cursor_moved.connect(self._on_cursor_dragged)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def mode(self) -> CursorMode:
        return self._mode

    def set_mode_changed_callback(self, cb: _ModeCallback) -> None:
        """Register a callable invoked with the new CursorMode on every mode change."""
        self._mode_changed_cb = cb

    def zoom_to_cursors(self) -> tuple[float, float] | None:
        """Return (x_min, x_max) spanning the two cursors, or None if not in TWO mode."""
        if self._mode != CursorMode.TWO:
            return None
        x1, x2 = self._positions
        return (min(x1, x2), max(x1, x2))

    def toggle(self) -> None:
        """Advance: HIDDEN → ONE → TWO → HIDDEN."""
        if self._mode == CursorMode.HIDDEN:
            self._ensure_initialized()
            self._mode = CursorMode.ONE
        elif self._mode == CursorMode.ONE:
            self._mode = CursorMode.TWO
        else:
            self._mode = CursorMode.HIDDEN
        self._commit_mode()

    def press_cursor1(self) -> None:
        """Dot key: HIDDEN→ONE, ONE→HIDDEN, TWO→ONE."""
        if self._mode == CursorMode.HIDDEN:
            self._ensure_initialized()
            self._mode = CursorMode.ONE
        elif self._mode == CursorMode.ONE:
            self._mode = CursorMode.HIDDEN
        else:  # TWO
            self._mode = CursorMode.ONE
        self._commit_mode()

    def press_cursor2(self) -> None:
        """Comma key: HIDDEN→TWO, ONE→TWO, TWO→HIDDEN."""
        if self._mode == CursorMode.HIDDEN:
            self._ensure_initialized()
            self._mode = CursorMode.TWO
        elif self._mode == CursorMode.ONE:
            self._mode = CursorMode.TWO
        else:  # TWO
            self._mode = CursorMode.HIDDEN
        self._commit_mode()

    def reset(self) -> None:
        """Called by AppController on file load — next toggle re-places cursors."""
        self._initialized = False
        if self._mode != CursorMode.HIDDEN:
            self._mode = CursorMode.HIDDEN
            self._view.apply_mode(CursorMode.HIDDEN, self._positions)
            self._table.show_cursor_columns(False)
            if self._mode_changed_cb is not None:
                self._mode_changed_cb(self._mode)

    def recolor_signal(self, active: ActiveSignal, color) -> None:
        """Update cursor label colors when a signal's color changes."""
        self._view.recolor_labels(active, color)

    def on_signal_removed(self, active: ActiveSignal) -> None:
        """Remove cursor labels before the signal's ViewBox is destroyed.

        Must be called *before* PlotArea.remove_signal() so the ViewBox
        is still in the scene when the label is removed.
        """
        self._view.remove_labels_for(active)

    def on_all_signals_cleared(self) -> None:
        """Clear all cursor labels before ViewBoxes are destroyed."""
        self._view.clear_labels()

    def refresh(self) -> None:
        """Re-compute cursor values and labels for the current active signals.

        Called by AppController after any change to the active signal list
        (add, remove, reorder).
        """
        self._refresh(update_labels=True)

    # ------------------------------------------------------------------
    # Slots (private)
    # ------------------------------------------------------------------

    def _on_cursor_dragged(self, index: int, x: float) -> None:
        self._positions[index] = x
        self._refresh(update_labels=True)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _ensure_initialized(self) -> None:
        if not self._initialized:
            self._place_viewport_positions()
            self._initialized = True
        elif not self._get_cursor_persistent():
            self._place_viewport_positions()

    def _commit_mode(self) -> None:
        self._view.apply_mode(self._mode, self._positions)
        self._table.show_cursor_columns(self._mode != CursorMode.HIDDEN)
        self._refresh(update_labels=True)
        if self._mode_changed_cb is not None:
            self._mode_changed_cb(self._mode)

    def _place_viewport_positions(self) -> None:
        try:
            x_min, x_max = self._get_x_range()
        except Exception:
            x_min, x_max = 0.0, 1.0
        span = max(x_max - x_min, 0.0)
        self._positions[0] = x_min + span * 0.25
        self._positions[1] = x_min + span * 0.75

    def _refresh(self, *, update_labels: bool) -> None:
        """Update table values and (optionally) plot labels."""
        if self._mode == CursorMode.HIDDEN:
            return

        active_signals = self._get_active_signals()
        c1_x = self._positions[0]
        c2_x = self._positions[1] if self._mode == CursorMode.TWO else None

        for active in active_signals:
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
                active_signals, self._positions, self._mode
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
