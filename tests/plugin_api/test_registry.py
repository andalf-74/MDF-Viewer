"""Tests for PluginRegistry and its registration wrappers (#71)."""

from __future__ import annotations

import logging

import pytest

from mdf_viewer.plugin_api.registry import (
    DockWidgetRegistration,
    MenuActionRegistration,
    PluginRegistry,
)


def test_add_menu_action_tags_plugin_name() -> None:
    registry = PluginRegistry()
    registration = MenuActionRegistration(plugin_name="exporter", label="Export", callback=lambda: None)
    registry.add_menu_action(registration)
    assert registry.menu_actions == [registration]
    assert registry.menu_actions[0].plugin_name == "exporter"


@pytest.mark.requirement("REQ-PLUGIN-150")
def test_menu_action_invoke_swallows_and_logs_exception(caplog: pytest.LogCaptureFixture) -> None:
    def boom() -> None:
        raise ValueError("plugin bug")

    registration = MenuActionRegistration(plugin_name="exporter", label="Export", callback=boom)
    with caplog.at_level(logging.ERROR, logger="mdf_viewer.plugin_api"):
        registration.invoke()  # must not raise
    assert "exporter" in caplog.text
    assert "Export" in caplog.text


@pytest.mark.requirement("REQ-PLUGIN-150")
def test_dock_widget_build_swallows_and_logs_exception(caplog: pytest.LogCaptureFixture) -> None:
    def boom() -> object:
        raise ValueError("plugin bug")

    registration = DockWidgetRegistration(
        plugin_name="artificial_signals", title="Add Signal", widget_factory=boom, mode="dialog",
    )
    with caplog.at_level(logging.ERROR, logger="mdf_viewer.plugin_api"):
        result = registration.build()
    assert result is None
    assert "artificial_signals" in caplog.text


def test_dock_widget_build_returns_widget_on_success() -> None:
    sentinel = object()
    registration = DockWidgetRegistration(
        plugin_name="exporter", title="Export", widget_factory=lambda: sentinel, mode="docked",
    )
    assert registration.build() is sentinel


def test_remove_registrations_for_only_removes_matching_plugin() -> None:
    registry = PluginRegistry()
    registry.add_menu_action(MenuActionRegistration("a", "A action", lambda: None))
    registry.add_menu_action(MenuActionRegistration("b", "B action", lambda: None))
    registry.add_dock_widget(DockWidgetRegistration("a", "A dock", lambda: None, "docked"))
    registry.add_dock_widget(DockWidgetRegistration("b", "B dock", lambda: None, "dialog"))

    registry.remove_registrations_for("a")

    assert [r.plugin_name for r in registry.menu_actions] == ["b"]
    assert [r.plugin_name for r in registry.dock_widgets] == ["b"]
