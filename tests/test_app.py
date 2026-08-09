"""Tests for the application bootstrap in mdf_viewer.app.

run() wires up the real MVC graph and calls QApplication.exec(), so every
Qt/model/controller class it constructs is mocked here; only the
startup-argument routing (REQ-FILE-080) is under test.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from mdf_viewer.app import run


@pytest.fixture(autouse=True)
def _noop_logging_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """run() calls the real configure_logging()/install_excepthook() against
    a fully-mocked Settings instance — harmless (RotatingFileHandler's
    FileNotFoundError against a MagicMock-derived path is swallowed by
    configure_logging()'s own OSError guard) but pointless I/O attempts in
    every test in this file; stub them out except where explicitly tested.
    """
    monkeypatch.setattr("mdf_viewer.logging_config.configure_logging", lambda settings: None)
    monkeypatch.setattr("mdf_viewer.logging_config.install_excepthook", lambda: None)


@pytest.fixture()
def app_mocks():
    with (
        patch("PyQt6.QtWidgets.QApplication") as mock_qapp_cls,
        patch("PyQt6.QtWidgets.QMessageBox") as mock_msgbox_cls,
        patch("PyQt6.QtWidgets.QSplashScreen"),
        patch("PyQt6.QtGui.QIcon"),
        patch("PyQt6.QtGui.QPainter"),
        patch("PyQt6.QtGui.QPixmap"),
        patch("PyQt6.QtGui.QFont"),
        patch("mdf_viewer.view.main_window.MainWindow") as mock_window_cls,
        patch("mdf_viewer.settings.Settings") as mock_settings_cls,
        patch("mdf_viewer.license.license_manager.LicenseManager"),
        patch("mdf_viewer.model.mdf_loader.MdfLoader"),
        patch("mdf_viewer.controller.app_controller.AppController") as mock_controller_cls,
        patch("mdf_viewer.controller.cursor_controller.CursorController"),
        patch("mdf_viewer.controller.zoom_controller.ZoomController"),
        patch("mdf_viewer.view.cursors.CursorView"),
        patch("mdf_viewer.plugin_api.loader.PluginLoader") as mock_loader_cls,
    ):
        mock_qapp_cls.return_value.primaryScreen.return_value.devicePixelRatio.return_value = 1.0
        mock_settings_cls.return_value.plugins_dir = None
        yield {
            "window": mock_window_cls.return_value,
            "controller": mock_controller_cls.return_value,
            "message_box": mock_msgbox_cls,
            "plugin_loader": mock_loader_cls.return_value,
            "plugin_loader_cls": mock_loader_cls,
            "settings": mock_settings_cls.return_value,
        }


@pytest.mark.requirement("REQ-FILE-080")
def test_run_with_no_argv_loads_nothing(app_mocks) -> None:
    run(["mdf-viewer"])
    app_mocks["controller"].load_file.assert_not_called()
    app_mocks["window"].open_config.assert_not_called()


@pytest.mark.requirement("REQ-FILE-080")
def test_run_with_measurement_path_argv_loads_it(app_mocks, tmp_path: Path) -> None:
    mf4 = tmp_path / "test.mf4"
    mf4.touch()

    run(["mdf-viewer", str(mf4)])

    app_mocks["controller"].load_file.assert_called_once_with(mf4)
    app_mocks["window"].open_config.assert_not_called()


@pytest.mark.requirement("REQ-FILE-080")
def test_run_with_mvc_path_argv_opens_config_instead(app_mocks, tmp_path: Path) -> None:
    mvc = tmp_path / "session.mvc"
    mvc.touch()

    run(["mdf-viewer", str(mvc)])

    app_mocks["window"].open_config.assert_called_once_with(mvc)
    app_mocks["controller"].load_file.assert_not_called()


@pytest.mark.requirement("REQ-FILE-080")
def test_run_with_nonexistent_argv_path_loads_nothing(app_mocks, tmp_path: Path) -> None:
    missing = tmp_path / "missing.mf4"

    run(["mdf-viewer", str(missing)])

    app_mocks["controller"].load_file.assert_not_called()
    app_mocks["window"].open_config.assert_not_called()


# ---------------------------------------------------------------------------
# Plugin loader wiring (#74)
# ---------------------------------------------------------------------------

def test_run_loads_plugins(app_mocks) -> None:
    run(["mdf-viewer"])
    app_mocks["plugin_loader"].load_all.assert_called_once()


def test_run_deactivates_plugins_on_shutdown(app_mocks) -> None:
    run(["mdf-viewer"])
    app_mocks["plugin_loader"].deactivate_all.assert_called_once()


@pytest.mark.requirement("REQ-LOG-030")
def test_run_logs_startup_and_shutdown(app_mocks, caplog) -> None:
    from mdf_viewer import __version__

    with caplog.at_level("INFO", logger="mdf_viewer.app"):
        run(["mdf-viewer"])
    messages = [r.message for r in caplog.records]
    assert any(f"MDF-Viewer {__version__} starting" in m for m in messages)
    assert any("MDF-Viewer shutting down" in m for m in messages)


@pytest.mark.requirement("REQ-PLUGIN-410")
def test_run_threads_settings_into_plugin_loader(app_mocks) -> None:
    run(["mdf-viewer"])
    kwargs = app_mocks["plugin_loader_cls"].call_args.kwargs
    assert kwargs["settings"] is app_mocks["settings"]


def test_run_wires_plugin_loader_hooks_to_the_real_loader(app_mocks) -> None:
    """#150 — MainWindow's Rescan/Reload menu entries must be driven by the
    real PluginLoader instance, not a stand-in."""
    run(["mdf-viewer"])

    app_mocks["window"].set_plugin_loader_hooks.assert_called_once()
    kwargs = app_mocks["window"].set_plugin_loader_hooks.call_args.kwargs

    kwargs["rescan"]()
    app_mocks["plugin_loader"].rescan.assert_called_once()

    kwargs["reload_plugin"]("SomePlugin")
    app_mocks["plugin_loader"].reload_one.assert_called_once_with("SomePlugin")

    kwargs["active_plugin_names"]()
    app_mocks["plugin_loader"].active_plugin_names.assert_called_once()

    kwargs["list_packages"]()
    app_mocks["plugin_loader"].list_packages.assert_called_once()

    kwargs["set_plugin_enabled"]("some_folder", False)
    app_mocks["plugin_loader"].set_enabled.assert_called_once_with("some_folder", False)

    kwargs["active_plugin_names_for"]("some_folder")
    app_mocks["plugin_loader"].active_plugin_names_for.assert_called_once_with("some_folder")


# ---------------------------------------------------------------------------
# _xaxis_cursor_kwargs (#86 — X-Axis Signal tabs)
# ---------------------------------------------------------------------------

def _make_workspace(view_type: str = "plot", axis_signal=None):
    from mdf_viewer.controller.app_controller import TabWorkspace

    return TabWorkspace(plot=object(), table=object(), view_type=view_type, axis_signal=axis_signal)


def _make_axis_signal():
    import numpy as np
    from PyQt6.QtGui import QColor

    from mdf_viewer.model.signal_data import SignalData
    from mdf_viewer.model.signal_metadata import SignalMetadata
    from mdf_viewer.view_model.active_signal import ActiveSignal

    data = SignalData(timestamps=np.array([0.0, 1.0, 2.0]), samples=np.array([10.0, 20.0, 30.0]))
    meta = SignalMetadata(name="axis")
    return ActiveSignal(data=data, metadata=meta, color=QColor(1, 2, 3))


def test_xaxis_cursor_kwargs_empty_for_plot_workspace() -> None:
    from mdf_viewer.app import _xaxis_cursor_kwargs

    assert _xaxis_cursor_kwargs(_make_workspace(view_type="plot")) == {}


def test_xaxis_cursor_kwargs_empty_when_axis_signal_unset() -> None:
    from mdf_viewer.app import _xaxis_cursor_kwargs

    assert _xaxis_cursor_kwargs(_make_workspace(view_type="xaxis", axis_signal=None)) == {}


@pytest.mark.requirement("REQ-XAXIS-052")
def test_xaxis_cursor_kwargs_pin_reference_signal_returns_axis_signal() -> None:
    from mdf_viewer.app import _xaxis_cursor_kwargs

    axis = _make_axis_signal()
    kwargs = _xaxis_cursor_kwargs(_make_workspace(view_type="xaxis", axis_signal=axis))
    assert kwargs["pin_reference_signal"]() is axis


def test_xaxis_cursor_kwargs_to_render_x_interpolates_axis_value() -> None:
    from mdf_viewer.app import _xaxis_cursor_kwargs

    axis = _make_axis_signal()
    kwargs = _xaxis_cursor_kwargs(_make_workspace(view_type="xaxis", axis_signal=axis))
    assert kwargs["to_render_x"](0.5) == pytest.approx(15.0)  # halfway between 10 and 20


def test_xaxis_cursor_kwargs_to_render_x_clamps_out_of_range_time() -> None:
    from mdf_viewer.app import _xaxis_cursor_kwargs

    axis = _make_axis_signal()
    kwargs = _xaxis_cursor_kwargs(_make_workspace(view_type="xaxis", axis_signal=axis))
    assert kwargs["to_render_x"](-5.0) == pytest.approx(10.0)   # clamped to first instant
    assert kwargs["to_render_x"](100.0) == pytest.approx(30.0)  # clamped to last instant


@pytest.mark.requirement("REQ-XAXIS-041")
def test_xaxis_cursor_kwargs_resolve_time_at_render_x_finds_nearest_instant() -> None:
    from mdf_viewer.app import _xaxis_cursor_kwargs

    axis = _make_axis_signal()
    kwargs = _xaxis_cursor_kwargs(_make_workspace(view_type="xaxis", axis_signal=axis))
    assert kwargs["resolve_time_at_render_x"](21.0, current_time=0.0) == pytest.approx(1.0)


@pytest.mark.requirement("REQ-XAXIS-050")
def test_xaxis_cursor_kwargs_step_value_steps_by_axis_value() -> None:
    from mdf_viewer.app import _xaxis_cursor_kwargs

    axis = _make_axis_signal()
    kwargs = _xaxis_cursor_kwargs(_make_workspace(view_type="xaxis", axis_signal=axis))
    # From t=0 (value 10), stepping forward by >=15 lands on t=2 (value 30).
    assert kwargs["step_value"](0.0, 1, 15.0) == pytest.approx(2.0)
