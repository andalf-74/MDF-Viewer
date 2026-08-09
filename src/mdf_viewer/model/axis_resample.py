"""Resamples a signal onto another signal's own recorded values (#86).

Used by X-Axis Signal tabs, where the shared plot X-axis represents a
chosen "axis signal"'s recorded value instead of time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from mdf_viewer.model.interpolate import interpolate

if TYPE_CHECKING:
    from mdf_viewer.view_model.active_signal import ActiveSignal


def resample_to_axis(axis: "ActiveSignal", other: "ActiveSignal") -> tuple[np.ndarray, np.ndarray]:
    """Resample *other* onto *axis*'s own recorded instants (REQ-XAXIS-020).

    Returns parallel (x, y) arrays in *axis*'s own recorded temporal order —
    not sorted by value (REQ-XAXIS-021) — where x is *axis*'s own recorded
    value (offset-independent) at each instant, and y is *other*'s
    interpolated-or-stepped value at that same shared display-time instant.
    An instant where *other* has no value there (REQ-PLOT-083 no-extrapolation)
    is omitted from the result (REQ-XAXIS-022).

    Using axis.data.samples (not display_timestamps) for x, but
    axis.display_timestamps to query *other*, is what makes REQ-XAXIS-072
    fall out for free: shifting the axis signal's own measurement offset
    changes which instant *other* is sampled at (changing y), without
    moving any point's x position (data.samples never shifts).
    """
    xs = axis.data.samples
    query_times = axis.display_timestamps
    x_out: list[float] = []
    y_out: list[float] = []
    for i in range(len(query_times)):
        y = interpolate(other, float(query_times[i]))
        if y is None:
            continue
        x_out.append(float(xs[i]))
        y_out.append(y)
    return np.array(x_out), np.array(y_out)
