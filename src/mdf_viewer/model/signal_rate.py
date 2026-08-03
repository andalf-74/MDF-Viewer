"""Shared "pick the fastest-sampled signal" helper.

Used by CursorController (REQ-PLOT-091, arrow-key stepping) and
model.signal_search (REQ-SEARCH-031, the search scan grid).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mdf_viewer.view_model.active_signal import ActiveSignal


def highest_rate_signal(signals: list[ActiveSignal]) -> Any | None:
    """Return the signal with the highest effective sample rate.

    Computed directly from each signal's own timestamps (samples per second
    over its span) rather than SignalMetadata.raster_s, so a signal with an
    indeterminate/variable raster still participates. A signal with fewer
    than two samples, or a zero/negative timestamp span, rates lowest.
    Ties keep the first candidate encountered.
    """
    best: Any | None = None
    best_rate = -1.0
    for signal in signals:
        ts = signal.data.timestamps
        span = float(ts[-1] - ts[0]) if len(ts) >= 2 else 0.0
        rate = (len(ts) - 1) / span if span > 0 else 0.0
        if rate > best_rate:
            best_rate = rate
            best = signal
    return best
