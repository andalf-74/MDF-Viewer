"""Tests for Plugin.start()/stop() and event auto-wiring (#72)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from mdf_viewer.controller.app_controller import AppController
from mdf_viewer.controller.events import SignalAddedEvent
from mdf_viewer.plugin_api.context import PluginContext
from mdf_viewer.plugin_api.plugin import Plugin
from mdf_viewer.plugin_api.registry import PluginRegistry


class _StubContext:
    """Minimal stand-in for PluginContext, for isolated Plugin unit tests
    that don't need a real AppController/EventBus."""

    def __init__(self) -> None:
        self.subscribed: list[tuple[str, object]] = []
        self.registered_actions: list[str] = []
        self.teardown_calls = 0
        self.raise_on_teardown = False

    def subscribe(self, event_name: str, handler) -> None:
        self.subscribed.append((event_name, handler))

    def register_menu_action(self, label: str, callback) -> None:
        self.registered_actions.append(label)

    def _teardown(self) -> None:
        self.teardown_calls += 1
        if self.raise_on_teardown:
            raise RuntimeError("teardown boom")


# ---------------------------------------------------------------------------
# start() — auto-wiring, idempotency, failure path
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLUGIN-181")
def test_start_auto_wires_only_overridden_handlers() -> None:
    class OnlySignalAdded(Plugin):
        name = "OnlySignalAdded"

        def activate(self, context) -> None:
            pass

        def on_signal_added(self, event) -> None:
            pass

    plugin = OnlySignalAdded()
    context = _StubContext()

    assert plugin.start(context) is True
    assert [name for name, _ in context.subscribed] == ["signal_added"]
    assert plugin.is_active is True
    assert plugin.context is context


def test_start_wires_nothing_when_no_handlers_overridden() -> None:
    class NoHandlers(Plugin):
        name = "NoHandlers"

        def activate(self, context) -> None:
            pass

    plugin = NoHandlers()
    context = _StubContext()

    plugin.start(context)

    assert context.subscribed == []


def test_start_is_idempotent() -> None:
    calls = []

    class CountingPlugin(Plugin):
        name = "Counting"

        def activate(self, context) -> None:
            calls.append(1)

    plugin = CountingPlugin()
    context = _StubContext()

    assert plugin.start(context) is True
    assert plugin.start(context) is True
    assert len(calls) == 1


@pytest.mark.requirement("REQ-PLUGIN-172")
def test_start_failure_tears_down_partial_registration_and_returns_false() -> None:
    class BadPlugin(Plugin):
        name = "Bad"

        def activate(self, context) -> None:
            context.register_menu_action("Should not survive", lambda: None)
            raise ValueError("boom mid-activation")

    plugin = BadPlugin()
    context = _StubContext()

    assert plugin.start(context) is False
    assert plugin.is_active is False
    assert plugin.context is None
    assert context.teardown_calls == 1


def test_start_failure_leaves_plugin_startable_again() -> None:
    attempts = []

    class FlakyPlugin(Plugin):
        name = "Flaky"

        def activate(self, context) -> None:
            attempts.append(1)
            if len(attempts) == 1:
                raise ValueError("first attempt fails")

    plugin = FlakyPlugin()
    context = _StubContext()

    assert plugin.start(context) is False
    assert plugin.start(context) is True
    assert plugin.is_active is True


# ---------------------------------------------------------------------------
# stop() — idempotency, teardown-always, resilience to failures
# ---------------------------------------------------------------------------

def test_stop_is_a_noop_if_never_started() -> None:
    class MinimalPlugin(Plugin):
        name = "Minimal"

        def activate(self, context) -> None:
            pass

    MinimalPlugin().stop()  # must not raise


def test_stop_calls_deactivate_once_and_tears_down() -> None:
    calls = []

    class TrackedPlugin(Plugin):
        name = "Tracked"

        def activate(self, context) -> None:
            pass

        def deactivate(self) -> None:
            calls.append(1)

    plugin = TrackedPlugin()
    context = _StubContext()
    plugin.start(context)

    plugin.stop()

    assert calls == [1]
    assert context.teardown_calls == 1
    assert plugin.is_active is False
    assert plugin.context is None


def test_stop_is_idempotent() -> None:
    calls = []

    class TrackedPlugin(Plugin):
        name = "Tracked"

        def activate(self, context) -> None:
            pass

        def deactivate(self) -> None:
            calls.append(1)

    plugin = TrackedPlugin()
    context = _StubContext()
    plugin.start(context)

    plugin.stop()
    plugin.stop()

    assert calls == [1]  # not called a second time


@pytest.mark.requirement("REQ-PLUGIN-171")
def test_stop_resets_state_even_if_deactivate_raises() -> None:
    class BadDeactivate(Plugin):
        name = "BadDeactivate"

        def activate(self, context) -> None:
            pass

        def deactivate(self) -> None:
            raise ValueError("boom")

    plugin = BadDeactivate()
    context = _StubContext()
    plugin.start(context)

    plugin.stop()  # must not raise

    assert context.teardown_calls == 1
    assert plugin.is_active is False
    assert plugin.context is None


def test_stop_resets_state_even_if_teardown_raises() -> None:
    class MinimalPlugin(Plugin):
        name = "Minimal"

        def activate(self, context) -> None:
            pass

    plugin = MinimalPlugin()
    context = _StubContext()
    context.raise_on_teardown = True
    plugin.start(context)

    plugin.stop()  # must not raise

    assert plugin.is_active is False
    assert plugin.context is None


# ---------------------------------------------------------------------------
# End-to-end: real AppController + PluginContext + PluginRegistry
# ---------------------------------------------------------------------------

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


def test_overridden_handler_receives_a_real_event(ctrl: AppController) -> None:
    received = []

    class ListenerPlugin(Plugin):
        name = "Listener"

        def activate(self, context) -> None:
            pass

        def on_signal_added(self, event) -> None:
            received.append(event)

    registry = PluginRegistry()
    context = PluginContext(plugin_name="Listener", app=ctrl, registry=registry)
    plugin = ListenerPlugin()

    assert plugin.start(context) is True
    event = SignalAddedEvent(signal=MagicMock())
    ctrl.events.signal_added.emit(event)

    assert len(received) == 1
    assert not isinstance(received[0], SignalAddedEvent)  # translated, never the raw payload (#149)

    plugin.stop()
    ctrl.events.signal_added.emit(event)
    assert len(received) == 1  # no second delivery after stop()


def test_real_registry_has_no_leak_after_failed_activation(ctrl: AppController) -> None:
    class BadPlugin(Plugin):
        name = "Bad"

        def activate(self, context) -> None:
            context.register_menu_action("Should not survive", lambda: None)
            raise ValueError("boom")

    registry = PluginRegistry()
    context = PluginContext(plugin_name="Bad", app=ctrl, registry=registry)
    plugin = BadPlugin()

    assert plugin.start(context) is False
    assert registry.menu_actions == []
