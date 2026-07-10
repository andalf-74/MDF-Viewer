"""Tests for interpolate(), including measurement-offset handling (#101)."""

from __future__ import annotations

import numpy as np
import pytest
from PyQt6.QtGui import QColor

from mdf_viewer.model.interpolate import interpolate
from mdf_viewer.model.loaded_measurement import LoadedMeasurement
from mdf_viewer.model.mdf_loader import MdfLoader
from mdf_viewer.model.measurement import MeasurementInfo
from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.view_model.active_signal import ActiveSignal


def _make_active(measurement: LoadedMeasurement | None = None) -> ActiveSignal:
    t = np.array([0.0, 1.0, 2.0])
    y = np.array([0.0, 10.0, 20.0])
    data = SignalData(timestamps=t, samples=y)
    meta = SignalMetadata(name="sig")
    return ActiveSignal(data=data, metadata=meta, color=QColor(255, 0, 0), measurement=measurement)


def test_interpolate_without_measurement_uses_raw_time() -> None:
    active = _make_active(measurement=None)
    assert interpolate(active, 0.5) == 5.0


@pytest.mark.requirement("REQ-PLOT-305")
def test_interpolate_subtracts_measurement_offset() -> None:
    measurement = LoadedMeasurement(
        loader=MdfLoader(), info=MeasurementInfo(file_name="run1.mf4"), label="run1", offset_s=10.0,
    )
    active = _make_active(measurement=measurement)
    # Display time 10.5 -> raw time 0.5 -> interpolated value 5.0.
    assert interpolate(active, 10.5) == 5.0


@pytest.mark.requirement("REQ-PLOT-305")
def test_interpolate_out_of_range_after_offset_adjustment() -> None:
    measurement = LoadedMeasurement(
        loader=MdfLoader(), info=MeasurementInfo(file_name="run1.mf4"), label="run1", offset_s=10.0,
    )
    active = _make_active(measurement=measurement)
    # Display time 0.5 -> raw time -9.5, outside the signal's own range.
    assert interpolate(active, 0.5) is None
