"""Tests for PluginContext's read surface (#71)."""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from mdf_viewer.controller.app_controller import AppController
from mdf_viewer.enums import CursorMode
from mdf_viewer.model.loaded_measurement import LoadedMeasurement
from mdf_viewer.model.measurement import MeasurementInfo
from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.plugin_api.context import PluginContext
from mdf_viewer.plugin_api.registry import PluginRegistry


def _make_signal_data() -> SignalData:
    t = np.array([0.0, 0.5, 1.0])
    return SignalData(timestamps=t, samples=np.array([10.0, 20.0, 30.0]))


def _make_metadata(name: str = "sig", gi: int = 0, ci: int = 1) -> SignalMetadata:
    return SignalMetadata(name=name, unit="V", group_index=gi, channel_index=ci)


@pytest.fixture()
def deps() -> dict:
    loader = MagicMock()
    loader.channel_tree.return_value = []
    loader.measurement_info.return_value = MeasurementInfo(file_name="test.mf4")
    loader.load_signal.return_value = (_make_signal_data(), _make_metadata())
    plot = MagicMock()
    plot.get_stripes.return_value = []
    plot.get_stripe_sizes.return_value = []
    plot.get_active_stripe.return_value = None
    plot.get_stripe_for_signal.return_value = None
    return {
        "loader": loader,
        "browser": MagicMock(),
        "plot": plot,
        "table": MagicMock(),
        "info_box": MagicMock(),
        "signal_info": MagicMock(),
    }


@pytest.fixture()
def ctrl(deps: dict) -> AppController:
    return AppController(
        loader=deps["loader"],
        signal_browser=deps["browser"],
        plot_area=deps["plot"],
        active_signals_table=deps["table"],
        measurement_info_box=deps["info_box"],
        signal_info_box=deps["signal_info"],
    )


def _make_pool_loader() -> MagicMock:
    loader = MagicMock()
    loader.channel_tree.return_value = []
    loader.measurement_info.return_value = MeasurementInfo(file_name="test.mf4")
    loader.load_signal.return_value = (_make_signal_data(), _make_metadata())
    loader.is_open = True
    return loader


@pytest.fixture()
def registry() -> PluginRegistry:
    return PluginRegistry()


@pytest.fixture()
def context(ctrl: AppController, registry: PluginRegistry) -> PluginContext:
    return PluginContext(plugin_name="exporter", app=ctrl, registry=registry)


# ---------------------------------------------------------------------------
# active_signals (REQ-PLUGIN-070)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLUGIN-070")
def test_active_signals_groups_by_tab_and_marks_active_tab(
    ctrl: AppController, context: PluginContext
) -> None:
    ctrl.add_signal(0, 1)
    ctrl.create_tab(MagicMock(), MagicMock())
    ctrl.add_signal(0, 1)
    ctrl.switch_tab(0)

    tabs = context.active_signals

    assert len(tabs) == 2
    assert [t.tab_index for t in tabs] == [0, 1]
    assert len(tabs[0].signals) == 1
    assert len(tabs[1].signals) == 1
    assert tabs[0].is_active is True
    assert tabs[1].is_active is False


@pytest.mark.requirement("REQ-PLUGIN-080")
def test_active_signals_default_tab_name_fallback(
    ctrl: AppController, context: PluginContext
) -> None:
    tabs = context.active_signals
    assert tabs[0].tab_name == "Tab 1"


def test_active_signals_uses_tab_name_provider(ctrl: AppController) -> None:
    provider_ctx = PluginContext(
        plugin_name="exporter",
        app=ctrl,
        registry=PluginRegistry(),
        tab_name_provider=lambda i: f"Custom {i}",
    )
    tabs = provider_ctx.active_signals
    assert tabs[0].tab_name == "Custom 0"


# ---------------------------------------------------------------------------
# measurements (REQ-PLUGIN-100)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLUGIN-100")
def test_measurements_reports_full_pool_and_primary(
    deps: dict, registry: PluginRegistry
) -> None:
    loaders = iter([_make_pool_loader(), _make_pool_loader()])
    ctrl = AppController(
        loader=deps["loader"],
        signal_browser=deps["browser"],
        plot_area=deps["plot"],
        active_signals_table=deps["table"],
        measurement_info_box=deps["info_box"],
        signal_info_box=deps["signal_info"],
        loader_factory=lambda: next(loaders),
    )
    ctrl.replace_measurements(["a.mf4", "b.mf4"])
    context = PluginContext(plugin_name="exporter", app=ctrl, registry=registry)

    views = context.measurements

    assert [v.label for v in views] == ["M1", "M2"]
    assert [v.is_primary for v in views] == [True, False]


@pytest.mark.requirement("REQ-PLUGIN-100")
def test_measurements_primary_flag_uses_identity_not_equality(
    ctrl: AppController, context: PluginContext
) -> None:
    """Two structurally-equal-but-distinct LoadedMeasurements must not both
    read as Primary — is_primary must compare by object identity."""
    loader_a = MagicMock()
    loader_a.is_open = False
    m1 = LoadedMeasurement(loader=loader_a, info=MeasurementInfo(file_name="run.mf4"), label="M1")
    m2 = LoadedMeasurement(loader=loader_a, info=MeasurementInfo(file_name="run.mf4"), label="M1")
    assert m1 == m2  # structurally equal, distinct objects

    ctrl._measurements = [m1, m2]
    ctrl._primary_measurement = m2

    views = context.measurements
    assert [v.is_primary for v in views] == [False, True]


# ---------------------------------------------------------------------------
# cursor_positions (REQ-PLUGIN-110)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLUGIN-110")
def test_cursor_positions_reads_synchronous_snapshot(
    ctrl: AppController, context: PluginContext
) -> None:
    cursor_ctrl = MagicMock()
    cursor_ctrl.snapshot.return_value = {"mode": "TWO", "positions": [1.5, 2.5]}
    ctrl.set_cursor_controller(cursor_ctrl)

    cursors = context.cursor_positions

    assert cursors[0].mode is CursorMode.TWO
    assert cursors[0].positions == (1.5, 2.5)
    assert cursors[0].is_active is True


@pytest.mark.requirement("REQ-PLUGIN-110")
def test_cursor_positions_defaults_to_hidden_when_no_cursor_controller(
    context: PluginContext,
) -> None:
    cursors = context.cursor_positions
    assert cursors[0].mode is CursorMode.HIDDEN
    assert cursors[0].positions == ()


# ---------------------------------------------------------------------------
# get_samples (REQ-PLUGIN-090)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLUGIN-090")
def test_get_samples_returns_copies_of_live_signal_data(
    ctrl: AppController, context: PluginContext
) -> None:
    ctrl.add_signal(0, 1)
    signal_view = context.active_signals[0].signals[0]

    samples = context.get_samples(signal_view)

    assert samples is not None
    timestamps, values = samples
    active = ctrl.active_signals[0]
    assert np.array_equal(timestamps, active.display_timestamps)
    assert np.array_equal(values, active.data.samples)
    # Must be copies, not references, into the app's live arrays.
    timestamps[0] = -999.0
    assert active.display_timestamps[0] != -999.0


@pytest.mark.requirement("REQ-PLUGIN-090")
def test_get_samples_returns_none_for_a_removed_signal(
    ctrl: AppController, context: PluginContext
) -> None:
    ctrl.add_signal(0, 1)
    signal_view = context.active_signals[0].signals[0]
    ctrl.remove_signal(ctrl.active_signals[0])

    assert context.get_samples(signal_view) is None
