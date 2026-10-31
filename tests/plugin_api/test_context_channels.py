"""Tests for PluginContext's channel enumeration and reading (#189)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

from mdf_viewer.controller.app_controller import AppController
from mdf_viewer.errors import MdfLoadError
from mdf_viewer.model.measurement import MeasurementInfo
from mdf_viewer.model.mdf_loader import ChannelGroupInfo
from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.model.virtual_measurement_loader import VirtualMeasurementLoader
from mdf_viewer.model.virtual_signal import VirtualSignal
from mdf_viewer.plugin_api import ChannelLoadError
from mdf_viewer.plugin_api.context import PluginContext
from mdf_viewer.plugin_api.registry import PluginRegistry


class _FakeFileLoader:
    """A file-backed loader with a fixed two-group tree.

    load_signal() returns metadata that deliberately differs from the
    tree's (name/unit), as MdfLoader's two extraction paths can.
    """

    def __init__(self, name: str = "run.mf4") -> None:
        self._path = Path(name)
        self.tree_calls = 0
        self.fail_tree = False
        self.load_error: Exception | None = None
        self.samples = np.array([1.0, 2.0, 3.0])

    @property
    def is_open(self) -> bool:
        return True

    @property
    def path(self) -> Path:
        return self._path

    def open(self, path) -> None:
        self._path = Path(path)

    def measurement_info(self) -> MeasurementInfo:
        return MeasurementInfo(file_name=self._path.name)

    def channel_tree(self) -> list[ChannelGroupInfo]:
        self.tree_calls += 1
        if self.fail_tree:
            raise MdfLoadError("Failed to enumerate channels: boom")
        return [
            ChannelGroupInfo(name="G0", index=0, channels=(
                SignalMetadata(name="rpm", unit="1/min", group_index=0, channel_index=0, group_name="G0"),
                SignalMetadata(name="speed", unit="km/h", group_index=0, channel_index=1, group_name="G0"),
            )),
            ChannelGroupInfo(name="G1", index=1, channels=(
                SignalMetadata(name="rpm", unit="1/min", group_index=1, channel_index=0, group_name="G1"),
            )),
        ]

    def load_signal(self, group_index: int, channel_index: int):
        if self.load_error is not None:
            raise self.load_error
        data = SignalData(timestamps=np.array([0.0, 1.0, 2.0]), samples=self.samples)
        meta = SignalMetadata(
            name=f"channel_{channel_index}", unit="", group_index=group_index, channel_index=channel_index,
        )
        return data, meta

    def close(self) -> None:
        pass


def _make_ctrl(loaders: list) -> AppController:
    it = iter(loaders)
    plot = MagicMock()
    plot.get_stripes.return_value = []
    plot.get_stripe_sizes.return_value = []
    plot.get_active_stripe.return_value = None
    plot.get_stripe_for_signal.return_value = None
    return AppController(
        loader=MagicMock(),
        signal_browser=MagicMock(),
        plot_area=plot,
        active_signals_table=MagicMock(),
        measurement_info_box=MagicMock(),
        signal_info_box=MagicMock(),
        loader_factory=lambda: next(it),
    )


def _virtual_signal(name: str, resolver=None) -> VirtualSignal:
    def default_resolver():
        return (
            SignalData(timestamps=np.array([0.0, 1.0]), samples=np.array([5.0, 6.0])),
            SignalMetadata(name=name),
        )

    return VirtualSignal(
        name=name, resolver=resolver or default_resolver, template=SignalMetadata(name=name, unit="V"),
    )


@pytest.fixture()
def file_loader() -> _FakeFileLoader:
    return _FakeFileLoader()


@pytest.fixture()
def ctrl(file_loader: _FakeFileLoader) -> AppController:
    controller = _make_ctrl([file_loader, _FakeFileLoader("other.mf4"), _FakeFileLoader("new.mf4")])
    controller.replace_measurements(["run.mf4"])
    return controller


@pytest.fixture()
def context(ctrl: AppController) -> PluginContext:
    return PluginContext(plugin_name="Reader", app=ctrl, registry=PluginRegistry())


def _real(context: PluginContext):
    return context.measurements[0]


# ---------------------------------------------------------------------------
# list_channels / find_channels
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLUGIN-571")
def test_list_channels_follows_channel_tree_order(context: PluginContext) -> None:
    channels = context.list_channels(_real(context))
    assert [(c.group_name, c.name) for c in channels] == [("G0", "rpm"), ("G0", "speed"), ("G1", "rpm")]


@pytest.mark.requirement("REQ-PLUGIN-572")
def test_list_channels_exposes_unit_and_measurement(context: PluginContext) -> None:
    rpm = context.list_channels(_real(context))[0]
    assert rpm.unit == "1/min"
    assert rpm.measurement.same_measurement(_real(context))


@pytest.mark.requirement("REQ-PLUGIN-571")
def test_list_channels_of_virtual_measurement_is_attach_order(
    ctrl: AppController, context: PluginContext,
) -> None:
    loader = context.create_virtual_measurement()
    context.attach_virtual_signal(loader, _virtual_signal("b"))
    context.attach_virtual_signal(loader, _virtual_signal("a"))
    context.register_virtual_measurement(loader, "Calc")
    virtual = context.measurements[1]

    assert [c.name for c in context.list_channels(virtual)] == ["b", "a"]


@pytest.mark.requirement("REQ-PLUGIN-575")
def test_list_channels_of_closed_measurement_is_empty(ctrl: AppController, context: PluginContext) -> None:
    view = _real(context)
    ctrl.close_measurement(ctrl.measurements[0])

    assert context.list_channels(view) == []
    assert context.find_channels("rpm", view) == []


def test_list_channels_logs_and_returns_empty_when_tree_fails(
    file_loader: _FakeFileLoader, context: PluginContext, caplog: pytest.LogCaptureFixture,
) -> None:
    file_loader.fail_tree = True

    assert context.list_channels(_real(context)) == []
    assert "Could not enumerate channels" in caplog.text


def test_list_channels_caches_file_backed_tree(file_loader: _FakeFileLoader, context: PluginContext) -> None:
    before = file_loader.tree_calls  # the app read it once already, for the Signal Browser
    context.list_channels(_real(context))
    context.list_channels(_real(context))
    assert file_loader.tree_calls == before + 1


def test_list_channels_never_caches_virtual_tree(context: PluginContext) -> None:
    loader = context.create_virtual_measurement()
    context.attach_virtual_signal(loader, _virtual_signal("a"))
    context.register_virtual_measurement(loader, "Calc")
    virtual = context.measurements[1]
    assert len(context.list_channels(virtual)) == 1

    context.attach_virtual_signal(loader, _virtual_signal("b"))

    assert [c.name for c in context.list_channels(virtual)] == ["a", "b"]


@pytest.mark.requirement("REQ-PLUGIN-573")
def test_find_channels_is_exact_and_case_sensitive(context: PluginContext) -> None:
    assert [c.group_name for c in context.find_channels("rpm")] == ["G0", "G1"]
    assert context.find_channels("RPM") == []
    assert context.find_channels("rp") == []


@pytest.mark.requirement("REQ-PLUGIN-573")
def test_find_channels_across_measurements_in_pool_order(ctrl: AppController, context: PluginContext) -> None:
    ctrl.add_measurements(["other.mf4"])

    found = context.find_channels("speed")

    assert [c.measurement.label for c in found] == ["M1", "M2"]


@pytest.mark.requirement("REQ-PLUGIN-573")
def test_find_channels_scoped_to_one_measurement(ctrl: AppController, context: PluginContext) -> None:
    ctrl.add_measurements(["other.mf4"])
    second = context.measurements[1]

    found = context.find_channels("speed", second)

    assert [c.measurement.label for c in found] == ["M2"]


# ---------------------------------------------------------------------------
# load_samples
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLUGIN-580")
def test_load_samples_reads_an_unplotted_channel(context: PluginContext) -> None:
    speed = context.find_channels("speed")[0]

    timestamps, values = context.load_samples(speed)

    np.testing.assert_array_equal(timestamps, [0.0, 1.0, 2.0])
    np.testing.assert_array_equal(values, [1.0, 2.0, 3.0])


@pytest.mark.requirement("REQ-PLUGIN-581")
def test_load_samples_applies_offset_at_call_time(ctrl: AppController, context: PluginContext) -> None:
    speed = context.find_channels("speed")[0]  # taken while the offset is still 0
    ctrl.measurements[0].offset_s = 10.0

    timestamps, _ = context.load_samples(speed)

    np.testing.assert_array_equal(timestamps, [10.0, 11.0, 12.0])


@pytest.mark.requirement("REQ-PLUGIN-582")
def test_load_samples_returns_copies(file_loader: _FakeFileLoader, context: PluginContext) -> None:
    _, values = context.load_samples(context.find_channels("speed")[0])
    values[0] = 999.0
    assert file_loader.samples[0] == 1.0


@pytest.mark.requirement("REQ-PLUGIN-583")
def test_load_samples_of_closed_measurement_is_none(ctrl: AppController, context: PluginContext) -> None:
    speed = context.find_channels("speed")[0]
    ctrl.close_measurement(ctrl.measurements[0])
    assert context.load_samples(speed) is None


@pytest.mark.requirement("REQ-PLUGIN-583")
def test_load_samples_of_replaced_measurement_is_none(ctrl: AppController, context: PluginContext) -> None:
    speed = context.find_channels("speed")[0]
    ctrl.replace_single_measurement(ctrl.measurements[0], "other.mf4")

    assert context.load_samples(speed) is None
    assert len(context.find_channels("speed")) == 1  # the replacement is readable under its new identity


@pytest.mark.requirement("REQ-PLUGIN-583")
def test_load_samples_of_detached_virtual_channel_is_none(context: PluginContext) -> None:
    loader = context.create_virtual_measurement()
    signal = _virtual_signal("a")
    context.attach_virtual_signal(loader, signal)
    context.register_virtual_measurement(loader, "Calc")
    channel = context.find_channels("a")[0]

    context.detach_virtual_signal(loader, signal)

    assert context.load_samples(channel) is None


@pytest.mark.requirement("REQ-PLUGIN-586")
def test_load_samples_runs_virtual_resolver(context: PluginContext) -> None:
    loader = context.create_virtual_measurement()
    context.attach_virtual_signal(loader, _virtual_signal("a"))
    context.register_virtual_measurement(loader, "Calc")

    _, values = context.load_samples(context.find_channels("a")[0])

    np.testing.assert_array_equal(values, [5.0, 6.0])


@pytest.mark.requirement("REQ-PLUGIN-584")
def test_load_samples_maps_resolver_error_to_channel_load_error(context: PluginContext) -> None:
    def broken():
        raise ValueError("division by zero in formula")

    loader = context.create_virtual_measurement()
    context.attach_virtual_signal(loader, _virtual_signal("a", resolver=broken))
    context.register_virtual_measurement(loader, "Calc")

    with pytest.raises(ChannelLoadError, match="division by zero"):
        context.load_samples(context.find_channels("a")[0])


@pytest.mark.requirement("REQ-PLUGIN-584")
def test_load_samples_maps_mdf_load_error(file_loader: _FakeFileLoader, context: PluginContext) -> None:
    file_loader.load_error = MdfLoadError("Channel 'speed' is not numeric")

    with pytest.raises(ChannelLoadError, match="not numeric"):
        context.load_samples(context.find_channels("speed")[0])


@pytest.mark.requirement("REQ-PLUGIN-585")
@pytest.mark.parametrize("error", [RuntimeError("weird"), RecursionError("too deep")])
def test_load_samples_maps_unexpected_errors(
    file_loader: _FakeFileLoader, context: PluginContext, error: Exception,
) -> None:
    file_loader.load_error = error

    with pytest.raises(ChannelLoadError, match="Unexpected error reading 'speed'"):
        context.load_samples(context.find_channels("speed")[0])


# ---------------------------------------------------------------------------
# PluginSignalView.channel
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLUGIN-574")
def test_plotted_signal_channel_equals_the_listed_channel(ctrl: AppController, context: PluginContext) -> None:
    ctrl.add_signal(0, 1, measurement=ctrl.measurements[0])
    signal_view = context.active_signals[0].signals[0]

    listed = context.find_channels("speed")[0]

    # load_signal() reported the name as "channel_1"; the view still shows
    # the browser's name and equals the listed channel by handle.
    assert signal_view.channel == listed
    assert signal_view.channel.name == "speed"
    assert context.load_samples(signal_view.channel) is not None


@pytest.mark.requirement("REQ-PLUGIN-574")
def test_plotted_signal_without_measurement_has_no_channel(context: PluginContext) -> None:
    active = MagicMock(measurement=None)
    assert context._to_signal_view(active).channel is None


# ---------------------------------------------------------------------------
# Measurement lifecycle events, as a plugin sees them
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLUGIN-592")
def test_replace_closed_view_has_old_path_and_key_added_view_has_new_key(
    ctrl: AppController, context: PluginContext,
) -> None:
    old_view = _real(context)
    closed, added = [], []
    context.subscribe("measurement_closed", closed.append)
    context.subscribe("measurement_added", added.append)

    ctrl.replace_single_measurement(ctrl.measurements[0], "other.mf4")

    assert closed[0].measurement.path == "run.mf4"
    assert closed[0].measurement.same_measurement(old_view)
    assert added[0].measurement.path == "other.mf4"
    assert not added[0].measurement.same_measurement(old_view)
    assert context.list_channels(added[0].measurement)  # usable straight away


@pytest.mark.requirement("REQ-PLUGIN-590")
def test_added_view_is_usable_inside_the_handler(ctrl: AppController, context: PluginContext) -> None:
    channel_counts = []
    context.subscribe(
        "measurement_added", lambda e: channel_counts.append(len(context.list_channels(e.measurement))),
    )

    ctrl.add_measurements(["other.mf4"])

    assert channel_counts == [3]


@pytest.mark.requirement("REQ-PLUGIN-561")
def test_find_channels_inside_bulk_close_handler_leaks_no_token(ctrl: AppController, context: PluginContext) -> None:
    ctrl.add_measurements(["other.mf4"])
    old_views = context.measurements
    context.subscribe("measurement_closed", lambda e: context.find_channels("rpm"))

    ctrl.replace_measurements(["new.mf4"])

    assert all(context.list_channels(v) == [] for v in old_views)
    assert [m.label for m in ctrl.measurements] == ["M1"]
    # No token was minted for an already-closed measurement mid-loop.
    assert all(
        any(m is tokenized for m in ctrl.measurements) for tokenized in ctrl._measurement_tokens.values()
    )


@pytest.mark.requirement("REQ-PLUGIN-590")
def test_registering_virtual_measurement_inside_added_handler(ctrl: AppController, context: PluginContext) -> None:
    labels = []

    def on_added(event) -> None:
        labels.append(event.measurement.label)
        if not event.measurement.is_virtual:
            loader = context.create_virtual_measurement()
            context.attach_virtual_signal(loader, _virtual_signal("derived"))
            context.register_virtual_measurement(loader, "Calc")

    context.subscribe("measurement_added", on_added)

    ctrl.add_measurements(["other.mf4"])

    assert labels == ["M2", "Calc"]
    assert [m.label for m in ctrl.measurements] == ["M1", "M2", "Calc"]
