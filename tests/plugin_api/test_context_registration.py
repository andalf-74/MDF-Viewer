"""Tests for PluginContext's registration + event-subscription surface (#71)."""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from mdf_viewer.controller.app_controller import AppController
from mdf_viewer.controller.events import SignalRemovedEvent
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
def context(ctrl: AppController, registry: PluginRegistry) -> PluginContext:
    return PluginContext(plugin_name="exporter", app=ctrl, registry=registry)


# ---------------------------------------------------------------------------
# register_menu_action / register_dock_widget (REQ-PLUGIN-120/130)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLUGIN-120")
def test_register_menu_action_tags_plugin_name(
    context: PluginContext, registry: PluginRegistry
) -> None:
    context.register_menu_action("Export", lambda: None)
    assert len(registry.menu_actions) == 1
    assert registry.menu_actions[0].plugin_name == "exporter"
    assert registry.menu_actions[0].label == "Export"


@pytest.mark.requirement("REQ-PLUGIN-130")
def test_register_dock_widget_tags_plugin_name(
    context: PluginContext, registry: PluginRegistry
) -> None:
    context.register_dock_widget("Add Signal", lambda: MagicMock(), mode="dialog")
    assert len(registry.dock_widgets) == 1
    assert registry.dock_widgets[0].plugin_name == "exporter"
    assert registry.dock_widgets[0].mode == "dialog"


# ---------------------------------------------------------------------------
# subscribe / unsubscribe_all (REQ-PLUGIN-140/150)
# ---------------------------------------------------------------------------

def test_subscribe_rejects_unknown_event_name(context: PluginContext) -> None:
    with pytest.raises(ValueError):
        context.subscribe("not_a_real_event", lambda payload: None)


@pytest.mark.requirement("REQ-PLUGIN-080")
@pytest.mark.requirement("REQ-PLUGIN-141")
def test_subscribe_delivers_a_translated_event_not_the_raw_payload(
    ctrl: AppController, context: PluginContext,
) -> None:
    """The plugin must never receive the raw EventBus payload (#149) — it
    carries the live ActiveSignal and the raw TabWorkspace directly."""
    received = []
    context.subscribe("signal_removed", received.append)

    raw_signal = MagicMock()
    event = SignalRemovedEvent(signal=raw_signal)
    ctrl.events.signal_removed.emit(event)

    assert len(received) == 1
    translated = received[0]
    assert not isinstance(translated, SignalRemovedEvent)
    assert translated.signal.metadata is raw_signal.metadata
    assert translated.tab_index is None


@pytest.mark.requirement("REQ-PLUGIN-150")
def test_subscribe_handler_exception_is_caught_and_logged(
    ctrl: AppController, context: PluginContext, caplog: pytest.LogCaptureFixture,
) -> None:
    def boom(payload) -> None:
        raise ValueError("plugin bug")

    context.subscribe("signal_removed", boom)

    with caplog.at_level(logging.ERROR, logger="mdf_viewer.plugin_api"):
        ctrl.events.signal_removed.emit(SignalRemovedEvent(signal=MagicMock()))  # must not raise

    assert "exporter" in caplog.text
    assert "signal_removed" in caplog.text


@pytest.mark.requirement("REQ-PLUGIN-150")
def test_a_raising_handler_does_not_break_other_subscribers(
    ctrl: AppController, context: PluginContext,
) -> None:
    other_received = []

    def boom(payload) -> None:
        raise ValueError("plugin bug")

    context.subscribe("signal_removed", boom)
    context.subscribe("signal_removed", other_received.append)

    event = SignalRemovedEvent(signal=MagicMock())
    ctrl.events.signal_removed.emit(event)

    assert len(other_received) == 1
    assert other_received[0].tab_index is None


def test_unsubscribe_all_stops_delivery(ctrl: AppController, context: PluginContext) -> None:
    received = []
    context.subscribe("signal_removed", received.append)

    context.unsubscribe_all()
    ctrl.events.signal_removed.emit(SignalRemovedEvent(signal=MagicMock()))

    assert received == []


def test_unsubscribe_all_is_safe_to_call_twice(ctrl: AppController, context: PluginContext) -> None:
    context.subscribe("signal_removed", lambda payload: None)
    context.unsubscribe_all()
    context.unsubscribe_all()  # must not raise


# ---------------------------------------------------------------------------
# _teardown (#72) — framework-internal, called by Plugin.start()/stop()
# ---------------------------------------------------------------------------

def test_teardown_unsubscribes_and_removes_registrations(
    ctrl: AppController, context: PluginContext, registry: PluginRegistry,
) -> None:
    received = []
    context.subscribe("signal_removed", received.append)
    context.register_menu_action("Export", lambda: None)
    context.register_dock_widget("Settings", lambda: MagicMock(), mode="dialog")

    context._teardown()

    assert registry.menu_actions == []
    assert registry.dock_widgets == []
    ctrl.events.signal_removed.emit(SignalRemovedEvent(signal=MagicMock()))
    assert received == []


def test_teardown_only_affects_this_plugins_registrations(
    ctrl: AppController, registry: PluginRegistry,
) -> None:
    context_a = PluginContext(plugin_name="a", app=ctrl, registry=registry)
    context_b = PluginContext(plugin_name="b", app=ctrl, registry=registry)
    context_a.register_menu_action("A action", lambda: None)
    context_b.register_menu_action("B action", lambda: None)

    context_a._teardown()

    assert [r.plugin_name for r in registry.menu_actions] == ["b"]


# ---------------------------------------------------------------------------
# Event-translation coverage guard-rails (#149) — a future event added to
# EventBus without a matching PluginContext translation must be caught here,
# not discovered later as a live leak of live ActiveSignal/TabWorkspace
# objects to plugin code.
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLUGIN-142")
def test_known_events_matches_eventbus_real_signals() -> None:
    from PyQt6.QtCore import pyqtSignal

    from mdf_viewer.controller.events import EventBus
    from mdf_viewer.plugin_api.context import _KNOWN_EVENTS

    real_signal_names = {name for name in vars(EventBus) if isinstance(vars(EventBus)[name], pyqtSignal)}
    assert _KNOWN_EVENTS == real_signal_names


@pytest.mark.requirement("REQ-PLUGIN-142")
def test_every_known_event_has_a_working_translation(context: PluginContext) -> None:
    from mdf_viewer.plugin_api.context import _KNOWN_EVENTS

    dummy_signal = MagicMock()
    payloads = {
        "file_loaded": MagicMock(path="x.mf4", tab=None),
        "signal_added": MagicMock(signal=dummy_signal, tab=None),
        "signal_removed": MagicMock(signal=dummy_signal, tab=None),
        "selection_changed": MagicMock(selected=[dummy_signal], tab=None),
        "cursor_moved": MagicMock(positions=[1.0, 2.0], mode=None, tab=None),
    }
    assert set(payloads) == _KNOWN_EVENTS  # this test itself must cover every known event

    for event_name, payload in payloads.items():
        translated = context._translate_event(event_name, payload)
        assert translated is not None


def test_translate_event_raises_loudly_for_an_unknown_name(context: PluginContext) -> None:
    with pytest.raises(AssertionError):
        context._translate_event("not_a_real_event", MagicMock())
