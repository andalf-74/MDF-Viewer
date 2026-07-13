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
        mock_settings_cls.return_value.check_for_updates = False
        mock_settings_cls.return_value.plugins_dir = None
        yield {
            "window": mock_window_cls.return_value,
            "controller": mock_controller_cls.return_value,
            "message_box": mock_msgbox_cls,
            "plugin_loader": mock_loader_cls.return_value,
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
