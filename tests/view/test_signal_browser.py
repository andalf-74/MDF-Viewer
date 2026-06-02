"""Tests for SignalBrowser.

All tests require a QApplication (provided by pytest-qt's qtbot fixture).
"""

from __future__ import annotations

import pytest
from PyQt6.QtCore import QItemSelectionModel
from PyQt6.QtWidgets import QAbstractItemView
from pytestqt.qtbot import QtBot

from mdf_viewer.model.mdf_loader import ChannelGroupInfo
from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.view.signal_browser import SignalBrowser


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_metadata(name: str, unit: str, gi: int, ci: int) -> SignalMetadata:
    return SignalMetadata(name=name, unit=unit, group_index=gi, channel_index=ci)


@pytest.fixture()
def sample_groups() -> list[ChannelGroupInfo]:
    return [
        ChannelGroupInfo(
            name="Group 0",
            index=0,
            channels=(
                _make_metadata("time", "s", 0, 0),
                _make_metadata("sin", "V", 0, 1),
                _make_metadata("cos", "A", 0, 2),
            ),
        ),
        ChannelGroupInfo(
            name="Group 1",
            index=1,
            channels=(
                _make_metadata("speed", "km/h", 1, 0),
                _make_metadata("raw_flag", "", 1, 1),  # no unit
            ),
        ),
    ]


@pytest.fixture()
def browser(qtbot: QtBot) -> SignalBrowser:
    w = SignalBrowser()
    qtbot.addWidget(w)
    return w


@pytest.fixture()
def populated_browser(browser: SignalBrowser, sample_groups) -> SignalBrowser:
    browser.populate(sample_groups)
    return browser


def _px(browser: SignalBrowser, item):
    """Map a source model QStandardItem to its proxy model QModelIndex."""
    src = browser._model.indexFromItem(item)
    return browser._proxy.mapFromSource(src)


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

def test_tree_initially_empty(browser: SignalBrowser) -> None:
    assert browser._model.rowCount() == 0


def test_add_button_disabled_initially(browser: SignalBrowser) -> None:
    assert not browser._add_btn.isEnabled()


def test_filter_field_exists(browser: SignalBrowser) -> None:
    from PyQt6.QtWidgets import QLineEdit
    assert isinstance(browser._filter_edit, QLineEdit)


def test_filter_field_has_placeholder(browser: SignalBrowser) -> None:
    assert browser._filter_edit.placeholderText() != ""


# ---------------------------------------------------------------------------
# Selection mode and drag
# ---------------------------------------------------------------------------

def test_selection_mode_is_extended(browser: SignalBrowser) -> None:
    assert browser._tree.selectionMode() == QAbstractItemView.SelectionMode.ExtendedSelection


def test_drag_enabled(browser: SignalBrowser) -> None:
    assert browser._tree.dragEnabled()


def test_drag_mode_is_drag_only(browser: SignalBrowser) -> None:
    assert browser._tree.dragDropMode() == QAbstractItemView.DragDropMode.DragOnly


# ---------------------------------------------------------------------------
# populate()
# ---------------------------------------------------------------------------

def test_populate_creates_top_level_groups(populated_browser: SignalBrowser) -> None:
    assert populated_browser._model.rowCount() == 2


def test_populate_group_names(populated_browser: SignalBrowser) -> None:
    assert populated_browser._model.item(0).text() == "Group 0"
    assert populated_browser._model.item(1).text() == "Group 1"


def test_populate_group_0_has_three_children(populated_browser: SignalBrowser) -> None:
    assert populated_browser._model.item(0).rowCount() == 3


def test_populate_group_1_has_two_children(populated_browser: SignalBrowser) -> None:
    assert populated_browser._model.item(1).rowCount() == 2


def test_channel_label_includes_unit(populated_browser: SignalBrowser) -> None:
    sin_item = populated_browser._model.item(0).child(1)
    assert sin_item.text() == "sin [V]"


def test_channel_label_omits_empty_unit(populated_browser: SignalBrowser) -> None:
    raw_item = populated_browser._model.item(1).child(1)
    assert raw_item.text() == "raw_flag"


def test_add_button_disabled_after_populate(populated_browser: SignalBrowser) -> None:
    assert not populated_browser._add_btn.isEnabled()


def test_populate_replaces_previous_content(
    browser: SignalBrowser, sample_groups
) -> None:
    browser.populate(sample_groups)
    tiny = [
        ChannelGroupInfo(
            name="Solo",
            index=0,
            channels=(_make_metadata("x", "", 0, 0),),
        )
    ]
    browser.populate(tiny)
    assert browser._model.rowCount() == 1
    assert browser._model.item(0).text() == "Solo"


def test_populate_clears_filter(browser: SignalBrowser, sample_groups) -> None:
    browser.populate(sample_groups)
    browser._filter_edit.setText("sin")
    browser.populate(sample_groups)
    assert browser._filter_edit.text() == ""


# ---------------------------------------------------------------------------
# clear()
# ---------------------------------------------------------------------------

def test_clear_removes_items(populated_browser: SignalBrowser) -> None:
    populated_browser.clear()
    assert populated_browser._model.rowCount() == 0


def test_clear_disables_add_button(populated_browser: SignalBrowser) -> None:
    group_item = populated_browser._model.item(0)
    populated_browser._tree.setCurrentIndex(_px(populated_browser, group_item.child(1)))
    assert populated_browser._add_btn.isEnabled()

    populated_browser.clear()
    assert not populated_browser._add_btn.isEnabled()


def test_clear_resets_filter(populated_browser: SignalBrowser) -> None:
    populated_browser._filter_edit.setText("sin")
    populated_browser.clear()
    assert populated_browser._filter_edit.text() == ""


# ---------------------------------------------------------------------------
# Selection → button state
# ---------------------------------------------------------------------------

def test_add_button_enabled_when_channel_selected(
    populated_browser: SignalBrowser,
) -> None:
    populated_browser._tree.setCurrentIndex(
        _px(populated_browser, populated_browser._model.item(0).child(1))
    )
    assert populated_browser._add_btn.isEnabled()


def test_add_button_disabled_when_group_selected(
    populated_browser: SignalBrowser,
) -> None:
    populated_browser._tree.setCurrentIndex(
        _px(populated_browser, populated_browser._model.item(0))
    )
    assert not populated_browser._add_btn.isEnabled()


# ---------------------------------------------------------------------------
# add_signals_requested signal — single selection
# ---------------------------------------------------------------------------

def test_add_button_emits_correct_indices(
    populated_browser: SignalBrowser, qtbot: QtBot
) -> None:
    cos_item = populated_browser._model.item(0).child(2)
    populated_browser._tree.setCurrentIndex(_px(populated_browser, cos_item))
    with qtbot.waitSignal(
        populated_browser.add_signals_requested, timeout=500
    ) as blocker:
        populated_browser._add_btn.click()
    assert blocker.args == [[(0, 2)]]


def test_double_click_channel_emits_signal(
    populated_browser: SignalBrowser, qtbot: QtBot
) -> None:
    sin_item = populated_browser._model.item(0).child(1)
    with qtbot.waitSignal(
        populated_browser.add_signals_requested, timeout=500
    ) as blocker:
        populated_browser._tree.doubleClicked.emit(_px(populated_browser, sin_item))
    assert blocker.args == [[(0, 1)]]


def test_double_click_group_does_not_emit(
    populated_browser: SignalBrowser, qtbot: QtBot
) -> None:
    with qtbot.assertNotEmitted(populated_browser.add_signals_requested):
        populated_browser._tree.doubleClicked.emit(
            _px(populated_browser, populated_browser._model.item(0))
        )


def test_speed_channel_correct_indices(
    populated_browser: SignalBrowser, qtbot: QtBot
) -> None:
    speed_item = populated_browser._model.item(1).child(0)
    populated_browser._tree.setCurrentIndex(_px(populated_browser, speed_item))
    with qtbot.waitSignal(
        populated_browser.add_signals_requested, timeout=500
    ) as blocker:
        populated_browser._add_btn.click()
    assert blocker.args == [[(1, 0)]]


# ---------------------------------------------------------------------------
# add_signals_requested signal — multi-selection
# ---------------------------------------------------------------------------

def test_add_button_emits_all_selected_channels(
    populated_browser: SignalBrowser, qtbot: QtBot
) -> None:
    sm = populated_browser._tree.selectionModel()
    sin_idx = _px(populated_browser, populated_browser._model.item(0).child(1))
    cos_idx = _px(populated_browser, populated_browser._model.item(0).child(2))
    sm.select(sin_idx, QItemSelectionModel.SelectionFlag.ClearAndSelect)
    sm.select(cos_idx, QItemSelectionModel.SelectionFlag.Select)
    with qtbot.waitSignal(populated_browser.add_signals_requested, timeout=500) as blocker:
        populated_browser._add_btn.click()
    locations = blocker.args[0]
    assert (0, 1) in locations
    assert (0, 2) in locations


def test_selected_locations_excludes_group_items(
    populated_browser: SignalBrowser,
) -> None:
    group_item = populated_browser._model.item(0)
    populated_browser._tree.setCurrentIndex(_px(populated_browser, group_item))
    assert populated_browser._selected_locations() == []


def test_selected_locations_returns_multiple(
    populated_browser: SignalBrowser,
) -> None:
    sm = populated_browser._tree.selectionModel()
    sin_idx = _px(populated_browser, populated_browser._model.item(0).child(1))
    cos_idx = _px(populated_browser, populated_browser._model.item(0).child(2))
    sm.select(sin_idx, QItemSelectionModel.SelectionFlag.ClearAndSelect)
    sm.select(cos_idx, QItemSelectionModel.SelectionFlag.Select)
    locs = populated_browser._selected_locations()
    assert len(locs) == 2
    assert (0, 1) in locs
    assert (0, 2) in locs


# ---------------------------------------------------------------------------
# Filter behaviour
# ---------------------------------------------------------------------------

def test_filter_hides_non_matching_groups(populated_browser: SignalBrowser) -> None:
    # "sin" only appears in Group 0 → Group 1 should be hidden
    populated_browser._filter_edit.setText("sin")
    assert populated_browser._proxy.rowCount() == 1


def test_filter_shows_parent_group_when_child_matches(
    populated_browser: SignalBrowser,
) -> None:
    populated_browser._filter_edit.setText("sin")
    group0_proxy = populated_browser._proxy.index(0, 0)
    assert populated_browser._proxy.data(group0_proxy) == "Group 0"


def test_filter_shows_only_matching_children(populated_browser: SignalBrowser) -> None:
    populated_browser._filter_edit.setText("sin")
    group0_proxy = populated_browser._proxy.index(0, 0)
    assert populated_browser._proxy.rowCount(group0_proxy) == 1


def test_filter_case_insensitive(populated_browser: SignalBrowser) -> None:
    populated_browser._filter_edit.setText("SIN")
    assert populated_browser._proxy.rowCount() == 1


def test_filter_empty_shows_all(populated_browser: SignalBrowser) -> None:
    populated_browser._filter_edit.setText("sin")
    populated_browser._filter_edit.clear()
    assert populated_browser._proxy.rowCount() == 2


def test_filter_no_match_hides_all(populated_browser: SignalBrowser) -> None:
    populated_browser._filter_edit.setText("zzznomatch")
    assert populated_browser._proxy.rowCount() == 0


def test_filter_matches_partial_name(populated_browser: SignalBrowser) -> None:
    # "speed" is in Group 1; "spee" should match it
    populated_browser._filter_edit.setText("spee")
    assert populated_browser._proxy.rowCount() == 1
    group1_proxy = populated_browser._proxy.index(0, 0)
    assert "Group 1" in populated_browser._proxy.data(group1_proxy)
