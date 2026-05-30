"""Tests for SignalBrowser.

All tests require a QApplication (provided by pytest-qt's qtbot fixture).
"""

from __future__ import annotations

import pytest
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


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

def test_tree_initially_empty(browser: SignalBrowser) -> None:
    assert browser._model.rowCount() == 0


def test_add_button_disabled_initially(browser: SignalBrowser) -> None:
    assert not browser._add_btn.isEnabled()


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


# ---------------------------------------------------------------------------
# clear()
# ---------------------------------------------------------------------------

def test_clear_removes_items(populated_browser: SignalBrowser) -> None:
    populated_browser.clear()
    assert populated_browser._model.rowCount() == 0


def test_clear_disables_add_button(populated_browser: SignalBrowser) -> None:
    # Select a channel to enable the button, then clear
    group_item = populated_browser._model.item(0)
    chan_index = populated_browser._model.indexFromItem(group_item.child(1))
    populated_browser._tree.setCurrentIndex(chan_index)
    assert populated_browser._add_btn.isEnabled()

    populated_browser.clear()
    assert not populated_browser._add_btn.isEnabled()


# ---------------------------------------------------------------------------
# Selection → button state
# ---------------------------------------------------------------------------

def test_add_button_enabled_when_channel_selected(
    populated_browser: SignalBrowser,
) -> None:
    chan_index = populated_browser._model.indexFromItem(
        populated_browser._model.item(0).child(1)  # "sin [V]"
    )
    populated_browser._tree.setCurrentIndex(chan_index)
    assert populated_browser._add_btn.isEnabled()


def test_add_button_disabled_when_group_selected(
    populated_browser: SignalBrowser,
) -> None:
    group_index = populated_browser._model.indexFromItem(
        populated_browser._model.item(0)
    )
    populated_browser._tree.setCurrentIndex(group_index)
    assert not populated_browser._add_btn.isEnabled()


# ---------------------------------------------------------------------------
# add_signal_requested signal
# ---------------------------------------------------------------------------

def test_add_button_emits_correct_indices(
    populated_browser: SignalBrowser, qtbot: QtBot
) -> None:
    # Select "cos [A]" which is group=0, channel=2
    cos_item = populated_browser._model.item(0).child(2)
    populated_browser._tree.setCurrentIndex(
        populated_browser._model.indexFromItem(cos_item)
    )
    with qtbot.waitSignal(
        populated_browser.add_signal_requested, timeout=500
    ) as blocker:
        populated_browser._add_btn.click()
    assert blocker.args == [0, 2]


def test_double_click_channel_emits_signal(
    populated_browser: SignalBrowser, qtbot: QtBot
) -> None:
    sin_item = populated_browser._model.item(0).child(1)
    sin_index = populated_browser._model.indexFromItem(sin_item)
    with qtbot.waitSignal(
        populated_browser.add_signal_requested, timeout=500
    ) as blocker:
        populated_browser._tree.doubleClicked.emit(sin_index)
    assert blocker.args == [0, 1]


def test_double_click_group_does_not_emit(
    populated_browser: SignalBrowser, qtbot: QtBot
) -> None:
    group_index = populated_browser._model.indexFromItem(
        populated_browser._model.item(0)
    )
    with qtbot.assertNotEmitted(populated_browser.add_signal_requested):
        populated_browser._tree.doubleClicked.emit(group_index)


def test_speed_channel_correct_indices(
    populated_browser: SignalBrowser, qtbot: QtBot
) -> None:
    # "speed [km/h]" is group=1, channel=0
    speed_item = populated_browser._model.item(1).child(0)
    populated_browser._tree.setCurrentIndex(
        populated_browser._model.indexFromItem(speed_item)
    )
    with qtbot.waitSignal(
        populated_browser.add_signal_requested, timeout=500
    ) as blocker:
        populated_browser._add_btn.click()
    assert blocker.args == [1, 0]
