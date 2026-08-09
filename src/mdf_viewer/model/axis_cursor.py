"""Cursor-position resolution against an axis signal's own values (#86).

Pure, Qt-free helpers used by X-Axis Signal tabs, where a cursor's position
is stored as a genuine time internally (REQ-XAXIS-040) but must be resolved
from/against the axis signal's own recorded *value* — the render-space
coordinate a mouse drag or arrow-key step actually operates in.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from mdf_viewer.view_model.active_signal import ActiveSignal


def time_to_axis_render_x(axis: "ActiveSignal", time: float) -> float:
    """Convert a genuine time value to the render-space X coordinate an
    X-Axis Signal tab's plot actually uses — *axis*'s own interpolated
    value at *time* (#86).

    *time* is clamped into *axis*'s own recorded range before
    interpolating: its raw timestamps are always ascending (only its
    *values*, REQ-XAXIS-021, can be non-monotonic), so this is always
    well-defined and never returns None. Shared by app.py's CursorView
    wiring and AppController.search_execute()'s pan-to-match, so a
    Signal Value Search match pans to the correct location in this tab
    type instead of treating *time* as if it were already a render-space
    coordinate (only true for an ordinary Plot tab).
    """
    from mdf_viewer.model.interpolate import interpolate

    ts = axis.display_timestamps
    if len(ts) == 0:
        return 0.0
    clamped = min(max(time, float(ts[0])), float(ts[-1]))
    value = interpolate(axis, clamped)
    return value if value is not None else 0.0


def nearest_instant_by_value(
    axis: "ActiveSignal", target_value: float, current_time: float | None
) -> float:
    """Return *axis*'s own recorded display-time whose value is nearest
    *target_value*, tie-broken by whichever candidate's own time is nearest
    *current_time* (REQ-XAXIS-041).

    When several recorded instants share the exact same value (e.g. a
    standstill span), the tie-break means dragging within that span always
    resolves back to whichever instant is already closest to the cursor's
    current position — the cursor cannot be moved elsewhere by dragging
    through it (REQ-XAXIS-043) without this needing any separate check.

    *current_time* of ``None`` (no prior cursor position to anchor to, e.g.
    first-ever placement) ties-break by taking the first matching instant.
    Returns *current_time* (or 0.0 if that's also None) if *axis* has no
    samples at all.
    """
    xs = axis.data.samples
    ts = axis.display_timestamps
    if len(xs) == 0:
        return current_time if current_time is not None else 0.0
    diffs = np.abs(xs - target_value)
    min_diff = diffs.min()
    candidate_idxs = np.flatnonzero(diffs == min_diff)
    if current_time is None:
        return float(ts[candidate_idxs[0]])
    candidate_times = ts[candidate_idxs]
    best = int(np.argmin(np.abs(candidate_times - current_time)))
    return float(candidate_times[best])


def step_by_axis_value(
    axis: "ActiveSignal", current_time: float, direction: int, amount: float
) -> float:
    """Step *current_time* to the next recorded instant of *axis* whose
    value differs from the value at *current_time* by at least *amount*,
    skipping over any span where the value does not change (REQ-XAXIS-050/051).

    Clamps at the axis signal's own first/last recorded instant rather than
    moving out of range. Returns *current_time* unchanged if *axis* has no
    samples.
    """
    xs = axis.data.samples
    ts = axis.display_timestamps
    if len(xs) == 0:
        return current_time
    start = int(np.argmin(np.abs(ts - current_time)))
    base_value = xs[start]
    step = 1 if direction > 0 else -1
    i = start
    while 0 <= i + step < len(ts):
        i += step
        if abs(float(xs[i] - base_value)) >= amount:
            return float(ts[i])
    return float(ts[i])
