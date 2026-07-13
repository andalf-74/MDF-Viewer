"""Tests for the Signal Statistics proof-of-concept plugin (#75).

Loads the real, committed plugin at <repo root>/plugins/signal_statistics/
through the real PluginLoader — the same discovery mechanism the app
itself uses in dev mode — rather than importing it directly, so these
tests prove the actual shipped file works via the actual pipeline.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from PyQt6.QtWidgets import QFormLayout
from pytestqt.qtbot import QtBot

from mdf_viewer.controller.app_controller import AppController
from mdf_viewer.model.measurement import MeasurementInfo
from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.plugin_api.loader import PluginLoader

REPO_PLUGINS_DIR = Path(__file__).resolve().parents[2] / "plugins"


@pytest.fixture()
def deps() -> dict:
    loader = MagicMock()
    loader.channel_tree.return_value = []
    loader.measurement_info.return_value = MeasurementInfo(file_name="test.mf4")
    t = np.array([0.0, 1.0, 2.0, 3.0])
    loader.load_signal.return_value = (
        SignalData(timestamps=t, samples=np.array([2.0, 4.0, 6.0, 8.0])),
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


def test_plugin_is_discovered_and_activated_by_the_real_loader(
    qtbot: QtBot, ctrl: AppController,
) -> None:
    assert (REPO_PLUGINS_DIR / "signal_statistics" / "__init__.py").is_file()

    loader = PluginLoader(app=ctrl, plugins_dir=REPO_PLUGINS_DIR)
    result = loader.load_all()

    assert result.loaded == ["Signal Statistics"]
    assert result.failed == []

    loader.deactivate_all()


def test_plugin_dock_widget_reflects_min_max_mean_and_resets_on_deselect(
    qtbot: QtBot, ctrl: AppController,
) -> None:
    loader = PluginLoader(app=ctrl, plugins_dir=REPO_PLUGINS_DIR)
    loader.load_all()

    # Mirrors what MainWindow._build_plugin_dock_sections() (#73) does in
    # the real app: lazily build the registered widget once.
    registration = ctrl.plugin_registry.dock_widgets[0]
    widget = registration.build()
    qtbot.addWidget(widget)
    form = widget.layout()
    assert isinstance(form, QFormLayout)
    min_label = form.itemAt(0, QFormLayout.ItemRole.FieldRole).widget()
    max_label = form.itemAt(1, QFormLayout.ItemRole.FieldRole).widget()
    mean_label = form.itemAt(2, QFormLayout.ItemRole.FieldRole).widget()
    assert min_label.text() == "—"

    ctrl.add_signal(0, 1)
    ctrl.set_selected_signal(ctrl.active_signals[0])

    assert min_label.text() == "2"
    assert max_label.text() == "8"
    assert mean_label.text() == "5"

    ctrl.set_selected_signal(None)

    assert min_label.text() == "—"
    assert max_label.text() == "—"
    assert mean_label.text() == "—"

    loader.deactivate_all()


def test_plugin_shows_placeholder_for_multi_selection(qtbot: QtBot, ctrl: AppController) -> None:
    loader = PluginLoader(app=ctrl, plugins_dir=REPO_PLUGINS_DIR)
    loader.load_all()
    registration = ctrl.plugin_registry.dock_widgets[0]
    widget = registration.build()
    qtbot.addWidget(widget)
    form = widget.layout()
    min_label = form.itemAt(0, QFormLayout.ItemRole.FieldRole).widget()

    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    ctrl.set_multi_selected(ctrl.active_signals)

    assert min_label.text() == "—"

    loader.deactivate_all()
