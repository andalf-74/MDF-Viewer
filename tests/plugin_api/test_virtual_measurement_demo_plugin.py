"""Tests for the Virtual Measurement Demo proof-of-concept plugin (#152).

Loads the real, committed plugin at <repo root>/plugins/virtual_measurement_demo/
through the real PluginLoader — the same discovery mechanism the app itself
uses — proving the actual shipped file exercises #147's virtual measurement
pipeline correctly end-to-end.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from pytestqt.qtbot import QtBot

from mdf_viewer.controller.app_controller import AppController
from mdf_viewer.plugin_api.loader import PluginLoader

REPO_PLUGINS_DIR = Path(__file__).resolve().parents[2] / "plugins"


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


def test_plugin_is_discovered_and_activated_by_the_real_loader(
    qtbot: QtBot, ctrl: AppController,
) -> None:
    assert (REPO_PLUGINS_DIR / "virtual_measurement_demo" / "__init__.py").is_file()

    loader = PluginLoader(app=ctrl, plugins_dir=REPO_PLUGINS_DIR, app_version="1.0")
    result = loader.load_all()

    # Not an exact-list assertion: REPO_PLUGINS_DIR also holds other
    # committed plugins (e.g. #75's signal_statistics) that load alongside
    # this one.
    assert "Virtual Measurement Demo" in result.loaded
    assert result.failed == []

    loader.deactivate_all()


def test_create_action_registers_a_two_signal_virtual_measurement(
    qtbot: QtBot, ctrl: AppController,
) -> None:
    loader = PluginLoader(app=ctrl, plugins_dir=REPO_PLUGINS_DIR, app_version="1.0")
    loader.load_all()
    registration = next(
        r for r in ctrl.plugin_registry.menu_actions if r.plugin_name == "Virtual Measurement Demo"
    )
    assert registration.label == "Create Virtual Measurement"

    assert registration.invoke() is True

    assert len(ctrl.measurements) == 1
    measurement = ctrl.measurements[0]
    assert measurement.label == "Virtual Measurement Demo"
    assert measurement.owner_plugin == "Virtual Measurement Demo"
    channel_names = [ch.name for group in measurement.loader.channel_tree() for ch in group.channels]
    assert channel_names == ["Sine Wave", "Counter"]

    loader.deactivate_all()


def test_create_action_twice_disambiguates_labels(qtbot: QtBot, ctrl: AppController) -> None:
    loader = PluginLoader(app=ctrl, plugins_dir=REPO_PLUGINS_DIR, app_version="1.0")
    loader.load_all()
    registration = next(
        r for r in ctrl.plugin_registry.menu_actions if r.plugin_name == "Virtual Measurement Demo"
    )

    registration.invoke()
    registration.invoke()

    labels = sorted(m.label for m in ctrl.measurements)
    assert labels == ["Virtual Measurement Demo", "Virtual Measurement Demo (2)"]

    loader.deactivate_all()


def test_on_measurement_closed_logs_for_virtual_measurement_close(
    qtbot: QtBot, ctrl: AppController, capsys: pytest.CaptureFixture,
) -> None:
    loader = PluginLoader(app=ctrl, plugins_dir=REPO_PLUGINS_DIR, app_version="1.0")
    loader.load_all()
    registration = next(
        r for r in ctrl.plugin_registry.menu_actions if r.plugin_name == "Virtual Measurement Demo"
    )
    registration.invoke()
    measurement = ctrl.measurements[0]

    ctrl.close_measurement(measurement)

    captured = capsys.readouterr()
    assert "measurement_closed" in captured.out
    assert "Virtual Measurement Demo" in captured.out

    loader.deactivate_all()


def test_attach_extra_action_grows_the_already_registered_measurement(
    qtbot: QtBot, ctrl: AppController,
) -> None:
    loader = PluginLoader(app=ctrl, plugins_dir=REPO_PLUGINS_DIR, app_version="1.0")
    loader.load_all()
    actions = {
        r.label: r
        for r in ctrl.plugin_registry.menu_actions
        if r.plugin_name == "Virtual Measurement Demo"
    }
    actions["Create Virtual Measurement"].invoke()
    measurement = ctrl.measurements[0]

    actions["Attach Extra Signal to Demo Measurement"].invoke()

    channel_names = [ch.name for group in measurement.loader.channel_tree() for ch in group.channels]
    assert channel_names == ["Sine Wave", "Counter", "Ramp 1"]

    loader.deactivate_all()


def test_attach_extra_action_before_create_is_a_safe_noop(
    qtbot: QtBot, ctrl: AppController, capsys: pytest.CaptureFixture,
) -> None:
    loader = PluginLoader(app=ctrl, plugins_dir=REPO_PLUGINS_DIR, app_version="1.0")
    loader.load_all()
    actions = {
        r.label: r
        for r in ctrl.plugin_registry.menu_actions
        if r.plugin_name == "Virtual Measurement Demo"
    }

    assert actions["Attach Extra Signal to Demo Measurement"].invoke() is True
    assert ctrl.measurements == []

    loader.deactivate_all()


def test_detach_counter_action_removes_a_plotted_counter_signal(
    qtbot: QtBot, ctrl: AppController,
) -> None:
    loader = PluginLoader(app=ctrl, plugins_dir=REPO_PLUGINS_DIR, app_version="1.0")
    loader.load_all()
    actions = {
        r.label: r
        for r in ctrl.plugin_registry.menu_actions
        if r.plugin_name == "Virtual Measurement Demo"
    }
    actions["Create Virtual Measurement"].invoke()
    measurement = ctrl.measurements[0]
    ctrl.add_signal(0, 1, measurement=measurement)  # plot "Counter"
    assert len(ctrl.current_workspace.active) == 1

    actions["Detach Counter Signal from Demo Measurement"].invoke()

    assert ctrl.current_workspace.active == []
    channel_names = [ch.name for group in measurement.loader.channel_tree() for ch in group.channels]
    assert channel_names == ["Sine Wave"]

    loader.deactivate_all()


def test_on_measurement_updated_logs_for_attach(
    qtbot: QtBot, ctrl: AppController, capsys: pytest.CaptureFixture,
) -> None:
    loader = PluginLoader(app=ctrl, plugins_dir=REPO_PLUGINS_DIR, app_version="1.0")
    loader.load_all()
    actions = {
        r.label: r
        for r in ctrl.plugin_registry.menu_actions
        if r.plugin_name == "Virtual Measurement Demo"
    }
    actions["Create Virtual Measurement"].invoke()

    actions["Attach Extra Signal to Demo Measurement"].invoke()

    captured = capsys.readouterr()
    assert "measurement_updated" in captured.out
    assert "attached" in captured.out

    loader.deactivate_all()
