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
    view = PluginMeasurementView.from_measurement(measurement, is_primary=True, token=1)
    assert view.label == "M2"
    assert view.offset_s == 3.5
    assert view.is_primary is True
    assert view.path == ""  # loader never opened a real file in this test
    assert view.is_virtual is False


@pytest.mark.requirement("REQ-PLUGIN-550")
def test_measurement_view_is_virtual_true_for_a_virtual_measurement() -> None:
    from mdf_viewer.model.virtual_measurement_loader import VirtualMeasurementLoader

    measurement = LoadedMeasurement(
        loader=VirtualMeasurementLoader(owner_plugin="p"),
        info=MeasurementInfo(file_name=""),
        label="Virtual",
        owner_plugin="p",
    )
    view = PluginMeasurementView.from_measurement(measurement, is_primary=False, token=1)
    assert view.is_virtual is True


def test_measurement_view_is_frozen() -> None:
    view = PluginMeasurementView.from_measurement(_make_measurement(), is_primary=False, token=1)
    with pytest.raises(dataclasses.FrozenInstanceError):
        view.label = "renamed"  # type: ignore[misc]


@pytest.mark.requirement("REQ-VMEAS-210")
def test_measurement_view_from_virtual_measurement_does_not_crash() -> None:
    """Regression: from_measurement() used to read loader._path directly,
    which AttributeErrors on VirtualMeasurementLoader (#147)."""
    from mdf_viewer.model.virtual_measurement_loader import VirtualMeasurementLoader

    measurement = LoadedMeasurement(
        loader=VirtualMeasurementLoader(owner_plugin="p"),
        info=MeasurementInfo(file_name=""),
        label="Virtual",
        owner_plugin="p",
    )
    view = PluginMeasurementView.from_measurement(measurement, is_primary=False, token=1)
    assert view.path == ""


# ---------------------------------------------------------------------------
# Measurement identity and channel handles (#189)
# ---------------------------------------------------------------------------

from mdf_viewer.plugin_api.types import PluginChannelView  # noqa: E402


def _channel_view(token: int = 1, gi: int = 0, ci: int = 2, *, name: str = "rpm", unit: str = "1/min",
                  offset_s: float = 0.0) -> PluginChannelView:
    measurement = _make_measurement()
    measurement.offset_s = offset_s
    view = PluginMeasurementView.from_measurement(measurement, is_primary=False, token=token)
    meta = SignalMetadata(name=name, unit=unit, comment="", group_index=gi, channel_index=ci, group_name="G")
    return PluginChannelView.from_metadata(meta, view)


@pytest.mark.requirement("REQ-PLUGIN-560")
def test_measurement_view_key_is_stable_across_offset_change() -> None:
    measurement = _make_measurement()
    before = PluginMeasurementView.from_measurement(measurement, is_primary=False, token=5)
    measurement.offset_s = 3.0
    after = PluginMeasurementView.from_measurement(measurement, is_primary=True, token=5)

    assert before != after  # snapshot fields differ...
    assert before.key == after.key  # ...but the identity doesn't
    assert before.same_measurement(after)


@pytest.mark.requirement("REQ-PLUGIN-572")
def test_channel_view_equality_uses_only_the_handle() -> None:
    a = _channel_view(name="rpm", unit="1/min", offset_s=0.0)
    b = _channel_view(name="channel_2", unit="", offset_s=4.0)  # different descriptive fields

    assert a == b
    assert hash(a) == hash(b)
    assert {a: "x"}[b] == "x"


@pytest.mark.requirement("REQ-PLUGIN-572")
@pytest.mark.parametrize("other", [dict(token=2), dict(gi=1), dict(ci=3)])
def test_channel_view_differs_when_any_handle_part_differs(other: dict) -> None:
    assert _channel_view() != _channel_view(**other)


@pytest.mark.requirement("REQ-PLUGIN-572")
def test_channel_view_exposes_descriptive_fields_and_measurement() -> None:
    view = _channel_view(token=9)
    assert (view.name, view.unit, view.comment, view.group_name) == ("rpm", "1/min", "", "G")
    assert view.measurement.key == 9


@pytest.mark.requirement("REQ-PLUGIN-574")
def test_signal_view_channel_defaults_to_none() -> None:
    view = PluginSignalView.from_active(_make_active(), token=1, measurement_view=None)
    assert view.channel is None
