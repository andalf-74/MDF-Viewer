"""Tests for MainWindow.

Covers widget composition, menu/toolbar structure, and controller wiring.
File-dialog and message-box calls are patched so no real filesystem or
display interaction is needed.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pytestqt.qtbot import QtBot

from PyQt6.QtWidgets import QDialog, QMessageBox, QWidget

from mdf_viewer.controller.app_controller import LoadResult
from mdf_viewer.errors import MdfLoadError
from mdf_viewer.plugin_api.loader import PluginLoadResult
from mdf_viewer.plugin_api.registry import PluginRegistry, TabTypeRegistration
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
    controller = MagicMock()
    # A real, empty PluginRegistry (#73) — a bare MagicMock's auto-iteration
    # (__iter__ defaults to an empty iterator, __bool__ defaults to True)
    # would silently make iterating registry.menu_actions/dock_widgets in
    # _rebuild_plugins_menu behave unpredictably.
    controller.plugin_registry = PluginRegistry()
    return controller


def _plot_index(window: MainWindow, plot_area) -> int | None:
    """Test double for AppController.tab_index_for_plot()'s identity search
    (#148) — mock_controller has no real _workspaces to search, so this
    mirrors it against window's own plot pages instead. For every existing
    (pre-#148) test, every real tab is a plot tab, so this returns the same
    value the raw tab-bar index already would — existing assertions like
    `remove_tab.assert_called_once_with(0)` keep passing unchanged."""
    placeholder_index = window._placeholder_index()
    plot_pages = [
        window._tab_widget.widget(i)
        for i in range(window._tab_widget.count())
        if i != placeholder_index and window._is_plot_page(window._tab_widget.widget(i))
    ]
    for idx, page in enumerate(plot_pages):
        if page.plot_area is plot_area:
            return idx
    return None


@pytest.fixture()
def wired(window: MainWindow, mock_controller: MagicMock) -> MainWindow:
    window.set_controller(mock_controller)
    mock_controller.tab_index_for_plot.side_effect = lambda plot_area: _plot_index(window, plot_area)
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
# Pluggable Tab Types (#148)
# ---------------------------------------------------------------------------

def _make_registration(type_id: str = "fixture", display_name: str = "Fixture Tab") -> TabTypeRegistration:
    return TabTypeRegistration(
        plugin_name="test_plugin", type_id=type_id, display_name=display_name,
        view_factory=lambda: QWidget(),
    )


@pytest.mark.requirement("REQ-PLUGIN-330")
def test_new_tab_requested_behaves_like_new_tab_with_no_registered_types(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    wired._on_new_tab_requested()
    assert wired._real_tab_count() == 2
    assert wired._is_plot_page(wired._tab_widget.widget(1))


def test_new_tab_requested_offers_a_choice_once_a_type_is_registered(
    wired: MainWindow,
) -> None:
    wired._tab_types = [_make_registration()]
    patch_add, patch_exec = _select_menu_action_by_text("Fixture Tab")
    with patch_add, patch_exec:
        wired._on_new_tab_requested()
    assert wired._real_tab_count() == 2
    new_page = wired._tab_widget.widget(1)
    assert not wired._is_plot_page(new_page)
    assert wired._tab_widget.tabText(1) == "Fixture Tab"


@pytest.mark.requirement("REQ-PLUGIN-331")
def test_new_tab_requested_plot_choice_creates_a_plot_tab(wired: MainWindow) -> None:
    wired._tab_types = [_make_registration()]
    patch_add, patch_exec = _select_menu_action_by_text("Plot")
    with patch_add, patch_exec:
        wired._on_new_tab_requested()
    assert wired._is_plot_page(wired._tab_widget.widget(1))


def test_new_tab_requested_dismissed_menu_creates_nothing(wired: MainWindow) -> None:
    wired._tab_types = [_make_registration()]
    with patch("PyQt6.QtWidgets.QMenu.exec", return_value=None):
        wired._on_new_tab_requested()
    assert wired._real_tab_count() == 1


@pytest.mark.requirement("REQ-PLUGIN-332")
def test_create_non_plot_tab_failed_factory_creates_nothing(wired: MainWindow) -> None:
    registration = TabTypeRegistration(
        plugin_name="p", type_id="broken", display_name="Broken",
        view_factory=lambda: (_ for _ in ()).throw(ValueError("boom")),
    )
    index = wired._create_non_plot_tab(registration)
    assert index == -1
    assert wired._real_tab_count() == 1


def test_non_plot_tab_is_renamable(wired: MainWindow) -> None:
    registration = _make_registration()
    wired._create_non_plot_tab(registration)
    with patch("PyQt6.QtWidgets.QInputDialog.getText", return_value=("Renamed", True)):
        wired._on_tab_bar_double_clicked(1)
    assert wired._tab_widget.tabText(1) == "Renamed"


@pytest.mark.requirement("REQ-PLUGIN-341")
def test_switching_to_non_plot_tab_does_not_call_switch_tab(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    wired._create_non_plot_tab(_make_registration())
    mock_controller.switch_tab.reset_mock()
    wired._tab_widget.setCurrentIndex(1)
    mock_controller.switch_tab.assert_not_called()


def test_switching_back_to_plot_tab_after_non_plot_uses_translated_index(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    wired._on_new_tab()  # Tab 2 (plot), index 1
    wired._create_non_plot_tab(_make_registration())  # index 2
    mock_controller.switch_tab.reset_mock()
    wired._tab_widget.setCurrentIndex(0)  # Tab 1, workspace index 0
    mock_controller.switch_tab.assert_called_with(0)
    wired._tab_widget.setCurrentIndex(1)  # Tab 2 (plot), workspace index 1
    mock_controller.switch_tab.assert_called_with(1)


@pytest.mark.requirement("REQ-PLUGIN-342")
def test_closing_non_plot_tab_shows_no_confirmation(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    wired._create_non_plot_tab(_make_registration())
    with patch("PyQt6.QtWidgets.QMessageBox.question") as mock_question:
        wired._on_tab_close_requested(1)
    mock_question.assert_not_called()
    assert wired._real_tab_count() == 1


def test_closing_non_plot_tab_never_calls_remove_tab(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    wired._create_non_plot_tab(_make_registration())
    mock_controller.remove_tab.reset_mock()
    wired._on_tab_close_requested(1)
    mock_controller.remove_tab.assert_not_called()


def test_closing_non_plot_tab_removes_it_from_tab_type_by_page(wired: MainWindow) -> None:
    wired._create_non_plot_tab(_make_registration())
    page = wired._tab_widget.widget(1)
    wired._on_tab_close_requested(1)
    assert page not in wired._tab_type_by_page


def test_closing_last_plot_tab_still_parks_with_a_non_plot_tab_open(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    """#130 regression guard: closing the only plot tab must park it even
    though a non-plot tab keeps _real_tab_count() above 1 (#148)."""
    mock_controller.tab_has_signals.return_value = False
    wired._create_non_plot_tab(_make_registration())  # index 1
    plot_page = wired._tab_widget.widget(0)
    with patch.object(plot_page, "deleteLater") as mock_delete_later:
        wired._on_tab_close_requested(0)
    mock_delete_later.assert_not_called()
    assert wired._parked_page is plot_page


def test_empty_placeholder_shown_only_when_all_real_tabs_gone(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    mock_controller.tab_has_signals.return_value = False
    wired._create_non_plot_tab(_make_registration())  # index 1
    wired._on_tab_close_requested(0)  # close the only plot tab
    assert wired._content_stack.currentWidget() is wired._tab_widget
    wired._on_tab_close_requested(0)  # close the remaining non-plot tab
    assert wired._content_stack.currentWidget() is wired._empty_tabs_placeholder


def test_context_menu_disables_duplicate_and_copy_for_non_plot_tab(
    wired: MainWindow,
) -> None:
    wired._create_non_plot_tab(_make_registration())
    from PyQt6.QtWidgets import QMenu
    captured: dict[str, object] = {}
    orig_add_action = QMenu.addAction

    def _tracking_add_action(self, text):
        action = orig_add_action(self, text)
        captured[text] = action
        return action

    tab_bar = wired._tab_widget.tabBar()
    pos = tab_bar.tabRect(1).center()
    with patch.object(QMenu, "addAction", _tracking_add_action), \
         patch.object(QMenu, "exec", return_value=None):
        wired._on_tab_context_menu(pos)
    assert captured["Duplicate Tab"].isEnabled() is False
    assert captured["Copy Signals to new Tab"].isEnabled() is False


def test_copy_signals_to_new_tab_translates_indices_around_a_non_plot_tab(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    """A non-plot tab between two plot tabs must not shift the workspace
    indices passed to the controller (#148)."""
    mock_controller.tab_has_signals.return_value = True
    wired._create_non_plot_tab(_make_registration())  # tab-bar index 1
    wired._on_new_tab()  # Tab 2 (plot), tab-bar index 2, workspace index 1

    wired._on_copy_signals_to_new_tab(0)  # source is Tab 1, workspace index 0

    mock_controller.copy_signals_to_new_tab.assert_called_once_with(0, 1)


def test_duplicate_tab_translates_indices_around_a_non_plot_tab(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    mock_controller.tab_has_signals.return_value = True
    wired._create_non_plot_tab(_make_registration())  # tab-bar index 1
    wired._on_new_tab()  # Tab 2 (plot), tab-bar index 2, workspace index 1

    wired._on_duplicate_tab(0)  # source is Tab 1, workspace index 0

    mock_controller.duplicate_tab_signals.assert_called_once_with(0, 1)


def test_all_active_signals_tables_skips_non_plot_tabs(wired: MainWindow) -> None:
    wired._create_non_plot_tab(_make_registration())
    tables = wired._all_active_signals_tables()
    assert len(tables) == 1
    assert tables[0] is wired.active_signals_table


def test_tab_page_splitter_sizes_skips_non_plot_tabs(wired: MainWindow) -> None:
    wired._create_non_plot_tab(_make_registration())
    sizes = wired._tab_page_splitter_sizes()
    assert len(sizes) == 1


def test_plot_tab_names_excludes_non_plot_tabs(wired: MainWindow) -> None:
    wired._create_non_plot_tab(_make_registration())
    wired._on_new_tab()
    assert wired._plot_tab_names() == ["Tab 1", "Tab 2"]


def test_tab_names_includes_non_plot_tabs(wired: MainWindow) -> None:
    wired._create_non_plot_tab(_make_registration())
    assert wired._tab_names() == ["Tab 1", "Fixture Tab"]


def test_drag_reorder_skips_non_plot_tabs(wired: MainWindow, mock_controller: MagicMock) -> None:
    wired._create_non_plot_tab(_make_registration())
    wired._on_new_tab()  # Tab 2 (plot)
    mock_controller.reorder_tabs.reset_mock()

    wired._on_tab_bar_tab_moved(0, 0)  # placeholder already last; triggers resync

    called_plot_areas = mock_controller.reorder_tabs.call_args[0][0]
    assert len(called_plot_areas) == 2  # only the 2 plot pages, non-plot excluded


def test_cycle_tab_includes_non_plot_tabs_without_crashing(wired: MainWindow) -> None:
    wired._create_non_plot_tab(_make_registration())
    wired._on_new_tab()  # Tab 2 (plot)
    wired._tab_widget.setCurrentIndex(0)

    wired._cycle_tab(1)  # -> non-plot tab
    assert wired._tab_widget.currentIndex() == 1
    wired._cycle_tab(1)  # -> Tab 2
    assert wired._tab_widget.currentIndex() == 2
    wired._cycle_tab(1)  # wraps back to Tab 1
    assert wired._tab_widget.currentIndex() == 0


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


@pytest.mark.requirement("REQ-PLOT-255")
def test_tab_bar_enforces_minimum_width_for_short_names(window: MainWindow) -> None:
    from mdf_viewer.view.main_window import _MIN_REAL_TAB_WIDTH
    window._tab_widget.setTabText(0, "DTI")
    tab_bar = window._tab_widget.tabBar()
    assert tab_bar.tabSizeHint(0).width() >= _MIN_REAL_TAB_WIDTH


@pytest.mark.requirement("REQ-PLOT-255")
def test_tab_bar_placeholder_tab_exempt_from_minimum_width(window: MainWindow) -> None:
    from mdf_viewer.view.main_window import _MIN_REAL_TAB_WIDTH
    tab_bar = window._tab_widget.tabBar()
    placeholder_index = window._placeholder_index()
    assert tab_bar.tabSizeHint(placeholder_index).width() < _MIN_REAL_TAB_WIDTH


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
# Theme-aware icon selection
# ---------------------------------------------------------------------------

def test_icon_color_dark_scheme_uses_light_stroke(monkeypatch) -> None:
    from PyQt6.QtCore import Qt
    from mdf_viewer.view import main_window

    style_hints = MagicMock()
    style_hints.colorScheme.return_value = Qt.ColorScheme.Dark
    monkeypatch.setattr(
        main_window.QApplication, "styleHints", lambda: style_hints
    )
    assert main_window._icon_color() == "#f0f0ec"


@pytest.mark.parametrize("scheme_name", ["Light", "Unknown"])
def test_icon_color_light_or_unknown_scheme_uses_dark_stroke(
    monkeypatch, scheme_name: str
) -> None:
    from PyQt6.QtCore import Qt
    from mdf_viewer.view import main_window

    style_hints = MagicMock()
    style_hints.colorScheme.return_value = getattr(Qt.ColorScheme, scheme_name)
    monkeypatch.setattr(
        main_window.QApplication, "styleHints", lambda: style_hints
    )
    assert main_window._icon_color() == "#2a2a28"


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
    m1, m2 = MagicMock(label="M1", owner_plugin=None), MagicMock(label="M2", owner_plugin=None)
    mock_controller.measurements = [m1, m2]
    wired._file_menu.aboutToShow.emit()
    assert wired._replace_measurement_menu.isEnabled() is True
    actions = wired._replace_measurement_menu.actions()
    assert [a.text() for a in actions] == ["M1", "M2"]


@pytest.mark.requirement("REQ-FILE-100")
def test_replace_measurement_menu_rebuilt_on_each_show(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    mock_controller.measurements = [MagicMock(label="M1", owner_plugin=None)]
    wired._file_menu.aboutToShow.emit()
    mock_controller.measurements = [
        MagicMock(label="M1", owner_plugin=None), MagicMock(label="M2", owner_plugin=None),
    ]
    wired._file_menu.aboutToShow.emit()
    assert len(wired._replace_measurement_menu.actions()) == 2


@pytest.mark.requirement("REQ-FILE-100")
def test_replace_measurement_menu_entry_invokes_replace_flow(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    m1 = MagicMock(label="M1", owner_plugin=None)
    mock_controller.measurements = [m1]
    wired._file_menu.aboutToShow.emit()
    with patch.object(wired, "_replace_single_measurement") as mock_replace:
        wired._replace_measurement_menu.actions()[0].trigger()
    mock_replace.assert_called_once_with(m1)


@pytest.mark.requirement("REQ-VMEAS-440")
def test_replace_measurement_menu_excludes_virtual_measurements(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    real = MagicMock(label="M1", owner_plugin=None)
    virtual = MagicMock(label="Virtual", owner_plugin="p")
    mock_controller.measurements = [real, virtual]
    wired._file_menu.aboutToShow.emit()
    actions = wired._replace_measurement_menu.actions()
    assert [a.text() for a in actions] == ["M1"]


@pytest.mark.requirement("REQ-VMEAS-440")
def test_replace_measurement_menu_disabled_when_only_virtual_measurements(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    mock_controller.measurements = [MagicMock(label="Virtual", owner_plugin="p")]
    wired._file_menu.aboutToShow.emit()
    assert wired._replace_measurement_menu.isEnabled() is False


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
# Apply Config (#105, REQ-FILE-110..119)
# ---------------------------------------------------------------------------

def _measurement_config(label: str, path: str = ""):
    from mdf_viewer.model.viewer_config import MeasurementConfig
    return MeasurementConfig(path=path, label=label, offset_s=0.0)


def test_apply_config_action_disabled_without_controller(window: MainWindow) -> None:
    window._file_menu.aboutToShow.emit()
    assert window._apply_config_action.isEnabled() is False


def test_apply_config_action_disabled_with_no_measurements(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    mock_controller.measurements = []
    wired._file_menu.aboutToShow.emit()
    assert wired._apply_config_action.isEnabled() is False


def test_apply_config_action_enabled_with_measurements(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    mock_controller.measurements = [MagicMock(label="M1")]
    wired._file_menu.aboutToShow.emit()
    assert wired._apply_config_action.isEnabled() is True


@pytest.mark.requirement("REQ-FILE-110")
def test_apply_config_cancel_file_dialog_does_nothing(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    wired._settings = MagicMock()
    mock_controller.active_signals = []  # prevent teardown from triggering the real dialog
    with patch(
        "mdf_viewer.view.main_window.QFileDialog.getOpenFileName", return_value=("", "")
    ):
        wired._on_apply_config()
    mock_controller.restore_config.assert_not_called()


@pytest.mark.requirement("REQ-FILE-110")
def test_apply_config_load_error_shows_message_box(
    wired: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    from mdf_viewer.errors import ConfigLoadError
    p = tmp_path / "bad.mvc"
    wired._settings = MagicMock()
    mock_controller.active_signals = []  # prevent teardown from triggering the real dialog
    with patch(
        "mdf_viewer.view.main_window.QFileDialog.getOpenFileName",
        return_value=(str(p), ""),
    ), patch(
        "mdf_viewer.config_manager.ConfigManager.load",
        side_effect=ConfigLoadError("bad"),
    ), patch("mdf_viewer.view.main_window.QMessageBox.critical") as mock_crit:
        wired._on_apply_config()
    mock_crit.assert_called_once()
    mock_controller.restore_config.assert_not_called()


@pytest.mark.requirement("REQ-FILE-114")
def test_apply_config_mapping_cancel_leaves_window_geometry_unchanged(
    wired: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    """Regression: a cancelled mapping dialog used to still resize the
    window, because geometry/splitter sizes were applied unconditionally
    before the (cancellable) mapping dialog rather than after it succeeds."""
    p = tmp_path / "session.mvc"
    wired._settings = MagicMock()
    mock_controller.active_signals = []  # prevent teardown from triggering the real dialog
    mock_controller.measurements = []
    original_width = wired.width()
    config = _minimal_config(
        measurements=(_measurement_config("M1"),),
        window_geometry={"x": 5, "y": 5, "width": original_width + 500, "height": 700, "maximized": False},
    )
    with patch(
        "mdf_viewer.view.main_window.QFileDialog.getOpenFileName",
        return_value=(str(p), ""),
    ), patch(
        "mdf_viewer.config_manager.ConfigManager.load", return_value=config,
    ), patch(
        "mdf_viewer.view.measurement_mapping_dialog.MeasurementMappingDialog.exec",
        return_value=0,
    ):
        wired._on_apply_config()
    assert wired.width() == original_width


@pytest.mark.requirement("REQ-FILE-114")
def test_apply_config_mapping_cancel_aborts(
    wired: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    p = tmp_path / "session.mvc"
    wired._settings = MagicMock()
    mock_controller.active_signals = []  # prevent teardown from triggering the real dialog
    mock_controller.measurements = []
    config = _minimal_config(measurements=(_measurement_config("M1"),))
    with patch(
        "mdf_viewer.view.main_window.QFileDialog.getOpenFileName",
        return_value=(str(p), ""),
    ), patch(
        "mdf_viewer.config_manager.ConfigManager.load", return_value=config,
    ), patch(
        "mdf_viewer.view.measurement_mapping_dialog.MeasurementMappingDialog.exec",
        return_value=0,
    ):
        wired._on_apply_config()
    mock_controller.restore_config.assert_not_called()


@pytest.mark.requirement("REQ-FILE-112")
def test_apply_config_skips_mapping_dialog_when_no_measurement_slots(
    wired: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    p = tmp_path / "session.mvc"
    wired._settings = MagicMock()
    mock_controller.active_signals = []  # prevent teardown from triggering the real dialog
    mock_controller.measurements = []
    config = _minimal_config()  # measurements=() by default
    with patch(
        "mdf_viewer.view.main_window.QFileDialog.getOpenFileName",
        return_value=(str(p), ""),
    ), patch(
        "mdf_viewer.config_manager.ConfigManager.load", return_value=config,
    ), patch(
        "mdf_viewer.view.measurement_mapping_dialog.MeasurementMappingDialog.__init__",
    ) as mock_dlg_init, patch.object(
        wired._session, "reset_to_single_tab"
    ), patch.object(
        wired._session, "build_tab_skeletons", return_value=[],
    ), patch.object(
        wired, "_on_save_config_as"
    ):
        wired._on_apply_config()
    mock_dlg_init.assert_not_called()
    mock_controller.restore_config.assert_called_once_with(config, {}, [], [])


@pytest.mark.requirement("REQ-FILE-117")
def test_apply_config_success_calls_restore_pipeline(
    wired: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    p = tmp_path / "session.mvc"
    wired._settings = MagicMock()
    mock_controller.active_signals = []  # prevent teardown from triggering the real dialog
    mock_controller.measurements = []
    config = _minimal_config(measurements=(_measurement_config("M1"),))
    with patch(
        "mdf_viewer.view.main_window.QFileDialog.getOpenFileName",
        return_value=(str(p), ""),
    ), patch(
        "mdf_viewer.config_manager.ConfigManager.load", return_value=config,
    ), patch(
        "mdf_viewer.view.measurement_mapping_dialog.MeasurementMappingDialog.exec",
        return_value=1,
    ), patch(
        "mdf_viewer.view.measurement_mapping_dialog.MeasurementMappingDialog.mapping",
        return_value=[None],
    ), patch.object(
        wired._session, "reset_to_single_tab"
    ) as mock_reset, patch.object(
        wired._session, "build_tab_skeletons"
    ) as mock_skeleton, patch.object(
        wired, "_on_save_config_as"
    ) as mock_save_as:
        wired._on_apply_config()
    mock_reset.assert_called_once()
    mock_skeleton.assert_called_once_with(list(config.tabs))
    mock_controller.restore_config.assert_called_once()
    mock_save_as.assert_called_once()


@pytest.mark.requirement("REQ-FILE-119")
def test_apply_config_does_not_set_current_config_path(
    wired: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    p = tmp_path / "session.mvc"
    wired._settings = MagicMock()
    wired._settings.plot_background_color = (0, 0, 0)
    mock_controller.active_signals = []  # prevent teardown from triggering the real dialog
    mock_controller.measurements = []
    mock_controller.current_config_path = "sentinel"
    config = _minimal_config(measurements=(_measurement_config("M1"),))
    with patch(
        "mdf_viewer.view.main_window.QFileDialog.getOpenFileName",
        return_value=(str(p), ""),
    ), patch(
        "mdf_viewer.config_manager.ConfigManager.load", return_value=config,
    ), patch(
        "mdf_viewer.view.measurement_mapping_dialog.MeasurementMappingDialog.exec",
        return_value=1,
    ), patch(
        "mdf_viewer.view.measurement_mapping_dialog.MeasurementMappingDialog.mapping",
        return_value=[None],
    ), patch.object(
        wired, "_reset_to_single_tab"
    ), patch.object(
        wired, "_build_tab_skeletons"
    ), patch.object(
        wired, "_on_save_config_as"
    ):
        wired._on_apply_config()
    assert mock_controller.current_config_path == "sentinel"


@pytest.mark.requirement("REQ-FILE-116")
def test_apply_config_never_touches_measurement_pool_methods(
    wired: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    p = tmp_path / "session.mvc"
    wired._settings = MagicMock()
    wired._settings.plot_background_color = (0, 0, 0)
    mock_controller.active_signals = []  # prevent teardown from triggering the real dialog
    mock_controller.measurements = []
    config = _minimal_config(measurements=(_measurement_config("M1"),))
    with patch(
        "mdf_viewer.view.main_window.QFileDialog.getOpenFileName",
        return_value=(str(p), ""),
    ), patch(
        "mdf_viewer.config_manager.ConfigManager.load", return_value=config,
    ), patch(
        "mdf_viewer.view.measurement_mapping_dialog.MeasurementMappingDialog.exec",
        return_value=1,
    ), patch(
        "mdf_viewer.view.measurement_mapping_dialog.MeasurementMappingDialog.mapping",
        return_value=[None],
    ), patch.object(
        wired, "_reset_to_single_tab"
    ), patch.object(
        wired, "_build_tab_skeletons"
    ), patch.object(
        wired, "_on_save_config_as"
    ):
        wired._on_apply_config()
    mock_controller.replace_measurements.assert_not_called()
    mock_controller.add_measurements.assert_not_called()
    mock_controller.restore_measurements.assert_not_called()
    mock_controller.close_measurement.assert_not_called()
    mock_controller.set_primary_measurement.assert_not_called()
    mock_controller.toggle_measurements_synchronized.assert_not_called()


# ---------------------------------------------------------------------------
# Status bar
# ---------------------------------------------------------------------------

def test_status_bar_present(window: MainWindow) -> None:
    assert window.statusBar() is not None


def test_show_status_displays_message(window: MainWindow) -> None:
    window.show_status("hello world", timeout_ms=0)
    assert window.statusBar().currentMessage() == "hello world"


@pytest.mark.requirement("REQ-STATUS-010")
def test_show_status_records_into_history(window: MainWindow) -> None:
    window.show_status("hello world", timeout_ms=0)
    assert [e.text for e in window._status_history.entries] == ["hello world"]


@pytest.mark.requirement("REQ-STATUS-010")
def test_show_status_records_every_call_regardless_of_log(window: MainWindow) -> None:
    window.show_status("logged", timeout_ms=0)
    window.show_status("not logged", timeout_ms=0, log=False)
    assert [e.text for e in window._status_history.entries] == ["logged", "not logged"]


@pytest.mark.requirement("REQ-STATUS-014")
def test_show_status_logs_at_info_by_default(window: MainWindow, caplog) -> None:
    with caplog.at_level("INFO", logger="mdf_viewer.view.main_window"):
        window.show_status("workspace saved", timeout_ms=0)
    assert "workspace saved" in caplog.text


@pytest.mark.requirement("REQ-STATUS-014")
def test_show_status_log_false_skips_the_log(window: MainWindow, caplog) -> None:
    with caplog.at_level("INFO", logger="mdf_viewer.view.main_window"):
        window.show_status("routine guard message", timeout_ms=0, log=False)
    assert "routine guard message" not in caplog.text


@pytest.mark.requirement("REQ-STATUS-015")
def test_show_status_log_false_still_recorded_in_history(window: MainWindow) -> None:
    window.show_status("routine guard message", timeout_ms=0, log=False)
    assert [e.text for e in window._status_history.entries] == ["routine guard message"]


@pytest.mark.requirement("REQ-STATUS-020")
def test_status_history_button_present(window: MainWindow) -> None:
    from PyQt6.QtWidgets import QPushButton
    button = window.statusBar().findChild(QPushButton, "status_history_button")
    assert button is not None


@pytest.mark.requirement("REQ-STATUS-020")
def test_status_history_button_click_opens_dialog(window: MainWindow) -> None:
    assert window._status_history_dialog is None
    window._on_show_status_history()
    assert window._status_history_dialog is not None
    assert window._status_history_dialog.isVisible()


@pytest.mark.requirement("REQ-STATUS-022")
def test_status_history_button_reclick_reuses_same_dialog(window: MainWindow) -> None:
    window._on_show_status_history()
    first = window._status_history_dialog
    window._on_show_status_history()
    assert window._status_history_dialog is first


@pytest.mark.requirement("REQ-STATUS-022")
def test_status_history_reopen_after_close_reuses_same_instance(window: MainWindow) -> None:
    window._on_show_status_history()
    first = window._status_history_dialog
    first.close()
    assert not first.isVisible()
    window._on_show_status_history()
    assert window._status_history_dialog is first
    assert first.isVisible()


@pytest.mark.requirement("REQ-STATUS-023")
def test_show_status_appends_live_to_open_dialog(window: MainWindow) -> None:
    window._on_show_status_history()
    window.show_status("a new message", timeout_ms=0)
    assert "a new message" in window._status_history_dialog._text.toPlainText()


@pytest.mark.requirement("REQ-STATUS-023")
def test_show_status_appends_even_while_dialog_hidden(window: MainWindow) -> None:
    window._on_show_status_history()
    window._status_history_dialog.close()
    window.show_status("recorded while hidden", timeout_ms=0)
    window._on_show_status_history()
    assert "recorded while hidden" in window._status_history_dialog._text.toPlainText()


def test_show_status_with_no_dialog_built_does_not_error(window: MainWindow) -> None:
    assert window._status_history_dialog is None
    window.show_status("no dialog yet", timeout_ms=0)  # should not raise


def test_close_event_closes_open_status_history_dialog(window: MainWindow) -> None:
    window._on_show_status_history()
    dialog = window._status_history_dialog
    assert dialog.isVisible()
    window.close()
    assert not dialog.isVisible()


def test_close_event_with_no_status_history_dialog_does_not_error(window: MainWindow) -> None:
    assert window._status_history_dialog is None
    window.close()  # should not raise


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
# Import/Export Labels (#143)
# ---------------------------------------------------------------------------

def test_import_labels_action_exists(window: MainWindow) -> None:
    assert window._import_labels_action is not None


def test_export_labels_action_exists(window: MainWindow) -> None:
    assert window._export_labels_action is not None


def test_import_export_labels_disabled_with_no_controller(window: MainWindow) -> None:
    window._update_import_export_labels_enabled()
    assert not window._import_labels_action.isEnabled()
    assert not window._export_labels_action.isEnabled()


@pytest.mark.requirement("REQ-LABEL-072")
def test_import_labels_enabled_when_measurement_loaded(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    mock_controller.measurement_count = 1
    mock_controller.active_signals = []
    wired._update_import_export_labels_enabled()
    assert wired._import_labels_action.isEnabled()


@pytest.mark.requirement("REQ-LABEL-072")
def test_import_labels_disabled_with_no_measurement(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    mock_controller.measurement_count = 0
    mock_controller.active_signals = []
    wired._update_import_export_labels_enabled()
    assert not wired._import_labels_action.isEnabled()


@pytest.mark.requirement("REQ-LABEL-073")
def test_export_labels_enabled_when_active_signals_exist(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    mock_controller.measurement_count = 1
    mock_controller.active_signals = [MagicMock()]
    wired._update_import_export_labels_enabled()
    assert wired._export_labels_action.isEnabled()


@pytest.mark.requirement("REQ-LABEL-073")
def test_export_labels_disabled_with_no_active_signals(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    mock_controller.measurement_count = 1
    mock_controller.active_signals = []
    wired._update_import_export_labels_enabled()
    assert not wired._export_labels_action.isEnabled()


def test_import_labels_cancelled_dialog_does_nothing(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    mock_controller.active_signals = []
    with patch(
        "mdf_viewer.view.main_window.QFileDialog.getOpenFileName", return_value=("", "")
    ):
        wired._on_import_labels()
    mock_controller.import_label_list.assert_not_called()


def test_import_labels_reads_file_and_calls_controller(
    wired: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    from mdf_viewer.controller.app_controller import LabelImportResult

    mock_controller.active_signals = []
    lab_path = tmp_path / "labels.lab"
    lab_path.write_bytes(b"[Measurement]\n[Group]\nSpeed\n")
    mock_controller.import_label_list.return_value = LabelImportResult()
    with patch(
        "mdf_viewer.view.main_window.QFileDialog.getOpenFileName",
        return_value=(str(lab_path), ""),
    ):
        wired._on_import_labels()
    mock_controller.import_label_list.assert_called_once_with(lab_path.read_bytes())


@pytest.mark.requirement("REQ-LABEL-051")
def test_import_labels_shows_no_dialog_on_clean_import(
    wired: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    from mdf_viewer.controller.app_controller import LabelImportResult

    mock_controller.active_signals = []
    lab_path = tmp_path / "labels.lab"
    lab_path.write_bytes(b"[Measurement]\n")
    mock_controller.import_label_list.return_value = LabelImportResult()
    with patch(
        "mdf_viewer.view.main_window.QFileDialog.getOpenFileName",
        return_value=(str(lab_path), ""),
    ), patch(
        "mdf_viewer.view.main_window.LabelImportResultDialog"
    ) as mock_dialog:
        wired._on_import_labels()
    mock_dialog.assert_not_called()


@pytest.mark.requirement("REQ-LABEL-050")
def test_import_labels_shows_dialog_when_something_to_report(
    wired: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    from mdf_viewer.controller.app_controller import LabelImportResult

    mock_controller.active_signals = []
    lab_path = tmp_path / "labels.lab"
    lab_path.write_bytes(b"[Measurement]\n")
    mock_controller.import_label_list.return_value = LabelImportResult(not_found=["Ghost"])
    with patch(
        "mdf_viewer.view.main_window.QFileDialog.getOpenFileName",
        return_value=(str(lab_path), ""),
    ), patch(
        "mdf_viewer.view.main_window.LabelImportResultDialog"
    ) as mock_dialog:
        wired._on_import_labels()
    mock_dialog.assert_called_once_with(["Ghost"], [], parent=wired)
    mock_dialog.return_value.exec.assert_called_once()


@pytest.mark.requirement("REQ-LABEL-010")
def test_import_labels_shows_error_on_parse_failure(
    wired: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    from mdf_viewer.errors import LabelListParseError

    mock_controller.active_signals = []
    lab_path = tmp_path / "labels.lab"
    lab_path.write_bytes(b"not a label list")
    mock_controller.import_label_list.side_effect = LabelListParseError("bad file")
    with patch(
        "mdf_viewer.view.main_window.QFileDialog.getOpenFileName",
        return_value=(str(lab_path), ""),
    ), patch(
        "mdf_viewer.view.main_window.QMessageBox.critical"
    ) as mock_critical:
        wired._on_import_labels()
    mock_critical.assert_called_once()


def test_import_labels_shows_error_when_file_cannot_be_read(
    wired: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    mock_controller.active_signals = []
    missing_path = tmp_path / "does_not_exist.lab"
    with patch(
        "mdf_viewer.view.main_window.QFileDialog.getOpenFileName",
        return_value=(str(missing_path), ""),
    ), patch(
        "mdf_viewer.view.main_window.QMessageBox.critical"
    ) as mock_critical:
        wired._on_import_labels()
    mock_critical.assert_called_once()
    mock_controller.import_label_list.assert_not_called()


def test_export_labels_cancelled_dialog_does_nothing(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    mock_controller.active_signals = []
    with patch(
        "mdf_viewer.view.main_window.QFileDialog.getSaveFileName", return_value=("", "")
    ):
        wired._on_export_labels()
    mock_controller.export_label_list.assert_not_called()


@pytest.mark.requirement("REQ-LABEL-060")
def test_export_labels_writes_controller_output(
    wired: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    mock_controller.active_signals = []
    mock_controller.export_label_list.return_value = b"[Measurement]\n\n[Group]\nSpeed\n"
    out_path = tmp_path / "out.lab"
    with patch(
        "mdf_viewer.view.main_window.QFileDialog.getSaveFileName",
        return_value=(str(out_path), ""),
    ):
        wired._on_export_labels()
    assert out_path.read_bytes() == b"[Measurement]\n\n[Group]\nSpeed\n"


def test_export_labels_shows_error_when_file_cannot_be_written(
    wired: MainWindow, mock_controller: MagicMock, tmp_path
) -> None:
    mock_controller.active_signals = []
    mock_controller.export_label_list.return_value = b"[Measurement]\n"
    bad_path = tmp_path / "no_such_dir" / "out.lab"  # parent dir doesn't exist
    with patch(
        "mdf_viewer.view.main_window.QFileDialog.getSaveFileName",
        return_value=(str(bad_path), ""),
    ), patch(
        "mdf_viewer.view.main_window.QMessageBox.critical"
    ) as mock_critical:
        wired._on_export_labels()
    mock_critical.assert_called_once()


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


# ---------------------------------------------------------------------------
# WorkspaceSessionController — Phase 0/2 for non-plot tabs (#148)
# ---------------------------------------------------------------------------

def _make_view_type_tab_config(name: str, view_type: str = "plot"):
    from mdf_viewer.model.viewer_config import StripeConfig, TabConfig
    return TabConfig(
        name=name, stripes=(StripeConfig(name="Stripe 1", size=1),), active_stripe_index=0,
        signals=(), x_range=(0.0, 1.0), y_ranges=(), merged_groups=(), synced_groups=(),
        cursor_mode="HIDDEN", cursor_positions=(0.0, 0.0), selected_signal=None,
        view_type=view_type,
    )


def test_reset_to_single_tab_removes_non_plot_tabs(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    wired._create_non_plot_tab(_make_registration("fixture", "Fixture"))
    wired._create_non_plot_tab(_make_registration("fixture2", "Fixture 2"))
    assert wired._real_tab_count() == 3

    wired._session.reset_to_single_tab()

    assert wired._real_tab_count() == 1
    assert wired._is_plot_page(wired._tab_widget.widget(0))
    assert wired._tab_type_by_page == {}


def test_reset_to_single_tab_keeps_first_plot_page_when_earlier_tabs_are_non_plot(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    """The survivor must be found by kind, not assumed at index 0 (#148 —
    the original code's invariant, broken the moment a non-plot tab can
    precede the one real plot tab)."""
    original_plot_page = wired._tab_widget.widget(0)
    # Reorder so a non-plot tab ends up first in the bar.
    fixture_index = wired._create_non_plot_tab(_make_registration())
    wired._tab_widget.tabBar().moveTab(fixture_index, 0)
    assert not wired._is_plot_page(wired._tab_widget.widget(0))

    wired._session.reset_to_single_tab()

    assert wired._real_tab_count() == 1
    assert wired._tab_widget.widget(0) is original_plot_page


@pytest.mark.requirement("REQ-PLUGIN-351")
def test_build_tab_skeletons_preserves_saved_tab_order_with_mixed_types(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    workspace_sentinel = object()
    mock_controller.all_workspaces.return_value = [workspace_sentinel]
    wired._tab_types = [_make_registration("fixture", "Fixture Tab")]
    tab_configs = [
        _make_view_type_tab_config("Fixture", "fixture"),
        _make_view_type_tab_config("Plot Tab", "plot"),
    ]

    resolved = wired._session.build_tab_skeletons(tab_configs)

    names = [wired._tab_widget.tabText(i) for i in range(wired._real_tab_count())]
    assert names == ["Fixture", "Plot Tab"]
    assert not wired._is_plot_page(wired._tab_widget.widget(0))
    assert wired._is_plot_page(wired._tab_widget.widget(1))
    assert resolved == [None, workspace_sentinel]


@pytest.mark.requirement("REQ-PLUGIN-352")
def test_build_tab_skeletons_skips_unregistered_type(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    workspace_sentinel = object()
    mock_controller.all_workspaces.return_value = [workspace_sentinel]
    wired._tab_types = []  # nothing registered
    tab_configs = [
        _make_view_type_tab_config("Unknown", "some_unregistered_type"),
        _make_view_type_tab_config("Plot Tab", "plot"),
    ]

    resolved = wired._session.build_tab_skeletons(tab_configs)

    assert wired._real_tab_count() == 1  # only the plot tab was created
    assert resolved == [None, workspace_sentinel]


def test_build_tab_skeletons_with_zero_plot_entries_keeps_survivor_as_implicit_extra(
    wired: MainWindow, mock_controller: MagicMock
) -> None:
    survivor_page = wired._tab_widget.widget(0)
    wired._tab_types = [_make_registration("fixture", "Fixture Tab")]
    tab_configs = [_make_view_type_tab_config("Fixture A", "fixture"), _make_view_type_tab_config("Fixture B", "fixture")]

    resolved = wired._session.build_tab_skeletons(tab_configs)

    assert resolved == [None, None]
    assert wired._real_tab_count() == 3  # implicit survivor + 2 restored
    assert wired._tab_widget.widget(0) is survivor_page
    assert [wired._tab_widget.tabText(i) for i in range(1, 3)] == ["Fixture A", "Fixture B"]


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


# ---------------------------------------------------------------------------
# Plugins menu (#73)
# ---------------------------------------------------------------------------

def test_plugins_menu_always_present_even_when_registry_is_empty(wired: MainWindow) -> None:
    """REQ-PLUGIN-391 (#150) — reverses the original "hidden when empty"
    rule (formerly REQ-PLUGIN-211): Rescan must be reachable even with
    zero plugins active, e.g. bootstrapping from an empty plugins/ folder."""
    assert wired._plugins_menu is not None
    assert any(a.text() == "&Plugins" for a in wired.menuBar().actions())
    assert wired._plugins_menu.actions()[0].text() == "Rescan Plugins"


def test_plugins_menu_appears_between_edit_and_help(window: MainWindow) -> None:
    from mdf_viewer.plugin_api.registry import MenuActionRegistration

    controller = MagicMock()
    registry = PluginRegistry()
    registry.add_menu_action(MenuActionRegistration("exporter", "Export", lambda: None))
    controller.plugin_registry = registry

    window.set_controller(controller)

    titles = [a.text() for a in window.menuBar().actions()]
    assert titles.index("&Edit") < titles.index("&Plugins") < titles.index("&Help")


def test_plugins_menu_action_calls_invoke(window: MainWindow) -> None:
    from mdf_viewer.plugin_api.registry import MenuActionRegistration

    calls = []
    controller = MagicMock()
    registry = PluginRegistry()
    registry.add_menu_action(MenuActionRegistration("exporter", "Export", lambda: calls.append(1)))
    controller.plugin_registry = registry
    window.set_controller(controller)

    action = next(a for a in window._plugins_menu.actions() if a.text() == "Export")
    action.trigger()

    assert calls == [1]


def test_plugins_menu_action_failure_shows_status_message(window: MainWindow) -> None:
    from mdf_viewer.plugin_api.registry import MenuActionRegistration

    def boom() -> None:
        raise ValueError("plugin bug")

    controller = MagicMock()
    registry = PluginRegistry()
    registry.add_menu_action(MenuActionRegistration("exporter", "Export", boom))
    controller.plugin_registry = registry
    window.set_controller(controller)

    action = next(a for a in window._plugins_menu.actions() if a.text() == "Export")
    action.trigger()

    assert "Export" in window.statusBar().currentMessage()


def test_dialog_mode_dock_widget_gets_menu_action(window: MainWindow) -> None:
    from mdf_viewer.plugin_api.registry import DockWidgetRegistration

    controller = MagicMock()
    registry = PluginRegistry()
    registry.add_dock_widget(
        DockWidgetRegistration("exporter", "Exporter Settings", lambda: QWidget(), "dialog")
    )
    controller.plugin_registry = registry
    window.set_controller(controller)

    assert any(a.text() == "Exporter Settings…" for a in window._plugins_menu.actions())


def test_dialog_mode_widget_is_built_once_and_cached(window: MainWindow) -> None:
    from mdf_viewer.plugin_api.registry import DockWidgetRegistration

    build_calls = []

    def factory() -> QWidget:
        build_calls.append(1)
        return QWidget()

    controller = MagicMock()
    registry = PluginRegistry()
    registration = DockWidgetRegistration("exporter", "Exporter Settings", factory, "dialog")
    registry.add_dock_widget(registration)
    controller.plugin_registry = registry
    window.set_controller(controller)

    with patch.object(QDialog, "exec", return_value=0):
        window._on_plugin_dialog_action(registration)
        window._on_plugin_dialog_action(registration)

    assert len(build_calls) == 1


def test_dialog_mode_widget_build_failure_does_nothing(window: MainWindow) -> None:
    from mdf_viewer.plugin_api.registry import DockWidgetRegistration

    def boom() -> QWidget:
        raise ValueError("plugin bug")

    controller = MagicMock()
    registry = PluginRegistry()
    registration = DockWidgetRegistration("exporter", "Exporter Settings", boom, "dialog")
    registry.add_dock_widget(registration)
    controller.plugin_registry = registry
    window.set_controller(controller)

    window._on_plugin_dialog_action(registration)  # must not raise

    assert registration not in window._plugin_dialogs


# ---------------------------------------------------------------------------
# Plugin Preferences dialog (#159)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLUGIN-431")
def test_plugin_preferences_action_present_and_disabled_when_registry_empty(
    window: MainWindow,
) -> None:
    controller = MagicMock()
    controller.plugin_registry = PluginRegistry()
    window.set_controller(controller)

    action = next(a for a in window._plugins_menu.actions() if a.text() == "Plugin Preferences…")
    assert not action.isEnabled()


@pytest.mark.requirement("REQ-PLUGIN-431")
def test_plugin_preferences_action_enabled_when_a_page_is_registered(window: MainWindow) -> None:
    from mdf_viewer.plugin_api.registry import PreferencesPageRegistration

    controller = MagicMock()
    registry = PluginRegistry()
    registry.add_preferences_page(PreferencesPageRegistration("exporter", "Export", lambda: QWidget()))
    controller.plugin_registry = registry
    window.set_controller(controller)

    action = next(a for a in window._plugins_menu.actions() if a.text() == "Plugin Preferences…")
    assert action.isEnabled()


@pytest.mark.requirement("REQ-PLUGIN-430")
def test_plugin_preferences_dialog_gets_one_tab_per_plugin(window: MainWindow) -> None:
    from mdf_viewer.plugin_api.registry import PreferencesPageRegistration

    controller = MagicMock()
    registry = PluginRegistry()
    registry.add_preferences_page(PreferencesPageRegistration("a", "A Prefs", lambda: QWidget()))
    registry.add_preferences_page(PreferencesPageRegistration("b", "B Prefs", lambda: QWidget()))
    controller.plugin_registry = registry
    window.set_controller(controller)

    with patch.object(QDialog, "exec", return_value=0):
        window._on_plugin_preferences(registry)

    tabs = window._plugin_preferences_dialog.tabs
    assert tabs.count() == 2
    assert {tabs.tabText(i) for i in range(tabs.count())} == {"A Prefs", "B Prefs"}


@pytest.mark.requirement("REQ-PLUGIN-433")
def test_plugin_preferences_widget_is_built_once_and_cached(window: MainWindow) -> None:
    from mdf_viewer.plugin_api.registry import PreferencesPageRegistration

    build_calls = []

    def factory() -> QWidget:
        build_calls.append(1)
        return QWidget()

    controller = MagicMock()
    registry = PluginRegistry()
    registry.add_preferences_page(PreferencesPageRegistration("exporter", "Export", factory))
    controller.plugin_registry = registry
    window.set_controller(controller)

    with patch.object(QDialog, "exec", return_value=0):
        window._on_plugin_preferences(registry)
        window._on_plugin_preferences(registry)

    assert len(build_calls) == 1


@pytest.mark.requirement("REQ-PLUGIN-434")
def test_plugin_preferences_page_build_failure_is_omitted_others_still_appear(
    window: MainWindow,
) -> None:
    from mdf_viewer.plugin_api.registry import PreferencesPageRegistration

    def boom() -> QWidget:
        raise ValueError("plugin bug")

    controller = MagicMock()
    registry = PluginRegistry()
    registry.add_preferences_page(PreferencesPageRegistration("broken", "Broken", boom))
    registry.add_preferences_page(PreferencesPageRegistration("ok", "OK Prefs", lambda: QWidget()))
    controller.plugin_registry = registry
    window.set_controller(controller)

    with patch.object(QDialog, "exec", return_value=0):
        window._on_plugin_preferences(registry)  # must not raise

    tabs = window._plugin_preferences_dialog.tabs
    assert tabs.count() == 1
    assert tabs.tabText(0) == "OK Prefs"
    assert "broken" not in window._plugin_preferences_tab_widgets


@pytest.mark.requirement("REQ-PLUGIN-432")
def test_plugin_preferences_dialog_has_only_a_close_button(window: MainWindow) -> None:
    from PyQt6.QtWidgets import QDialogButtonBox

    from mdf_viewer.plugin_api.registry import PreferencesPageRegistration

    controller = MagicMock()
    registry = PluginRegistry()
    registry.add_preferences_page(PreferencesPageRegistration("exporter", "Export", lambda: QWidget()))
    controller.plugin_registry = registry
    window.set_controller(controller)

    with patch.object(QDialog, "exec", return_value=0):
        window._on_plugin_preferences(registry)

    box = window._plugin_preferences_dialog.findChild(QDialogButtonBox)
    assert box.standardButtons() == QDialogButtonBox.StandardButton.Close


@pytest.mark.requirement("REQ-PLUGIN-440")
def test_teardown_plugin_ui_removes_only_that_plugins_preferences_tab(window: MainWindow) -> None:
    from mdf_viewer.plugin_api.registry import PreferencesPageRegistration

    controller = MagicMock()
    registry = PluginRegistry()
    registry.add_preferences_page(PreferencesPageRegistration("exporter", "Export", lambda: QWidget()))
    registry.add_preferences_page(PreferencesPageRegistration("other", "Other", lambda: QWidget()))
    controller.plugin_registry = registry
    window.set_controller(controller)
    with patch.object(QDialog, "exec", return_value=0):
        window._on_plugin_preferences(registry)

    window._teardown_plugin_ui("exporter")

    tabs = window._plugin_preferences_dialog.tabs
    assert tabs.count() == 1
    assert tabs.tabText(0) == "Other"
    assert "exporter" not in window._plugin_preferences_tab_widgets
    assert "other" in window._plugin_preferences_tab_widgets


def test_teardown_plugin_ui_preferences_tab_removal_is_safe_when_dialog_never_opened(
    window: MainWindow,
) -> None:
    controller = MagicMock()
    controller.plugin_registry = PluginRegistry()
    window.set_controller(controller)

    window._teardown_plugin_ui("exporter")  # must not raise


# ---------------------------------------------------------------------------
# Docked-mode plugin widgets (#73)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLUGIN-220")
def test_docked_mode_dock_widget_added_to_signal_info_box(window: MainWindow) -> None:
    from mdf_viewer.plugin_api.registry import DockWidgetRegistration

    before = window.signal_info_box._splitter.count()
    controller = MagicMock()
    registry = PluginRegistry()
    registry.add_dock_widget(
        DockWidgetRegistration("exporter", "Exporter Settings", lambda: QWidget(), "docked")
    )
    controller.plugin_registry = registry

    window.set_controller(controller)

    assert window.signal_info_box._splitter.count() == before + 1


def test_docked_mode_build_failure_adds_no_section(window: MainWindow) -> None:
    from mdf_viewer.plugin_api.registry import DockWidgetRegistration

    def boom() -> QWidget:
        raise ValueError("plugin bug")

    before = window.signal_info_box._splitter.count()
    controller = MagicMock()
    registry = PluginRegistry()
    registry.add_dock_widget(DockWidgetRegistration("exporter", "Exporter Settings", boom, "docked"))
    controller.plugin_registry = registry

    window.set_controller(controller)

    assert window.signal_info_box._splitter.count() == before


# ---------------------------------------------------------------------------
# Plugin Rescan/Reload — view-layer plumbing (#150)
# ---------------------------------------------------------------------------

def test_sync_plugin_ui_does_not_rebuild_an_already_tracked_dock_section(window: MainWindow) -> None:
    """_sync_plugin_ui() is add-only: calling it again with the same
    registry contents must not touch an already-tracked plugin's section —
    proven here by the widget factory not being called a second time."""
    from mdf_viewer.plugin_api.registry import DockWidgetRegistration

    build_calls = []

    def factory() -> QWidget:
        build_calls.append(1)
        return QWidget()

    controller = MagicMock()
    registry = PluginRegistry()
    registry.add_dock_widget(DockWidgetRegistration("exporter", "Exporter Settings", factory, "docked"))
    controller.plugin_registry = registry
    window.set_controller(controller)
    assert len(build_calls) == 1

    window._sync_plugin_ui()

    assert len(build_calls) == 1


def test_teardown_plugin_ui_removes_only_that_plugins_dock_section(window: MainWindow) -> None:
    from mdf_viewer.plugin_api.registry import DockWidgetRegistration

    controller = MagicMock()
    registry = PluginRegistry()
    registry.add_dock_widget(DockWidgetRegistration("exporter", "Exporter Settings", lambda: QWidget(), "docked"))
    registry.add_dock_widget(DockWidgetRegistration("other", "Other Settings", lambda: QWidget(), "docked"))
    controller.plugin_registry = registry
    window.set_controller(controller)
    before = window.signal_info_box._splitter.count()

    window._teardown_plugin_ui("exporter")

    assert window.signal_info_box._splitter.count() == before - 1
    assert "exporter" not in window._plugin_dock_widgets
    assert "other" in window._plugin_dock_widgets


def test_teardown_plugin_ui_closes_a_torn_down_plugins_cached_dialog(window: MainWindow) -> None:
    from mdf_viewer.plugin_api.registry import DockWidgetRegistration

    controller = MagicMock()
    registry = PluginRegistry()
    registration = DockWidgetRegistration("exporter", "Exporter Settings", lambda: QWidget(), "dialog")
    registry.add_dock_widget(registration)
    controller.plugin_registry = registry
    window.set_controller(controller)
    with patch.object(QDialog, "exec", return_value=0):
        window._on_plugin_dialog_action(registration)
    assert registration in window._plugin_dialogs

    window._teardown_plugin_ui("exporter")

    assert registration not in window._plugin_dialogs


def test_teardown_plugin_ui_leaves_other_plugins_cached_dialog_untouched(window: MainWindow) -> None:
    from mdf_viewer.plugin_api.registry import DockWidgetRegistration

    controller = MagicMock()
    registry = PluginRegistry()
    reg_a = DockWidgetRegistration("exporter", "Exporter Settings", lambda: QWidget(), "dialog")
    reg_b = DockWidgetRegistration("other", "Other Settings", lambda: QWidget(), "dialog")
    registry.add_dock_widget(reg_a)
    registry.add_dock_widget(reg_b)
    controller.plugin_registry = registry
    window.set_controller(controller)
    with patch.object(QDialog, "exec", return_value=0):
        window._on_plugin_dialog_action(reg_a)
        window._on_plugin_dialog_action(reg_b)

    window._teardown_plugin_ui("exporter")

    assert reg_b in window._plugin_dialogs


def test_teardown_plugin_ui_closes_every_open_tab_of_its_type_not_just_the_first(
    wired: MainWindow,
) -> None:
    """Regression test for the blocking Plan-review finding: closing
    matching tabs in ascending index order corrupts every close after the
    first, since removeTab() shifts every higher index down. With 2+ open
    tabs of the torn-down plugin's own type, both must close."""
    registration = TabTypeRegistration(
        plugin_name="fixture_plugin", type_id="fixture", display_name="Fixture Tab",
        view_factory=lambda: QWidget(),
    )
    baseline = wired._real_tab_count()
    wired._create_non_plot_tab(registration)
    wired._create_non_plot_tab(registration)
    wired._create_non_plot_tab(registration)
    assert wired._real_tab_count() == baseline + 3

    wired._teardown_plugin_ui("fixture_plugin")

    assert wired._real_tab_count() == baseline
    assert not any(
        reg.plugin_name == "fixture_plugin" for reg in wired._tab_type_by_page.values()
    )


def test_teardown_plugin_ui_leaves_other_plugins_open_tabs_untouched(wired: MainWindow) -> None:
    target = TabTypeRegistration(
        plugin_name="fixture_plugin", type_id="fixture", display_name="Fixture Tab",
        view_factory=lambda: QWidget(),
    )
    other = TabTypeRegistration(
        plugin_name="other_plugin", type_id="other", display_name="Other Tab",
        view_factory=lambda: QWidget(),
    )
    wired._create_non_plot_tab(target)
    wired._create_non_plot_tab(other)
    before = wired._real_tab_count()

    wired._teardown_plugin_ui("fixture_plugin")

    assert wired._real_tab_count() == before - 1
    assert any(reg.plugin_name == "other_plugin" for reg in wired._tab_type_by_page.values())


# ---------------------------------------------------------------------------
# Rescan trigger (#150)
# ---------------------------------------------------------------------------

def test_rescan_action_disabled_without_a_hook(wired: MainWindow) -> None:
    rescan_action = wired._plugins_menu.actions()[0]
    assert rescan_action.text() == "Rescan Plugins"
    assert not rescan_action.isEnabled()


def test_set_plugin_loader_hooks_enables_the_rescan_action(wired: MainWindow) -> None:
    wired.set_plugin_loader_hooks(
        rescan=lambda: PluginLoadResult(), reload_plugin=lambda name: True, active_plugin_names=lambda: [],
    )

    assert wired._plugins_menu.actions()[0].isEnabled()


def test_set_plugin_loader_hooks_stores_the_overview_hooks(wired: MainWindow) -> None:
    list_packages = lambda: []
    set_plugin_enabled = lambda folder, enabled: PluginLoadResult()
    active_plugin_names_for = lambda folder: []

    wired.set_plugin_loader_hooks(
        rescan=lambda: PluginLoadResult(),
        reload_plugin=lambda name: True,
        active_plugin_names=lambda: [],
        list_packages=list_packages,
        set_plugin_enabled=set_plugin_enabled,
        active_plugin_names_for=active_plugin_names_for,
    )

    assert wired._list_packages_hook is list_packages
    assert wired._set_plugin_enabled_hook is set_plugin_enabled
    assert wired._active_plugin_names_for_hook is active_plugin_names_for


def test_set_plugin_loader_hooks_overview_hooks_default_to_none(wired: MainWindow) -> None:
    wired.set_plugin_loader_hooks(
        rescan=lambda: PluginLoadResult(), reload_plugin=lambda name: True, active_plugin_names=lambda: [],
    )

    assert wired._list_packages_hook is None
    assert wired._set_plugin_enabled_hook is None
    assert wired._active_plugin_names_for_hook is None


def test_on_rescan_plugins_does_nothing_without_a_hook(wired: MainWindow) -> None:
    wired._on_rescan_plugins()  # must not raise
    assert wired.statusBar().currentMessage() == ""


def test_on_rescan_plugins_calls_hook_and_refreshes_ui(wired: MainWindow) -> None:
    calls = []

    def rescan() -> PluginLoadResult:
        calls.append(1)
        return PluginLoadResult(loaded=["NewPlugin"], failed=[])

    wired.set_plugin_loader_hooks(rescan=rescan, reload_plugin=lambda name: True, active_plugin_names=lambda: [])

    wired._on_rescan_plugins()

    assert calls == [1]


def test_on_rescan_plugins_shows_loaded_and_failed_counts(wired: MainWindow) -> None:
    wired.set_plugin_loader_hooks(
        rescan=lambda: PluginLoadResult(loaded=["A", "B"], failed=["C"]),
        reload_plugin=lambda name: True,
        active_plugin_names=lambda: [],
    )

    wired._on_rescan_plugins()

    assert wired.statusBar().currentMessage() == "Rescan: loaded 2, failed 1"


def test_on_rescan_plugins_shows_nothing_new_when_result_is_empty(wired: MainWindow) -> None:
    wired.set_plugin_loader_hooks(
        rescan=lambda: PluginLoadResult(), reload_plugin=lambda name: True, active_plugin_names=lambda: [],
    )

    wired._on_rescan_plugins()

    assert wired.statusBar().currentMessage() == "Rescan: nothing new"


# ---------------------------------------------------------------------------
# Reload trigger (#150)
# ---------------------------------------------------------------------------

def test_reload_submenu_disabled_when_no_plugins_active(wired: MainWindow) -> None:
    wired.set_plugin_loader_hooks(
        rescan=lambda: PluginLoadResult(), reload_plugin=lambda name: True, active_plugin_names=lambda: [],
    )

    reload_action = wired._plugins_menu.actions()[2]
    assert reload_action.text() == "Reload Plugin"
    assert not reload_action.isEnabled()


def test_reload_submenu_lists_every_active_plugin_by_name(wired: MainWindow) -> None:
    wired.set_plugin_loader_hooks(
        rescan=lambda: PluginLoadResult(),
        reload_plugin=lambda name: True,
        active_plugin_names=lambda: ["Alpha", "Bravo"],
    )

    reload_action = wired._plugins_menu.actions()[2]
    assert reload_action.isEnabled()
    submenu = reload_action.menu()
    assert [a.text() for a in submenu.actions()] == ["Alpha", "Bravo"]


def test_reload_submenu_action_reloads_the_correct_name_not_the_last_one(wired: MainWindow) -> None:
    """Regression test for the loop-variable-capture idiom (minor Plan-
    review finding): every per-name action must reload its OWN name, not
    whichever name the loop variable last held."""
    calls = []
    wired.set_plugin_loader_hooks(
        rescan=lambda: PluginLoadResult(),
        reload_plugin=lambda name: calls.append(name) or True,
        active_plugin_names=lambda: ["Alpha", "Bravo"],
    )

    submenu = wired._plugins_menu.actions()[2].menu()
    submenu.actions()[0].trigger()

    assert calls == ["Alpha"]


def test_on_reload_plugin_does_nothing_without_a_hook(wired: MainWindow) -> None:
    wired._on_reload_plugin("Alpha")  # must not raise
    assert wired.statusBar().currentMessage() == ""


def test_on_reload_plugin_sequences_teardown_then_hook_then_sync(wired: MainWindow) -> None:
    order = []
    original_teardown = wired._teardown_plugin_ui
    original_sync = wired._sync_plugin_ui

    def tracked_teardown(name: str) -> None:
        order.append(("teardown", name))
        original_teardown(name)

    def tracked_hook(name: str) -> bool:
        order.append(("hook", name))
        return True

    def tracked_sync() -> None:
        order.append(("sync", None))
        original_sync()

    wired._teardown_plugin_ui = tracked_teardown
    wired._sync_plugin_ui = tracked_sync
    wired.set_plugin_loader_hooks(
        rescan=lambda: PluginLoadResult(), reload_plugin=tracked_hook, active_plugin_names=lambda: [],
    )
    order.clear()  # drop the sync call set_plugin_loader_hooks() itself triggers

    wired._on_reload_plugin("Alpha")

    assert order == [("teardown", "Alpha"), ("hook", "Alpha"), ("sync", None)]


def test_on_reload_plugin_shows_success_status_message(wired: MainWindow) -> None:
    wired.set_plugin_loader_hooks(
        rescan=lambda: PluginLoadResult(), reload_plugin=lambda name: True, active_plugin_names=lambda: [],
    )

    wired._on_reload_plugin("Alpha")

    assert wired.statusBar().currentMessage() == "Reloaded 'Alpha'."


def test_on_reload_plugin_shows_failure_status_message_no_rollback(wired: MainWindow) -> None:
    """Reload failure is reported plainly — REQ-PLUGIN-372's no-rollback
    rule means there is no "back" to report succeeding at."""
    wired.set_plugin_loader_hooks(
        rescan=lambda: PluginLoadResult(), reload_plugin=lambda name: False, active_plugin_names=lambda: [],
    )

    wired._on_reload_plugin("Alpha")

    assert wired.statusBar().currentMessage() == "Reload of 'Alpha' failed — see log for detail."


def test_on_reload_plugin_tears_down_live_ui_before_calling_the_hook(wired: MainWindow) -> None:
    """End-to-end (within MainWindow) proof that Reload actually closes a
    plugin's open tab, cached dialog, and dock section before reloading —
    not just that the pieces work in isolation (covered by the M2 tests)."""
    from mdf_viewer.plugin_api.registry import DockWidgetRegistration, PreferencesPageRegistration

    registry = PluginRegistry()
    registry.add_dock_widget(DockWidgetRegistration("Alpha", "Alpha Settings", lambda: QWidget(), "docked"))
    dialog_reg = DockWidgetRegistration("Alpha", "Alpha Dialog", lambda: QWidget(), "dialog")
    registry.add_dock_widget(dialog_reg)
    registry.add_preferences_page(PreferencesPageRegistration("Alpha", "Alpha Prefs", lambda: QWidget()))
    wired._controller.plugin_registry = registry
    wired._sync_plugin_ui()
    with patch.object(QDialog, "exec", return_value=0):
        wired._on_plugin_dialog_action(dialog_reg)
        wired._on_plugin_preferences(registry)
    tab_registration = TabTypeRegistration(
        plugin_name="Alpha", type_id="alpha_tab", display_name="Alpha Tab", view_factory=lambda: QWidget(),
    )
    wired._create_non_plot_tab(tab_registration)
    before_tab_count = wired._real_tab_count()
    assert "Alpha" in wired._plugin_dock_widgets
    assert dialog_reg in wired._plugin_dialogs
    assert "Alpha" in wired._plugin_preferences_tab_widgets

    def fake_reload(name: str) -> bool:
        # Mirrors what the real reload_one() does to the registry via
        # Plugin.stop() -> PluginContext._teardown() ->
        # remove_registrations_for() — without this, _sync_plugin_ui()'s
        # add-only pass would just see the (untouched) old registration
        # still present and re-add it, which isn't what a real reload that
        # registers nothing fresh would do.
        registry.remove_registrations_for(name)
        return True

    wired.set_plugin_loader_hooks(
        rescan=lambda: PluginLoadResult(), reload_plugin=fake_reload, active_plugin_names=lambda: [],
    )
    wired._on_reload_plugin("Alpha")

    assert "Alpha" not in wired._plugin_dock_widgets
    assert dialog_reg not in wired._plugin_dialogs
    assert "Alpha" not in wired._plugin_preferences_tab_widgets
    assert wired._real_tab_count() == before_tab_count - 1


# ---------------------------------------------------------------------------
# Plugin Overview trigger (#160)
# ---------------------------------------------------------------------------

def _pkg(folder_name, enabled=True, active_plugin_names=None, failed=False, failure_reason=None, metadata=None):
    from mdf_viewer.plugin_api.loader import PluginPackageInfo

    return PluginPackageInfo(
        folder_name=folder_name,
        enabled=enabled,
        active_plugin_names=active_plugin_names or [],
        failed=failed,
        failure_reason=failure_reason,
        metadata=metadata or [],
    )


def _wire_overview_hooks(
    wired, list_packages=None, set_plugin_enabled=None, active_plugin_names_for=None,
):
    wired.set_plugin_loader_hooks(
        rescan=lambda: PluginLoadResult(),
        reload_plugin=lambda name: True,
        active_plugin_names=lambda: [],
        list_packages=list_packages or (lambda: []),
        set_plugin_enabled=set_plugin_enabled or (lambda folder, enabled: PluginLoadResult()),
        active_plugin_names_for=active_plugin_names_for or (lambda folder: []),
    )


def test_plugin_overview_action_disabled_without_hook(wired: MainWindow) -> None:
    wired.set_plugin_loader_hooks(
        rescan=lambda: PluginLoadResult(), reload_plugin=lambda name: True, active_plugin_names=lambda: [],
    )

    overview_action = wired._plugins_menu.actions()[1]
    assert overview_action.text() == "Plugin Overview…"
    assert not overview_action.isEnabled()


def test_plugin_overview_action_enabled_with_hook(wired: MainWindow) -> None:
    _wire_overview_hooks(wired)

    overview_action = wired._plugins_menu.actions()[1]
    assert overview_action.isEnabled()


def test_plugin_overview_action_positioned_between_rescan_and_reload(wired: MainWindow) -> None:
    _wire_overview_hooks(wired)

    texts = [a.text() for a in wired._plugins_menu.actions()]
    assert texts.index("Rescan Plugins") < texts.index("Plugin Overview…") < texts.index("Reload Plugin")


def test_on_plugin_overview_does_nothing_without_a_hook(wired: MainWindow) -> None:
    wired._on_plugin_overview()  # must not raise
    assert wired._plugin_overview_dialog is None


def test_on_plugin_overview_populates_dialog_from_hook(wired: MainWindow) -> None:
    packages = [_pkg("plugin_a"), _pkg("plugin_b", enabled=False)]
    _wire_overview_hooks(wired, list_packages=lambda: packages)

    with patch.object(QDialog, "exec", return_value=0):
        wired._on_plugin_overview()

    assert set(wired._plugin_overview_dialog.checkboxes) == {"plugin_a", "plugin_b"}
    assert wired._plugin_overview_dialog.checkboxes["plugin_a"].isChecked() is True
    assert wired._plugin_overview_dialog.checkboxes["plugin_b"].isChecked() is False


def test_on_plugin_overview_dialog_is_cached_across_opens(wired: MainWindow) -> None:
    _wire_overview_hooks(wired, list_packages=lambda: [_pkg("plugin_a")])

    with patch.object(QDialog, "exec", return_value=0):
        wired._on_plugin_overview()
        first_dialog = wired._plugin_overview_dialog
        wired._on_plugin_overview()

    assert wired._plugin_overview_dialog is first_dialog


def test_on_plugin_overview_toggled_does_nothing_without_a_hook(wired: MainWindow) -> None:
    wired._on_plugin_overview_toggled("plugin_a", False)  # must not raise


def test_on_plugin_overview_toggled_disable_sequences_teardown_then_hook_then_sync(
    wired: MainWindow,
) -> None:
    order = []
    original_teardown = wired._teardown_plugin_ui
    original_sync = wired._sync_plugin_ui

    def tracked_teardown(name: str) -> None:
        order.append(("teardown", name))
        original_teardown(name)

    def tracked_set_enabled(folder: str, enabled: bool) -> PluginLoadResult:
        order.append(("hook", folder, enabled))
        return PluginLoadResult()

    def tracked_sync() -> None:
        order.append(("sync", None))
        original_sync()

    wired._teardown_plugin_ui = tracked_teardown
    wired._sync_plugin_ui = tracked_sync
    _wire_overview_hooks(
        wired,
        set_plugin_enabled=tracked_set_enabled,
        active_plugin_names_for=lambda folder: ["Alpha"],
    )
    order.clear()  # drop the sync call set_plugin_loader_hooks() itself triggers

    wired._on_plugin_overview_toggled("plugin_a", False)

    assert order == [
        ("teardown", "Alpha"), ("hook", "plugin_a", False), ("sync", None),
    ]


def test_on_plugin_overview_toggled_disable_queries_live_state_not_stale_snapshot(
    wired: MainWindow,
) -> None:
    """F4 fix regression test: a toolsuite folder whose active-plugin set
    has drifted since the dialog was populated (e.g. a second plugin
    activated after the dialog opened) must still have every currently
    active plugin torn down — not just the one the dialog's stale
    PluginPackageInfo snapshot knew about."""
    torn_down = []
    wired._teardown_plugin_ui = lambda name: torn_down.append(name)
    # Dialog was populated when only "Alpha" was active from this folder;
    # by the time the checkbox is toggled, "Bravo" has also become active
    # — active_plugin_names_for must be queried live, not from the stale
    # PluginPackageInfo the dialog still holds.
    _wire_overview_hooks(
        wired,
        list_packages=lambda: [_pkg("toolsuite", active_plugin_names=["Alpha"])],
        active_plugin_names_for=lambda folder: ["Alpha", "Bravo"],
    )

    wired._on_plugin_overview_toggled("toolsuite", False)

    assert sorted(torn_down) == ["Alpha", "Bravo"]


def test_on_plugin_overview_toggled_disable_shows_no_confirmation(wired: MainWindow) -> None:
    """Silent/immediate, matching Reload's existing precedent — no
    QMessageBox or similar should appear."""
    with patch.object(QMessageBox, "question") as mock_question:
        _wire_overview_hooks(wired, active_plugin_names_for=lambda folder: ["Alpha"])
        wired._on_plugin_overview_toggled("plugin_a", False)
    mock_question.assert_not_called()


def test_on_plugin_overview_toggled_enable_calls_hook_and_syncs(wired: MainWindow) -> None:
    calls = []

    def set_enabled(folder: str, enabled: bool) -> PluginLoadResult:
        calls.append((folder, enabled))
        return PluginLoadResult(loaded=["Alpha"])

    _wire_overview_hooks(
        wired, set_plugin_enabled=set_enabled, active_plugin_names_for=lambda folder: ["Alpha"],
    )

    wired._on_plugin_overview_toggled("plugin_a", True)

    assert calls == [("plugin_a", True)]


def test_on_plugin_overview_toggled_enable_that_fails_still_shows_checked_with_failure(
    wired: MainWindow,
) -> None:
    """F3 fix (corrected): re-enabling a plugin that is still broken must
    NOT be shown as unchecked — that would silently disagree with the
    persisted setting (set_enabled(True) marks it enabled regardless of
    whether activation succeeds, matching REQ-PLUGIN-360's "always retry,
    never permanently remembered as broken" policy) and, if left
    uncorrected, that exact mismatch survives a restart: a live-tested
    regression where the dialog showed unchecked but settings.json still
    said enabled, so the next launch showed it checked again with no
    explanation. The dialog must always reflect a fresh list_packages()
    call — checked + a failure indicator, the same as any other
    enabled-but-broken plugin."""
    still_broken = _pkg("broken_plugin", enabled=True, failed=True, failure_reason="boom")
    _wire_overview_hooks(
        wired,
        list_packages=lambda: [still_broken],
        set_plugin_enabled=lambda folder, enabled: PluginLoadResult(failed=["broken_plugin"]),
        active_plugin_names_for=lambda folder: [],  # still nothing active — enable failed
    )
    with patch.object(QDialog, "exec", return_value=0):
        wired._on_plugin_overview()

    wired._on_plugin_overview_toggled("broken_plugin", True)

    checkbox = wired._plugin_overview_dialog.checkboxes["broken_plugin"]
    assert checkbox.isChecked() is True
    assert "failed to activate" in wired.statusBar().currentMessage()


def test_on_plugin_overview_toggled_enable_success_shows_checked_without_failure(
    wired: MainWindow,
) -> None:
    _wire_overview_hooks(
        wired,
        list_packages=lambda: [_pkg("plugin_a", enabled=True, active_plugin_names=["Alpha"])],
        set_plugin_enabled=lambda folder, enabled: PluginLoadResult(loaded=["Alpha"]),
        active_plugin_names_for=lambda folder: ["Alpha"],
    )
    with patch.object(QDialog, "exec", return_value=0):
        wired._on_plugin_overview()

    wired._on_plugin_overview_toggled("plugin_a", True)

    checkbox = wired._plugin_overview_dialog.checkboxes["plugin_a"]
    assert checkbox.isChecked() is True


def test_on_plugin_overview_toggled_tears_down_live_ui_before_disabling(wired: MainWindow) -> None:
    """End-to-end (within MainWindow) proof that disabling via the Overview
    dialog actually closes a plugin's open tab, cached dialog, and dock
    section — mirrors test_on_reload_plugin_tears_down_live_ui_before_
    calling_the_hook for the disable path."""
    from mdf_viewer.plugin_api.registry import DockWidgetRegistration, PreferencesPageRegistration

    registry = PluginRegistry()
    registry.add_dock_widget(DockWidgetRegistration("Alpha", "Alpha Settings", lambda: QWidget(), "docked"))
    dialog_reg = DockWidgetRegistration("Alpha", "Alpha Dialog", lambda: QWidget(), "dialog")
    registry.add_dock_widget(dialog_reg)
    registry.add_preferences_page(PreferencesPageRegistration("Alpha", "Alpha Prefs", lambda: QWidget()))
    wired._controller.plugin_registry = registry
    wired._sync_plugin_ui()
    with patch.object(QDialog, "exec", return_value=0):
        wired._on_plugin_dialog_action(dialog_reg)
        wired._on_plugin_preferences(registry)
    tab_registration = TabTypeRegistration(
        plugin_name="Alpha", type_id="alpha_tab", display_name="Alpha Tab", view_factory=lambda: QWidget(),
    )
    wired._create_non_plot_tab(tab_registration)
    before_tab_count = wired._real_tab_count()
    assert "Alpha" in wired._plugin_dock_widgets
    assert dialog_reg in wired._plugin_dialogs
    assert "Alpha" in wired._plugin_preferences_tab_widgets

    def fake_set_enabled(folder: str, enabled: bool) -> PluginLoadResult:
        registry.remove_registrations_for("Alpha")
        return PluginLoadResult()

    _wire_overview_hooks(
        wired, set_plugin_enabled=fake_set_enabled, active_plugin_names_for=lambda folder: ["Alpha"],
    )

    wired._on_plugin_overview_toggled("alpha_pkg", False)

    assert "Alpha" not in wired._plugin_dock_widgets
    assert dialog_reg not in wired._plugin_dialogs
    assert "Alpha" not in wired._plugin_preferences_tab_widgets
    assert wired._real_tab_count() == before_tab_count - 1


# ---------------------------------------------------------------------------
# _on_preferences — logging live-apply (#126)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-LOG-024")
def test_on_preferences_configures_logging_when_accepted(
    window: MainWindow, tmp_path
) -> None:
    from mdf_viewer.settings import Settings

    settings = Settings(path=tmp_path / "settings.json")
    window.set_settings(settings)
    calls = []
    with patch(
        "mdf_viewer.view.preferences_dialog.PreferencesDialog.exec", return_value=True
    ), patch("mdf_viewer.logging_config.configure_logging", side_effect=lambda s: calls.append(s)):
        window._on_preferences()
    assert calls == [settings]


def test_on_preferences_configures_logging_even_without_controller(
    window: MainWindow, tmp_path
) -> None:
    """Logging config has nothing to do with the controller — must not be
    silently skipped just because no controller happens to be wired yet."""
    from mdf_viewer.settings import Settings

    settings = Settings(path=tmp_path / "settings.json")
    window.set_settings(settings)
    assert window._controller is None
    calls = []
    with patch(
        "mdf_viewer.view.preferences_dialog.PreferencesDialog.exec", return_value=True
    ), patch("mdf_viewer.logging_config.configure_logging", side_effect=lambda s: calls.append(s)):
        window._on_preferences()
    assert calls == [settings]


def test_on_preferences_does_not_configure_logging_when_cancelled(
    window: MainWindow, tmp_path
) -> None:
    from mdf_viewer.settings import Settings

    settings = Settings(path=tmp_path / "settings.json")
    window.set_settings(settings)
    calls = []
    with patch(
        "mdf_viewer.view.preferences_dialog.PreferencesDialog.exec", return_value=False
    ), patch("mdf_viewer.logging_config.configure_logging", side_effect=lambda s: calls.append(s)):
        window._on_preferences()
    assert calls == []
