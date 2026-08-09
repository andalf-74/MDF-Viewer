"""Tests for small reusable view widgets (view/widgets/)."""

from __future__ import annotations

import pytest
from PyQt6.QtGui import QColor
from pytestqt.qtbot import QtBot

from mdf_viewer.view.widgets.color_swatch import ColorSwatch
from mdf_viewer.view.widgets.visibility_toggle_button import VisibilityToggleButton


@pytest.fixture()
def button(qtbot: QtBot) -> VisibilityToggleButton:
    b = VisibilityToggleButton(True)
    qtbot.addWidget(b)
    return b


def test_defaults_to_given_state(button: VisibilityToggleButton) -> None:
    assert button.visible_state is True


def test_set_visible_state_updates_state(button: VisibilityToggleButton) -> None:
    button.set_visible_state(False)
    assert button.visible_state is False
    button.set_visible_state(True)
    assert button.visible_state is True


def test_icon_changes_between_states(button: VisibilityToggleButton) -> None:
    open_icon = button.icon()
    button.set_visible_state(False)
    hidden_icon = button.icon()
    # QIcon has no simple equality by content, but cacheKey() differs for
    # distinct icon sources loaded from different files.
    assert open_icon.cacheKey() != hidden_icon.cacheKey()


def test_constructs_hidden_by_default_when_asked(qtbot: QtBot) -> None:
    b = VisibilityToggleButton(False)
    qtbot.addWidget(b)
    assert b.visible_state is False


def test_has_a_tooltip(button: VisibilityToggleButton) -> None:
    """#129: icon-only button, no other text cue at all."""
    assert button.toolTip() != ""


# ---------------------------------------------------------------------------
# ColorSwatch
# ---------------------------------------------------------------------------

def test_color_swatch_has_a_tooltip(qtbot: QtBot) -> None:
    """#129: icon-only (flat colored rectangle), no other text cue at all."""
    swatch = ColorSwatch(QColor(255, 0, 0))
    qtbot.addWidget(swatch)
    assert swatch.toolTip() != ""


# ---------------------------------------------------------------------------
# text_filter (apply_text_filter / wire_debounced_filter) — #86
# ---------------------------------------------------------------------------

def test_apply_text_filter_plain_substring(qtbot: QtBot) -> None:
    from PyQt6.QtCore import QSortFilterProxyModel
    from PyQt6.QtGui import QStandardItem, QStandardItemModel
    from mdf_viewer.view.widgets import apply_text_filter

    model = QStandardItemModel()
    model.appendRow(QStandardItem("engine_speed"))
    model.appendRow(QStandardItem("vehicle_speed"))
    model.appendRow(QStandardItem("driven_distance"))
    proxy = QSortFilterProxyModel()
    proxy.setSourceModel(model)

    apply_text_filter(proxy, "speed")
    assert proxy.rowCount() == 2


def test_apply_text_filter_wildcard(qtbot: QtBot) -> None:
    from PyQt6.QtCore import QSortFilterProxyModel
    from PyQt6.QtGui import QStandardItem, QStandardItemModel
    from mdf_viewer.view.widgets import apply_text_filter

    model = QStandardItemModel()
    model.appendRow(QStandardItem("engine_speed"))
    model.appendRow(QStandardItem("vehicle_speed"))
    model.appendRow(QStandardItem("driven_distance"))
    proxy = QSortFilterProxyModel()
    proxy.setSourceModel(model)

    apply_text_filter(proxy, "*distance")
    assert proxy.rowCount() == 1


def test_apply_text_filter_empty_string_matches_everything(qtbot: QtBot) -> None:
    from PyQt6.QtCore import QSortFilterProxyModel
    from PyQt6.QtGui import QStandardItem, QStandardItemModel
    from mdf_viewer.view.widgets import apply_text_filter

    model = QStandardItemModel()
    model.appendRow(QStandardItem("a"))
    model.appendRow(QStandardItem("b"))
    proxy = QSortFilterProxyModel()
    proxy.setSourceModel(model)

    apply_text_filter(proxy, "")
    assert proxy.rowCount() == 2


def test_apply_text_filter_wildcard_does_not_require_full_match(qtbot: QtBot) -> None:
    """A plain (non-wildcard) term must behave as "contains", not "equals"
    — setFilterWildcard() alone would require the whole string to match."""
    from PyQt6.QtCore import QSortFilterProxyModel
    from PyQt6.QtGui import QStandardItem, QStandardItemModel
    from mdf_viewer.view.widgets import apply_text_filter

    model = QStandardItemModel()
    model.appendRow(QStandardItem("engine_speed"))
    proxy = QSortFilterProxyModel()
    proxy.setSourceModel(model)

    apply_text_filter(proxy, "speed")  # no wildcard chars, partial match
    assert proxy.rowCount() == 1


def test_wire_debounced_filter_delays_application(qtbot: QtBot) -> None:
    from PyQt6.QtWidgets import QLineEdit
    from mdf_viewer.view.widgets import wire_debounced_filter

    edit = QLineEdit()
    qtbot.addWidget(edit)
    calls = []
    timer = wire_debounced_filter(edit, lambda: calls.append(edit.text()), delay_ms=30)

    edit.setText("abc")
    assert calls == []  # not applied synchronously
    qtbot.wait(60)
    assert calls == ["abc"]


def test_wire_debounced_filter_coalesces_rapid_typing(qtbot: QtBot) -> None:
    from PyQt6.QtWidgets import QLineEdit
    from mdf_viewer.view.widgets import wire_debounced_filter

    edit = QLineEdit()
    qtbot.addWidget(edit)
    calls = []
    wire_debounced_filter(edit, lambda: calls.append(edit.text()), delay_ms=50)

    edit.setText("a")
    edit.setText("ab")
    edit.setText("abc")
    qtbot.wait(90)
    assert calls == ["abc"]  # only the final value, one call
