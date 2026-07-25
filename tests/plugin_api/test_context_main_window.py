"""Tests for PluginContext's main_window accessor (#76)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from mdf_viewer.controller.app_controller import AppController
from mdf_viewer.plugin_api.context import PluginContext
from mdf_viewer.plugin_api.registry import PluginRegistry


@pytest.fixture()
def deps() -> dict:
    loader = MagicMock()
    loader.channel_tree.return_value = []
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


@pytest.fixture()
def registry() -> PluginRegistry:
    return PluginRegistry()


@pytest.mark.requirement("REQ-PLUGIN-450")
def test_main_window_defaults_to_none(ctrl: AppController, registry: PluginRegistry) -> None:
    context = PluginContext(plugin_name="exporter", app=ctrl, registry=registry)

    assert context.main_window is None


@pytest.mark.requirement("REQ-PLUGIN-451")
def test_main_window_returns_the_live_object_unwrapped(
    ctrl: AppController, registry: PluginRegistry
) -> None:
    sentinel_window = object()

    context = PluginContext(
        plugin_name="exporter", app=ctrl, registry=registry, main_window=sentinel_window
    )

    assert context.main_window is sentinel_window


@pytest.mark.requirement("REQ-PLUGIN-452")
def test_app_version_defaults_to_empty_string(ctrl: AppController, registry: PluginRegistry) -> None:
    context = PluginContext(plugin_name="exporter", app=ctrl, registry=registry)

    assert context.app_version == ""


@pytest.mark.requirement("REQ-PLUGIN-452")
def test_app_version_returns_the_configured_version(
    ctrl: AppController, registry: PluginRegistry
) -> None:
    context = PluginContext(
        plugin_name="exporter", app=ctrl, registry=registry, app_version="2.3"
    )

    assert context.app_version == "2.3"
