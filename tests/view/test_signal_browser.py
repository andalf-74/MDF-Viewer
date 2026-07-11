"""Tests for SignalBrowser (#103: flat, cross-measurement channel list).

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
def other_groups() -> list[ChannelGroupInfo]:
    return [
        ChannelGroupInfo(
            name="Group 0",
            index=0,
            channels=(
                _make_metadata("sin", "V", 0, 0),  # same name as sample_groups' "sin"
                _make_metadata("torque", "Nm", 0, 1),
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
    browser.populate_all([("M1", sample_groups)])
    return browser


def _px(browser: SignalBrowser, item):
    """Map a source model QStandardItem to its proxy model QModelIndex."""
    src = browser._model.indexFromItem(item)
    return browser._proxy.mapFromSource(src)


def _row_text(browser: SignalBrowser, row: int) -> str:
    return browser._proxy.index(row, 0).data()


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

def test_list_initially_empty(browser: SignalBrowser) -> None:
    assert browser._model.rowCount() == 0


@pytest.mark.requirement("REQ-BROWSER-032")
def test_add_button_disabled_initially(browser: SignalBrowser) -> None:
    assert not browser._add_btn.isEnabled()


@pytest.mark.requirement("REQ-BROWSER-020")
def test_filter_field_exists(browser: SignalBrowser) -> None:
    from PyQt6.QtWidgets import QLineEdit
    assert isinstance(browser._filter_edit, QLineEdit)


def test_filter_field_has_placeholder(browser: SignalBrowser) -> None:
    assert browser._filter_edit.placeholderText() != ""


# ---------------------------------------------------------------------------
# Selection mode and drag
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-BROWSER-030")
def test_selection_mode_is_extended(browser: SignalBrowser) -> None:
    assert browser._tree.selectionMode() == QAbstractItemView.SelectionMode.ExtendedSelection


@pytest.mark.requirement("REQ-BROWSER-031")
def test_drag_enabled(browser: SignalBrowser) -> None:
    assert browser._tree.dragEnabled()


@pytest.mark.requirement("REQ-BROWSER-031")
def test_drag_mode_is_drag_only(browser: SignalBrowser) -> None:
    assert browser._tree.dragDropMode() == QAbstractItemView.DragDropMode.DragOnly


# ---------------------------------------------------------------------------
# populate_all() — single measurement (REQ-BROWSER-010/011)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-BROWSER-010")
def test_populate_all_creates_one_row_per_channel(populated_browser: SignalBrowser) -> None:
    # 3 channels in Group 0 + 2 in Group 1 = 5 flat rows, no group nodes.
    assert populated_browser._model.rowCount() == 5


@pytest.mark.requirement("REQ-BROWSER-011")
def test_populate_all_has_no_child_rows(populated_browser: SignalBrowser) -> None:
    for row in range(populated_browser._model.rowCount()):
        assert populated_browser._model.item(row).rowCount() == 0


@pytest.mark.requirement("REQ-BROWSER-010")
def test_single_measurement_has_no_prefix(populated_browser: SignalBrowser) -> None:
    texts = [populated_browser._model.item(r).text() for r in range(populated_browser._model.rowCount())]
    assert not any(t.startswith("[") for t in texts)


def test_channel_label_includes_unit(populated_browser: SignalBrowser) -> None:
    texts = [populated_browser._model.item(r).text() for r in range(populated_browser._model.rowCount())]
    assert "sin [V]" in texts


def test_channel_label_omits_empty_unit(populated_browser: SignalBrowser) -> None:
    texts = [populated_browser._model.item(r).text() for r in range(populated_browser._model.rowCount())]
    assert "raw_flag" in texts


@pytest.mark.requirement("REQ-BROWSER-013")
def test_channel_tooltip_shows_group_name(populated_browser: SignalBrowser) -> None:
    items = [populated_browser._model.item(r) for r in range(populated_browser._model.rowCount())]
    sin_item = next(i for i in items if i.text() == "sin [V]")
    assert sin_item.toolTip() == "Group 0"
    speed_item = next(i for i in items if i.text() == "speed [km/h]")
    assert speed_item.toolTip() == "Group 1"


@pytest.mark.requirement("REQ-BROWSER-032")
def test_add_button_disabled_after_populate(populated_browser: SignalBrowser) -> None:
    assert not populated_browser._add_btn.isEnabled()


@pytest.mark.requirement("REQ-BROWSER-012")
def test_populate_all_replaces_previous_content(
    browser: SignalBrowser, sample_groups
) -> None:
    browser.populate_all([("M1", sample_groups)])
    tiny = [
        ChannelGroupInfo(
            name="Solo",
            index=0,
            channels=(_make_metadata("x", "", 0, 0),),
        )
    ]
    browser.populate_all([("M1", tiny)])
    assert browser._model.rowCount() == 1
    assert browser._model.item(0).text() == "x"


@pytest.mark.requirement("REQ-BROWSER-012")
def test_populate_all_clears_filter(browser: SignalBrowser, sample_groups) -> None:
    browser.populate_all([("M1", sample_groups)])
    browser._filter_edit.setText("sin")
    browser.populate_all([("M1", sample_groups)])
    assert browser._filter_edit.text() == ""


# ---------------------------------------------------------------------------
# clear()
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-BROWSER-012")
def test_clear_removes_items(populated_browser: SignalBrowser) -> None:
    populated_browser.clear()
    assert populated_browser._model.rowCount() == 0


@pytest.mark.requirement("REQ-BROWSER-032")
def test_clear_disables_add_button(populated_browser: SignalBrowser) -> None:
    populated_browser._tree.setCurrentIndex(_px(populated_browser, populated_browser._model.item(1)))
    assert populated_browser._add_btn.isEnabled()

    populated_browser.clear()
    assert not populated_browser._add_btn.isEnabled()


@pytest.mark.requirement("REQ-BROWSER-012")
def test_clear_resets_filter(populated_browser: SignalBrowser) -> None:
    populated_browser._filter_edit.setText("sin")
    populated_browser.clear()
    assert populated_browser._filter_edit.text() == ""


# ---------------------------------------------------------------------------
# Selection → button state
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-BROWSER-032")
def test_add_button_enabled_when_channel_selected(
    populated_browser: SignalBrowser,
) -> None:
    populated_browser._tree.setCurrentIndex(
        _px(populated_browser, populated_browser._model.item(0))
    )
    assert populated_browser._add_btn.isEnabled()


# ---------------------------------------------------------------------------
# add_signals_requested signal — single selection
# ---------------------------------------------------------------------------

def _item_by_text(browser: SignalBrowser, text: str):
    for row in range(browser._model.rowCount()):
        item = browser._model.item(row)
        if item.text() == text:
            return item
    raise AssertionError(f"no item with text {text!r}")


@pytest.mark.requirement("REQ-BROWSER-031")
def test_add_button_emits_correct_indices(
    populated_browser: SignalBrowser, qtbot: QtBot
) -> None:
    cos_item = _item_by_text(populated_browser, "cos [A]")
    populated_browser._tree.setCurrentIndex(_px(populated_browser, cos_item))
    with qtbot.waitSignal(
        populated_browser.add_signals_requested, timeout=500
    ) as blocker:
        populated_browser._add_btn.click()
    assert blocker.args == [[(0, 0, 2)]]


@pytest.mark.requirement("REQ-BROWSER-031")
def test_double_click_channel_emits_signal(
    populated_browser: SignalBrowser, qtbot: QtBot
) -> None:
    sin_item = _item_by_text(populated_browser, "sin [V]")
    with qtbot.waitSignal(
        populated_browser.add_signals_requested, timeout=500
    ) as blocker:
        populated_browser._tree.doubleClicked.emit(_px(populated_browser, sin_item))
    assert blocker.args == [[(0, 0, 1)]]


@pytest.mark.requirement("REQ-BROWSER-031")
def test_speed_channel_correct_indices(
    populated_browser: SignalBrowser, qtbot: QtBot
) -> None:
    speed_item = _item_by_text(populated_browser, "speed [km/h]")
    populated_browser._tree.setCurrentIndex(_px(populated_browser, speed_item))
    with qtbot.waitSignal(
        populated_browser.add_signals_requested, timeout=500
    ) as blocker:
        populated_browser._add_btn.click()
    assert blocker.args == [[(0, 1, 0)]]


# ---------------------------------------------------------------------------
# add_signals_requested signal — multi-selection
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-BROWSER-030")
@pytest.mark.requirement("REQ-BROWSER-031")
def test_add_button_emits_all_selected_channels(
    populated_browser: SignalBrowser, qtbot: QtBot
) -> None:
    sm = populated_browser._tree.selectionModel()
    sin_idx = _px(populated_browser, _item_by_text(populated_browser, "sin [V]"))
    cos_idx = _px(populated_browser, _item_by_text(populated_browser, "cos [A]"))
    sm.select(sin_idx, QItemSelectionModel.SelectionFlag.ClearAndSelect)
    sm.select(cos_idx, QItemSelectionModel.SelectionFlag.Select)
    with qtbot.waitSignal(populated_browser.add_signals_requested, timeout=500) as blocker:
        populated_browser._add_btn.click()
    locations = blocker.args[0]
    assert (0, 0, 1) in locations
    assert (0, 0, 2) in locations


@pytest.mark.requirement("REQ-BROWSER-030")
def test_selected_locations_returns_multiple(
    populated_browser: SignalBrowser,
) -> None:
    sm = populated_browser._tree.selectionModel()
    sin_idx = _px(populated_browser, _item_by_text(populated_browser, "sin [V]"))
    cos_idx = _px(populated_browser, _item_by_text(populated_browser, "cos [A]"))
    sm.select(sin_idx, QItemSelectionModel.SelectionFlag.ClearAndSelect)
    sm.select(cos_idx, QItemSelectionModel.SelectionFlag.Select)
    locs = populated_browser._selected_locations()
    assert len(locs) == 2
    assert (0, 0, 1) in locs
    assert (0, 0, 2) in locs


# ---------------------------------------------------------------------------
# Filter behaviour (text filter, unaffected in mechanics by #103)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-BROWSER-024")
def test_filter_is_debounced(populated_browser: SignalBrowser, qtbot) -> None:
    # Typing does not filter immediately...
    populated_browser._filter_edit.setText("sin")
    assert populated_browser._proxy.rowCount() == 5
    # ...but does after the debounce delay elapses.
    qtbot.wait(populated_browser._filter_timer.interval() + 50)
    assert populated_browser._proxy.rowCount() == 1


@pytest.mark.requirement("REQ-BROWSER-020")
def test_filter_matches_single_channel(populated_browser: SignalBrowser) -> None:
    populated_browser._filter_edit.setText("sin")
    populated_browser._apply_filter()
    assert populated_browser._proxy.rowCount() == 1


@pytest.mark.requirement("REQ-BROWSER-021")
def test_filter_case_insensitive(populated_browser: SignalBrowser) -> None:
    populated_browser._filter_edit.setText("SIN")
    populated_browser._apply_filter()
    assert populated_browser._proxy.rowCount() == 1


@pytest.mark.requirement("REQ-BROWSER-020")
def test_filter_empty_shows_all(populated_browser: SignalBrowser) -> None:
    populated_browser._filter_edit.setText("sin")
    populated_browser._apply_filter()
    populated_browser._filter_edit.clear()
    populated_browser._apply_filter()
    assert populated_browser._proxy.rowCount() == 5


@pytest.mark.requirement("REQ-BROWSER-020")
def test_filter_no_match_hides_all(populated_browser: SignalBrowser) -> None:
    populated_browser._filter_edit.setText("zzznomatch")
    populated_browser._apply_filter()
    assert populated_browser._proxy.rowCount() == 0


@pytest.mark.requirement("REQ-BROWSER-022")
def test_filter_matches_partial_name(populated_browser: SignalBrowser) -> None:
    populated_browser._filter_edit.setText("spee")
    populated_browser._apply_filter()
    assert populated_browser._proxy.rowCount() == 1


# ---------------------------------------------------------------------------
# Wildcard filter behaviour
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-BROWSER-022")
def test_filter_wildcard_star_prefix(populated_browser: SignalBrowser) -> None:
    populated_browser._filter_edit.setText("*flag")
    populated_browser._apply_filter()
    assert populated_browser._proxy.rowCount() == 1


@pytest.mark.requirement("REQ-BROWSER-022")
def test_filter_wildcard_star_suffix(populated_browser: SignalBrowser) -> None:
    populated_browser._filter_edit.setText("raw*")
    populated_browser._apply_filter()
    assert populated_browser._proxy.rowCount() == 1


@pytest.mark.requirement("REQ-BROWSER-022")
def test_filter_wildcard_star_matches_multiple(populated_browser: SignalBrowser) -> None:
    # Unanchored substring match (pre-existing behavior, unchanged by #103):
    # "s*" matches any text containing "s" — "time [s]", "sin [V]",
    # "cos [A]", and "speed [km/h]" (not "raw_flag", no "s").
    populated_browser._filter_edit.setText("s*")
    populated_browser._apply_filter()
    assert populated_browser._proxy.rowCount() == 4


@pytest.mark.requirement("REQ-BROWSER-022")
def test_filter_wildcard_question_mark(populated_browser: SignalBrowser) -> None:
    populated_browser._filter_edit.setText("s?n*")
    populated_browser._apply_filter()
    assert populated_browser._proxy.rowCount() == 1


@pytest.mark.requirement("REQ-BROWSER-022")
def test_filter_wildcard_no_match(populated_browser: SignalBrowser) -> None:
    populated_browser._filter_edit.setText("*zzz*")
    populated_browser._apply_filter()
    assert populated_browser._proxy.rowCount() == 0


@pytest.mark.requirement("REQ-BROWSER-021")
@pytest.mark.requirement("REQ-BROWSER-022")
def test_filter_wildcard_case_insensitive(populated_browser: SignalBrowser) -> None:
    populated_browser._filter_edit.setText("*FLAG")
    populated_browser._apply_filter()
    assert populated_browser._proxy.rowCount() == 1


@pytest.mark.requirement("REQ-BROWSER-022")
def test_filter_plain_text_still_does_substring_match(populated_browser: SignalBrowser) -> None:
    populated_browser._filter_edit.setText("raw")
    populated_browser._apply_filter()
    assert populated_browser._proxy.rowCount() == 1


# ---------------------------------------------------------------------------
# Multiple Measurements (#103, REQ-BROWSER-010/013/050-054)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-BROWSER-050")
def test_no_prefix_and_no_filter_with_one_measurement(populated_browser: SignalBrowser) -> None:
    texts = [populated_browser._model.item(r).text() for r in range(populated_browser._model.rowCount())]
    assert all(not t.startswith("[") for t in texts)
    assert populated_browser._measurement_filter_combo.isHidden() is True


@pytest.mark.requirement("REQ-BROWSER-050")
def test_two_measurements_prefixes_every_row(
    browser: SignalBrowser, sample_groups, other_groups
) -> None:
    browser.populate_all([("M1", sample_groups), ("M2", other_groups)])
    texts = [browser._model.item(r).text() for r in range(browser._model.rowCount())]
    assert "[M1] sin [V]" in texts
    assert "[M2] sin [V]" in texts
    assert "[M2] torque [Nm]" in texts


@pytest.mark.requirement("REQ-BROWSER-050")
def test_measurement_filter_combo_shown_only_with_multiple(
    browser: SignalBrowser, sample_groups, other_groups
) -> None:
    browser.populate_all([("M1", sample_groups), ("M2", other_groups)])
    assert browser._measurement_filter_combo.isHidden() is False
    assert browser._measurement_filter_combo.count() == 3  # "All", M1, M2
    assert browser._measurement_filter_combo.itemText(0) == "All"
    assert browser._measurement_filter_combo.itemText(1) == "M1"
    assert browser._measurement_filter_combo.itemText(2) == "M2"


@pytest.mark.requirement("REQ-BROWSER-051")
def test_sort_groups_identically_named_channels_from_different_measurements(
    browser: SignalBrowser, sample_groups, other_groups
) -> None:
    """Sorting is keyed on the bare channel name, not the prefix, so
    "[M1] sin" and "[M2] sin" land adjacent despite the prefix ordering."""
    browser.populate_all([("M1", sample_groups), ("M2", other_groups)])
    texts = [_row_text(browser, r) for r in range(browser._proxy.rowCount())]
    sin_positions = [i for i, t in enumerate(texts) if "sin" in t]
    assert sin_positions == [sin_positions[0], sin_positions[0] + 1]
    assert texts[sin_positions[0]] == "[M1] sin [V]"
    assert texts[sin_positions[0] + 1] == "[M2] sin [V]"


@pytest.mark.requirement("REQ-BROWSER-052")
def test_measurement_filter_narrows_to_one_measurement(
    browser: SignalBrowser, sample_groups, other_groups
) -> None:
    browser.populate_all([("M1", sample_groups), ("M2", other_groups)])
    browser._measurement_filter_combo.setCurrentIndex(2)  # M2
    texts = [_row_text(browser, r) for r in range(browser._proxy.rowCount())]
    assert texts == ["[M2] sin [V]", "[M2] torque [Nm]"]


@pytest.mark.requirement("REQ-BROWSER-052")
def test_measurement_filter_defaults_to_all(
    browser: SignalBrowser, sample_groups, other_groups
) -> None:
    browser.populate_all([("M1", sample_groups), ("M2", other_groups)])
    assert browser._measurement_filter_combo.currentIndex() == 0
    assert browser._proxy.rowCount() == 7  # 5 + 2


@pytest.mark.requirement("REQ-BROWSER-053")
def test_text_filter_and_measurement_filter_compose(
    browser: SignalBrowser, sample_groups, other_groups
) -> None:
    browser.populate_all([("M1", sample_groups), ("M2", other_groups)])
    browser._measurement_filter_combo.setCurrentIndex(1)  # M1 only
    browser._filter_edit.setText("sin")
    browser._apply_filter()
    texts = [_row_text(browser, r) for r in range(browser._proxy.rowCount())]
    assert texts == ["[M1] sin [V]"]


@pytest.mark.requirement("REQ-BROWSER-052")
def test_repopulate_preserves_measurement_filter_by_label(
    browser: SignalBrowser, sample_groups, other_groups
) -> None:
    browser.populate_all([("M1", sample_groups), ("M2", other_groups)])
    browser._measurement_filter_combo.setCurrentIndex(2)  # M2

    browser.populate_all([("M1", sample_groups), ("M2", other_groups)])

    assert browser._measurement_filter_combo.currentIndex() == 2
    texts = [_row_text(browser, r) for r in range(browser._proxy.rowCount())]
    assert texts == ["[M2] sin [V]", "[M2] torque [Nm]"]


@pytest.mark.requirement("REQ-BROWSER-052")
def test_repopulate_resets_filter_to_all_when_filtered_measurement_gone(
    browser: SignalBrowser, sample_groups, other_groups
) -> None:
    browser.populate_all([("M1", sample_groups), ("M2", other_groups)])
    browser._measurement_filter_combo.setCurrentIndex(2)  # M2

    # M2 closed — only M1 remains.
    browser.populate_all([("M1", sample_groups)])

    assert browser._measurement_filter_combo.currentIndex() == 0
    assert browser._proxy.rowCount() == 5


def test_clear_hides_measurement_filter(
    browser: SignalBrowser, sample_groups, other_groups
) -> None:
    browser.populate_all([("M1", sample_groups), ("M2", other_groups)])
    browser.clear()
    assert browser._measurement_filter_combo.isHidden() is True


@pytest.mark.requirement("REQ-BROWSER-054")
def test_add_signals_requested_carries_each_rows_own_measurement(
    browser: SignalBrowser, sample_groups, other_groups, qtbot: QtBot
) -> None:
    browser.populate_all([("M1", sample_groups), ("M2", other_groups)])
    torque_item = _item_by_text(browser, "[M2] torque [Nm]")
    with qtbot.waitSignal(browser.add_signals_requested, timeout=500) as blocker:
        browser._tree.doubleClicked.emit(_px(browser, torque_item))
    assert blocker.args == [[(1, 0, 1)]]


@pytest.mark.requirement("REQ-BROWSER-054")
def test_add_signals_requested_can_span_measurements(
    browser: SignalBrowser, sample_groups, other_groups, qtbot: QtBot
) -> None:
    """A single multi-selection can legally span rows from different
    measurements (#103) — confirmed with the user for the mixed-measurement
    drag case; the same underlying _selected_locations() feeds both drag
    and the Add Signal button."""
    browser.populate_all([("M1", sample_groups), ("M2", other_groups)])
    sm = browser._tree.selectionModel()
    m1_sin = _px(browser, _item_by_text(browser, "[M1] sin [V]"))
    m2_torque = _px(browser, _item_by_text(browser, "[M2] torque [Nm]"))
    sm.select(m1_sin, QItemSelectionModel.SelectionFlag.ClearAndSelect)
    sm.select(m2_torque, QItemSelectionModel.SelectionFlag.Select)
    with qtbot.waitSignal(browser.add_signals_requested, timeout=500) as blocker:
        browser._add_btn.click()
    locations = blocker.args[0]
    assert (0, 0, 1) in locations
    assert (1, 0, 1) in locations
