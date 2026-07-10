"""Tests for ActiveSignal.display_timestamps (#101)."""

from __future__ import annotations

import numpy as np
import pytest
from PyQt6.QtGui import QColor

from mdf_viewer.model.loaded_measurement import LoadedMeasurement
from mdf_viewer.model.mdf_loader import MdfLoader
from mdf_viewer.model.measurement import MeasurementInfo
from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.view_model.active_signal import ActiveSignal


def _make_active(measurement: LoadedMeasurement | None = None) -> ActiveSignal:
    t = np.array([0.0, 1.0, 2.0])
    data = SignalData(timestamps=t, samples=t)
    meta = SignalMetadata(name="sig")
    return ActiveSignal(data=data, metadata=meta, color=QColor(255, 0, 0), measurement=measurement)


def test_display_timestamps_defaults_to_raw_when_no_measurement() -> None:
    active = _make_active(measurement=None)
    assert np.array_equal(active.display_timestamps, active.data.timestamps)


@pytest.mark.requirement("REQ-PLOT-304")
def test_display_timestamps_shifted_by_measurement_offset() -> None:
    measurement = LoadedMeasurement(
        loader=MdfLoader(), info=MeasurementInfo(file_name="run1.mf4"), label="run1", offset_s=5.0,
    )
    active = _make_active(measurement=measurement)
    assert np.array_equal(active.display_timestamps, np.array([5.0, 6.0, 7.0]))


@pytest.mark.requirement("REQ-PLOT-304")
def test_display_timestamps_tracks_live_offset_changes() -> None:
    measurement = LoadedMeasurement(
        loader=MdfLoader(), info=MeasurementInfo(file_name="run1.mf4"), label="run1",
    )
    active = _make_active(measurement=measurement)
    assert np.array_equal(active.display_timestamps, active.data.timestamps)
    measurement.offset_s = -2.0
    assert np.array_equal(active.display_timestamps, np.array([-2.0, -1.0, 0.0]))
