"""Shared interpolation helper used by CursorController and CursorView."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from mdf_viewer.view_model.active_signal import ActiveSignal


def interpolate(active: ActiveSignal, x: float) -> float | None:
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
