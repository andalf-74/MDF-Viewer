"""End-to-end smoke test for the whole PluginContext facade (#71).

Exercises the full lifecycle against a real AppController (only the loader/
view dependencies are mocked, per the project's established `deps()`
pattern) since there's no real plugin loader (#74) or UI wiring (#73) yet
to drive this through the real app.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import numpy as np
import pytest

from mdf_viewer.controller.app_controller import AppController
from mdf_viewer.controller.events import SignalAddedEvent
from mdf_viewer.model.measurement import MeasurementInfo
from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.plugin_api.context import PluginContext
from mdf_viewer.plugin_api.registry import PluginRegistry


@pytest.fixture()
def deps() -> dict:
    loader = MagicMock()
    loader.channel_tree.return_value = []
    loader.measurement_info.return_value = MeasurementInfo(file_name="test.mf4")
    t = np.array([0.0, 1.0, 2.0])
    loader.load_signal.return_value = (
        SignalData(timestamps=t, samples=np.array([1.0, 2.0, 3.0])),
        SignalMetadata(name="RPM", unit="1/min", group_index=0, channel_index=1),
    )
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


def test_full_plugin_context_lifecycle(ctrl: AppController) -> None:
    registry = PluginRegistry()
    context = PluginContext(plugin_name="exporter", app=ctrl, registry=registry)

    # 1. Add a signal through the real controller.
    ctrl.add_signal(0, 1)

    # 2. Read access.
    tabs = context.active_signals
    assert len(tabs) == 1
    assert tabs[0].is_active is True
    signal_view = tabs[0].signals[0]
    assert signal_view.metadata.name == "RPM"

    assert context.measurements == []  # legacy single-loader path never populates the pool

    cursors = context.cursor_positions
    assert len(cursors) == 1

    # 3. Sample data, always a copy.
    samples = context.get_samples(signal_view)
    assert samples is not None
    timestamps, values = samples
    assert np.array_equal(values, [1.0, 2.0, 3.0])

    # 4. UI registration stubs.
    menu_calls = []
    context.register_menu_action("Export Between Cursors", lambda: menu_calls.append(1))
    context.register_dock_widget("Exporter Settings", lambda: MagicMock(), mode="dialog")
    assert len(registry.menu_actions) == 1
    assert len(registry.dock_widgets) == 1
    registry.menu_actions[0].invoke()
    assert menu_calls == [1]

    # 5. Event subscription — trigger a real signal_added by adding a second
    # channel, through the real controller (not a manually-built event), so
    # the payload's `tab` is the real TabWorkspace. The plugin must receive
    # a translated, read-only payload (#149), never the raw event carrying
    # the live ActiveSignal/TabWorkspace.
    received = []
    context.subscribe("signal_added", received.append)
    ctrl.add_signal(0, 2)
    assert len(received) == 1
    assert received[0].signal.metadata.name == "RPM"
    assert received[0].tab_index == 0

    event = SignalAddedEvent(signal=ctrl.active_signals[0])

    # 6. Remove the signal — get_samples must now report it gone.
    ctrl.remove_signal(ctrl.active_signals[0])
    assert context.get_samples(signal_view) is None

    # 7. Unsubscribe — handler stops firing.
    context.unsubscribe_all()
    ctrl.events.signal_added.emit(event)
    assert len(received) == 1  # unchanged, no second delivery
