"""Tests for PluginContext's get_setting/set_setting surface (#159)."""

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


@pytest.fixture()
def mock_settings() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def context(ctrl: AppController, registry: PluginRegistry) -> PluginContext:
    return PluginContext(plugin_name="exporter", app=ctrl, registry=registry)


@pytest.fixture()
def context_with_settings(
    ctrl: AppController, registry: PluginRegistry, mock_settings: MagicMock
) -> PluginContext:
    return PluginContext(
        plugin_name="exporter", app=ctrl, registry=registry, settings=mock_settings
    )


@pytest.mark.requirement("REQ-PLUGIN-413")
def test_get_setting_returns_default_when_no_settings_backend(context: PluginContext) -> None:
    assert context.get_setting("threshold", 42) == 42


@pytest.mark.requirement("REQ-PLUGIN-410")
def test_get_setting_delegates_to_settings_get_plugin_setting(
    context_with_settings: PluginContext, mock_settings: MagicMock
) -> None:
    mock_settings.get_plugin_setting.return_value = "value"

    result = context_with_settings.get_setting("threshold", 42)

    mock_settings.get_plugin_setting.assert_called_once_with("exporter", "threshold", 42)
    assert result == "value"


@pytest.mark.requirement("REQ-PLUGIN-413")
def test_set_setting_is_noop_when_no_settings_backend(context: PluginContext) -> None:
    context.set_setting("threshold", 42)  # must not raise


@pytest.mark.requirement("REQ-PLUGIN-410")
def test_set_setting_delegates_to_settings_set_plugin_setting(
    context_with_settings: PluginContext, mock_settings: MagicMock
) -> None:
    context_with_settings.set_setting("threshold", 42)

    mock_settings.set_plugin_setting.assert_called_once_with("exporter", "threshold", 42)


@pytest.mark.requirement("REQ-PLUGIN-412")
def test_get_setting_never_calls_the_setter(
    context_with_settings: PluginContext, mock_settings: MagicMock
) -> None:
    context_with_settings.get_setting("threshold", 42)

    mock_settings.set_plugin_setting.assert_not_called()
