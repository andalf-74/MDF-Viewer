"""Tests for resample_to_axis() (#86)."""

from __future__ import annotations

import numpy as np
import pytest
from PyQt6.QtGui import QColor

from mdf_viewer.model.axis_resample import resample_to_axis
from mdf_viewer.model.loaded_measurement import LoadedMeasurement
from mdf_viewer.model.mdf_loader import MdfLoader
from mdf_viewer.model.measurement import MeasurementInfo
from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.view_model.active_signal import ActiveSignal


def _make_active(
    t: list[float], y: list[float], measurement: LoadedMeasurement | None = None
) -> ActiveSignal:
    data = SignalData(timestamps=np.array(t), samples=np.array(y))
    meta = SignalMetadata(name="sig")
    return ActiveSignal(data=data, metadata=meta, color=QColor(255, 0, 0), measurement=measurement)


@pytest.mark.requirement("REQ-XAXIS-020")
def test_resamples_other_at_axis_own_instants() -> None:
    axis = _make_active([0.0, 1.0, 2.0], [10.0, 20.0, 30.0])
    other = _make_active([0.0, 1.0, 2.0], [0.0, 100.0, 200.0])
    x, y = resample_to_axis(axis, other)
    np.testing.assert_array_equal(x, [10.0, 20.0, 30.0])
    np.testing.assert_array_equal(y, [0.0, 100.0, 200.0])


@pytest.mark.requirement("REQ-XAXIS-021")
def test_preserves_axis_own_temporal_order_even_when_non_monotonic() -> None:
    # A driven-distance-like axis signal that reverses (standstill/rewind).
    axis = _make_active([0.0, 1.0, 2.0, 3.0], [0.0, 5.0, 5.0, 2.0])
    other = _make_active([0.0, 1.0, 2.0, 3.0], [1.0, 2.0, 3.0, 4.0])
    x, y = resample_to_axis(axis, other)
    np.testing.assert_array_equal(x, [0.0, 5.0, 5.0, 2.0])
    np.testing.assert_array_equal(y, [1.0, 2.0, 3.0, 4.0])


@pytest.mark.requirement("REQ-XAXIS-022")
def test_omits_instants_where_other_has_no_value() -> None:
    axis = _make_active([0.0, 1.0, 2.0, 3.0], [10.0, 20.0, 30.0, 40.0])
    # other only covers [0, 1] -> no-extrapolation drops axis instants 2 and 3.
    other = _make_active([0.0, 1.0], [0.0, 100.0])
    x, y = resample_to_axis(axis, other)
    np.testing.assert_array_equal(x, [10.0, 20.0])
    np.testing.assert_array_equal(y, [0.0, 100.0])


@pytest.mark.requirement("REQ-XAXIS-072")
def test_axis_own_measurement_offset_shifts_y_values_not_x_positions() -> None:
    other = _make_active([0.0, 1.0, 2.0, 3.0, 4.0], [0.0, 100.0, 200.0, 300.0, 400.0])
    axis_unshifted = _make_active([0.0, 1.0, 2.0], [10.0, 20.0, 30.0])
    x0, y0 = resample_to_axis(axis_unshifted, other)

    measurement = LoadedMeasurement(
        loader=MdfLoader(), info=MeasurementInfo(file_name="run1.mf4"), label="run1", offset_s=1.0,
    )
    axis_shifted = _make_active([0.0, 1.0, 2.0], [10.0, 20.0, 30.0], measurement=measurement)
    x1, y1 = resample_to_axis(axis_shifted, other)

    # x positions (axis signal's own recorded values) are unaffected by its offset.
    np.testing.assert_array_equal(x1, x0)
    # y values shift, since the instant queried against `other` moved by the offset.
    np.testing.assert_array_equal(y0, [0.0, 100.0, 200.0])
    np.testing.assert_array_equal(y1, [100.0, 200.0, 300.0])


def test_returns_empty_arrays_when_axis_has_no_samples() -> None:
    axis = _make_active([], [])
    other = _make_active([0.0, 1.0], [0.0, 100.0])
    x, y = resample_to_axis(axis, other)
    assert len(x) == 0
    assert len(y) == 0
