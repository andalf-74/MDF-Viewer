"""Tests for the Tab Type Fixture plugin (#148).

Loads the real, committed plugin at <repo root>/plugins/tab_type_fixture/
through the real PluginLoader — the same discovery mechanism the app
itself uses in dev mode — rather than importing it directly, so these
tests prove the actual shipped file works via the actual pipeline
(matches #75's test_signal_statistics_plugin.py precedent exactly).
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PyQt6.QtWidgets import QLabel
from pytestqt.qtbot import QtBot

from mdf_viewer.controller.app_controller import AppController
from mdf_viewer.plugin_api.loader import PluginLoader

REPO_PLUGINS_DIR = Path(__file__).resolve().parents[2] / "plugins"


@pytest.fixture()
def ctrl() -> AppController:
    return AppController(
        loader=MagicMock(),
        signal_browser=MagicMock(),
        plot_area=MagicMock(),
        active_signals_table=MagicMock(),
        measurement_info_box=MagicMock(),
        signal_info_box=MagicMock(),
    )


def test_plugin_is_discovered_and_activated_by_the_real_loader(
    qtbot: QtBot, ctrl: AppController,
) -> None:
    assert (REPO_PLUGINS_DIR / "tab_type_fixture" / "__init__.py").is_file()

    loader = PluginLoader(app=ctrl, plugins_dir=REPO_PLUGINS_DIR)
    result = loader.load_all()

    assert "Tab Type Fixture" in result.loaded
    assert result.failed == []

    loader.deactivate_all()


@pytest.mark.requirement("REQ-PLUGIN-320")
def test_plugin_registers_its_tab_type(ctrl: AppController) -> None:
    loader = PluginLoader(app=ctrl, plugins_dir=REPO_PLUGINS_DIR)
    loader.load_all()

    fixture_types = [t for t in ctrl.plugin_registry.tab_types if t.plugin_name == "Tab Type Fixture"]
    assert len(fixture_types) == 1
    assert fixture_types[0].type_id == "fixture_tab"
    assert fixture_types[0].display_name == "Fixture Tab"

    loader.deactivate_all()


def test_plugin_view_factory_builds_a_fresh_widget_each_call(
    qtbot: QtBot, ctrl: AppController,
) -> None:
    loader = PluginLoader(app=ctrl, plugins_dir=REPO_PLUGINS_DIR)
    loader.load_all()
    registration = next(t for t in ctrl.plugin_registry.tab_types if t.type_id == "fixture_tab")

    widget_a = registration.build()
    widget_b = registration.build()
    qtbot.addWidget(widget_a)
    qtbot.addWidget(widget_b)

    assert isinstance(widget_a, QLabel)
    assert widget_a is not widget_b

    loader.deactivate_all()
