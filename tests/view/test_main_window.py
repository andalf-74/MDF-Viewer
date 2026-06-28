"""Tests for MainWindow.

Covers widget composition, menu/toolbar structure, and controller wiring.
File-dialog and message-box calls are patched so no real filesystem or
display interaction is needed.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pytestqt.qtbot import QtBot

from PyQt6.QtWidgets import QMessageBox

from mdf_viewer.errors import MdfLoadError
from mdf_viewer.view.active_signals_table import ActiveSignalsTable
from mdf_viewer.view.main_window import MainWindow
from mdf_viewer.view.measurement_info_box import MeasurementInfoBox
from mdf_viewer.view.plot_area import PlotArea
from mdf_viewer.view.signal_browser import SignalBrowser
from mdf_viewer.view.signal_info_box import SignalInfoBox


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def window(qtbot: QtBot) -> MainWindow:
    w = MainWindow()
    qtbot.addWidget(w)
    return w


@pytest.fixture()
def mock_controller() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def wired(window: MainWindow, mock_controller: MagicMock) -> MainWindow:
    window.set_controller(mock_controller)
    return window


# ---------------------------------------------------------------------------
# Window properties
# ---------------------------------------------------------------------------

def test_window_title(window: MainWindow) -> None:
    assert "MDF-Viewer" in window.windowTitle()


def test_initial_size(window: MainWindow) -> None:
    assert window.width() == 1280
    assert window.height() == 800


# ---------------------------------------------------------------------------
# Widget composition
# ---------------------------------------------------------------------------

def test_has_signal_browser(window: MainWindow) -> None:
    assert isinstance(window.signal_browser, SignalBrowser)


def test_has_plot_area(window: MainWindow) -> None:
    assert isinstance(window.plot_area, PlotArea)


def test_has_active_signals_table(window: MainWindow) -> None:
    assert isinstance(window.active_signals_table, ActiveSignalsTable)


def test_has_measurement_info_box(window: MainWindow) -> None:
    assert isinstance(window.measurement_info_box, MeasurementInfoBox)


def test_has_signal_info_box(window: MainWindow) -> None:
    assert isinstance(window.signal_info_box, SignalInfoBox)


# ---------------------------------------------------------------------------
# Menu bar
# ---------------------------------------------------------------------------

def test_file_menu_exists(window: MainWindow) -> None:
    titles = [window.menuBar().actions()[i].text() for i in range(window.menuBar().actions().__len__())]
    assert any("File" in t for t in titles)


def test_file_menu_has_load_action(window: MainWindow) -> None:
    file_menu = window.menuBar().actions()[0].menu()
    texts = [a.text() for a in file_menu.actions()]
    assert any("Load" in t for t in texts)


def test_file_menu_has_exit_action(window: MainWindow) -> None:
    file_menu = window.menuBar().actions()[0].menu()
    texts = [a.text() for a in file_menu.actions()]
    assert any("Exit" in t for t in texts)


def test_load_action_has_shortcut(window: MainWindow) -> None:
    assert not window._load_action.shortcut().isEmpty()


# ---------------------------------------------------------------------------
# Toolbar
# ---------------------------------------------------------------------------

def test_toolbar_is_present(window: MainWindow) -> None:
    assert len(window.findChildren(type(window.addToolBar("_dummy"))) ) >= 1


def test_toolbar_has_load_action(window: MainWindow) -> None:
    toolbars = window.findChildren(type(window.addToolBar("_t")))
    toolbar_actions = [a for tb in toolbars for a in tb.actions()]
    assert window._load_action in toolbar_actions


def test_toolbar_has_zoom_fit_action(window: MainWindow) -> None:
    toolbars = window.findChildren(type(window.addToolBar("_t")))
    toolbar_actions = [a for tb in toolbars for a in tb.actions()]
    assert window._zoom_fit_action in toolbar_actions


def test_toolbar_has_cursor_action(window: MainWindow) -> None:
    toolbars = window.findChildren(type(window.addToolBar("_t")))
    toolbar_actions = [a for tb in toolbars for a in tb.actions()]
    assert window._cursor_action in toolbar_actions


# ---------------------------------------------------------------------------
# Help menu / About
# ---------------------------------------------------------------------------

def test_help_menu_has_about_action(window: MainWindow) -> None:
    assert window._about_action in window._help_menu.actions()


def test_about_action_shows_message_box(window: MainWindow) -> None:
    with patch("mdf_viewer.view.main_window.QMessageBox.about") as mock_about:
        window._about_action.trigger()
    mock_about.assert_called_once()
    args, _ = mock_about.call_args
    assert args[0] is window
    assert "MDF-Viewer" in args[2]


# ---------------------------------------------------------------------------
# Theme-aware icon selection
# ---------------------------------------------------------------------------

def test_icon_suffix_dark_scheme_uses_unsuffixed_icons(monkeypatch) -> None:
    from PyQt6.QtCore import Qt
    from mdf_viewer.view import main_window

    style_hints = MagicMock()
    style_hints.colorScheme.return_value = Qt.ColorScheme.Dark
    monkeypatch.setattr(
        main_window.QApplication, "styleHints", lambda: style_hints
    )
    assert main_window._icon_suffix() == ""


@pytest.mark.parametrize("scheme_name", ["Light", "Unknown"])
def test_icon_suffix_light_or_unknown_scheme_uses_light_icons(
    monkeypatch, scheme_name: str
) -> None:
    from PyQt6.QtCore import Qt
    from mdf_viewer.view import main_window

    style_hints = MagicMock()
    style_hints.colorScheme.return_value = getattr(Qt.ColorScheme, scheme_name)
    monkeypatch.setattr(
        main_window.QApplication, "styleHints", lambda: style_hints
    )
    assert main_window._icon_suffix() == "_light"


# ---------------------------------------------------------------------------
# Controller wiring
# ---------------------------------------------------------------------------

def test_add_signal_connects_after_set_controller(
    wired: MainWindow, mock_controller: MagicMock, qtbot: QtBot
) -> None:
    wired.signal_browser.add_signals_requested.emit([(2, 5)])
    mock_controller.add_signal.assert_called_once_with(2, 5)


def test_add_signal_not_called_before_set_controller(
    window: MainWindow, qtbot: QtBot
) -> None:
    # Emit before set_controller — must not crash
    window.signal_browser.add_signals_requested.emit([(0, 1)])


def test_load_file_calls_controller(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    with patch(
        "mdf_viewer.view.main_window.QFileDialog.getOpenFileName",
        return_value=("/fake/file.mf4", "MDF Files"),
    ):
        wired._load_action.trigger()
    mock_controller.load_file.assert_called_once_with("/fake/file.mf4")


def test_load_file_cancelled_does_not_call_controller(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    with patch(
        "mdf_viewer.view.main_window.QFileDialog.getOpenFileName",
        return_value=("", ""),
    ):
        wired._load_action.trigger()
    mock_controller.load_file.assert_not_called()


def test_load_error_shows_message_box(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    mock_controller.load_file.side_effect = MdfLoadError("corrupted file")
    with patch(
        "mdf_viewer.view.main_window.QFileDialog.getOpenFileName",
        return_value=("/bad/file.mf4", "MDF Files"),
    ):
        with patch("mdf_viewer.view.main_window.QMessageBox.critical") as mock_crit:
            wired._load_action.trigger()
    mock_crit.assert_called_once()
    assert "corrupted file" in mock_crit.call_args[0][2]


def test_add_signal_error_shows_message_box(
    wired: MainWindow, mock_controller: MagicMock, qtbot: QtBot
) -> None:
    mock_controller.add_signal.side_effect = MdfLoadError("non-numeric channel")
    with patch("mdf_viewer.view.main_window.QMessageBox.critical") as mock_crit:
        wired.signal_browser.add_signals_requested.emit([(0, 1)])
    mock_crit.assert_called_once()
    assert "non-numeric channel" in mock_crit.call_args[0][2]


# ---------------------------------------------------------------------------
# Recent files menu
# ---------------------------------------------------------------------------

def test_recent_files_not_shown_without_provider(window: MainWindow) -> None:
    window._file_menu.aboutToShow.emit()
    assert window._recent_actions == []


def test_recent_files_shown_when_provider_set(
    window: MainWindow, tmp_path, qtbot: QtBot
) -> None:
    p = tmp_path / "test.mf4"
    p.touch()
    window.set_recent_files_provider(lambda: [p])
    window._file_menu.aboutToShow.emit()
    assert len(window._recent_actions) == 1
    assert window._recent_actions[0].text() == "test.mf4"


def test_recent_files_empty_provider_shows_no_actions(
    window: MainWindow, qtbot: QtBot
) -> None:
    window.set_recent_files_provider(lambda: [])
    window._file_menu.aboutToShow.emit()
    assert window._recent_actions == []
    assert window._recent_sep is None


def test_recent_files_rebuilt_on_each_show(
    window: MainWindow, tmp_path, qtbot: QtBot
) -> None:
    p = tmp_path / "file.mf4"
    p.touch()
    calls = []
    window.set_recent_files_provider(lambda: calls.append(1) or [p])
    window._file_menu.aboutToShow.emit()
    window._file_menu.aboutToShow.emit()
    assert len(calls) == 2
    assert len(window._recent_actions) == 1  # not doubled


def test_open_recent_calls_controller(
    wired: MainWindow, mock_controller: MagicMock, tmp_path, qtbot: QtBot
) -> None:
    p = tmp_path / "recent.mf4"
    p.touch()
    wired.set_recent_files_provider(lambda: [p])
    wired._file_menu.aboutToShow.emit()
    wired._recent_actions[0].trigger()
    mock_controller.load_file.assert_called_once_with(p)


def test_open_recent_error_shows_message_box(
    wired: MainWindow, mock_controller: MagicMock, tmp_path, qtbot: QtBot
) -> None:
    p = tmp_path / "bad.mf4"
    p.touch()
    mock_controller.load_file.side_effect = MdfLoadError("bad file")
    wired.set_recent_files_provider(lambda: [p])
    wired._file_menu.aboutToShow.emit()
    with patch("mdf_viewer.view.main_window.QMessageBox.critical") as mock_crit:
        wired._recent_actions[0].trigger()
    mock_crit.assert_called_once()


# ---------------------------------------------------------------------------
# Status bar
# ---------------------------------------------------------------------------

def test_status_bar_present(window: MainWindow) -> None:
    assert window.statusBar() is not None


def test_show_status_displays_message(window: MainWindow) -> None:
    window.show_status("hello world", timeout_ms=0)
    assert window.statusBar().currentMessage() == "hello world"


# ---------------------------------------------------------------------------
# _on_add_signals — multi-add and skip notification
# ---------------------------------------------------------------------------

def test_on_add_signals_calls_add_signal_for_each(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    mock_controller.add_signal.return_value = True
    wired._on_add_signals([(0, 1), (1, 2)])
    assert mock_controller.add_signal.call_count == 2
    mock_controller.add_signal.assert_any_call(0, 1)
    mock_controller.add_signal.assert_any_call(1, 2)


def test_on_add_signals_shows_status_when_skipped(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    mock_controller.add_signal.return_value = False
    wired._on_add_signals([(0, 1), (0, 2)])
    msg = wired.statusBar().currentMessage()
    assert "2 signals already active" in msg


def test_on_add_signals_skipped_singular(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    mock_controller.add_signal.return_value = False
    wired._on_add_signals([(0, 1)])
    msg = wired.statusBar().currentMessage()
    assert "1 signal already active" in msg


def test_on_add_signals_no_status_when_none_skipped(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    mock_controller.add_signal.return_value = True
    wired._on_add_signals([(0, 1)])
    assert wired.statusBar().currentMessage() == ""


# ---------------------------------------------------------------------------
# _on_file_dropped
# ---------------------------------------------------------------------------

def test_file_dropped_loads_when_no_file_loaded(
    wired: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    mock_controller.is_file_loaded = False
    path = tmp_path / "test.mf4"
    wired._on_file_dropped(path)
    mock_controller.load_file.assert_called_once_with(path)


def test_file_dropped_asks_confirmation_when_file_loaded(
    wired: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    mock_controller.is_file_loaded = True
    path = tmp_path / "test.mf4"
    with patch(
        "mdf_viewer.view.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.No,
    ):
        wired._on_file_dropped(path)
    mock_controller.load_file.assert_not_called()


def test_file_dropped_loads_when_confirmed(
    wired: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    mock_controller.is_file_loaded = True
    path = tmp_path / "test.mf4"
    with patch(
        "mdf_viewer.view.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Yes,
    ):
        wired._on_file_dropped(path)
    mock_controller.load_file.assert_called_once_with(path)


def test_file_dropped_error_shows_message_box(
    wired: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    mock_controller.is_file_loaded = False
    mock_controller.load_file.side_effect = MdfLoadError("corrupt")
    path = tmp_path / "bad.mf4"
    with patch("mdf_viewer.view.main_window.QMessageBox.critical") as mock_crit:
        wired._on_file_dropped(path)
    mock_crit.assert_called_once()


# ---------------------------------------------------------------------------
# Zoom to Cursors toolbar action
# ---------------------------------------------------------------------------

def test_zoom_cursors_action_initially_disabled(window: MainWindow) -> None:
    assert not window._zoom_cursors_action.isEnabled()


def test_zoom_cursors_action_enabled_when_mode_two(window: MainWindow) -> None:
    from mdf_viewer.controller.cursor_controller import CursorMode
    window._on_cursor_mode_changed(CursorMode.TWO)
    assert window._zoom_cursors_action.isEnabled()


def test_zoom_cursors_action_disabled_when_mode_one(window: MainWindow) -> None:
    from mdf_viewer.controller.cursor_controller import CursorMode
    window._on_cursor_mode_changed(CursorMode.TWO)
    window._on_cursor_mode_changed(CursorMode.ONE)
    assert not window._zoom_cursors_action.isEnabled()


def test_zoom_cursors_action_disabled_when_hidden(window: MainWindow) -> None:
    from mdf_viewer.controller.cursor_controller import CursorMode
    window._on_cursor_mode_changed(CursorMode.TWO)
    window._on_cursor_mode_changed(CursorMode.HIDDEN)
    assert not window._zoom_cursors_action.isEnabled()


def test_zoom_cursors_delegates_to_controller(
    window: MainWindow, mock_controller: MagicMock
) -> None:
    window.set_controller(mock_controller)
    window._on_zoom_to_cursors()
    mock_controller.zoom_to_cursors.assert_called_once()


def test_color_change_calls_recolor_signals(
    wired: MainWindow, mock_controller: MagicMock, qtbot: QtBot
) -> None:
    from PyQt6.QtGui import QColor
    import numpy as np
    from mdf_viewer.model.signal_data import SignalData
    from mdf_viewer.model.signal_metadata import SignalMetadata
    from mdf_viewer.view_model.active_signal import ActiveSignal

    t = np.linspace(0, 1, 10)
    active = ActiveSignal(
        data=SignalData(timestamps=t, samples=t),
        metadata=SignalMetadata(name="x", group_index=0, channel_index=0),
        color=QColor(255, 0, 0),
    )
    new_color = QColor(0, 255, 0)

    wired.active_signals_table.color_change_requested.emit([active], new_color)

    mock_controller.recolor_signals.assert_called_once_with([active], new_color)


def test_plot_signal_clicked_selects_table_row(
    wired: MainWindow, qtbot: QtBot
) -> None:
    import numpy as np
    from PyQt6.QtGui import QColor
    from mdf_viewer.model.signal_data import SignalData
    from mdf_viewer.model.signal_metadata import SignalMetadata
    from mdf_viewer.view_model.active_signal import ActiveSignal

    t = np.linspace(0, 1, 10)
    active = ActiveSignal(
        data=SignalData(timestamps=t, samples=t),
        metadata=SignalMetadata(name="x", group_index=0, channel_index=0),
        color=QColor(255, 0, 0),
    )
    wired.active_signals_table.add_row(active)

    received = []
    wired.active_signals_table.selection_changed.connect(received.append)
    wired.plot_area.signal_clicked.emit(active)

    assert received == [active]


def test_plot_signal_clicked_none_clears_table_selection(
    wired: MainWindow, qtbot: QtBot
) -> None:
    import numpy as np
    from PyQt6.QtGui import QColor
    from mdf_viewer.model.signal_data import SignalData
    from mdf_viewer.model.signal_metadata import SignalMetadata
    from mdf_viewer.view_model.active_signal import ActiveSignal

    t = np.linspace(0, 1, 10)
    active = ActiveSignal(
        data=SignalData(timestamps=t, samples=t),
        metadata=SignalMetadata(name="x", group_index=0, channel_index=0),
        color=QColor(255, 0, 0),
    )
    wired.active_signals_table.add_row(active)
    wired.active_signals_table._table.selectRow(0)

    received = []
    wired.active_signals_table.selection_changed.connect(received.append)
    wired.plot_area.signal_clicked.emit(None)

    assert received == [None]


# ---------------------------------------------------------------------------
# Config menu actions
# ---------------------------------------------------------------------------

def test_save_config_action_exists(window: MainWindow) -> None:
    assert window._save_config_action is not None


def test_save_config_as_action_exists(window: MainWindow) -> None:
    assert window._save_config_as_action is not None


def test_save_config_action_shortcut_is_ctrl_s(window: MainWindow) -> None:
    from PyQt6.QtGui import QKeySequence
    assert window._save_config_action.shortcut() == QKeySequence("Ctrl+S")


# ---------------------------------------------------------------------------
# closeEvent — prompt logic
# ---------------------------------------------------------------------------

def test_should_not_prompt_when_no_active_signals(
    window: MainWindow, mock_controller: MagicMock
) -> None:
    from mdf_viewer.settings import Settings
    settings = MagicMock(spec=Settings)
    settings.prompt_save_config_on_close = True
    window._settings = settings
    window._controller = mock_controller
    mock_controller.active_signals = []
    assert not window._should_prompt_save_on_close()


def test_should_not_prompt_when_setting_is_off(
    window: MainWindow, mock_controller: MagicMock
) -> None:
    from mdf_viewer.settings import Settings
    settings = MagicMock(spec=Settings)
    settings.prompt_save_config_on_close = False
    window._settings = settings
    window._controller = mock_controller
    mock_controller.active_signals = [MagicMock()]
    assert not window._should_prompt_save_on_close()


def test_should_prompt_when_active_signals_and_setting_on(
    window: MainWindow, mock_controller: MagicMock
) -> None:
    from mdf_viewer.settings import Settings
    settings = MagicMock(spec=Settings)
    settings.prompt_save_config_on_close = True
    window._settings = settings
    window._controller = mock_controller
    mock_controller.active_signals = [MagicMock()]
    assert window._should_prompt_save_on_close()


def test_close_event_accept_when_not_prompted(
    window: MainWindow, mock_controller: MagicMock
) -> None:
    from PyQt6.QtGui import QCloseEvent
    window._controller = mock_controller
    mock_controller.active_signals = []  # no prompt
    event = QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted()


def test_close_event_cancel_ignores_event(
    window: MainWindow, mock_controller: MagicMock, qtbot: QtBot
) -> None:
    from PyQt6.QtGui import QCloseEvent
    from mdf_viewer.settings import Settings
    settings = MagicMock(spec=Settings)
    settings.prompt_save_config_on_close = True
    window._settings = settings
    window._controller = mock_controller
    mock_controller.active_signals = [MagicMock()]
    mock_controller.current_config_path = None

    event = QCloseEvent()
    with patch.object(
        QMessageBox, "question",
        return_value=QMessageBox.StandardButton.Cancel
    ):
        window.closeEvent(event)

    assert not event.isAccepted()


# ---------------------------------------------------------------------------
# Open dialog routing
# ---------------------------------------------------------------------------

def test_on_load_file_routes_mvc_to_load_config(
    window: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    mvc = tmp_path / "session.mvc"
    mvc.touch()
    window._controller = mock_controller
    window._settings = MagicMock()

    with patch("PyQt6.QtWidgets.QFileDialog.getOpenFileName", return_value=(str(mvc), "")):
        with patch.object(window, "_load_config") as mock_load_config:
            window._on_load_file()
            mock_load_config.assert_called_once_with(mvc)


def test_on_load_file_routes_mdf_to_load_file(
    window: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    mdf = tmp_path / "data.mf4"
    mdf.touch()
    window._controller = mock_controller

    with patch("PyQt6.QtWidgets.QFileDialog.getOpenFileName", return_value=(str(mdf), "")):
        with patch.object(window, "_load_file") as mock_load_file:
            window._on_load_file()
            mock_load_file.assert_called_once_with(str(mdf))


def test_on_open_recent_routes_mvc(
    window: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    mvc = tmp_path / "session.mvc"
    mvc.touch()
    window._controller = mock_controller
    window._settings = MagicMock()

    with patch.object(window, "_load_config") as mock_lc:
        window._on_open_recent(mvc)
        mock_lc.assert_called_once_with(mvc)


def test_on_open_recent_routes_mdf(
    window: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    mdf = tmp_path / "data.mf4"
    mdf.touch()
    window._controller = mock_controller

    with patch.object(window, "_load_file") as mock_lf:
        window._on_open_recent(mdf)
        mock_lf.assert_called_once_with(mdf)


# ---------------------------------------------------------------------------
# open_config — public entry point used by app.py for CLI / file association
# ---------------------------------------------------------------------------

def test_open_config_delegates_to_load_config(
    window: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    mvc = tmp_path / "session.mvc"
    mvc.touch()
    window._controller = mock_controller
    window._settings = MagicMock()

    with patch.object(window, "_load_config") as mock_lc:
        window.open_config(mvc)
        mock_lc.assert_called_once_with(mvc)


def test_open_config_mvc_not_routed_to_load_file(
    window: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    mvc = tmp_path / "session.mvc"
    mvc.touch()
    window._controller = mock_controller
    window._settings = MagicMock()

    with patch.object(window, "_load_config"):
        with patch.object(window, "_load_file") as mock_lf:
            window.open_config(mvc)
            mock_lf.assert_not_called()
