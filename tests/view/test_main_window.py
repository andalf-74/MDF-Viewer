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

from mdf_viewer.controller.app_controller import LoadResult
from mdf_viewer.errors import MdfLoadError
from mdf_viewer.view.active_signals_table import ActiveSignalsTable
from mdf_viewer.view.main_window import MainWindow
from mdf_viewer.view.measurement_info_box import MeasurementInfoBox
from mdf_viewer.view.plot_stripes_area import PlotStripesArea
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
    assert isinstance(window.plot_area, PlotStripesArea)


def test_has_active_signals_table(window: MainWindow) -> None:
    assert isinstance(window.active_signals_table, ActiveSignalsTable)


def test_has_measurement_info_box(window: MainWindow) -> None:
    assert isinstance(window.measurement_info_box, MeasurementInfoBox)


def test_has_signal_info_box(window: MainWindow) -> None:
    assert isinstance(window.signal_info_box, SignalInfoBox)


# ---------------------------------------------------------------------------
# Tabs (#99)
# ---------------------------------------------------------------------------

def test_tab_widget_starts_with_one_tab(window: MainWindow) -> None:
    assert window._real_tab_count() == 1
    assert window._tab_widget.tabText(0) == "Tab 1"


def test_plus_tab_is_pinned_last(window: MainWindow) -> None:
    last = window._tab_widget.count() - 1
    assert window._tab_widget.tabText(last) == "+"
    assert window._is_placeholder(last)


def test_first_tab_page_holds_initial_plot_area_and_table(window: MainWindow) -> None:
    page = window._tab_widget.widget(0)
    assert page.plot_area is window.plot_area
    assert page.active_signals_table is window.active_signals_table


def test_content_stack_shows_tab_widget_initially(window: MainWindow) -> None:
    assert window._content_stack.currentWidget() is window._tab_widget


def test_new_tab_action_creates_second_tab(wired: MainWindow) -> None:
    wired._on_new_tab()
    assert wired._real_tab_count() == 2
    assert wired._tab_widget.tabText(1) == "Tab 2"
    assert wired._tab_widget.currentIndex() == 1


def test_new_tab_has_its_own_plot_area_and_table(wired: MainWindow) -> None:
    wired._on_new_tab()
    page = wired._tab_widget.widget(1)
    assert isinstance(page.plot_area, PlotStripesArea)
    assert isinstance(page.active_signals_table, ActiveSignalsTable)
    assert page.plot_area is not wired.plot_area
    assert page.active_signals_table is not wired.active_signals_table


def test_new_tab_invokes_tab_factory(wired: MainWindow) -> None:
    factory = MagicMock()
    wired.set_tab_factory(factory)
    wired._on_new_tab()
    factory.assert_called_once()
    called_plot_area, called_table = factory.call_args[0]
    assert called_plot_area is wired._tab_widget.widget(1).plot_area
    assert called_table is wired._tab_widget.widget(1).active_signals_table


def test_new_tab_wires_view_signals_to_controller(wired: MainWindow, mock_controller: MagicMock) -> None:
    wired._on_new_tab()
    page = wired._tab_widget.widget(1)
    page.active_signals_table.remove_all_requested.emit()
    mock_controller.remove_all.assert_called_once()


def test_switching_tabs_calls_controller_switch_tab(wired: MainWindow, mock_controller: MagicMock) -> None:
    wired._on_new_tab()
    wired._tab_widget.setCurrentIndex(0)
    mock_controller.switch_tab.assert_called_with(0)


def test_closing_last_tab_shows_empty_placeholder(wired: MainWindow, mock_controller: MagicMock) -> None:
    mock_controller.tab_has_signals.return_value = False
    wired._on_tab_close_requested(0)
    assert wired._real_tab_count() == 0
    assert wired._content_stack.currentWidget() is wired._empty_tabs_placeholder


def test_closing_last_tab_calls_controller_remove_tab(wired: MainWindow, mock_controller: MagicMock) -> None:
    mock_controller.tab_has_signals.return_value = False
    wired._on_tab_close_requested(0)
    mock_controller.remove_tab.assert_called_once_with(0)


def test_closing_non_last_tab_deletes_the_page_widget(wired: MainWindow, mock_controller: MagicMock) -> None:
    """removeTab() alone doesn't delete the page widget (Qt's own docs say so
    explicitly) — without an explicit deleteLater(), a closed tab's whole
    PlotStripesArea (every stripe/curve/ViewBox/axis) and ActiveSignalsTable
    would leak for the rest of the app session (found while scanning for
    the same leak class as the stripe/signal-lifecycle bugs in
    plot_stripe.py, #120)."""
    mock_controller.tab_has_signals.return_value = False
    wired._on_new_tab()  # now 2 real tabs; closing one is not the last-tab case
    page = wired._tab_widget.widget(0)
    with patch.object(page, "deleteLater") as mock_delete_later:
        wired._on_tab_close_requested(0)
    mock_delete_later.assert_called_once()


def test_closing_the_last_tab_parks_rather_than_deletes_the_page_widget(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    """Closing the very last real tab must NOT deleteLater() its widgets.

    AppController.remove_tab() deliberately keeps that sole TabWorkspace
    alive instead of dropping it (current_workspace must never be empty),
    so destroying its Qt objects here would leave the controller holding a
    reference to already-deleted widgets — the next thing that touched it
    (e.g. the next "New Tab") crashed with "wrapped C/C++ object ... has
    been deleted" (#130, found live-testing #124)."""
    mock_controller.tab_has_signals.return_value = False
    page = wired._tab_widget.widget(0)
    with patch.object(page, "deleteLater") as mock_delete_later:
        wired._on_tab_close_requested(0)
    mock_delete_later.assert_not_called()
    assert wired._parked_page is page


def test_new_tab_button_in_empty_placeholder_recreates_tab(wired: MainWindow, mock_controller: MagicMock) -> None:
    mock_controller.tab_has_signals.return_value = False
    wired._on_tab_close_requested(0)
    wired._on_new_tab()
    assert wired._real_tab_count() == 1
    assert wired._content_stack.currentWidget() is wired._tab_widget


def test_new_tab_after_closing_last_tab_reuses_the_parked_page(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    """The parked page's exact plot_area/table are reused (#130) — building
    a fresh pair instead would register a second TabWorkspace via the tab
    factory while AppController.remove_tab() already kept the original one
    alive, silently orphaning it as a never-shown extra workspace."""
    mock_controller.tab_has_signals.return_value = False
    parked_page = wired._tab_widget.widget(0)
    wired._on_tab_close_requested(0)
    wired._on_new_tab()
    assert wired._tab_widget.widget(0) is parked_page
    assert wired._parked_page is None


# ---------------------------------------------------------------------------
# Copy Signals to new Tab (#119)
# ---------------------------------------------------------------------------

def test_copy_signals_to_new_tab_inserts_immediately_after_source(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    mock_controller.tab_has_signals.return_value = True
    wired._on_new_tab()  # Tab 2
    wired._on_new_tab()  # Tab 3

    wired._on_copy_signals_to_new_tab(0)

    assert wired._real_tab_count() == 4
    assert wired._tab_widget.tabText(0) == "Tab 1"
    assert wired._tab_widget.tabText(1) == "Copy of Tab 1"
    assert wired._tab_widget.tabText(2) == "Tab 2"
    assert wired._tab_widget.tabText(3) == "Tab 3"
    mock_controller.copy_signals_to_new_tab.assert_called_once_with(0, 1)


def test_copy_signals_to_new_tab_on_last_real_tab(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    """moveTab() is a no-op (doesn't fire tabMoved) when the source is
    already the last real tab, since the new tab was appended right after
    it — confirm the end state is still correct even though the usual
    drag-reorder resync path never runs (#119 review finding)."""
    mock_controller.tab_has_signals.return_value = True

    wired._on_copy_signals_to_new_tab(0)  # tab 0 is the only (and last) real tab

    assert wired._real_tab_count() == 2
    assert wired._tab_widget.tabText(1) == "Copy of Tab 1"
    mock_controller.copy_signals_to_new_tab.assert_called_once_with(0, 1)


def test_copy_signals_to_new_tab_nested_copy_naming(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    mock_controller.tab_has_signals.return_value = True
    wired._on_copy_signals_to_new_tab(0)  # -> "Copy of Tab 1" at index 1

    wired._on_copy_signals_to_new_tab(1)

    assert wired._tab_widget.tabText(2) == "Copy of Copy of Tab 1"


def test_tab_context_menu_copy_signals_action(wired: MainWindow, mock_controller: MagicMock) -> None:
    mock_controller.tab_has_signals.return_value = True
    tab_bar = wired._tab_widget.tabBar()
    pos = tab_bar.tabRect(0).center()
    patch_add, patch_exec = _select_menu_action_by_text("Copy Signals to new Tab")
    with patch_add, patch_exec:
        wired._on_tab_context_menu(pos)
    assert wired._real_tab_count() == 2
    assert wired._tab_widget.tabText(1) == "Copy of Tab 1"
    mock_controller.copy_signals_to_new_tab.assert_called_once_with(0, 1)


def test_tab_context_menu_copy_signals_disabled_when_source_has_no_signals(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    mock_controller.tab_has_signals.return_value = False
    from PyQt6.QtWidgets import QMenu
    captured: dict[str, object] = {}
    orig_add_action = QMenu.addAction

    def _tracking_add_action(self, text):
        action = orig_add_action(self, text)
        captured[text] = action
        return action

    tab_bar = wired._tab_widget.tabBar()
    pos = tab_bar.tabRect(0).center()
    with patch.object(QMenu, "addAction", _tracking_add_action), \
         patch.object(QMenu, "exec", return_value=None):
        wired._on_tab_context_menu(pos)
    assert captured["Copy Signals to new Tab"].isEnabled() is False


# ---------------------------------------------------------------------------
# Tab close warning + left-neighbor focus (#99 M6)
# ---------------------------------------------------------------------------

def test_close_empty_tab_no_warning(wired: MainWindow, mock_controller: MagicMock) -> None:
    mock_controller.tab_has_signals.return_value = False
    with patch("PyQt6.QtWidgets.QMessageBox.question") as mock_question:
        wired._on_tab_close_requested(0)
    mock_question.assert_not_called()
    assert wired._real_tab_count() == 0


def test_close_tab_with_signals_warns(wired: MainWindow, mock_controller: MagicMock) -> None:
    mock_controller.tab_has_signals.return_value = True
    with patch(
        "PyQt6.QtWidgets.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Cancel,
    ) as mock_question:
        wired._on_tab_close_requested(0)
    mock_question.assert_called_once()
    # Cancelled: tab must still be open.
    assert wired._real_tab_count() == 1


def test_close_tab_with_signals_confirmed_closes(wired: MainWindow, mock_controller: MagicMock) -> None:
    mock_controller.tab_has_signals.return_value = True
    with patch(
        "PyQt6.QtWidgets.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Yes,
    ):
        wired._on_tab_close_requested(0)
    assert wired._real_tab_count() == 0
    mock_controller.remove_tab.assert_called_once_with(0)


def test_closing_first_tab_activates_next_remaining(wired: MainWindow, mock_controller: MagicMock) -> None:
    mock_controller.tab_has_signals.return_value = False
    wired._on_new_tab()
    wired._on_new_tab()
    wired._tab_widget.setCurrentIndex(0)
    wired._on_tab_close_requested(0)
    assert wired._tab_widget.currentIndex() == 0
    assert wired._tab_widget.tabText(0) == "Tab 2"


def test_closing_middle_tab_activates_left_neighbor(wired: MainWindow, mock_controller: MagicMock) -> None:
    mock_controller.tab_has_signals.return_value = False
    wired._on_new_tab()
    wired._on_new_tab()
    wired._on_tab_close_requested(1)
    assert wired._tab_widget.currentIndex() == 0
    assert wired._tab_widget.tabText(0) == "Tab 1"
    assert wired._tab_widget.tabText(1) == "Tab 3"


def test_closing_last_of_three_activates_left_neighbor(wired: MainWindow, mock_controller: MagicMock) -> None:
    mock_controller.tab_has_signals.return_value = False
    wired._on_new_tab()
    wired._on_new_tab()
    wired._on_tab_close_requested(2)
    assert wired._tab_widget.currentIndex() == 1
    assert wired._tab_widget.tabText(1) == "Tab 2"


def test_new_tab_menu_action_exists(window: MainWindow) -> None:
    """#115: moved from the File menu to the Edit menu."""
    texts = [a.text() for a in window._edit_menu.actions()]
    assert any("New Tab" in t for t in texts)


# ---------------------------------------------------------------------------
# New Stripe menu action (#112, REQ-PLOT-196)
# ---------------------------------------------------------------------------

def test_new_stripe_menu_action_exists(window: MainWindow) -> None:
    """#115: moved from the File menu to the Edit menu."""
    texts = [a.text() for a in window._edit_menu.actions()]
    assert any("New Stripe" in t for t in texts)


def test_on_new_stripe_calls_controller_create_stripe(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    wired._on_new_stripe()
    mock_controller.create_stripe.assert_called_once()


def test_on_new_stripe_noop_without_controller(window: MainWindow) -> None:
    window._on_new_stripe()  # must not raise


# ---------------------------------------------------------------------------
# "+" tab pinning and drag-reorder resync (#99)
# ---------------------------------------------------------------------------

def test_clicking_plus_tab_creates_new_tab_instead_of_selecting_it(wired: MainWindow) -> None:
    placeholder_index = wired._placeholder_index()
    wired._on_tab_bar_clicked(placeholder_index)
    assert wired._real_tab_count() == 2
    assert wired._tab_widget.tabText(wired._tab_widget.currentIndex()) == "Tab 2"


def test_plus_tab_stays_last_after_new_tabs(wired: MainWindow) -> None:
    wired._on_new_tab()
    wired._on_new_tab()
    last = wired._tab_widget.count() - 1
    assert wired._tab_widget.tabText(last) == "+"


def test_dragging_plus_tab_self_corrects_to_last(wired: MainWindow) -> None:
    wired._on_new_tab()  # now [Tab 1, Tab 2, +]
    tab_bar = wired._tab_widget.tabBar()
    tab_bar.moveTab(2, 0)  # simulate dragging "+" to the front
    last = wired._tab_widget.count() - 1
    assert wired._tab_widget.tabText(last) == "+"
    assert wired._tab_widget.tabText(0) == "Tab 1"
    assert wired._tab_widget.tabText(1) == "Tab 2"


def test_dragging_real_tab_resyncs_controller_order(wired: MainWindow, mock_controller: MagicMock) -> None:
    wired._on_new_tab()  # now [Tab 1, Tab 2, +]
    tab_bar = wired._tab_widget.tabBar()
    tab_bar.moveTab(0, 1)  # swap Tab 1 and Tab 2
    assert wired._tab_widget.tabText(0) == "Tab 2"
    assert wired._tab_widget.tabText(1) == "Tab 1"
    called_order = mock_controller.reorder_tabs.call_args[0][0]
    assert called_order == [
        wired._tab_widget.widget(0).plot_area,
        wired._tab_widget.widget(1).plot_area,
    ]


def test_cycle_tab_forward_wraps_around(wired: MainWindow) -> None:
    wired._on_new_tab()
    wired._on_new_tab()
    wired._tab_widget.setCurrentIndex(2)
    wired._cycle_tab(1)
    assert wired._tab_widget.currentIndex() == 0


def test_cycle_tab_backward_wraps_around(wired: MainWindow) -> None:
    wired._on_new_tab()
    wired._tab_widget.setCurrentIndex(0)
    wired._cycle_tab(-1)
    assert wired._tab_widget.currentIndex() == 1


def test_cycle_tab_noop_with_zero_tabs(window: MainWindow) -> None:
    window._on_tab_close_requested(0)
    window._cycle_tab(1)  # must not raise


def test_double_click_renames_tab(window: MainWindow) -> None:
    with patch(
        "PyQt6.QtWidgets.QInputDialog.getText", return_value=("Engine Data", True)
    ):
        window._on_tab_bar_double_clicked(0)
    assert window._tab_widget.tabText(0) == "Engine Data"


def test_rename_cancelled_keeps_old_name(window: MainWindow) -> None:
    with patch(
        "PyQt6.QtWidgets.QInputDialog.getText", return_value=("Engine Data", False)
    ):
        window._on_tab_bar_double_clicked(0)
    assert window._tab_widget.tabText(0) == "Tab 1"


def test_rename_blank_name_keeps_old_name(window: MainWindow) -> None:
    with patch("PyQt6.QtWidgets.QInputDialog.getText", return_value=("   ", True)):
        window._on_tab_bar_double_clicked(0)
    assert window._tab_widget.tabText(0) == "Tab 1"


def _select_menu_action_by_text(target_text: str):
    """Patch QMenu so exec() returns whichever added action has *target_text*."""
    from PyQt6.QtWidgets import QMenu
    added: dict[str, object] = {}
    orig_add_action = QMenu.addAction

    def _tracking_add_action(self, text):
        action = orig_add_action(self, text)
        added[text] = action
        return action

    return (
        patch.object(QMenu, "addAction", _tracking_add_action),
        patch.object(QMenu, "exec", lambda self, *a, **k: added.get(target_text)),
    )


def test_tab_context_menu_rename_action(window: MainWindow) -> None:
    tab_bar = window._tab_widget.tabBar()
    pos = tab_bar.tabRect(0).center()
    patch_add, patch_exec = _select_menu_action_by_text("Rename")
    with patch_add, patch_exec, \
         patch("PyQt6.QtWidgets.QInputDialog.getText", return_value=("Renamed", True)):
        window._on_tab_context_menu(pos)
    assert window._tab_widget.tabText(0) == "Renamed"


def test_tab_context_menu_close_action(window: MainWindow) -> None:
    tab_bar = window._tab_widget.tabBar()
    pos = tab_bar.tabRect(0).center()
    patch_add, patch_exec = _select_menu_action_by_text("Close")
    with patch_add, patch_exec:
        window._on_tab_context_menu(pos)
    assert window._real_tab_count() == 0


def test_tab_context_menu_outside_any_tab_is_noop(window: MainWindow) -> None:
    from PyQt6.QtCore import QPoint
    with patch("PyQt6.QtWidgets.QMenu.exec") as mock_exec:
        window._on_tab_context_menu(QPoint(-10, -10))
        mock_exec.assert_not_called()


# ---------------------------------------------------------------------------
# Menu bar
# ---------------------------------------------------------------------------

def test_file_menu_exists(window: MainWindow) -> None:
    titles = [window.menuBar().actions()[i].text() for i in range(window.menuBar().actions().__len__())]
    assert any("File" in t for t in titles)


@pytest.mark.requirement("REQ-FILE-011")
def test_file_menu_has_load_action(window: MainWindow) -> None:
    file_menu = window.menuBar().actions()[0].menu()
    texts = [a.text() for a in file_menu.actions()]
    assert any("Open" in t for t in texts)


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


def test_toolbar_all_stripes_action_before_zoom_actions(window: MainWindow) -> None:
    """#114: "All Stripes" moved next to Load, ahead of the two zoom actions
    it governs, rather than sitting between Zoom Y and Swimlanes where its
    scope was ambiguous."""
    toolbars = window.findChildren(type(window.addToolBar("_t")))
    toolbar_actions = [a for tb in toolbars for a in tb.actions()]
    all_stripes_idx = toolbar_actions.index(window._zoom_all_stripes_action)
    assert all_stripes_idx < toolbar_actions.index(window._zoom_fit_action)
    assert all_stripes_idx < toolbar_actions.index(window._zoom_y_action)


def test_toolbar_separator_after_zoom_y_action(window: MainWindow) -> None:
    """#114: a new separator after "Zoom Y to View" visually brackets the
    two actions "All Stripes" affects, rather than leaving that ambiguous."""
    toolbars = window.findChildren(type(window.addToolBar("_t")))
    toolbar_actions = [a for tb in toolbars for a in tb.actions()]
    y_idx = toolbar_actions.index(window._zoom_y_action)
    swimlanes_idx = toolbar_actions.index(window._swimlanes_action)
    between = toolbar_actions[y_idx + 1:swimlanes_idx]
    assert any(a.isSeparator() for a in between)


def test_new_tab_action_in_edit_menu_not_file_menu(window: MainWindow) -> None:
    """#115: "New Tab" moved from the File menu to the Edit menu."""
    assert window._new_tab_action in window._edit_menu.actions()
    assert window._new_tab_action not in window._file_menu.actions()


def test_new_stripe_action_in_edit_menu_not_file_menu(window: MainWindow) -> None:
    """#115: "New Stripe" moved from the File menu to the Edit menu."""
    assert window._new_stripe_action in window._edit_menu.actions()
    assert window._new_stripe_action not in window._file_menu.actions()


# ---------------------------------------------------------------------------
# Zoom-scope toggle
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-057")
def test_toolbar_has_zoom_all_stripes_action(window: MainWindow) -> None:
    toolbars = window.findChildren(type(window.addToolBar("_t")))
    toolbar_actions = [a for tb in toolbars for a in tb.actions()]
    assert window._zoom_all_stripes_action in toolbar_actions


@pytest.mark.requirement("REQ-PLOT-057")
def test_zoom_all_stripes_action_checkable_and_checked_by_default(
    window: MainWindow,
) -> None:
    assert window._zoom_all_stripes_action.isCheckable()
    assert window._zoom_all_stripes_action.isChecked()


@pytest.mark.requirement("REQ-PLOT-057")
def test_zoom_scope_toggled_writes_active_stripe_to_settings(
    window: MainWindow,
) -> None:
    from mdf_viewer.settings import Settings
    settings = MagicMock(spec=Settings)
    window.set_settings(settings)
    window._zoom_all_stripes_action.setChecked(False)
    assert settings.zoom_scope == "active_stripe"


@pytest.mark.requirement("REQ-PLOT-057")
def test_zoom_scope_toggled_writes_all_stripes_to_settings(
    window: MainWindow,
) -> None:
    from mdf_viewer.settings import Settings
    settings = MagicMock(spec=Settings)
    window.set_settings(settings)
    window._zoom_all_stripes_action.setChecked(False)
    window._zoom_all_stripes_action.setChecked(True)
    assert settings.zoom_scope == "all_stripes"


def test_zoom_scope_toggled_without_settings_does_not_crash(
    window: MainWindow,
) -> None:
    window._zoom_all_stripes_action.setChecked(False)  # must not raise


@pytest.mark.requirement("REQ-PLOT-057")
def test_set_zoom_all_stripes_updates_checked_state(window: MainWindow) -> None:
    window.set_zoom_all_stripes(False)
    assert not window._zoom_all_stripes_action.isChecked()
    window.set_zoom_all_stripes(True)
    assert window._zoom_all_stripes_action.isChecked()


# ---------------------------------------------------------------------------
# Measurement Synchronization (#102)
# ---------------------------------------------------------------------------

def test_edit_menu_has_sync_measurements_action(window: MainWindow) -> None:
    assert window._sync_measurements_action in window._edit_menu.actions()


def test_sync_measurements_action_disabled_by_default(window: MainWindow) -> None:
    assert not window._sync_measurements_action.isEnabled()


def test_sync_measurements_action_checkable_and_unchecked_by_default(
    window: MainWindow,
) -> None:
    assert window._sync_measurements_action.isCheckable()
    assert not window._sync_measurements_action.isChecked()


def test_load_files_enables_sync_action_with_two_measurements(
    wired: MainWindow, mock_controller: MagicMock,
) -> None:
    # measurement_count is read both before _load_files (to decide the
    # Replace/Add prompt) and after (to enable/disable the sync action) —
    # set it to 0 so the prompt is skipped, then bump it once
    # replace_measurements "returns" via a side effect, simulating the
    # count actually changing as a result of the load.
    mock_controller.measurement_count = 0

    def _replace(paths):
        mock_controller.measurement_count = 2
        return LoadResult(succeeded=[MagicMock()])

    mock_controller.replace_measurements.side_effect = _replace
    wired._load_files(["a.mf4", "b.mf4"])
    assert wired._sync_measurements_action.isEnabled()


def test_load_files_disables_sync_action_with_one_measurement(
    wired: MainWindow, mock_controller: MagicMock,
) -> None:
    mock_controller.measurement_count = 0

    def _replace(paths):
        mock_controller.measurement_count = 1
        return LoadResult(succeeded=[MagicMock()])

    mock_controller.replace_measurements.side_effect = _replace
    wired._load_files(["a.mf4"])
    assert not wired._sync_measurements_action.isEnabled()


@pytest.mark.requirement("REQ-PLOT-310")
def test_sync_action_toggled_calls_controller_when_state_differs(
    wired: MainWindow, mock_controller: MagicMock,
) -> None:
    mock_controller.is_measurements_synchronized = False
    wired._sync_measurements_action.setChecked(True)
    mock_controller.toggle_measurements_synchronized.assert_called_once()


@pytest.mark.requirement("REQ-PLOT-310")
def test_sync_action_toggled_noop_when_state_already_matches(
    wired: MainWindow, mock_controller: MagicMock,
) -> None:
    """Regression for the two-control feedback-loop guard: pushing the
    button's new state into the menu checkbox must not re-toggle the
    controller a second time and revert it."""
    mock_controller.is_measurements_synchronized = True
    wired._sync_measurements_action.setChecked(True)
    mock_controller.toggle_measurements_synchronized.assert_not_called()


def test_sync_button_click_toggles_controller_and_updates_menu_checkbox(
    wired: MainWindow, mock_controller: MagicMock,
) -> None:
    mock_controller.is_measurements_synchronized = True
    wired._on_sync_button_clicked()
    mock_controller.toggle_measurements_synchronized.assert_called_once()
    assert wired._sync_measurements_action.isChecked() is True


def test_sync_action_toggled_without_controller_does_not_crash(
    window: MainWindow,
) -> None:
    window._sync_measurements_action.setChecked(True)  # must not raise


def test_sync_button_click_without_controller_does_not_crash(
    window: MainWindow,
) -> None:
    window._on_sync_button_clicked()  # must not raise


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
# Update checking (REQ-NFR-031/032)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-NFR-031")
def test_trigger_startup_update_check_starts_background_thread(window: MainWindow) -> None:
    from mdf_viewer.view.main_window import _UpdateCheckThread
    with patch.object(_UpdateCheckThread, "start") as mock_start:
        window.trigger_startup_update_check()
    # Runs via QThread.start() (a real background thread) rather than a
    # direct, blocking call to run() on the GUI thread.
    mock_start.assert_called_once()
    assert isinstance(window._update_thread, _UpdateCheckThread)


@pytest.mark.requirement("REQ-NFR-032")
def test_update_check_thread_silent_on_network_failure(qtbot: QtBot) -> None:
    from mdf_viewer.view.main_window import _UpdateCheckThread
    from mdf_viewer.update_checker import UpdateCheckError
    thread = _UpdateCheckThread("1.0")
    emitted: list = []
    thread.update_available.connect(emitted.append)
    with patch(
        "mdf_viewer.update_checker.fetch_latest_release",
        side_effect=UpdateCheckError("network down"),
    ):
        thread.run()  # called synchronously here — must not raise or emit
    assert emitted == []


@pytest.mark.requirement("REQ-NFR-031")
def test_update_check_thread_emits_when_newer_available(qtbot: QtBot) -> None:
    from mdf_viewer.view.main_window import _UpdateCheckThread
    from mdf_viewer.update_checker import ReleaseInfo
    thread = _UpdateCheckThread("1.0")
    with qtbot.waitSignal(thread.update_available, timeout=500) as blocker:
        with patch(
            "mdf_viewer.update_checker.fetch_latest_release",
            return_value=ReleaseInfo(tag="v2.0", url="https://example.com/v2.0"),
        ):
            thread.run()
    assert blocker.args == ["v2.0", "https://example.com/v2.0"]


@pytest.mark.requirement("REQ-NFR-032")
def test_manual_check_for_update_reports_failure(window: MainWindow) -> None:
    from mdf_viewer.update_checker import UpdateCheckError
    with patch(
        "mdf_viewer.update_checker.fetch_latest_release",
        side_effect=UpdateCheckError("network down"),
    ):
        with patch("mdf_viewer.view.main_window.QMessageBox.warning") as mock_warn:
            window._on_check_for_update()
    mock_warn.assert_called_once()


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

@pytest.mark.requirement("REQ-BROWSER-031")
def test_add_signal_connects_after_set_controller(
    wired: MainWindow, mock_controller: MagicMock, qtbot: QtBot
) -> None:
    wired.signal_browser.add_signals_requested.emit([(0, 2, 5)])
    mock_controller.add_signal.assert_called_once_with(
        2, 5, measurement=mock_controller.measurement_at.return_value
    )


@pytest.mark.requirement("REQ-BROWSER-031")
def test_add_signals_mixed_measurements_resolves_each_own_measurement(
    wired: MainWindow, mock_controller: MagicMock, qtbot: QtBot
) -> None:
    """A single add-signal request can span multiple measurements (#103) —
    each item resolves its own measurement rather than sharing one."""
    wired.signal_browser.add_signals_requested.emit([(0, 2, 5), (1, 3, 0)])
    mock_controller.measurement_at.assert_any_call(0)
    mock_controller.measurement_at.assert_any_call(1)
    assert mock_controller.add_signal.call_count == 2


def test_add_signal_not_called_before_set_controller(
    window: MainWindow, qtbot: QtBot
) -> None:
    # Emit before set_controller — must not crash
    window.signal_browser.add_signals_requested.emit([(0, 0, 1)])


# ---------------------------------------------------------------------------
# Plot Stripes wiring
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-200")
def test_signals_dropped_on_stripe_calls_add_signal_with_stripe(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    stripe = MagicMock()
    wired.plot_area.signals_dropped_on_stripe.emit([(0, 2, 5)], stripe)
    mock_controller.add_signal.assert_called_once_with(
        2, 5, stripe=stripe, measurement=mock_controller.measurement_at.return_value
    )


@pytest.mark.requirement("REQ-PLOT-277")
def test_ast_segment_drop_calls_add_signal_with_that_segments_stripe(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    stripe2 = wired.plot_area.create_stripe()
    wired.active_signals_table.signals_dropped_on_stripe.emit([(0, 2, 5)], stripe2)
    mock_controller.add_signal.assert_called_once_with(
        2, 5, stripe=stripe2, measurement=mock_controller.measurement_at.return_value
    )


@pytest.mark.requirement("REQ-BROWSER-031")
def test_signals_dropped_on_stripe_resolves_each_items_own_measurement(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    stripe = MagicMock()
    wired.plot_area.signals_dropped_on_stripe.emit([(3, 2, 5)], stripe)
    mock_controller.measurement_at.assert_called_once_with(3)


@pytest.mark.requirement("REQ-BROWSER-031")
def test_signals_dropped_on_stripe_mixed_measurements_resolves_each(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    """A single drop can span rows from different measurements (#103)."""
    stripe = MagicMock()
    wired.plot_area.signals_dropped_on_stripe.emit([(0, 2, 5), (1, 3, 0)], stripe)
    mock_controller.measurement_at.assert_any_call(0)
    mock_controller.measurement_at.assert_any_call(1)
    assert mock_controller.add_signal.call_count == 2


def test_set_controller_wires_stripe_providers(
    window: MainWindow, mock_controller: MagicMock
) -> None:
    window.set_controller(mock_controller)
    assert window.active_signals_table._get_stripes is mock_controller.get_stripes
    assert window.active_signals_table._get_stripe_for_signal is mock_controller.get_stripe_for_signal


@pytest.mark.requirement("REQ-PLOT-270")
def test_wiring_bootstraps_segment_for_first_stripe(wired: MainWindow) -> None:
    """PlotStripesArea.__init__ creates (and fires stripe_created for) its
    first stripe before _wire_tab_view can connect anything — the bootstrap
    loop there must pick it up anyway."""
    stripes = wired.plot_area.get_stripes()
    assert len(stripes) == 1
    assert wired.active_signals_table._segments == [
        wired.active_signals_table._segment_for_stripe[stripes[0]]
    ]


@pytest.mark.requirement("REQ-PLOT-270")
def test_creating_a_stripe_creates_its_segment(wired: MainWindow) -> None:
    wired.plot_area.create_stripe()
    assert len(wired.active_signals_table._segments) == 2


@pytest.mark.requirement("REQ-PLOT-270")
def test_deleting_a_stripe_removes_its_segment(wired: MainWindow) -> None:
    stripe2 = wired.plot_area.create_stripe()
    wired.plot_area.delete_stripe(stripe2)
    assert len(wired.active_signals_table._segments) == 1


@pytest.mark.requirement("REQ-PLOT-274")
def test_bootstrapped_segment_size_matches_its_stripe(
    wired: MainWindow, qtbot: QtBot
) -> None:
    # A single segment absorbs both the header and button-row chrome (only
    # entry in the list, so both offsets apply to it) — it's shorter than
    # its stripe by that known, fixed amount, not equal to it. See
    # ActiveSignalsTable._build_ui's offset comment.
    wired.resize(1000, 700)
    wired.show()
    qtbot.waitExposed(wired)
    ast = wired.active_signals_table
    expected = wired.plot_area.get_stripe_sizes()[0] - ast._top_size_offset - ast._bottom_size_offset
    assert ast._segments_splitter.sizes()[0] == pytest.approx(expected, abs=2)


@pytest.mark.requirement("REQ-PLOT-274")
def test_new_segment_size_matches_its_stripe_immediately(
    wired: MainWindow, qtbot: QtBot
) -> None:
    # Not just eventually-consistent after a drag (#100 postmortem) — must
    # already match right after creation. Interior dividers (everything but
    # the very first/last segment) must match exactly; with exactly 2
    # stripes here, both segments are "first or last" and each absorbs one
    # of the two offsets, so allow a couple pixels of Qt rounding rather
    # than asserting exact equality.
    wired.resize(1000, 700)
    wired.show()
    qtbot.waitExposed(wired)
    wired.plot_area.create_stripe()
    ast = wired.active_signals_table
    stripe_sizes = wired.plot_area.get_stripe_sizes()
    expected = [
        stripe_sizes[0] - ast._top_size_offset,
        stripe_sizes[1] - ast._bottom_size_offset,
    ]
    assert ast._segments_splitter.sizes() == pytest.approx(expected, abs=2)


@pytest.mark.requirement("REQ-PLOT-274")
def test_interior_segment_matches_its_stripe_exactly(
    wired: MainWindow, qtbot: QtBot
) -> None:
    # The actual guarantee this sync mechanism exists for: with 3+ stripes,
    # every *interior* segment (not first, not last) is unaffected by the
    # header/button offset entirely and must match its stripe's height
    # exactly, with no rounding tolerance needed at all (#100 postmortem —
    # this is what a plain 1:1 pixel copy could never achieve, since the two
    # splitters' totals are never equal).
    wired.resize(1000, 700)
    wired.show()
    qtbot.waitExposed(wired)
    wired.plot_area.create_stripe()
    wired.plot_area.create_stripe()
    ast = wired.active_signals_table
    stripe_sizes = wired.plot_area.get_stripe_sizes()
    segment_sizes = ast._segments_splitter.sizes()
    assert segment_sizes[1] == stripe_sizes[1]


@pytest.mark.requirement("REQ-PLOT-278")
def test_segment_activated_makes_its_stripe_active(wired: MainWindow) -> None:
    stripe2 = wired.plot_area.create_stripe()
    wired.active_signals_table.segment_activated.emit(stripe2)
    assert wired.plot_area.get_active_stripe() is stripe2


@pytest.mark.requirement("REQ-PLOT-274")
def test_dragging_stripe_splitter_resizes_ast_segments(
    wired: MainWindow, qtbot: QtBot
) -> None:
    wired.plot_area.create_stripe()
    wired.resize(1000, 700)
    wired.show()
    qtbot.waitExposed(wired)
    before = list(wired.active_signals_table._segments_splitter.sizes())
    wired.plot_area.set_stripe_sizes([100, 500])  # simulate an interactive drag
    wired.plot_area._on_splitter_moved(0, 0)
    assert wired.active_signals_table._segments_splitter.sizes() != before


@pytest.mark.requirement("REQ-PLOT-274")
def test_dragging_ast_splitter_resizes_stripes(
    wired: MainWindow, qtbot: QtBot
) -> None:
    wired.plot_area.create_stripe()
    wired.resize(1000, 700)
    wired.show()
    qtbot.waitExposed(wired)
    before = list(wired.plot_area._splitter.sizes())
    wired.active_signals_table.set_segment_sizes([100, 500])  # simulate a drag
    wired.active_signals_table._on_segment_splitter_moved(0, 0)
    assert wired.plot_area._splitter.sizes() != before


@pytest.mark.requirement("REQ-PLOT-202")
def test_move_to_stripe_requested_calls_controller(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    stripe = MagicMock()
    wired.active_signals_table.move_to_stripe_requested.emit(["sig"], stripe)
    mock_controller.move_signals_to_stripe.assert_called_once_with(["sig"], stripe)


@pytest.mark.requirement("REQ-PLOT-191")
def test_move_to_new_stripe_requested_calls_controller(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    wired.active_signals_table.move_to_new_stripe_requested.emit(["sig"])
    mock_controller.move_signals_to_new_stripe.assert_called_once_with(["sig"])


@pytest.mark.requirement("REQ-PLOT-281")
def test_active_signals_dropped_on_stripe_calls_controller(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    a, b = MagicMock(), MagicMock()
    mock_controller.active_signals = [a, b]
    stripe = MagicMock()
    wired.plot_area.active_signals_dropped_on_stripe.emit({id(a)}, stripe)
    mock_controller.move_signals_to_stripe.assert_called_once_with([a], stripe)


@pytest.mark.requirement("REQ-PLOT-281")
def test_active_signals_dropped_on_stripe_no_op_for_unresolved_ids(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    mock_controller.active_signals = []
    stripe = MagicMock()
    wired.plot_area.active_signals_dropped_on_stripe.emit({999}, stripe)
    mock_controller.move_signals_to_stripe.assert_not_called()


@pytest.mark.requirement("REQ-PLOT-193")
def test_delete_stripe_requested_empty_stripe_deletes_directly(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    stripe = MagicMock()
    mock_controller.get_signals_in_stripe.return_value = []
    mock_controller.delete_stripe.return_value = True
    wired.plot_area.delete_stripe_requested.emit(stripe)
    mock_controller.delete_stripe.assert_called_once_with(stripe)


@pytest.mark.requirement("REQ-PLOT-194")
def test_delete_stripe_requested_nonempty_shows_confirmation(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    stripe = MagicMock()
    mock_controller.get_signals_in_stripe.return_value = ["sig"]
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Cancel) as mock_q:
        wired.plot_area.delete_stripe_requested.emit(stripe)
    mock_q.assert_called_once()
    mock_controller.delete_stripe.assert_not_called()


@pytest.mark.requirement("REQ-PLOT-194")
def test_delete_stripe_requested_nonempty_confirmed_forces_delete(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    stripe = MagicMock()
    mock_controller.get_signals_in_stripe.return_value = ["sig"]
    with patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes):
        wired.plot_area.delete_stripe_requested.emit(stripe)
    mock_controller.delete_stripe.assert_called_once_with(stripe, force=True)


@pytest.mark.requirement("REQ-FILE-011")
def test_load_file_calls_controller(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    mock_controller.measurement_count = 0
    mock_controller.replace_measurements.return_value = LoadResult(succeeded=[MagicMock()])
    with patch(
        "mdf_viewer.view.main_window.QFileDialog.getOpenFileNames",
        return_value=(["/fake/file.mf4"], "MDF Files"),
    ):
        wired._load_action.trigger()
    mock_controller.replace_measurements.assert_called_once_with(["/fake/file.mf4"])


@pytest.mark.requirement("REQ-FILE-011")
def test_load_file_cancelled_does_not_call_controller(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    with patch(
        "mdf_viewer.view.main_window.QFileDialog.getOpenFileNames",
        return_value=([], ""),
    ):
        wired._load_action.trigger()
    mock_controller.replace_measurements.assert_not_called()
    mock_controller.add_measurements.assert_not_called()


@pytest.mark.requirement("REQ-FILE-041")
@pytest.mark.requirement("REQ-FILE-040")
@pytest.mark.requirement("REQ-NFR-011")
def test_load_error_shows_message_box(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    mock_controller.measurement_count = 0
    mock_controller.replace_measurements.return_value = LoadResult(
        failed=[("/bad/file.mf4", MdfLoadError("corrupted file"))]
    )
    with patch(
        "mdf_viewer.view.main_window.QFileDialog.getOpenFileNames",
        return_value=(["/bad/file.mf4"], "MDF Files"),
    ):
        with patch("mdf_viewer.view.main_window.QMessageBox.critical") as mock_crit:
            wired._load_action.trigger()
    mock_crit.assert_called_once()
    assert "corrupted file" in mock_crit.call_args[0][2]


@pytest.mark.requirement("REQ-FILE-011")
def test_load_files_multi_select_calls_controller(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    mock_controller.measurement_count = 0
    mock_controller.replace_measurements.return_value = LoadResult(succeeded=[MagicMock()])
    with patch(
        "mdf_viewer.view.main_window.QFileDialog.getOpenFileNames",
        return_value=(["/fake/a.mf4", "/fake/b.mf4"], "MDF Files"),
    ):
        wired._load_action.trigger()
    mock_controller.replace_measurements.assert_called_once_with(["/fake/a.mf4", "/fake/b.mf4"])


@pytest.mark.requirement("REQ-BROWSER-041")
@pytest.mark.requirement("REQ-NFR-011")
def test_add_signal_error_shows_message_box(
    wired: MainWindow, mock_controller: MagicMock, qtbot: QtBot
) -> None:
    mock_controller.add_signal.side_effect = MdfLoadError("non-numeric channel")
    with patch("mdf_viewer.view.main_window.QMessageBox.critical") as mock_crit:
        wired.signal_browser.add_signals_requested.emit([(0, 0, 1)])
    mock_crit.assert_called_once()
    assert "non-numeric channel" in mock_crit.call_args[0][2]


# ---------------------------------------------------------------------------
# Recent files menu
# ---------------------------------------------------------------------------

def test_recent_files_not_shown_without_provider(window: MainWindow) -> None:
    window._file_menu.aboutToShow.emit()
    assert window._recent_actions == []


@pytest.mark.requirement("REQ-FILE-052")
def test_recent_files_shown_when_provider_set(
    window: MainWindow, tmp_path, qtbot: QtBot
) -> None:
    p = tmp_path / "test.mf4"
    p.touch()
    window.set_recent_files_provider(lambda: [p])
    window._file_menu.aboutToShow.emit()
    assert len(window._recent_actions) == 1
    assert window._recent_actions[0].text() == "test.mf4"


@pytest.mark.requirement("REQ-FILE-052")
def test_recent_files_empty_provider_shows_no_actions(
    window: MainWindow, qtbot: QtBot
) -> None:
    window.set_recent_files_provider(lambda: [])
    window._file_menu.aboutToShow.emit()
    assert window._recent_actions == []
    assert window._recent_sep is None


@pytest.mark.requirement("REQ-FILE-054")
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


@pytest.mark.requirement("REQ-FILE-052")
def test_open_recent_calls_controller(
    wired: MainWindow, mock_controller: MagicMock, tmp_path, qtbot: QtBot
) -> None:
    mock_controller.measurement_count = 0
    mock_controller.replace_measurements.return_value = LoadResult(succeeded=[MagicMock()])
    p = tmp_path / "recent.mf4"
    p.touch()
    wired.set_recent_files_provider(lambda: [p])
    wired._file_menu.aboutToShow.emit()
    wired._recent_actions[0].trigger()
    mock_controller.replace_measurements.assert_called_once_with([p])


@pytest.mark.requirement("REQ-FILE-041")
@pytest.mark.requirement("REQ-FILE-040")
def test_open_recent_error_shows_message_box(
    wired: MainWindow, mock_controller: MagicMock, tmp_path, qtbot: QtBot
) -> None:
    mock_controller.measurement_count = 0
    p = tmp_path / "bad.mf4"
    p.touch()
    mock_controller.replace_measurements.return_value = LoadResult(
        failed=[(str(p), MdfLoadError("bad file"))]
    )
    wired.set_recent_files_provider(lambda: [p])
    wired._file_menu.aboutToShow.emit()
    with patch("mdf_viewer.view.main_window.QMessageBox.critical") as mock_crit:
        wired._recent_actions[0].trigger()
    mock_crit.assert_called_once()


# ---------------------------------------------------------------------------
# Close Measurement menu (#103, REQ-FILE-029)
# ---------------------------------------------------------------------------

def test_close_measurement_menu_disabled_without_controller(window: MainWindow) -> None:
    window._file_menu.aboutToShow.emit()
    assert window._close_measurement_menu.isEnabled() is False
    assert window._close_measurement_menu.actions() == []


def test_close_measurement_menu_disabled_with_no_measurements(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    mock_controller.measurements = []
    wired._file_menu.aboutToShow.emit()
    assert wired._close_measurement_menu.isEnabled() is False


@pytest.mark.requirement("REQ-FILE-029")
def test_close_measurement_menu_lists_every_measurement_by_short_name(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    m1, m2 = MagicMock(label="M1"), MagicMock(label="M2")
    mock_controller.measurements = [m1, m2]
    wired._file_menu.aboutToShow.emit()
    assert wired._close_measurement_menu.isEnabled() is True
    actions = wired._close_measurement_menu.actions()
    assert [a.text() for a in actions] == ["M1", "M2"]


@pytest.mark.requirement("REQ-FILE-029")
def test_close_measurement_menu_rebuilt_on_each_show(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    mock_controller.measurements = [MagicMock(label="M1")]
    wired._file_menu.aboutToShow.emit()
    mock_controller.measurements = [MagicMock(label="M1"), MagicMock(label="M2")]
    wired._file_menu.aboutToShow.emit()
    assert len(wired._close_measurement_menu.actions()) == 2


@pytest.mark.requirement("REQ-FILE-028")
def test_close_measurement_no_confirmation_without_active_signals(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    m1 = MagicMock(label="M1")
    mock_controller.measurements = [m1]
    mock_controller.measurement_has_signals.return_value = False
    wired._file_menu.aboutToShow.emit()
    wired._close_measurement_menu.actions()[0].trigger()
    mock_controller.close_measurement.assert_called_once_with(m1)


@pytest.mark.requirement("REQ-FILE-028")
def test_close_measurement_confirmed_closes(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    m1 = MagicMock(label="M1")
    mock_controller.measurements = [m1]
    mock_controller.measurement_has_signals.return_value = True
    wired._file_menu.aboutToShow.emit()
    with patch("mdf_viewer.view.main_window.QMessageBox.question") as mock_q:
        mock_q.return_value = QMessageBox.StandardButton.Yes
        wired._close_measurement_menu.actions()[0].trigger()
    mock_controller.close_measurement.assert_called_once_with(m1)


@pytest.mark.requirement("REQ-FILE-028")
def test_close_measurement_cancelled_does_not_close(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    m1 = MagicMock(label="M1")
    mock_controller.measurements = [m1]
    mock_controller.measurement_has_signals.return_value = True
    wired._file_menu.aboutToShow.emit()
    with patch("mdf_viewer.view.main_window.QMessageBox.question") as mock_q:
        mock_q.return_value = QMessageBox.StandardButton.Cancel
        wired._close_measurement_menu.actions()[0].trigger()
    mock_controller.close_measurement.assert_not_called()


# ---------------------------------------------------------------------------
# Replace Measurement menu and flow (#122, REQ-FILE-100..108)
# ---------------------------------------------------------------------------

def test_replace_measurement_menu_disabled_without_controller(window: MainWindow) -> None:
    window._file_menu.aboutToShow.emit()
    assert window._replace_measurement_menu.isEnabled() is False
    assert window._replace_measurement_menu.actions() == []


def test_replace_measurement_menu_disabled_with_no_measurements(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    mock_controller.measurements = []
    wired._file_menu.aboutToShow.emit()
    assert wired._replace_measurement_menu.isEnabled() is False


@pytest.mark.requirement("REQ-FILE-100")
def test_replace_measurement_menu_lists_every_measurement_by_short_name(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    m1, m2 = MagicMock(label="M1"), MagicMock(label="M2")
    mock_controller.measurements = [m1, m2]
    wired._file_menu.aboutToShow.emit()
    assert wired._replace_measurement_menu.isEnabled() is True
    actions = wired._replace_measurement_menu.actions()
    assert [a.text() for a in actions] == ["M1", "M2"]


@pytest.mark.requirement("REQ-FILE-100")
def test_replace_measurement_menu_rebuilt_on_each_show(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    mock_controller.measurements = [MagicMock(label="M1")]
    wired._file_menu.aboutToShow.emit()
    mock_controller.measurements = [MagicMock(label="M1"), MagicMock(label="M2")]
    wired._file_menu.aboutToShow.emit()
    assert len(wired._replace_measurement_menu.actions()) == 2


@pytest.mark.requirement("REQ-FILE-100")
def test_replace_measurement_menu_entry_invokes_replace_flow(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    m1 = MagicMock(label="M1")
    mock_controller.measurements = [m1]
    wired._file_menu.aboutToShow.emit()
    with patch.object(wired, "_replace_single_measurement") as mock_replace:
        wired._replace_measurement_menu.actions()[0].trigger()
    mock_replace.assert_called_once_with(m1)


@pytest.mark.requirement("REQ-FILE-102")
def test_replace_single_measurement_cancel_dialog_does_nothing(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    m1 = MagicMock(label="M1")
    with patch(
        "mdf_viewer.view.main_window.QFileDialog.getOpenFileName", return_value=("", "")
    ):
        wired._replace_single_measurement(m1)
    mock_controller.replace_single_measurement.assert_not_called()


@pytest.mark.requirement("REQ-FILE-103")
def test_replace_single_measurement_success_calls_controller(
    wired: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    m1 = MagicMock(label="M1")
    p = tmp_path / "corrected.mf4"
    p.touch()
    mock_controller.measurement_has_signals.return_value = False
    mock_controller.replace_single_measurement.return_value = LoadResult(succeeded=[m1])
    with patch(
        "mdf_viewer.view.main_window.QFileDialog.getOpenFileName",
        return_value=(str(p), ""),
    ):
        wired._replace_single_measurement(m1)
    mock_controller.replace_single_measurement.assert_called_once_with(m1, str(p))


@pytest.mark.requirement("REQ-FILE-106")
def test_replace_single_measurement_failure_shows_error_dialog(
    wired: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    m1 = MagicMock(label="M1")
    p = tmp_path / "bad.mf4"
    p.touch()
    mock_controller.measurement_has_signals.return_value = False
    mock_controller.replace_single_measurement.return_value = LoadResult(
        failed=[(str(p), MdfLoadError("bad file"))]
    )
    with patch(
        "mdf_viewer.view.main_window.QFileDialog.getOpenFileName",
        return_value=(str(p), ""),
    ), patch("mdf_viewer.view.main_window.QMessageBox.critical") as mock_crit:
        wired._replace_single_measurement(m1)
    mock_crit.assert_called_once()


@pytest.mark.requirement("REQ-FILE-104")
def test_replace_single_measurement_restores_snapshots_scoped_to_measurement(
    wired: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    m1 = MagicMock(label="M1")
    p = tmp_path / "corrected.mf4"
    p.touch()
    window_settings = MagicMock(keep_signals_on_load="always")
    window_settings.prompt_save_config_on_close = False
    wired._settings = window_settings
    mock_controller.measurement_has_signals.return_value = True
    mock_controller.snapshot_measurement_signals.return_value = {0: ["snap0"]}
    mock_controller.replace_single_measurement.return_value = LoadResult(succeeded=[m1])
    with patch(
        "mdf_viewer.view.main_window.QFileDialog.getOpenFileName",
        return_value=(str(p), ""),
    ), patch.object(wired, "_restore_snapshots") as mock_restore:
        wired._replace_single_measurement(m1)
    mock_controller.snapshot_measurement_signals.assert_called_once_with(m1)
    mock_restore.assert_called_once_with({0: ["snap0"]})


# ---------------------------------------------------------------------------
# _collect_measurement_snapshots_if_keeping (#122, REQ-FILE-104)
# ---------------------------------------------------------------------------

def test_collect_measurement_snapshots_empty_when_setting_never(
    window: MainWindow, mock_controller: MagicMock
) -> None:
    window._controller = mock_controller
    mock_controller.active_signals = []  # prevent teardown from triggering the real dialog
    window._settings = MagicMock(keep_signals_on_load="never")
    m1 = MagicMock(label="M1")

    assert window._collect_measurement_snapshots_if_keeping(m1) == {}
    mock_controller.snapshot_measurement_signals.assert_not_called()


def test_collect_measurement_snapshots_empty_when_measurement_has_no_signals(
    window: MainWindow, mock_controller: MagicMock
) -> None:
    window._controller = mock_controller
    mock_controller.active_signals = []  # prevent teardown from triggering the real dialog
    window._settings = MagicMock(keep_signals_on_load="always")
    mock_controller.measurement_has_signals.return_value = False
    m1 = MagicMock(label="M1")

    assert window._collect_measurement_snapshots_if_keeping(m1) == {}
    mock_controller.snapshot_measurement_signals.assert_not_called()


def test_collect_measurement_snapshots_always_returns_scoped_snapshot(
    window: MainWindow, mock_controller: MagicMock
) -> None:
    window._controller = mock_controller
    mock_controller.active_signals = []  # prevent teardown from triggering the real dialog
    window._settings = MagicMock(keep_signals_on_load="always")
    mock_controller.measurement_has_signals.return_value = True
    mock_controller.snapshot_measurement_signals.return_value = {0: ["snap0"]}
    m1 = MagicMock(label="M1")

    result = window._collect_measurement_snapshots_if_keeping(m1)

    assert result == {0: ["snap0"]}
    mock_controller.snapshot_measurement_signals.assert_called_once_with(m1)


def test_collect_measurement_snapshots_ask_declined_returns_empty(
    window: MainWindow, mock_controller: MagicMock
) -> None:
    window._controller = mock_controller
    mock_controller.active_signals = []  # prevent teardown from triggering the real dialog
    window._settings = MagicMock(keep_signals_on_load="ask")
    mock_controller.measurement_has_signals.return_value = True
    m1 = MagicMock(label="M1")

    with patch(
        "PyQt6.QtWidgets.QMessageBox.question",
        return_value=QMessageBox.StandardButton.No,
    ):
        assert window._collect_measurement_snapshots_if_keeping(m1) == {}
    mock_controller.snapshot_measurement_signals.assert_not_called()


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

@pytest.mark.requirement("REQ-BROWSER-031")
def test_on_add_signals_calls_add_signal_for_each(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    mock_controller.add_signal.return_value = True
    wired._on_add_signals([(0, 0, 1), (0, 1, 2)])
    assert mock_controller.add_signal.call_count == 2
    measurement = mock_controller.measurement_at.return_value
    mock_controller.add_signal.assert_any_call(0, 1, measurement=measurement)
    mock_controller.add_signal.assert_any_call(1, 2, measurement=measurement)


@pytest.mark.requirement("REQ-BROWSER-031")
def test_on_add_signals_mixed_measurements_resolves_each_own_measurement(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    """A single request can span multiple measurements (#103)."""
    mock_controller.add_signal.return_value = True
    wired._on_add_signals([(0, 0, 1), (2, 3, 0)])
    mock_controller.measurement_at.assert_any_call(0)
    mock_controller.measurement_at.assert_any_call(2)


@pytest.mark.requirement("REQ-BROWSER-040")
def test_on_add_signals_shows_status_when_skipped(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    mock_controller.add_signal.return_value = False
    wired._on_add_signals([(0, 0, 1), (0, 0, 2)])
    msg = wired.statusBar().currentMessage()
    assert "2 signals already active" in msg


@pytest.mark.requirement("REQ-BROWSER-040")
def test_on_add_signals_skipped_singular(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    mock_controller.add_signal.return_value = False
    wired._on_add_signals([(0, 0, 1)])
    msg = wired.statusBar().currentMessage()
    assert "1 signal already active" in msg


@pytest.mark.requirement("REQ-BROWSER-040")
def test_on_add_signals_no_status_when_none_skipped(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    mock_controller.add_signal.return_value = True
    wired._on_add_signals([(0, 0, 1)])
    assert wired.statusBar().currentMessage() == ""


# ---------------------------------------------------------------------------
# _on_file_dropped
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-FILE-011")
def test_file_dropped_loads_when_no_file_loaded(
    wired: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    mock_controller.is_file_loaded = False
    mock_controller.measurement_count = 0
    mock_controller.replace_measurements.return_value = LoadResult(succeeded=[MagicMock()])
    path = tmp_path / "test.mf4"
    wired._on_file_dropped(path)
    mock_controller.replace_measurements.assert_called_once_with([path])


@pytest.mark.requirement("REQ-FILE-020")
def test_file_dropped_asks_confirmation_when_file_loaded(
    wired: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    mock_controller.is_file_loaded = True
    mock_controller.measurement_count = 1
    path = tmp_path / "test.mf4"
    with patch.object(wired, "_ask_replace_or_add", return_value=None) as mock_ask:
        wired._on_file_dropped(path)
    mock_ask.assert_called_once()
    mock_controller.replace_measurements.assert_not_called()
    mock_controller.add_measurements.assert_not_called()


@pytest.mark.requirement("REQ-FILE-020")
def test_file_dropped_replaces_when_replace_chosen(
    wired: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    mock_controller.is_file_loaded = True
    mock_controller.measurement_count = 1
    mock_controller.replace_measurements.return_value = LoadResult(succeeded=[MagicMock()])
    path = tmp_path / "test.mf4"
    with patch.object(wired, "_ask_replace_or_add", return_value="replace"):
        wired._on_file_dropped(path)
    mock_controller.replace_measurements.assert_called_once_with([path])
    mock_controller.add_measurements.assert_not_called()


@pytest.mark.requirement("REQ-FILE-020")
def test_file_dropped_adds_when_add_chosen(
    wired: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    mock_controller.is_file_loaded = True
    mock_controller.measurement_count = 1
    mock_controller.add_measurements.return_value = LoadResult(succeeded=[MagicMock()])
    path = tmp_path / "test.mf4"
    with patch.object(wired, "_ask_replace_or_add", return_value="add"):
        wired._on_file_dropped(path)
    mock_controller.add_measurements.assert_called_once_with([path])
    mock_controller.replace_measurements.assert_not_called()


@pytest.mark.requirement("REQ-FILE-041")
@pytest.mark.requirement("REQ-FILE-040")
def test_file_dropped_error_shows_message_box(
    wired: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    mock_controller.is_file_loaded = False
    mock_controller.measurement_count = 0
    path = tmp_path / "bad.mf4"
    mock_controller.replace_measurements.return_value = LoadResult(
        failed=[(str(path), MdfLoadError("corrupt"))]
    )
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


@pytest.mark.requirement("REQ-PLOT-120")
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


@pytest.mark.requirement("REQ-PLOT-040")
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
    wired.active_signals_table.select_signal(active)

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

@pytest.mark.requirement("REQ-FILE-070")
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


@pytest.mark.requirement("REQ-FILE-070")
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


@pytest.mark.requirement("REQ-FILE-070")
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
    mock_controller.active_signals = []  # prevent teardown from triggering the real dialog


@pytest.mark.requirement("REQ-FILE-070")
def test_close_event_accept_when_not_prompted(
    window: MainWindow, mock_controller: MagicMock
) -> None:
    from PyQt6.QtGui import QCloseEvent
    window._controller = mock_controller
    mock_controller.active_signals = []  # no prompt
    event = QCloseEvent()
    window.closeEvent(event)
    assert event.isAccepted()


def test_close_event_deletes_a_live_parked_page(
    window: MainWindow, mock_controller: MagicMock
) -> None:
    """A parked page (#130) left over from closing the last tab without a
    following "New Tab" is unparented and was never deleteLater()'d.
    closeEvent() must clean it up — otherwise it's exactly the
    orphaned-but-alive Qt object #120 warns about, still wired into
    whatever signal/slot connections it had, surviving past this window's
    own teardown and crashing something unrelated much later."""
    from PyQt6.QtGui import QCloseEvent
    window._controller = mock_controller
    mock_controller.active_signals = []  # no save prompt
    mock_controller.tab_has_signals.return_value = False
    window._on_tab_close_requested(0)
    parked_page = window._parked_page
    assert parked_page is not None
    with patch.object(parked_page, "deleteLater") as mock_delete_later:
        window.closeEvent(QCloseEvent())
    mock_delete_later.assert_called_once()
    assert window._parked_page is None


@pytest.mark.requirement("REQ-FILE-071")
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
    mock_controller.active_signals = []  # prevent teardown from triggering the real dialog


# ---------------------------------------------------------------------------
# Open dialog routing
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-FILE-013")
def test_on_load_file_routes_mvc_to_load_config(
    window: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    mvc = tmp_path / "session.mvc"
    mvc.touch()
    window._controller = mock_controller
    window._settings = MagicMock()
    window._settings.prompt_save_config_on_close = False

    with patch("PyQt6.QtWidgets.QFileDialog.getOpenFileNames", return_value=([str(mvc)], "")):
        with patch.object(window, "_load_config") as mock_load_config:
            window._on_load_file()
            mock_load_config.assert_called_once_with(mvc)


@pytest.mark.requirement("REQ-FILE-013")
def test_on_load_file_routes_mdf_to_load_files(
    window: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    mdf = tmp_path / "data.mf4"
    mdf.touch()
    window._controller = mock_controller

    with patch("PyQt6.QtWidgets.QFileDialog.getOpenFileNames", return_value=([str(mdf)], "")):
        with patch.object(window, "_load_files") as mock_load_files:
            window._on_load_file()
            mock_load_files.assert_called_once_with([str(mdf)])


@pytest.mark.requirement("REQ-FILE-011")
def test_on_load_file_multi_select_routes_to_load_files(
    window: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    a = tmp_path / "a.mf4"
    b = tmp_path / "b.mf4"
    a.touch()
    b.touch()
    window._controller = mock_controller

    with patch(
        "PyQt6.QtWidgets.QFileDialog.getOpenFileNames",
        return_value=([str(a), str(b)], ""),
    ):
        with patch.object(window, "_load_files") as mock_load_files:
            window._on_load_file()
            mock_load_files.assert_called_once_with([str(a), str(b)])


@pytest.mark.requirement("REQ-FILE-013")
def test_on_open_recent_routes_mvc(
    window: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    mvc = tmp_path / "session.mvc"
    mvc.touch()
    window._controller = mock_controller
    window._settings = MagicMock()
    window._settings.prompt_save_config_on_close = False

    with patch.object(window, "_load_config") as mock_lc:
        window._on_open_recent(mvc)
        mock_lc.assert_called_once_with(mvc)


@pytest.mark.requirement("REQ-FILE-013")
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
# Multi-tab "keep signals on reload" (#99 M8, REQ-PLOT-260)
# ---------------------------------------------------------------------------

def test_collect_snapshots_empty_when_setting_never(
    window: MainWindow, mock_controller: MagicMock
) -> None:
    window._controller = mock_controller
    mock_controller.active_signals = []  # prevent teardown from triggering the real dialog
    window._settings = MagicMock(keep_signals_on_load="never")
    mock_controller.tab_count = 2
    mock_controller.tab_has_signals.return_value = True

    assert window._collect_snapshots_if_keeping() == {}
    mock_controller.snapshot_tab_signals.assert_not_called()


def test_collect_snapshots_covers_every_tab_with_signals(
    window: MainWindow, mock_controller: MagicMock
) -> None:
    window._controller = mock_controller
    mock_controller.active_signals = []  # prevent teardown from triggering the real dialog
    window._settings = MagicMock(keep_signals_on_load="always")
    mock_controller.tab_count = 3
    mock_controller.tab_has_signals.side_effect = lambda i: i in (0, 2)
    mock_controller.snapshot_tab_signals.side_effect = lambda i: [f"snap{i}"]

    result = window._collect_snapshots_if_keeping()

    assert result == {0: ["snap0"], 2: ["snap2"]}


def test_collect_snapshots_ask_prompts_once_not_per_tab(
    window: MainWindow, mock_controller: MagicMock
) -> None:
    window._controller = mock_controller
    mock_controller.active_signals = []  # prevent teardown from triggering the real dialog
    window._settings = MagicMock(keep_signals_on_load="ask")
    mock_controller.tab_count = 2
    mock_controller.tab_has_signals.return_value = True
    mock_controller.snapshot_tab_signals.side_effect = lambda i: [f"snap{i}"]

    with patch(
        "PyQt6.QtWidgets.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Yes,
    ) as mock_question:
        result = window._collect_snapshots_if_keeping()

    mock_question.assert_called_once()
    assert result == {0: ["snap0"], 1: ["snap1"]}


def test_collect_snapshots_ask_declined_returns_empty(
    window: MainWindow, mock_controller: MagicMock
) -> None:
    window._controller = mock_controller
    mock_controller.active_signals = []  # prevent teardown from triggering the real dialog
    window._settings = MagicMock(keep_signals_on_load="ask")
    mock_controller.tab_count = 1
    mock_controller.tab_has_signals.return_value = True

    with patch(
        "PyQt6.QtWidgets.QMessageBox.question",
        return_value=QMessageBox.StandardButton.No,
    ):
        assert window._collect_snapshots_if_keeping() == {}


def test_collect_snapshots_skips_prompt_when_no_tab_has_signals(
    window: MainWindow, mock_controller: MagicMock
) -> None:
    window._controller = mock_controller
    mock_controller.active_signals = []  # prevent teardown from triggering the real dialog
    window._settings = MagicMock(keep_signals_on_load="ask")
    mock_controller.tab_count = 2
    mock_controller.tab_has_signals.return_value = False

    with patch("PyQt6.QtWidgets.QMessageBox.question") as mock_question:
        assert window._collect_snapshots_if_keeping() == {}
    mock_question.assert_not_called()


def test_restore_snapshots_restores_into_each_tab(
    window: MainWindow, mock_controller: MagicMock
) -> None:
    window._controller = mock_controller
    mock_controller.active_signals = []  # prevent teardown from triggering the real dialog
    snap_a, snap_b = _snap("a"), _snap("b")
    measurement = MagicMock(label="m")
    mock_controller.find_signal_locations_by_name.side_effect = (
        lambda name: [(measurement, MagicMock(group_index=0, channel_index=1))]
    )

    window._restore_snapshots({0: [snap_a], 2: [snap_b]})

    calls = mock_controller.restore_tab_signals.call_args_list
    restored_tabs = {c.args[0] for c in calls}
    assert restored_tabs == {0, 2}


@pytest.mark.requirement("REQ-FILE-090")
def test_restore_snapshots_ignores_group_name_preserving_prior_behavior(
    window: MainWindow, mock_controller: MagicMock
) -> None:
    """#106 M5 extracted a shared classify/dialog helper from
    _restore_snapshots and _resolve_config_signals; use_group_name=False
    for THIS caller preserves its pre-#106 behavior of never passing
    group_name to _classify_signal_name, even when the snapshot itself
    carries a real one (unlike _resolve_config_signals, which does use
    it) — a deliberate choice to avoid silently changing this shipped
    reload flow's resolution behavior as a side effect of the refactor.
    """
    window._controller = mock_controller
    mock_controller.active_signals = []
    snap = MagicMock()
    snap.name = "Speed"
    snap.group_name = "Engine"
    snap.measurement = None
    measurement = MagicMock()
    mock_controller.find_signal_locations_by_name.return_value = [
        (measurement, MagicMock(group_index=0, channel_index=1))
    ]

    with patch.object(
        window, "_classify_signal_name", wraps=window._classify_signal_name
    ) as spy:
        window._restore_snapshots({0: [snap]})

    spy.assert_called_once_with("Speed", "", measurement_aware=True, measurement=None)


# ---------------------------------------------------------------------------
# Near-match resolution wiring (#109, REQ-FILE-032-036)
# ---------------------------------------------------------------------------

def _snap(name: str) -> MagicMock:
    m = MagicMock()
    m.name = name
    # Real ActiveSignalSnapshot.measurement defaults to None (#106 M6) —
    # a bare MagicMock auto-vivifies any attribute access to a truthy
    # Mock instead, which would wrongly look like a snapshot carrying its
    # own scoped-restore measurement (REQ-FILE-093) to
    # _resolve_and_confirm_snapshots().
    m.measurement = None
    return m


def _near_candidate(name: str, gi: int = 0, ci: int = 1) -> MagicMock:
    m = MagicMock(group_index=gi, channel_index=ci)
    m.name = name
    return m


class _FakeNearMatchDialog:
    """Stand-in for NearMatchDialog that records what it was built with."""
    instances: list["_FakeNearMatchDialog"] = []

    def __init__(self, pending, parent=None):
        self.pending = pending
        self.exec_result = True
        self.mask = [True] * len(pending)
        _FakeNearMatchDialog.instances.append(self)

    def exec(self):
        return self.exec_result

    def checked_mask(self):
        return self.mask


@pytest.fixture(autouse=False)
def fake_near_match_dialog():
    _FakeNearMatchDialog.instances = []
    with patch("mdf_viewer.view.near_match_dialog.NearMatchDialog", _FakeNearMatchDialog):
        yield _FakeNearMatchDialog


def test_restore_snapshots_near_single_resolves_when_accepted(
    window: MainWindow, mock_controller: MagicMock, fake_near_match_dialog
) -> None:
    window._controller = mock_controller
    mock_controller.active_signals = []
    snap = _snap("a\\XCP:1")
    candidate = _near_candidate("a\\ETKC:1")
    measurement = MagicMock(label="m")

    with patch.object(
        window, "_classify_signal_name", return_value=("near_single", [(measurement, candidate)]),
    ):
        window._restore_snapshots({0: [snap]})

    assert len(fake_near_match_dialog.instances) == 1
    mock_controller.restore_tab_signals.assert_called_once_with(
        0, [(snap, candidate.group_index, candidate.channel_index, measurement)]
    )


def test_restore_snapshots_near_match_declined_goes_to_not_found(
    window: MainWindow, mock_controller: MagicMock
) -> None:
    window._controller = mock_controller
    mock_controller.active_signals = []
    snap = _snap("a\\XCP:1")
    candidate = _near_candidate("a\\ETKC:1")
    dlg = _FakeNearMatchDialog([("a\\XCP:1", candidate)])
    dlg.mask = [False]

    with patch.object(window, "_classify_signal_name", return_value=("near_single", [candidate])), \
         patch("mdf_viewer.view.near_match_dialog.NearMatchDialog", return_value=dlg), \
         patch("mdf_viewer.view.signals_not_found_dialog.SignalsNotFoundDialog") as mock_not_found_cls:
        mock_not_found_cls.return_value.exec.return_value = True
        window._restore_snapshots({0: [snap]})

    mock_controller.restore_tab_signals.assert_not_called()
    mock_not_found_cls.assert_called_once_with(["a\\XCP:1"], window)


def test_restore_snapshots_cancelling_near_match_dialog_declines_all(
    window: MainWindow, mock_controller: MagicMock
) -> None:
    window._controller = mock_controller
    mock_controller.active_signals = []
    snap = _snap("a\\XCP:1")
    candidate = _near_candidate("a\\ETKC:1")
    dlg = _FakeNearMatchDialog([("a\\XCP:1", candidate)])
    dlg.exec_result = False

    with patch.object(window, "_classify_signal_name", return_value=("near_single", [candidate])), \
         patch("mdf_viewer.view.near_match_dialog.NearMatchDialog", return_value=dlg), \
         patch("mdf_viewer.view.signals_not_found_dialog.SignalsNotFoundDialog") as mock_not_found_cls:
        mock_not_found_cls.return_value.exec.return_value = True
        window._restore_snapshots({0: [snap]})

    mock_controller.restore_tab_signals.assert_not_called()
    mock_not_found_cls.assert_called_once_with(["a\\XCP:1"], window)


def test_restore_snapshots_one_near_match_dialog_spans_all_tabs(
    window: MainWindow, mock_controller: MagicMock
) -> None:
    window._controller = mock_controller
    mock_controller.active_signals = []
    snap_a = _snap("a\\XCP:1")
    snap_b = _snap("b\\XCP:1")
    measurement = MagicMock(label="m")
    candidate_a = (measurement, _near_candidate("a\\ETKC:1"))
    candidate_b = (measurement, _near_candidate("b\\ETKC:1"))

    def classify(name, group_name="", measurement_aware=False, measurement=None):
        return ("near_single", [candidate_a if name == "a\\XCP:1" else candidate_b])

    captured = {}

    def make_dialog(pending, parent=None):
        dlg = _FakeNearMatchDialog(pending, parent)
        captured["dlg"] = dlg
        return dlg

    with patch.object(window, "_classify_signal_name", side_effect=classify), \
         patch("mdf_viewer.view.near_match_dialog.NearMatchDialog", side_effect=make_dialog):
        window._restore_snapshots({0: [snap_a], 1: [snap_b]})

    assert len(captured["dlg"].pending) == 2
    assert mock_controller.restore_tab_signals.call_count == 2


def test_restore_snapshots_near_multiple_uses_picker_then_near_match_dialog(
    window: MainWindow, mock_controller: MagicMock
) -> None:
    window._controller = mock_controller
    mock_controller.active_signals = []
    snap = _snap("a\\XCP:1")
    measurement = MagicMock(label="m")
    candidate_1 = (measurement, _near_candidate("a\\ETKC:1", ci=1))
    candidate_2 = (measurement, _near_candidate("a\\ETKC:2", ci=2))
    dlg = _FakeNearMatchDialog([("a\\XCP:1", candidate_2)])

    with patch.object(window, "_classify_signal_name", return_value=("near_multiple", [candidate_1, candidate_2])), \
         patch("mdf_viewer.view.signal_group_picker_dialog.SignalGroupPickerDialog") as mock_picker_cls, \
         patch("mdf_viewer.view.near_match_dialog.NearMatchDialog", return_value=dlg):
        mock_picker_cls.return_value.exec.return_value = True
        mock_picker_cls.return_value.selected.return_value = candidate_2
        window._restore_snapshots({0: [snap]})

    meta_2 = candidate_2[1]
    mock_controller.restore_tab_signals.assert_called_once_with(
        0, [(snap, meta_2.group_index, meta_2.channel_index, measurement)]
    )


# ---------------------------------------------------------------------------
# _resolve_config_signals_for_tabs near-match wiring (#109, #106 M6)
# ---------------------------------------------------------------------------

def _signal_config(
    name: str, group_name: str = "", *, stripe_index: int = 0, measurement_index: int = 0,
) -> "SignalConfig":
    from mdf_viewer.model.viewer_config import SignalConfig
    return SignalConfig(
        name=name,
        group_name=group_name,
        color=(255, 0, 0),
        line_width=1,
        line_style="solid",
        display_mode="line",
        marker_shape="circle",
        step_mode=False,
        enum_display_table=False,
        enum_display_cursor=False,
        enum_display_yaxis=False,
        stripe_index=stripe_index,
        measurement_index=measurement_index,
    )


def test_resolve_config_signals_for_tabs_near_single_resolves_when_accepted(
    window: MainWindow, mock_controller: MagicMock
) -> None:
    window._controller = mock_controller
    mock_controller.active_signals = []
    tab_config = MagicMock(signals=[_signal_config("a\\XCP:1")], stripes=[])
    measurement = MagicMock(label="m")
    candidate = (measurement, _near_candidate("a\\ETKC:1"))
    dlg = _FakeNearMatchDialog([("a\\XCP:1", candidate)])

    with patch.object(window, "_classify_signal_name", return_value=("near_single", [candidate])), \
         patch("mdf_viewer.view.near_match_dialog.NearMatchDialog", return_value=dlg):
        resolved_by_tab, not_found = window._resolve_config_signals_for_tabs(
            [tab_config], [measurement],
        )

    assert not_found == []
    resolved = resolved_by_tab[0]
    assert len(resolved) == 1
    snap, gi, ci, meas = resolved[0]
    assert snap.name == "a\\XCP:1"
    assert (gi, ci, meas) == (candidate[1].group_index, candidate[1].channel_index, measurement)


def test_resolve_config_signals_for_tabs_near_match_declined_goes_to_not_found(
    window: MainWindow, mock_controller: MagicMock
) -> None:
    window._controller = mock_controller
    mock_controller.active_signals = []
    tab_config = MagicMock(signals=[_signal_config("a\\XCP:1")], stripes=[])
    measurement = MagicMock(label="m")
    candidate = (measurement, _near_candidate("a\\ETKC:1"))
    dlg = _FakeNearMatchDialog([("a\\XCP:1", candidate)])
    dlg.mask = [False]

    with patch.object(window, "_classify_signal_name", return_value=("near_single", [candidate])), \
         patch("mdf_viewer.view.near_match_dialog.NearMatchDialog", return_value=dlg):
        resolved_by_tab, not_found = window._resolve_config_signals_for_tabs(
            [tab_config], [measurement],
        )

    assert resolved_by_tab == {}
    assert not_found == ["a\\XCP:1"]


def test_resolve_config_signals_for_tabs_exact_single_unaffected_by_near_match_logic(
    window: MainWindow, mock_controller: MagicMock
) -> None:
    window._controller = mock_controller
    mock_controller.active_signals = []
    tab_config = MagicMock(signals=[_signal_config("plain")], stripes=[])
    measurement = MagicMock(label="m")
    exact = (measurement, _near_candidate("plain"))

    with patch.object(window, "_classify_signal_name", return_value=("exact_single", [exact])):
        resolved_by_tab, not_found = window._resolve_config_signals_for_tabs(
            [tab_config], [measurement],
        )

    assert not_found == []
    assert len(resolved_by_tab[0]) == 1


@pytest.mark.requirement("REQ-FILE-090")
def test_resolve_config_signals_for_tabs_passes_group_name_preserving_prior_behavior(
    window: MainWindow, mock_controller: MagicMock
) -> None:
    """The mirror of test_restore_snapshots_ignores_group_name...: this
    call site DID already pass group_name pre-#106, and the M5/M6 refactor
    must not silently drop that either."""
    window._controller = mock_controller
    mock_controller.active_signals = []
    tab_config = MagicMock(signals=[_signal_config("Speed", "Engine")], stripes=[])
    measurement = MagicMock(label="m")

    with patch.object(
        window, "_classify_signal_name", wraps=window._classify_signal_name
    ) as spy:
        measurement.loader.find_signal_by_name.return_value = [_near_candidate("Speed")]
        window._resolve_config_signals_for_tabs([tab_config], [measurement])

    spy.assert_called_once_with(
        "Speed", "Engine", measurement_aware=True, measurement=measurement,
    )


@pytest.mark.requirement("REQ-FILE-093")
def test_resolve_config_signals_for_tabs_scopes_search_to_signals_own_measurement(
    window: MainWindow, mock_controller: MagicMock
) -> None:
    """A signal's saved measurement_index must scope its resolution to
    that one measurement, not the whole pool (REQ-FILE-093) — verified
    here by using the real (non-mocked) _classify_signal_name and
    confirming it only ever queries the measurement at that index."""
    window._controller = mock_controller
    mock_controller.active_signals = []
    tab_config = MagicMock(
        signals=[_signal_config("Speed", measurement_index=1)], stripes=[],
    )
    meas0, meas1 = MagicMock(label="M1"), MagicMock(label="M2")
    meas1.loader.find_signal_by_name.return_value = [_near_candidate("Speed")]

    resolved_by_tab, not_found = window._resolve_config_signals_for_tabs(
        [tab_config], [meas0, meas1],
    )

    meas0.loader.find_signal_by_name.assert_not_called()
    meas1.loader.find_signal_by_name.assert_called_once_with("Speed")
    assert not_found == []
    snap, gi, ci, meas = resolved_by_tab[0][0]
    assert meas is meas1


@pytest.mark.requirement("REQ-FILE-098")
def test_resolve_config_signals_for_tabs_missing_measurement_folds_into_not_found(
    window: MainWindow, mock_controller: MagicMock
) -> None:
    """A signal whose measurement_index points at a None slot (that
    measurement failed to load, #106 Phase 1) is folded into not_found
    without ever attempting name resolution — nothing to search."""
    window._controller = mock_controller
    mock_controller.active_signals = []
    tab_config = MagicMock(
        signals=[_signal_config("Speed", measurement_index=0)], stripes=[],
    )

    with patch.object(window, "_classify_signal_name") as spy:
        resolved_by_tab, not_found = window._resolve_config_signals_for_tabs(
            [tab_config], [None],
        )

    spy.assert_not_called()
    assert resolved_by_tab == {}
    assert not_found == ["Speed"]


# ---------------------------------------------------------------------------
# Session restore Phase 0 (_reset_to_single_tab) and Phase 1 helpers (#106)
# ---------------------------------------------------------------------------

def test_reset_to_single_tab_noop_without_controller(window: MainWindow) -> None:
    window._reset_to_single_tab()  # must not raise


def test_reset_to_single_tab_removes_extra_tabs(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    wired._on_new_tab()
    wired._on_new_tab()
    mock_controller.tab_count = 3

    wired._reset_to_single_tab()

    assert wired._real_tab_count() == 1
    assert mock_controller.remove_tab.call_count == 2
    mock_controller.remove_all.assert_called_once()


def test_reset_to_single_tab_deletes_removed_pages(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    wired._on_new_tab()
    mock_controller.tab_count = 2
    page = wired._tab_widget.widget(1)

    with patch.object(page, "deleteLater") as mock_delete:
        wired._reset_to_single_tab()

    mock_delete.assert_called_once()


def test_reset_to_single_tab_sets_current_index_to_zero(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    wired._on_new_tab()  # tab 1 becomes current
    mock_controller.tab_count = 2

    wired._reset_to_single_tab()

    assert wired._tab_widget.currentIndex() == 0


def test_reset_to_single_tab_already_single_still_clears_signals(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    mock_controller.tab_count = 1

    wired._reset_to_single_tab()

    mock_controller.remove_tab.assert_not_called()
    mock_controller.remove_all.assert_called_once()


def _make_measurement_config(path: str = "a.mf4", label: str = "M1", offset_s: float = 0.0):
    from mdf_viewer.model.viewer_config import MeasurementConfig
    return MeasurementConfig(path=path, label=label, offset_s=offset_s)


@pytest.mark.requirement("REQ-FILE-064")
def test_resolve_saved_measurements_all_found(window: MainWindow, tmp_path) -> None:
    meas = tmp_path / "a.mf4"
    meas.touch()
    configs = [_make_measurement_config(str(meas))]

    resolved, missing = window._resolve_saved_measurements(configs, tmp_path / "session.mvc")

    assert missing == []
    assert resolved[0].path == str(meas)


@pytest.mark.requirement("REQ-FILE-097")
def test_resolve_saved_measurements_missing_reports_original_path(
    window: MainWindow, tmp_path
) -> None:
    configs = [_make_measurement_config("nope.mf4")]

    resolved, missing = window._resolve_saved_measurements(configs, tmp_path / "session.mvc")

    assert missing == ["nope.mf4"]
    assert resolved[0].path == "nope.mf4"


@pytest.mark.requirement("REQ-FILE-097")
def test_resolve_saved_measurements_preserves_order_and_index_alignment(
    window: MainWindow, tmp_path
) -> None:
    found = tmp_path / "found.mf4"
    found.touch()
    configs = [
        _make_measurement_config("missing1.mf4", "M1"),
        _make_measurement_config(str(found), "M2"),
        _make_measurement_config("missing2.mf4", "M3"),
    ]

    resolved, missing = window._resolve_saved_measurements(configs, tmp_path / "session.mvc")

    assert len(resolved) == 3
    assert resolved[0].path == "missing1.mf4"
    assert resolved[1].path == str(found)
    assert resolved[2].path == "missing2.mf4"
    assert missing == ["missing1.mf4", "missing2.mf4"]


def test_confirm_missing_measurements_no_missing_returns_true(window: MainWindow) -> None:
    assert window._confirm_missing_measurements([]) is True


@pytest.mark.requirement("REQ-FILE-097")
def test_confirm_missing_measurements_continue(window: MainWindow) -> None:
    with patch(
        "mdf_viewer.view.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Yes,
    ):
        assert window._confirm_missing_measurements(["a.mf4"]) is True


@pytest.mark.requirement("REQ-FILE-097")
def test_confirm_missing_measurements_cancel(window: MainWindow) -> None:
    with patch(
        "mdf_viewer.view.main_window.QMessageBox.question",
        return_value=QMessageBox.StandardButton.Cancel,
    ):
        assert window._confirm_missing_measurements(["a.mf4"]) is False


# ---------------------------------------------------------------------------
# Session restore Phase 2 (_build_tab_skeletons / _build_stripe_skeleton, #106)
# ---------------------------------------------------------------------------

def _make_tab_config(name="Tab 1", stripes=None, active_stripe_index=0):
    from mdf_viewer.model.viewer_config import StripeConfig, TabConfig
    if stripes is None:
        stripes = [StripeConfig(name="Stripe 1", size=1)]
    return TabConfig(
        name=name, stripes=tuple(stripes), active_stripe_index=active_stripe_index,
        signals=(), x_range=(0.0, 1.0), y_ranges=(), merged_groups=(), synced_groups=(),
        cursor_mode="HIDDEN", cursor_positions=(0.0, 0.0), selected_signal=None,
    )


@pytest.mark.requirement("REQ-FILE-091")
def test_build_tab_skeletons_single_tab_renames_existing(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    configs = [_make_tab_config(name="Engine")]
    wired._build_tab_skeletons(configs)
    assert wired._tab_widget.tabText(0) == "Engine"
    assert wired._real_tab_count() == 1


@pytest.mark.requirement("REQ-FILE-091")
def test_build_tab_skeletons_multiple_tabs(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    configs = [_make_tab_config(name="Engine"), _make_tab_config(name="Chassis")]
    wired._build_tab_skeletons(configs)
    assert wired._real_tab_count() == 2
    assert wired._tab_widget.tabText(0) == "Engine"
    assert wired._tab_widget.tabText(1) == "Chassis"


def test_build_tab_skeletons_noop_without_controller(window: MainWindow) -> None:
    window._build_tab_skeletons([_make_tab_config()])  # must not raise


@pytest.mark.requirement("REQ-FILE-090")
def test_build_tab_skeletons_applies_page_splitter_sizes(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    # Asserts the setSizes() call itself, not a later .sizes() readback —
    # QSplitter redistributes requested sizes to fit actual widget geometry,
    # which a headless/offscreen test window may not have settled yet
    # (same reasoning as the existing _apply_splitter_sizes tests below).
    import dataclasses
    config = dataclasses.replace(_make_tab_config(), page_splitter_sizes=(700, 320))
    page = wired._tab_widget.widget(0)
    with patch.object(page, "setSizes") as mock_set_sizes:
        wired._build_tab_skeletons([config])
    mock_set_sizes.assert_called_once_with([700, 320])


@pytest.mark.requirement("REQ-FILE-090")
def test_build_stripe_skeleton_reuses_existing_first_stripe(wired: MainWindow) -> None:
    """PlotStripesArea already creates one stripe unconditionally — must
    be reused, not duplicated (the #106 Plan-review-caught bug)."""
    from mdf_viewer.model.viewer_config import StripeConfig
    page = wired._tab_widget.widget(0)
    stripes = [StripeConfig(name="Vibration", size=300)]

    wired._build_stripe_skeleton(page, stripes, 0)

    plot_stripes = page.plot_area.get_stripes()
    assert len(plot_stripes) == 1
    assert plot_stripes[0].name == "Vibration"


@pytest.mark.requirement("REQ-FILE-090")
def test_build_stripe_skeleton_creates_additional_stripes(wired: MainWindow) -> None:
    from mdf_viewer.model.viewer_config import StripeConfig
    page = wired._tab_widget.widget(0)
    stripes = [StripeConfig(name="Vibration", size=300), StripeConfig(name="Temp", size=150)]

    wired._build_stripe_skeleton(page, stripes, 1)

    plot_stripes = page.plot_area.get_stripes()
    assert [s.name for s in plot_stripes] == ["Vibration", "Temp"]
    assert page.plot_area.get_active_stripe() is plot_stripes[1]


@pytest.mark.requirement("REQ-FILE-090")
def test_build_stripe_skeleton_sets_sizes(wired: MainWindow) -> None:
    from mdf_viewer.model.viewer_config import StripeConfig
    page = wired._tab_widget.widget(0)
    stripes = [StripeConfig(name="A", size=300), StripeConfig(name="B", size=150)]

    with patch.object(page.plot_area, "set_stripe_sizes") as mock_set_sizes:
        wired._build_stripe_skeleton(page, stripes, 0)

    mock_set_sizes.assert_called_once_with([300, 150])


@pytest.mark.requirement("REQ-FILE-090")
def test_build_stripe_skeleton_ast_segment_label_updated(wired: MainWindow) -> None:
    from mdf_viewer.model.viewer_config import StripeConfig
    page = wired._tab_widget.widget(0)
    stripes = [StripeConfig(name="Vibration", size=1)]

    wired._build_stripe_skeleton(page, stripes, 0)

    seg = page.active_signals_table._segments[0]
    assert seg.name_label.text() == "Vibration"


# ---------------------------------------------------------------------------
# Duplicate Tab (#119)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-265")
def test_duplicate_tab_builds_matching_stripe_skeleton(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    source_page = wired._tab_widget.widget(0)
    source_plot = source_page.plot_area
    source_ast = source_page.active_signals_table
    stripe_1 = source_plot.get_stripes()[0]
    source_ast.rename_stripe_segment(stripe_1, "Vibration")
    stripe_2 = source_plot.create_stripe()
    source_ast.rename_stripe_segment(stripe_2, "Temp")
    source_plot.set_stripe_sizes([300, 150])
    source_plot.set_active_stripe(stripe_2)

    wired._on_duplicate_tab(0)

    dest_page = wired._tab_widget.widget(1)
    dest_plot = dest_page.plot_area
    dest_stripes = dest_plot.get_stripes()
    assert [s.name for s in dest_stripes] == ["Vibration", "Temp"]
    assert dest_plot.get_active_stripe() is dest_stripes[1]
    mock_controller.duplicate_tab_signals.assert_called_once_with(0, 1)


@pytest.mark.requirement("REQ-PLOT-265")
def test_duplicate_tab_copies_ast_column_widths(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    source_page = wired._tab_widget.widget(0)
    source_ast = source_page.active_signals_table
    source_ast.set_column_widths([w + 10 for w in source_ast.column_widths()])
    expected = source_ast.column_widths()  # readback: not every column is resizable

    wired._on_duplicate_tab(0)

    dest_page = wired._tab_widget.widget(1)
    assert dest_page.active_signals_table.column_widths() == expected


@pytest.mark.requirement("REQ-PLOT-265")
def test_duplicate_tab_copies_page_splitter_sizes(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    """Asserts the setSizes() call made on the new tab's page specifically
    (not a later .sizes() readback, which QSplitter may redistribute to
    fit actual widget geometry not yet settled in a headless test window —
    same reasoning as _build_tab_skeletons' own splitter-size test). Only
    the destination page's own setSizes is patched (after it's built by
    _on_new_tab() inside _on_duplicate_tab()), not the QSplitter class
    globally — patching the whole class also breaks PlotStripesArea's own
    internal splitter, which _on_new_tab() constructs a fresh one of."""
    source_page = wired._tab_widget.widget(0)
    source_page.setSizes([600, 250])
    expected = source_page.sizes()
    orig_on_new_tab = wired._on_new_tab
    captured: dict[str, object] = {}

    def _spy_on_new_tab():
        index = orig_on_new_tab()
        page = wired._tab_widget.widget(index)
        captured["mock"] = patch.object(page, "setSizes")
        captured["page"] = page
        captured["mock"].start()
        return index

    with patch.object(wired, "_on_new_tab", side_effect=_spy_on_new_tab):
        wired._on_duplicate_tab(0)
    try:
        captured["page"].setSizes.assert_called_once_with(expected)
    finally:
        captured["mock"].stop()


def test_duplicate_tab_inserts_immediately_after_source_and_names_it(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    wired._on_new_tab()  # Tab 2

    wired._on_duplicate_tab(0)

    assert wired._real_tab_count() == 3
    assert wired._tab_widget.tabText(1) == "Copy of Tab 1"
    assert wired._tab_widget.tabText(2) == "Tab 2"
    mock_controller.duplicate_tab_signals.assert_called_once_with(0, 1)


def test_duplicate_tab_on_last_real_tab(wired: MainWindow, mock_controller: MagicMock) -> None:
    """Same moveTab()-no-op edge case as Copy Signals to new Tab (#119
    review finding) — confirm it still lands correctly."""
    wired._on_duplicate_tab(0)  # tab 0 is the only (and last) real tab

    assert wired._real_tab_count() == 2
    assert wired._tab_widget.tabText(1) == "Copy of Tab 1"
    mock_controller.duplicate_tab_signals.assert_called_once_with(0, 1)


def test_tab_context_menu_duplicate_tab_action(wired: MainWindow, mock_controller: MagicMock) -> None:
    tab_bar = wired._tab_widget.tabBar()
    pos = tab_bar.tabRect(0).center()
    patch_add, patch_exec = _select_menu_action_by_text("Duplicate Tab")
    with patch_add, patch_exec:
        wired._on_tab_context_menu(pos)
    assert wired._real_tab_count() == 2
    assert wired._tab_widget.tabText(1) == "Copy of Tab 1"
    mock_controller.duplicate_tab_signals.assert_called_once_with(0, 1)


def test_tab_context_menu_duplicate_tab_enabled_even_with_no_signals(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    """Unlike Copy Signals to new Tab, Duplicate Tab stays enabled on an
    empty source tab (REQ-PLOT-263)."""
    mock_controller.tab_has_signals.return_value = False
    from PyQt6.QtWidgets import QMenu
    captured: dict[str, object] = {}
    orig_add_action = QMenu.addAction

    def _tracking_add_action(self, text):
        action = orig_add_action(self, text)
        captured[text] = action
        return action

    tab_bar = wired._tab_widget.tabBar()
    pos = tab_bar.tabRect(0).center()
    with patch.object(QMenu, "addAction", _tracking_add_action), \
         patch.object(QMenu, "exec", return_value=None):
        wired._on_tab_context_menu(pos)
    assert captured["Duplicate Tab"].isEnabled() is True


# ---------------------------------------------------------------------------
# open_config — public entry point used by app.py for CLI / file association
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-FILE-011")
@pytest.mark.requirement("REQ-FILE-013")
def test_open_config_delegates_to_load_config(
    window: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    mvc = tmp_path / "session.mvc"
    mvc.touch()
    window._controller = mock_controller
    window._settings = MagicMock()
    window._settings.prompt_save_config_on_close = False

    with patch.object(window, "_load_config") as mock_lc:
        window.open_config(mvc)
        mock_lc.assert_called_once_with(mvc)


@pytest.mark.requirement("REQ-FILE-013")
def test_open_config_mvc_not_routed_to_load_file(
    window: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    mvc = tmp_path / "session.mvc"
    mvc.touch()
    window._controller = mock_controller
    window._settings = MagicMock()
    window._settings.prompt_save_config_on_close = False

    with patch.object(window, "_load_config"):
        with patch.object(window, "_load_file") as mock_lf:
            window.open_config(mvc)
            mock_lf.assert_not_called()


# ---------------------------------------------------------------------------
# _classify_signal_name (#109, REQ-FILE-032/033)
# ---------------------------------------------------------------------------

def _candidate(name: str = "sig", group_name: str = "") -> MagicMock:
    m = MagicMock()
    m.name = name
    m.group_name = group_name
    return m


def test_classify_exact_single_match(window: MainWindow, mock_controller: MagicMock) -> None:
    window._controller = mock_controller
    mock_controller.active_signals = []  # prevent teardown from triggering the real dialog
    exact = _candidate("sig")
    mock_controller.find_signal_by_name.return_value = [exact]

    status, candidates = window._classify_signal_name("sig")

    assert status == "exact_single"
    assert candidates == [exact]
    mock_controller.find_similar_signal_by_name.assert_not_called()


def test_classify_exact_multiple_matches(window: MainWindow, mock_controller: MagicMock) -> None:
    window._controller = mock_controller
    mock_controller.active_signals = []  # prevent teardown from triggering the real dialog
    mock_controller.find_signal_by_name.return_value = [_candidate("sig"), _candidate("sig")]

    status, candidates = window._classify_signal_name("sig")

    assert status == "exact_multiple"
    assert len(candidates) == 2


def test_classify_near_single_match_only_when_no_exact(
    window: MainWindow, mock_controller: MagicMock
) -> None:
    window._controller = mock_controller
    mock_controller.active_signals = []  # prevent teardown from triggering the real dialog
    mock_controller.find_signal_by_name.return_value = []
    near = _candidate("a\\ETKC:1")
    mock_controller.find_similar_signal_by_name.return_value = [near]

    status, candidates = window._classify_signal_name("a\\XCP:1")

    assert status == "near_single"
    assert candidates == [near]


def test_classify_near_multiple_matches(window: MainWindow, mock_controller: MagicMock) -> None:
    window._controller = mock_controller
    mock_controller.active_signals = []  # prevent teardown from triggering the real dialog
    mock_controller.find_signal_by_name.return_value = []
    mock_controller.find_similar_signal_by_name.return_value = [
        _candidate("a\\ETKC:1"), _candidate("a\\ETKC:2"),
    ]

    status, candidates = window._classify_signal_name("a\\XCP:1")

    assert status == "near_multiple"
    assert len(candidates) == 2


def test_classify_not_found_when_no_exact_or_near_match(
    window: MainWindow, mock_controller: MagicMock
) -> None:
    window._controller = mock_controller
    mock_controller.active_signals = []  # prevent teardown from triggering the real dialog
    mock_controller.find_signal_by_name.return_value = []
    mock_controller.find_similar_signal_by_name.return_value = []

    status, candidates = window._classify_signal_name("unrelated")

    assert status == "not_found"
    assert candidates == []


def test_classify_never_prefers_near_match_over_exact(
    window: MainWindow, mock_controller: MagicMock
) -> None:
    """A near-match lookup must not even run when an exact match exists."""
    window._controller = mock_controller
    mock_controller.active_signals = []  # prevent teardown from triggering the real dialog
    mock_controller.find_signal_by_name.return_value = [_candidate("sig")]

    window._classify_signal_name("sig")

    mock_controller.find_similar_signal_by_name.assert_not_called()


def test_classify_narrows_exact_matches_by_group_name(
    window: MainWindow, mock_controller: MagicMock
) -> None:
    window._controller = mock_controller
    mock_controller.active_signals = []  # prevent teardown from triggering the real dialog
    wanted = _candidate("sig", group_name="Group B")
    mock_controller.find_signal_by_name.return_value = [_candidate("sig", group_name="Group A"), wanted]

    status, candidates = window._classify_signal_name("sig", group_name="Group B")

    assert status == "exact_single"
    assert candidates == [wanted]


def test_classify_group_name_narrowing_falls_back_when_no_match(
    window: MainWindow, mock_controller: MagicMock
) -> None:
    """If none of the candidates match group_name, keep the full candidate
    list rather than narrowing to nothing."""
    window._controller = mock_controller
    mock_controller.active_signals = []  # prevent teardown from triggering the real dialog
    all_candidates = [_candidate("sig", group_name="Group A"), _candidate("sig", group_name="Group A")]
    mock_controller.find_signal_by_name.return_value = all_candidates

    status, candidates = window._classify_signal_name("sig", group_name="Group Z")

    assert status == "exact_multiple"
    assert candidates == all_candidates


# ---------------------------------------------------------------------------
# Layout persistence (#77) — window geometry and splitter sizes
# ---------------------------------------------------------------------------

def _minimal_config(**overrides):
    """Build a single-tab ViewerConfig; overrides may name either a
    TabConfig field or a top-level ViewerConfig field."""
    from mdf_viewer.config_manager import CONFIG_FORMAT_VERSION
    from mdf_viewer.model.viewer_config import StripeConfig, TabConfig, ViewerConfig
    tab_field_names = {
        "signals", "x_range", "y_ranges", "merged_groups", "synced_groups",
        "cursor_mode", "cursor_positions", "selected_signal",
    }
    tab_fields = dict(
        name="Tab 1", stripes=(StripeConfig(name="Stripe 1", size=1),),
        active_stripe_index=0, signals=(),
        x_range=(0.0, 1.0), y_ranges=(), merged_groups=(), synced_groups=(),
        cursor_mode="HIDDEN", cursor_positions=(0.0, 0.0), selected_signal=None,
    )
    top_fields = dict(
        format_version=CONFIG_FORMAT_VERSION, measurements=(), primary_measurement_index=0,
        measurements_synchronized=False, active_tab_index=0,
        display_name_separator=".", display_name_direction="right", display_name_segments=1,
    )
    for key, value in overrides.items():
        if key in tab_field_names:
            tab_fields[key] = value
        else:
            top_fields[key] = value
    return ViewerConfig(tabs=(TabConfig(**tab_fields),), **top_fields)


@pytest.mark.requirement("REQ-FILE-061")
def test_capture_window_geometry_reflects_current_size(window: MainWindow) -> None:
    window.resize(999, 555)
    geo = window._capture_window_geometry()
    assert geo == {"x": geo["x"], "y": geo["y"], "width": 999, "height": 555, "maximized": False}


@pytest.mark.requirement("REQ-FILE-061")
def test_apply_window_geometry_resizes_and_moves(window: MainWindow) -> None:
    window._apply_window_geometry({"x": 10, "y": 20, "width": 900, "height": 600, "maximized": False})
    assert window.width() == 900
    assert window.height() == 600


@pytest.mark.requirement("REQ-FILE-061")
def test_apply_window_geometry_normalizes_before_resizing_when_maximized(
    window: MainWindow,
) -> None:
    """#107: restoring a maximized config while already maximized must not
    leave the window merely un-maximized (resize()/move() on an
    already-maximized window can drop that state at the OS level, making a
    later showMaximized() call a no-op unless normalized first)."""
    with patch.object(window, "isMaximized", return_value=True), \
         patch.object(window, "showNormal") as mock_show_normal, \
         patch.object(window, "showMaximized") as mock_show_maximized:
        window._apply_window_geometry(
            {"x": 10, "y": 20, "width": 900, "height": 600, "maximized": True}
        )
    mock_show_normal.assert_called_once()
    mock_show_maximized.assert_called_once()


@pytest.mark.requirement("REQ-FILE-061")
def test_apply_window_geometry_does_not_normalize_when_not_maximized(
    window: MainWindow,
) -> None:
    with patch.object(window, "isMaximized", return_value=False), \
         patch.object(window, "showNormal") as mock_show_normal:
        window._apply_window_geometry({"width": 900, "height": 600, "maximized": False})
    mock_show_normal.assert_not_called()


@pytest.mark.requirement("REQ-FILE-067")
def test_apply_window_geometry_none_is_noop(window: MainWindow) -> None:
    window.resize(1280, 800)
    window._apply_window_geometry(None)
    assert window.width() == 1280
    assert window.height() == 800


@pytest.mark.requirement("REQ-FILE-061")
def test_capture_splitter_sizes_includes_all_splitters_and_left_panel(window: MainWindow) -> None:
    sizes = window._capture_splitter_sizes()
    assert set(sizes) == {"left", "content", "outer", "left_panel", "info_drawer"}
    assert sizes["left_panel"] == {"pinned": True, "width": window._left_dock.width_px}


@pytest.mark.requirement("REQ-PLOT-225")
def test_capture_splitter_sizes_includes_info_drawer(window: MainWindow) -> None:
    sizes = window._capture_splitter_sizes()
    assert sizes["info_drawer"] == {
        "pinned": True,
        "width": window._info_dock.width_px,
        "inner": window.signal_info_box.splitter_sizes(),
    }


@pytest.mark.requirement("REQ-PLOT-225")
def test_apply_splitter_sizes_restores_info_drawer_width_and_pinned_state(
    window: MainWindow,
) -> None:
    window._apply_splitter_sizes({"info_drawer": {"pinned": False, "width": 300}})
    assert window._info_dock.width_px == 300
    assert not window._info_dock.pinned


@pytest.mark.requirement("REQ-PLOT-227")
def test_apply_splitter_sizes_restores_info_drawer_inner_split(window: MainWindow) -> None:
    with patch.object(window.signal_info_box, "set_splitter_sizes") as mock_set_sizes:
        window._apply_splitter_sizes({"info_drawer": {"inner": [40, 150]}})
    mock_set_sizes.assert_called_once_with([40, 150])


@pytest.mark.requirement("REQ-FILE-061")
def test_apply_splitter_sizes_sets_each_splitter(window: MainWindow) -> None:
    with patch.object(window._content_splitter, "setSizes") as mock_content, \
         patch.object(window._outer_splitter, "setSizes") as mock_outer:
        window._apply_splitter_sizes({"content": [500, 400], "outer": [300, 600]})
    mock_content.assert_called_once_with([500, 400])
    mock_outer.assert_called_once_with([300, 600])


@pytest.mark.requirement("REQ-FILE-067")
def test_apply_splitter_sizes_ignores_malformed_values(window: MainWindow) -> None:
    with patch.object(window._content_splitter, "setSizes") as mock_content:
        window._apply_splitter_sizes({"content": "not-a-list"})
    mock_content.assert_not_called()


@pytest.mark.requirement("REQ-FILE-067")
def test_apply_splitter_sizes_none_is_noop(window: MainWindow) -> None:
    with patch.object(window._content_splitter, "setSizes") as mock_content:
        window._apply_splitter_sizes(None)
    mock_content.assert_not_called()


@pytest.mark.requirement("REQ-FILE-061")
def test_save_config_to_attaches_window_and_splitter_state(
    window: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    window._controller = mock_controller
    window._settings = MagicMock()
    window._settings.config_path_mode = "absolute"
    mock_controller.capture_config.return_value = _minimal_config()
    mock_controller.active_signals = []  # prevent teardown from triggering the real "Save Workspace?" dialog

    with patch("mdf_viewer.config_manager.ConfigManager.save") as mock_save:
        window._save_config_to(tmp_path / "session.mvc")

    saved_config = mock_save.call_args[0][0]
    assert saved_config.window_geometry is not None
    assert saved_config.window_geometry["width"] == window.width()
    assert saved_config.splitter_sizes is not None
    assert "left" in saved_config.splitter_sizes


@pytest.mark.requirement("REQ-FILE-061")
def test_load_config_applies_saved_window_geometry(
    window: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    mvc = tmp_path / "session.mvc"
    mvc.touch()
    window._controller = mock_controller
    window._settings = MagicMock()
    mock_controller.active_signals = []  # prevent teardown from triggering the real "Save Workspace?" dialog
    config = _minimal_config(
        window_geometry={"x": 5, "y": 5, "width": 1000, "height": 700, "maximized": False},
    )

    with patch("mdf_viewer.config_manager.ConfigManager.load", return_value=config), \
         patch("mdf_viewer.config_manager.ConfigManager.resolve_measurement_path", return_value=None), \
         patch("PyQt6.QtWidgets.QFileDialog.getOpenFileName", return_value=("", "")):
        window._load_config(mvc)

    assert window.width() == 1000
    assert window.height() == 700
