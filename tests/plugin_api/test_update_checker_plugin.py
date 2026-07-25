"""Tests for the Update Checker plugin (#76).

Two layers, mirroring test_update_checker_checker.py's split:
- Integration tests load the real, committed plugin at
  <repo root>/plugins/update_checker/ through the real PluginLoader — the
  same discovery mechanism the app itself uses — proving the actual
  shipped package works via the actual pipeline.
- White-box tests import the plugin module directly by file path (the
  same sys.modules-registration technique PluginLoader itself uses, so a
  relative `from .checker import ...` still resolves) to exercise
  QThread-level behavior — background start, silent-vs-reported failure,
  and the Reload-mid-check teardown fix (Gap 1 of #76's architecture
  review) — that would be awkward to observe from outside the module.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from pytestqt.qtbot import QtBot

from mdf_viewer.controller.app_controller import AppController
from mdf_viewer.plugin_api.context import PluginContext
from mdf_viewer.plugin_api.loader import PluginLoader
from mdf_viewer.plugin_api.registry import PluginRegistry
from mdf_viewer.settings import UPDATE_CHECKER_PLUGIN_NAME, Settings

REPO_PLUGINS_DIR = Path(__file__).resolve().parents[2] / "plugins"
_INIT_PY = REPO_PLUGINS_DIR / "update_checker" / "__init__.py"


def _load_plugin_module():
    module_name = "_update_checker_plugin_under_test"
    spec = importlib.util.spec_from_file_location(
        module_name, _INIT_PY, submodule_search_locations=[str(_INIT_PY.parent)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


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


# ---------------------------------------------------------------------------
# Integration — real PluginLoader
# ---------------------------------------------------------------------------

def test_plugin_is_discovered_and_activated_by_the_real_loader(
    qtbot: QtBot, ctrl: AppController,
) -> None:
    assert _INIT_PY.is_file()

    loader = PluginLoader(app=ctrl, plugins_dir=REPO_PLUGINS_DIR, app_version="1.0")
    result = loader.load_all()

    # Not an exact-list assertion: REPO_PLUGINS_DIR also holds other
    # committed plugins that load alongside this one.
    assert "Update Checker" in result.loaded
    assert result.failed == []

    loader.deactivate_all()


def test_plugin_name_matches_settings_migration_constant(
    qtbot: QtBot, ctrl: AppController,
) -> None:
    """Guard against the two independently-maintained strings drifting
    apart (Gap 6 of #76's architecture review) — settings.py's migration
    writes into a namespace keyed by this exact string, with no other
    cross-check tying it to the plugin's own declared name.
    """
    loader = PluginLoader(app=ctrl, plugins_dir=REPO_PLUGINS_DIR, app_version="1.0")
    loader.load_all()

    instance = loader._active["Update Checker"].instance

    assert instance.name == UPDATE_CHECKER_PLUGIN_NAME

    loader.deactivate_all()


def test_plugin_registers_menu_action_and_preferences_page(
    qtbot: QtBot, ctrl: AppController,
) -> None:
    loader = PluginLoader(app=ctrl, plugins_dir=REPO_PLUGINS_DIR, app_version="1.0")
    loader.load_all()

    menu_labels = [r.label for r in ctrl.plugin_registry.menu_actions if r.plugin_name == "Update Checker"]
    pref_titles = [r.title for r in ctrl.plugin_registry.preferences_pages if r.plugin_name == "Update Checker"]
    assert menu_labels == ["Check for Update…"]
    assert pref_titles == ["Update Checker"]

    loader.deactivate_all()


def test_preferences_page_checkbox_reflects_and_persists_setting(
    qtbot: QtBot, ctrl: AppController, tmp_path: Path,
) -> None:
    from PyQt6.QtWidgets import QCheckBox

    real_settings = Settings(path=tmp_path / "settings.json")
    loader = PluginLoader(
        app=ctrl, plugins_dir=REPO_PLUGINS_DIR, settings=real_settings, app_version="1.0",
    )
    loader.load_all()

    registration = next(
        r for r in ctrl.plugin_registry.preferences_pages if r.plugin_name == "Update Checker"
    )
    page = registration.build()
    qtbot.addWidget(page)
    checkbox = page.findChild(QCheckBox)
    assert checkbox.isChecked() is True  # default

    checkbox.setChecked(False)

    assert real_settings.get_plugin_setting("Update Checker", "check_for_updates", True) is False

    loader.deactivate_all()


# ---------------------------------------------------------------------------
# White-box — direct module import (QThread-level behavior)
# ---------------------------------------------------------------------------

@pytest.fixture()
def module():
    return _load_plugin_module()


@pytest.fixture()
def context(qtbot: QtBot, tmp_path: Path) -> PluginContext:
    # A real (if empty) window, not None — QApplication.setOverrideCursor
    # (used by _on_check_for_update's busy-cursor wrapper) can fatally
    # abort on the offscreen Qt platform (tests/conftest.py) if no real
    # widget has ever been realized yet; every other test file exercising
    # busy_cursor does so through a fully-built real MainWindow fixture,
    # which already forces this initialization as a side effect.
    from PyQt6.QtWidgets import QMainWindow

    window = QMainWindow()
    qtbot.addWidget(window)
    return PluginContext(
        plugin_name="Update Checker",
        app=MagicMock(),
        registry=PluginRegistry(),
        settings=Settings(path=tmp_path / "settings.json"),
        main_window=window,
        app_version="1.0",
    )


@pytest.mark.requirement("REQ-NFR-030")
def test_activate_starts_check_by_default(qtbot: QtBot, module, context: PluginContext) -> None:
    plugin = module.UpdateCheckerPlugin()

    plugin.activate(context)

    thread = plugin._thread
    assert thread is not None
    assert thread in module._LIVE_THREADS
    assert thread.wait(2000)  # urlopen is patched to fail instantly (tests/plugin_api/conftest.py)
    qtbot.wait(50)  # let the queued finished-signal handlers run
    assert thread not in module._LIVE_THREADS


def test_deactivate_after_thread_already_finished_naturally_does_not_raise(
    qtbot: QtBot, module, context: PluginContext,
) -> None:
    """Regression: a check that completes on its own (e.g. app shutdown
    happening after a successful startup check, not via Reload) must leave
    `deactivate()` with nothing stale to touch. `deleteLater()` destroys
    the underlying C++ QThread object once Qt processes it; if
    `self._thread` still pointed at it, `deactivate()`'s `.disconnect()`
    call would raise `RuntimeError: wrapped C/C++ object ... has been
    deleted` — reproduced live in the real app, not just this test.
    """
    plugin = module.UpdateCheckerPlugin()
    plugin.activate(context)
    thread = plugin._thread
    assert thread is not None
    assert thread.wait(2000)
    qtbot.wait(50)  # let the queued finished-signal handler (_on_thread_finished) run
    assert plugin._thread is None  # cleared on natural completion, not just in deactivate()

    plugin.deactivate()  # must not raise, even though the thread object is now gone


def test_activate_does_not_start_check_when_setting_disabled(module, context: PluginContext) -> None:
    context.set_setting("check_for_updates", False)
    plugin = module.UpdateCheckerPlugin()

    plugin.activate(context)

    assert plugin._thread is None


@pytest.mark.requirement("REQ-NFR-032")
def test_update_check_thread_silent_on_network_failure(qtbot: QtBot, module) -> None:
    thread = module._UpdateCheckThread("1.0")
    emitted: list = []
    thread.update_available.connect(emitted.append)
    with patch(
        f"{module.__name__}.fetch_latest_release",
        side_effect=module.UpdateCheckError("network down"),
    ):
        thread.run()  # called synchronously here — must not raise or emit
    assert emitted == []


@pytest.mark.requirement("REQ-NFR-031")
def test_update_check_thread_emits_when_newer_available(qtbot: QtBot, module) -> None:
    thread = module._UpdateCheckThread("1.0")
    with qtbot.waitSignal(thread.update_available, timeout=500) as blocker:
        with patch(
            f"{module.__name__}.fetch_latest_release",
            return_value=SimpleNamespace(tag="v2.0", url="https://example.com/v2.0"),
        ):
            thread.run()
    assert blocker.args == ["v2.0", "https://example.com/v2.0"]


@pytest.mark.requirement("REQ-NFR-032")
def test_manual_check_for_update_reports_failure(
    qtbot: QtBot, module, context: PluginContext,
) -> None:
    # No startup check running in the background here — this test is only
    # about the manually-triggered path, and a concurrent real thread would
    # race the fetch_latest_release patch below (both call the same
    # module-level name).
    context.set_setting("check_for_updates", False)
    plugin = module.UpdateCheckerPlugin()
    plugin.activate(context)
    with patch(
        f"{module.__name__}.fetch_latest_release",
        side_effect=module.UpdateCheckError("network down"),
    ):
        with patch(f"{module.__name__}.QMessageBox.warning") as mock_warn:
            plugin._on_check_for_update()
    mock_warn.assert_called_once()


@pytest.mark.requirement("REQ-UPDATE-030")
def test_manual_check_shows_update_available_dialog(
    qtbot: QtBot, module, context: PluginContext,
) -> None:
    context.set_setting("check_for_updates", False)  # see reports_failure test above
    plugin = module.UpdateCheckerPlugin()
    plugin.activate(context)
    with patch(
        f"{module.__name__}.fetch_latest_release",
        return_value=SimpleNamespace(tag="v9.9", url="https://example.com/v9.9"),
    ):
        with patch(f"{module.__name__}.QMessageBox") as mock_box_cls:
            mock_box_cls.Icon.Information = MagicMock()
            mock_box_cls.ButtonRole.ActionRole = MagicMock()
            mock_box_cls.StandardButton.Close = MagicMock()
            plugin._on_check_for_update()
    mock_box_cls.assert_called_once()  # the QMessageBox(...) instance, not .information/.warning


@pytest.mark.requirement("REQ-UPDATE-040")
def test_manual_check_shows_up_to_date_dialog_when_no_newer_version(
    qtbot: QtBot, module, context: PluginContext,
) -> None:
    context.set_setting("check_for_updates", False)  # see reports_failure test above
    plugin = module.UpdateCheckerPlugin()
    plugin.activate(context)
    with patch(
        f"{module.__name__}.fetch_latest_release",
        return_value=SimpleNamespace(tag="v1.0", url="https://example.com/v1.0"),
    ):
        with patch(f"{module.__name__}.QMessageBox.information") as mock_info:
            plugin._on_check_for_update()
    mock_info.assert_called_once()


# ---------------------------------------------------------------------------
# Reload-mid-check teardown (Gap 1 of #76's architecture review)
#
# Both tests attach a thread the same way _start_check() wires one up, but
# deliberately never call .start() — these are testing the signal
# connect/disconnect wiring itself, not real QThread execution, so there is
# no real background thread or network call to race against.
# ---------------------------------------------------------------------------

def _attach_unstarted_thread(plugin, module, context: PluginContext):
    thread = module._UpdateCheckThread(context.app_version, context.main_window)
    plugin._thread = thread
    thread.update_available.connect(plugin._on_update_available)
    return thread


def test_deactivate_disconnects_in_flight_thread(module, context: PluginContext) -> None:
    calls: list = []
    module.UpdateCheckerPlugin._on_update_available = (
        lambda self, tag, url: calls.append((tag, url))
    )
    context.set_setting("check_for_updates", False)
    plugin = module.UpdateCheckerPlugin()
    plugin.activate(context)
    thread = _attach_unstarted_thread(plugin, module, context)

    plugin.deactivate()
    # Simulates a check that was still in flight finishing only after
    # Reload already tore this instance down (#150) — must not reach the
    # now-inactive instance's handler.
    thread.update_available.emit("v9.9", "https://example.com/v9.9")

    assert calls == []
    assert plugin._thread is None


def test_update_available_reaches_handler_while_still_active(module, context: PluginContext) -> None:
    calls: list = []
    module.UpdateCheckerPlugin._on_update_available = (
        lambda self, tag, url: calls.append((tag, url))
    )
    context.set_setting("check_for_updates", False)
    plugin = module.UpdateCheckerPlugin()
    plugin.activate(context)
    thread = _attach_unstarted_thread(plugin, module, context)

    thread.update_available.emit("v9.9", "https://example.com/v9.9")

    assert calls == [("v9.9", "https://example.com/v9.9")]


def test_deactivate_is_a_noop_when_no_check_was_started(module, context: PluginContext) -> None:
    context.set_setting("check_for_updates", False)
    plugin = module.UpdateCheckerPlugin()
    plugin.activate(context)

    plugin.deactivate()  # must not raise

    assert plugin._thread is None
