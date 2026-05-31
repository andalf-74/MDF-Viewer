"""Tests for ActiveSignalsTable."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest
from PyQt6.QtGui import QColor
from pytestqt.qtbot import QtBot

from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.view.active_signals_table import ActiveSignalsTable, _ColorSwatch
from mdf_viewer.view_model.active_signal import ActiveSignal


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_active(name: str = "sig", color: QColor | None = None) -> ActiveSignal:
    t = np.array([0.0, 1.0])
    data = SignalData(timestamps=t, samples=t)
    meta = SignalMetadata(name=name, unit="V", group_index=0, channel_index=0)
    return ActiveSignal(data=data, metadata=meta, color=color or QColor(255, 0, 0))


@pytest.fixture()
def table(qtbot: QtBot) -> ActiveSignalsTable:
    w = ActiveSignalsTable()
    qtbot.addWidget(w)
    return w


@pytest.fixture()
def populated(table: ActiveSignalsTable) -> tuple[ActiveSignalsTable, list[ActiveSignal]]:
    sigs = [
        _make_active("alpha", QColor(255, 0, 0)),
        _make_active("beta", QColor(0, 0, 255)),
        _make_active("gamma", QColor(0, 200, 0)),
    ]
    for s in sigs:
        table.add_row(s)
    return table, sigs


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

def test_initially_empty(table: ActiveSignalsTable) -> None:
    assert table._table.rowCount() == 0


def test_remove_button_disabled_initially(table: ActiveSignalsTable) -> None:
    assert not table._remove_btn.isEnabled()


def test_cursor_columns_hidden_initially(table: ActiveSignalsTable) -> None:
    assert table._table.isColumnHidden(2)
    assert table._table.isColumnHidden(3)
    assert table._table.isColumnHidden(4)


# ---------------------------------------------------------------------------
# add_row
# ---------------------------------------------------------------------------

def test_add_row_increases_row_count(table: ActiveSignalsTable) -> None:
    table.add_row(_make_active("x"))
    assert table._table.rowCount() == 1


def test_add_multiple_rows(table: ActiveSignalsTable) -> None:
    for i in range(3):
        table.add_row(_make_active(f"sig{i}"))
    assert table._table.rowCount() == 3


def test_add_row_shows_signal_name(table: ActiveSignalsTable) -> None:
    table.add_row(_make_active("engine_speed"))
    assert table._table.item(0, 1).text() == "engine_speed"


def test_add_row_places_color_swatch(table: ActiveSignalsTable) -> None:
    table.add_row(_make_active("x", QColor(100, 200, 50)))
    swatch = table._table.cellWidget(0, 0)
    assert isinstance(swatch, _ColorSwatch)


def test_add_row_swatch_has_correct_color(table: ActiveSignalsTable) -> None:
    color = QColor(123, 45, 67)
    table.add_row(_make_active("x", color))
    swatch = table._table.cellWidget(0, 0)
    assert swatch.color == color


# ---------------------------------------------------------------------------
# remove_row
# ---------------------------------------------------------------------------

def test_remove_row_decreases_row_count(populated: tuple) -> None:
    t, sigs = populated
    t.remove_row(sigs[1])
    assert t._table.rowCount() == 2


def test_remove_row_removes_correct_signal(populated: tuple) -> None:
    t, sigs = populated
    t.remove_row(sigs[1])
    assert t._table.item(0, 1).text() == "alpha"
    assert t._table.item(1, 1).text() == "gamma"


def test_remove_row_noop_for_unknown(table: ActiveSignalsTable) -> None:
    stranger = _make_active("x")
    table.remove_row(stranger)  # must not raise


def test_remove_first_row(populated: tuple) -> None:
    t, sigs = populated
    t.remove_row(sigs[0])
    assert t._table.item(0, 1).text() == "beta"


def test_remove_last_row(populated: tuple) -> None:
    t, sigs = populated
    t.remove_row(sigs[2])
    assert t._table.rowCount() == 2
    assert t._table.item(1, 1).text() == "beta"


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------

def test_clear_removes_all_rows(populated: tuple) -> None:
    t, _ = populated
    t.clear()
    assert t._table.rowCount() == 0


def test_clear_resets_internal_list(populated: tuple) -> None:
    t, _ = populated
    t.clear()
    assert t._signals == []


# ---------------------------------------------------------------------------
# show_cursor_columns
# ---------------------------------------------------------------------------

def test_show_cursor_columns_makes_them_visible(table: ActiveSignalsTable) -> None:
    table.show_cursor_columns(True)
    assert not table._table.isColumnHidden(2)
    assert not table._table.isColumnHidden(3)
    assert not table._table.isColumnHidden(4)


def test_hide_cursor_columns(table: ActiveSignalsTable) -> None:
    table.show_cursor_columns(True)
    table.show_cursor_columns(False)
    assert table._table.isColumnHidden(2)


# ---------------------------------------------------------------------------
# update_cursor_values
# ---------------------------------------------------------------------------

def test_update_cursor_values_sets_text(populated: tuple) -> None:
    t, sigs = populated
    t.update_cursor_values(sigs[0], "1.23", "4.56", "3.33")
    assert t._table.item(0, 2).text() == "1.23"
    assert t._table.item(0, 3).text() == "4.56"
    assert t._table.item(0, 4).text() == "3.33"


def test_update_cursor_values_noop_for_unknown(table: ActiveSignalsTable) -> None:
    stranger = _make_active("x")
    table.update_cursor_values(stranger, "1", "2", "3")  # must not raise


# ---------------------------------------------------------------------------
# Remove button state
# ---------------------------------------------------------------------------

def test_remove_button_enabled_after_selection(populated: tuple) -> None:
    t, sigs = populated
    idx = t._table.model().index(0, 1)
    t._table.setCurrentIndex(idx)
    assert t._remove_btn.isEnabled()


def test_remove_button_disabled_after_clear(populated: tuple) -> None:
    t, sigs = populated
    t._table.setCurrentIndex(t._table.model().index(0, 1))
    t.clear()
    assert not t._remove_btn.isEnabled()


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

def test_remove_button_emits_remove_requested(
    populated: tuple, qtbot: QtBot
) -> None:
    t, sigs = populated
    t._table.setCurrentIndex(t._table.model().index(1, 1))
    with qtbot.waitSignal(t.remove_requested, timeout=500) as blocker:
        t._remove_btn.click()
    assert blocker.args[0] is sigs[1]


def test_remove_all_button_emits_remove_all_requested(
    populated: tuple, qtbot: QtBot
) -> None:
    t, _ = populated
    with qtbot.waitSignal(t.remove_all_requested, timeout=500):
        t._remove_all_btn.click()


def test_selection_change_emits_active_signal(
    populated: tuple, qtbot: QtBot
) -> None:
    t, sigs = populated
    with qtbot.waitSignal(t.selection_changed, timeout=500) as blocker:
        t._table.setCurrentIndex(t._table.model().index(2, 1))
    assert blocker.args[0] is sigs[2]


def test_clearing_selection_emits_none(populated: tuple, qtbot: QtBot) -> None:
    t, _ = populated
    t._table.setCurrentIndex(t._table.model().index(0, 1))
    with qtbot.waitSignal(t.selection_changed, timeout=500) as blocker:
        t._table.clearSelection()
    assert blocker.args[0] is None


def test_color_change_emits_signal(populated: tuple, qtbot: QtBot) -> None:
    t, sigs = populated
    new_color = QColor(10, 20, 30)
    with patch(
        "mdf_viewer.view.active_signals_table.QColorDialog.getColor",
        return_value=new_color,
    ):
        with qtbot.waitSignal(t.color_change_requested, timeout=500) as blocker:
            t._on_color_swatch_clicked(sigs[0])
    assert blocker.args[0] is sigs[0]
    assert blocker.args[1] == new_color


def test_color_change_updates_swatch(populated: tuple, qtbot: QtBot) -> None:
    t, sigs = populated
    new_color = QColor(10, 20, 30)
    with patch(
        "mdf_viewer.view.active_signals_table.QColorDialog.getColor",
        return_value=new_color,
    ):
        t._on_color_swatch_clicked(sigs[0])
    swatch = t._table.cellWidget(0, 0)
    assert swatch.color == new_color


def test_color_change_cancelled_does_not_emit(
    populated: tuple, qtbot: QtBot
) -> None:
    t, sigs = populated
    invalid = QColor()  # invalid color = dialog cancelled
    with patch(
        "mdf_viewer.view.active_signals_table.QColorDialog.getColor",
        return_value=invalid,
    ):
        with qtbot.assertNotEmitted(t.color_change_requested):
            t._on_color_swatch_clicked(sigs[0])
