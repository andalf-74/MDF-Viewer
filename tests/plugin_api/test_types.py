"""Tests for the read-only plugin projections (#71)."""

from __future__ import annotations

import dataclasses

import numpy as np
import pytest
from PyQt6.QtGui import QColor

from mdf_viewer.model.loaded_measurement import LoadedMeasurement
from mdf_viewer.model.mdf_loader import MdfLoader
from mdf_viewer.model.measurement import MeasurementInfo
from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.plugin_api.types import PluginMeasurementView, PluginSignalView
from mdf_viewer.view_model.active_signal import ActiveSignal


def _make_active() -> ActiveSignal:
    t = np.array([0.0, 1.0, 2.0])
    data = SignalData(timestamps=t, samples=t)
    meta = SignalMetadata(name="sig", unit="V")
    return ActiveSignal(data=data, metadata=meta, color=QColor(255, 0, 0), display_mode="marker", line_width=3)


def _make_measurement(label: str = "M1") -> LoadedMeasurement:
    return LoadedMeasurement(loader=MdfLoader(), info=MeasurementInfo(file_name="run1.mf4"), label=label)


@pytest.mark.requirement("REQ-PLUGIN-080")
def test_signal_view_omits_curve_and_view_box() -> None:
    active = _make_active()
    active.curve = object()
    active.view_box = object()
    view = PluginSignalView.from_active(active, token=1, measurement_view=None)
    assert not hasattr(view, "curve")
    assert not hasattr(view, "view_box")


@pytest.mark.requirement("REQ-PLUGIN-080")
def test_signal_view_carries_display_state() -> None:
    active = _make_active()
    view = PluginSignalView.from_active(active, token=7, measurement_view=None)
    assert view.metadata is active.metadata
    assert view.color == active.color
    assert view.display_mode == "marker"
    assert view.line_width == 3
    assert view.visible is True
    assert view._signal_token == 7


def test_signal_view_is_frozen() -> None:
    view = PluginSignalView.from_active(_make_active(), token=1, measurement_view=None)
    with pytest.raises(dataclasses.FrozenInstanceError):
        view.visible = False  # type: ignore[misc]


@pytest.mark.requirement("REQ-PLUGIN-100")
def test_measurement_view_reads_label_and_offset() -> None:
    measurement = _make_measurement("M2")
    measurement.offset_s = 3.5
    view = PluginMeasurementView.from_measurement(measurement, is_primary=True)
    assert view.label == "M2"
    assert view.offset_s == 3.5
    assert view.is_primary is True
    assert view.path == ""  # loader never opened a real file in this test


def test_measurement_view_is_frozen() -> None:
    view = PluginMeasurementView.from_measurement(_make_measurement(), is_primary=False)
    with pytest.raises(dataclasses.FrozenInstanceError):
        view.label = "renamed"  # type: ignore[misc]
