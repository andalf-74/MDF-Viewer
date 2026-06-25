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
from typing import TYPE_CHECKING, Any, Callable

import numpy as np

from mdf_viewer.model.interpolate import interpolate as _interpolate

if TYPE_CHECKING:
    from mdf_viewer.controller.interfaces import CursorValueSinkProtocol, CursorViewProtocol
    from mdf_viewer.view_model.active_signal import ActiveSignal

_ModeCallback = Callable[["CursorMode"], None]

# Cursor line colors (RGB tuples consumed by CursorView.set_line_colors)
_COLOR_C1 = (220, 220, 50)   # yellow — Cursor 1 and Cursor L
_COLOR_C2 = (255, 140, 0)    # orange — Cursor 2
_COLOR_CR = (50, 150, 255)   # blue   — Cursor R


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
        get_cursor_mode: Callable[[], str] | None = None,
        get_cursor_colors: Callable[[], tuple] | None = None,
        get_y_range: Callable[[], tuple[float, float]] | None = None,
        get_show_delta_time: Callable[[], bool] | None = None,
        get_delta_time_color: Callable[[], tuple] | None = None,
        get_selected_signal: Callable[[], Any] | None = None,
        get_cursor_step_unit: Callable[[], str] | None = None,
        get_cursor_step_samples: Callable[[], int] | None = None,
        get_cursor_step_pixels: Callable[[], int] | None = None,
        get_cursor_step_time_ms: Callable[[], float] | None = None,
        get_x_per_pixel: Callable[[], float] | None = None,
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
        get_cursor_mode:
            Callable returning ``"1/2"`` or ``"L/R"``.  Defaults to
            ``lambda: "1/2"``.
        get_cursor_colors:
            Callable returning a 4-tuple ``(c1, c2, cl, cr)`` of RGB tuples.
            Defaults to the module-level color constants.
        get_y_range:
            Callable returning the current plot Y range as (y_min, y_max).
            Used to place the delta-time line on first TWO activation.
            Defaults to ``lambda: (0.0, 1.0)``.
        get_show_delta_time:
            Callable returning whether to show the delta-time line in the plot.
            Defaults to ``lambda: True``.
        get_delta_time_color:
            Callable returning the delta-time line color as an RGB tuple.
            Defaults to ``lambda: (200, 200, 200)``.
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
        self._get_cursor_mode: Callable[[], str] = (
            get_cursor_mode if get_cursor_mode is not None else (lambda: "1/2")
        )
        self._get_cursor_colors: Callable[[], tuple] = (
            get_cursor_colors
            if get_cursor_colors is not None
            else (lambda: (_COLOR_C1, _COLOR_C2, _COLOR_C1, _COLOR_CR))
        )
        self._get_y_range: Callable[[], tuple[float, float]] = (
            get_y_range if get_y_range is not None else (lambda: (0.0, 1.0))
        )
        self._get_show_delta_time: Callable[[], bool] = (
            get_show_delta_time if get_show_delta_time is not None else (lambda: True)
        )
        self._get_delta_time_color: Callable[[], tuple] = (
            get_delta_time_color
            if get_delta_time_color is not None
            else (lambda: (200, 200, 200))
        )
        self._get_selected_signal: Callable[[], Any] = (
            get_selected_signal if get_selected_signal is not None else (lambda: None)
        )
        self._get_cursor_step_unit: Callable[[], str] = (
            get_cursor_step_unit if get_cursor_step_unit is not None else (lambda: "samples")
        )
        self._get_cursor_step_samples: Callable[[], int] = (
            get_cursor_step_samples if get_cursor_step_samples is not None else (lambda: 1)
        )
        self._get_cursor_step_pixels: Callable[[], int] = (
            get_cursor_step_pixels if get_cursor_step_pixels is not None else (lambda: 1)
        )
        self._get_cursor_step_time_ms: Callable[[], float] = (
            get_cursor_step_time_ms if get_cursor_step_time_ms is not None else (lambda: 10.0)
        )
        self._get_x_per_pixel: Callable[[], float] = (
            get_x_per_pixel if get_x_per_pixel is not None else (lambda: 1.0)
        )

        self._mode = CursorMode.HIDDEN
        self._positions: list[float] = [0.0, 0.0]
        self._delta_y_pos: float | None = None
        self._initialized = False
        self._left_idx: int = 0
        self._mode_changed_cb: _ModeCallback | None = None
        self._active_cursor_idx: int | None = None

        cursor_view.cursor_moved.connect(self._on_cursor_dragged)
        cursor_view.cursor_clicked.connect(self._on_cursor_clicked)
        cursor_view.delta_line_moved.connect(self._on_delta_line_dragged)
        cursor_view.cursor_fetch_requested.connect(self._on_cursor_fetch)
        cursor_view.delta_fetch_requested.connect(self._on_delta_fetch)

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

    def press_left(self) -> None:
        """Move the active cursor one step to the left."""
        self._move_active_cursor(-1)

    def press_right(self) -> None:
        """Move the active cursor one step to the right."""
        self._move_active_cursor(+1)

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
        self._delta_y_pos = None
        self._active_cursor_idx = None
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

    def _on_cursor_clicked(self, index: int) -> None:
        self._active_cursor_idx = index

    def _on_cursor_dragged(self, index: int, x: float) -> None:
        self._active_cursor_idx = index
        self._positions[index] = x
        self._refresh(update_labels=True)

    def _on_delta_line_dragged(self, y: float) -> None:
        self._delta_y_pos = y

    def _on_cursor_fetch(self, index: int, x: float) -> None:
        """Move cursor to the X position clicked on the chevron."""
        self._positions[index] = x
        self._view.apply_mode(self._mode, self._positions)
        self._refresh(update_labels=True)

    def _on_delta_fetch(self, y: float) -> None:
        """Move the delta-time line to the Y position clicked on the chevron."""
        self._delta_y_pos = y
        self._refresh(update_labels=False)

    def _move_active_cursor(self, direction: int) -> None:
        """Move the active cursor one step in the given direction (-1 left, +1 right)."""
        if self._mode == CursorMode.HIDDEN:
            return
        idx = 0 if self._mode == CursorMode.ONE else self._active_cursor_idx
        if idx is None:
            return

        x = self._positions[idx]
        unit = self._get_cursor_step_unit()
        signal = self._get_selected_signal() or next(iter(self._get_active_signals()), None)

        if unit == "samples":
            if signal is None:
                return
            n = self._get_cursor_step_samples()
            new_x = self._step_by_sample(signal, x, direction, n)
        elif unit == "pixels":
            px = self._get_cursor_step_pixels()
            new_x = x + direction * px * self._get_x_per_pixel()
            new_x = self._clamp_to_signal(new_x, signal)
        else:  # "time"
            ms = self._get_cursor_step_time_ms()
            new_x = x + direction * ms / 1000.0
            new_x = self._clamp_to_signal(new_x, signal)

        self._positions[idx] = new_x
        self._view.apply_mode(self._mode, self._positions)
        self._refresh(update_labels=True)

    def _step_by_sample(self, signal: Any, x: float, direction: int, n: int) -> float:
        ts = signal.data.timestamps
        if len(ts) == 0:
            return x
        if direction > 0:
            idx = int(np.searchsorted(ts, x, side="right"))
            new_idx = min(idx + n - 1, len(ts) - 1)
        else:
            idx = int(np.searchsorted(ts, x, side="left")) - 1
            new_idx = max(idx - (n - 1), 0)
        return float(ts[new_idx])

    def _clamp_to_signal(self, x: float, signal: Any) -> float:
        if signal is not None and len(signal.data.timestamps) > 0:
            ts = signal.data.timestamps
            return max(float(ts[0]), min(float(ts[-1]), x))
        try:
            x_min, x_max = self._get_x_range()
            return max(x_min, min(x_max, x))
        except Exception:
            return x

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
        if self._mode == CursorMode.HIDDEN:
            self._active_cursor_idx = None
        elif self._mode == CursorMode.ONE:
            self._active_cursor_idx = 0
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
        """Update table values, cursor colors, and (optionally) plot labels."""
        if self._mode == CursorMode.HIDDEN:
            return

        cursor_mode = self._get_cursor_mode()
        active_signals = self._get_active_signals()
        color_c1, color_c2, color_cl, color_cr = self._get_cursor_colors()

        if cursor_mode == "L/R":
            self._table.set_cursor_column_headers("Cursor L", "Cursor R")
            if self._mode == CursorMode.TWO:
                p0, p1 = self._positions
                if p0 < p1:
                    self._left_idx = 0
                elif p1 < p0:
                    self._left_idx = 1
                # equal positions: keep _left_idx unchanged (tie-breaking)
                right_idx = 1 - self._left_idx
                cl_x = self._positions[self._left_idx]
                cr_x = self._positions[right_idx]
                line_colors: list = [None, None]
                line_colors[self._left_idx] = color_cl
                line_colors[right_idx] = color_cr
                self._view.set_line_colors(line_colors[0], line_colors[1])
                for active in active_signals:
                    cl_val = _interpolate(active, cl_x)
                    cr_val = _interpolate(active, cr_x)
                    delta: float | None = (
                        cr_val - cl_val
                        if cl_val is not None and cr_val is not None
                        else None
                    )
                    self._table.update_cursor_values(
                        active, _fmt(cl_val), _fmt(cr_val), _fmt(delta)
                    )
            else:  # ONE — single cursor is always Cursor L by definition
                self._view.set_line_colors(color_cl, color_cr)
                c_x = self._positions[0]
                for active in active_signals:
                    self._table.update_cursor_values(
                        active, _fmt(_interpolate(active, c_x)), "", ""
                    )
        else:  # "1/2" mode (default)
            self._table.set_cursor_column_headers("Cursor 1", "Cursor 2")
            self._view.set_line_colors(color_c1, color_c2)
            c1_x = self._positions[0]
            c2_x = self._positions[1] if self._mode == CursorMode.TWO else None
            for active in active_signals:
                c1_val = _interpolate(active, c1_x)
                c2_val = _interpolate(active, c2_x) if c2_x is not None else None
                delta2: float | None = (
                    c2_val - c1_val
                    if c1_val is not None and c2_val is not None
                    else None
                )
                self._table.update_cursor_values(
                    active, _fmt(c1_val), _fmt(c2_val), _fmt(delta2)
                )

        if update_labels:
            if cursor_mode == "L/R":
                n0 = "Cursor L" if self._left_idx == 0 else "Cursor R"
                n1 = "Cursor R" if self._left_idx == 0 else "Cursor L"
            else:
                n0, n1 = "Cursor 1", "Cursor 2"
            self._view.set_cursor_names(n0, n1)
            self._view.update_labels(active_signals, self._positions, self._mode)

        self._refresh_delta_time()

    def _refresh_delta_time(self) -> None:
        """Update the delta-time line, label, and table column header."""
        if self._mode == CursorMode.TWO:
            delta_t = abs(self._positions[1] - self._positions[0])
            delta_t_str = f"Δt = {delta_t:.4g} s"
            self._table.set_delta_column_header(delta_t_str)
            self._view.update_delta_time(
                x1=self._positions[0],
                x2=self._positions[1],
                delta_t_str=delta_t_str,
                y_pos=self._delta_y_pos,
                show=self._get_show_delta_time(),
                color=self._get_delta_time_color(),
            )
        else:
            self._table.set_delta_column_header("Δ")
            self._view.update_delta_time(
                x1=0.0, x2=0.0, delta_t_str="", y_pos=None, show=False, color=(0, 0, 0)
            )


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------

def _fmt(value: float | None) -> str:
    """Format a cursor value for display in the table."""
    if value is None:
        return ""
    return f"{value:.6g}"
