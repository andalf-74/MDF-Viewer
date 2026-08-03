"""Tests for SearchDialog (#110)."""

from __future__ import annotations

import numpy as np
import pytest
from PyQt6.QtGui import QColor
from pytestqt.qtbot import QtBot

from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.model.signal_search import SearchOperator
from mdf_viewer.view.search_dialog import SearchDialog, _COL_NAME, _COL_OPERATOR, _COL_VALUE
from mdf_viewer.view_model.active_signal import ActiveSignal


def _make_active(name: str = "sig") -> ActiveSignal:
    data = SignalData(timestamps=np.array([0.0, 1.0]), samples=np.array([0.0, 1.0]))
    meta = SignalMetadata(name=name)
    return ActiveSignal(data=data, metadata=meta, color=QColor(255, 0, 0))


@pytest.mark.requirement("REQ-SEARCH-015")
def test_is_non_modal(qtbot: QtBot) -> None:
    dlg = SearchDialog(parent=None)
    qtbot.addWidget(dlg)
    assert not dlg.isModal()


@pytest.mark.requirement("REQ-SEARCH-020")
@pytest.mark.requirement("REQ-SEARCH-021")
def test_set_rows_builds_one_row_per_signal(qtbot: QtBot) -> None:
    dlg = SearchDialog(parent=None)
    qtbot.addWidget(dlg)
    a, b = _make_active("a"), _make_active("b")
    dlg.set_rows([a, b])
    assert dlg._table.rowCount() == 2
    assert dlg._table.item(0, _COL_NAME).text() == "a"
    assert dlg._table.item(1, _COL_NAME).text() == "b"


@pytest.mark.requirement("REQ-SEARCH-021")
def test_set_rows_uses_name_for_when_given(qtbot: QtBot) -> None:
    dlg = SearchDialog(parent=None)
    qtbot.addWidget(dlg)
    a, b = _make_active("EngineCoolantTemperatureSensor"), _make_active("b")
    dlg.set_rows([a, b], name_for=lambda signal: f"[M1] {signal.metadata.name[:4]}")
    assert dlg._table.item(0, _COL_NAME).text() == "[M1] Engi"
    assert dlg._table.item(1, _COL_NAME).text() == "[M1] b"


@pytest.mark.requirement("REQ-SEARCH-021")
def test_set_rows_defaults_to_raw_name_without_name_for(qtbot: QtBot) -> None:
    dlg = SearchDialog(parent=None)
    qtbot.addWidget(dlg)
    a = _make_active("raw_name")
    dlg.set_rows([a])
    assert dlg._table.item(0, _COL_NAME).text() == "raw_name"


@pytest.mark.requirement("REQ-SEARCH-022")
def test_operator_combo_defaults_to_equals(qtbot: QtBot) -> None:
    dlg = SearchDialog(parent=None)
    qtbot.addWidget(dlg)
    dlg.set_rows([_make_active()])
    combo = dlg._table.cellWidget(0, _COL_OPERATOR)
    assert combo.currentData() == SearchOperator.EQ


@pytest.mark.requirement("REQ-SEARCH-013")
def test_set_rows_prefills_value_from_dict(qtbot: QtBot) -> None:
    dlg = SearchDialog(parent=None)
    qtbot.addWidget(dlg)
    a, b = _make_active("a"), _make_active("b")
    dlg.set_rows([a, b], prefill={a: 42.0})
    assert dlg._table.cellWidget(0, _COL_VALUE).text() == "42"
    assert dlg._table.cellWidget(1, _COL_VALUE).text() == ""


@pytest.mark.requirement("REQ-SEARCH-025")
def test_search_disabled_with_no_values_entered(qtbot: QtBot) -> None:
    dlg = SearchDialog(parent=None)
    qtbot.addWidget(dlg)
    dlg.set_rows([_make_active()])
    assert not dlg._search_button.isEnabled()


@pytest.mark.requirement("REQ-SEARCH-025")
def test_search_enabled_once_a_value_is_entered(qtbot: QtBot) -> None:
    dlg = SearchDialog(parent=None)
    qtbot.addWidget(dlg)
    dlg.set_rows([_make_active()])
    dlg._table.cellWidget(0, _COL_VALUE).setText("5")
    assert dlg._search_button.isEnabled()


@pytest.mark.requirement("REQ-SEARCH-025")
def test_search_disabled_again_after_value_cleared(qtbot: QtBot) -> None:
    dlg = SearchDialog(parent=None)
    qtbot.addWidget(dlg)
    dlg.set_rows([_make_active()])
    dlg._table.cellWidget(0, _COL_VALUE).setText("5")
    dlg._table.cellWidget(0, _COL_VALUE).setText("")
    assert not dlg._search_button.isEnabled()


@pytest.mark.requirement("REQ-SEARCH-013")
def test_search_enabled_immediately_after_prefill(qtbot: QtBot) -> None:
    dlg = SearchDialog(parent=None)
    qtbot.addWidget(dlg)
    a = _make_active()
    dlg.set_rows([a], prefill={a: 1.0})
    assert dlg._search_button.isEnabled()


@pytest.mark.requirement("REQ-SEARCH-023")
def test_search_clicked_excludes_blank_rows(qtbot: QtBot) -> None:
    dlg = SearchDialog(parent=None)
    qtbot.addWidget(dlg)
    a, b = _make_active("a"), _make_active("b")
    dlg.set_rows([a, b])
    dlg._table.cellWidget(0, _COL_VALUE).setText("5")
    # b's value left blank.

    emitted = []
    dlg.search_clicked.connect(emitted.append)
    dlg._search_button.click()

    assert len(emitted) == 1
    rows = emitted[0]
    assert len(rows) == 1
    assert rows[0].signal is a
    assert rows[0].operator == SearchOperator.EQ
    assert rows[0].value == 5.0


def test_search_clicked_uses_selected_operator(qtbot: QtBot) -> None:
    dlg = SearchDialog(parent=None)
    qtbot.addWidget(dlg)
    a = _make_active()
    dlg.set_rows([a])
    dlg._table.cellWidget(0, _COL_VALUE).setText("3000")
    combo = dlg._table.cellWidget(0, _COL_OPERATOR)
    combo.setCurrentIndex(list(SearchOperator).index(SearchOperator.GT))

    emitted = []
    dlg.search_clicked.connect(emitted.append)
    dlg._search_button.click()

    assert emitted[0][0].operator == SearchOperator.GT


@pytest.mark.requirement("REQ-SEARCH-043")
def test_show_no_match_makes_label_visible(qtbot: QtBot) -> None:
    # isHidden() (not isVisible()) reflects the widget's own explicit
    # shown/hidden flag regardless of whether the dialog itself is shown.
    dlg = SearchDialog(parent=None)
    qtbot.addWidget(dlg)
    assert dlg._no_match_label.isHidden() is True
    dlg.show_no_match()
    assert dlg._no_match_label.isHidden() is False


def test_set_rows_clears_previous_no_match_message(qtbot: QtBot) -> None:
    dlg = SearchDialog(parent=None)
    qtbot.addWidget(dlg)
    dlg.set_rows([_make_active()])
    dlg.show_no_match()
    dlg.set_rows([_make_active()])
    assert dlg._no_match_label.isHidden() is True


def test_search_clicked_clears_no_match_message(qtbot: QtBot) -> None:
    dlg = SearchDialog(parent=None)
    qtbot.addWidget(dlg)
    dlg.set_rows([_make_active()])
    dlg._table.cellWidget(0, _COL_VALUE).setText("1")
    dlg.show_no_match()
    dlg._search_button.click()
    assert dlg._no_match_label.isHidden() is True


def test_set_rows_rebuilds_and_replaces_previous_rows(qtbot: QtBot) -> None:
    dlg = SearchDialog(parent=None)
    qtbot.addWidget(dlg)
    dlg.set_rows([_make_active("a"), _make_active("b")])
    dlg.set_rows([_make_active("c")])
    assert dlg._table.rowCount() == 1
    assert dlg._table.item(0, _COL_NAME).text() == "c"


@pytest.mark.requirement("REQ-SEARCH-016")
def test_set_rows_updates_tab_label(qtbot: QtBot) -> None:
    dlg = SearchDialog(parent=None)
    qtbot.addWidget(dlg)
    dlg.set_rows([_make_active()], tab_name="Tab 2")
    assert "Tab 2" in dlg._tab_label.text()


@pytest.mark.requirement("REQ-SEARCH-016")
def test_set_rows_without_tab_name_leaves_label_unchanged(qtbot: QtBot) -> None:
    dlg = SearchDialog(parent=None)
    qtbot.addWidget(dlg)
    dlg.set_rows([_make_active()], tab_name="Tab 1")
    dlg.set_rows([_make_active()])
    assert "Tab 1" in dlg._tab_label.text()


@pytest.mark.requirement("REQ-SEARCH-018")
def test_set_rows_prefill_tuple_sets_operator_and_value(qtbot: QtBot) -> None:
    dlg = SearchDialog(parent=None)
    qtbot.addWidget(dlg)
    a = _make_active()
    dlg.set_rows([a], prefill={a: (SearchOperator.GT, 3000.0)})
    assert dlg._table.cellWidget(0, _COL_VALUE).text() == "3000"
    assert dlg._table.cellWidget(0, _COL_OPERATOR).currentData() == SearchOperator.GT


def test_current_criteria_by_name_excludes_blank_rows(qtbot: QtBot) -> None:
    dlg = SearchDialog(parent=None)
    qtbot.addWidget(dlg)
    a, b = _make_active("a"), _make_active("b")
    dlg.set_rows([a, b])
    dlg._table.cellWidget(0, _COL_VALUE).setText("5")
    assert dlg.current_criteria_by_name() == {"a": (SearchOperator.EQ, 5.0)}


def test_current_criteria_by_name_captures_operator(qtbot: QtBot) -> None:
    dlg = SearchDialog(parent=None)
    qtbot.addWidget(dlg)
    a = _make_active("a")
    dlg.set_rows([a])
    dlg._table.cellWidget(0, _COL_VALUE).setText("3000")
    combo = dlg._table.cellWidget(0, _COL_OPERATOR)
    combo.setCurrentIndex(list(SearchOperator).index(SearchOperator.GT))
    assert dlg.current_criteria_by_name() == {"a": (SearchOperator.GT, 3000.0)}
