"""Tests for SearchController's find-next/restart state (#110, REQ-SEARCH-041/042)."""

from __future__ import annotations

import numpy as np
from PyQt6.QtGui import QColor

from mdf_viewer.controller.search_controller import SearchController
from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.model.signal_search import SearchOperator, SearchRow
from mdf_viewer.view_model.active_signal import ActiveSignal


def _make_active(timestamps: list[float], samples: list[float]) -> ActiveSignal:
    data = SignalData(timestamps=np.array(timestamps), samples=np.array(samples))
    meta = SignalMetadata(name="sig")
    return ActiveSignal(data=data, metadata=meta, color=QColor(255, 0, 0))


def test_run_with_no_prior_search_starts_from_beginning() -> None:
    signal = _make_active([0.0, 1.0, 2.0, 3.0], [5.0, 5.0, 5.0, 5.0])
    rows = [SearchRow(signal=signal, operator=SearchOperator.EQ, value=5.0)]
    ctrl = SearchController()
    assert ctrl.run(rows) == 0.0


def test_run_repeated_with_unchanged_criteria_finds_next() -> None:
    signal = _make_active([0.0, 1.0, 2.0, 3.0], [5.0, 5.0, 5.0, 5.0])
    rows = [SearchRow(signal=signal, operator=SearchOperator.EQ, value=5.0)]
    ctrl = SearchController()
    assert ctrl.run(rows) == 0.0
    assert ctrl.run(rows) == 1.0
    assert ctrl.run(rows) == 2.0
    assert ctrl.run(rows) == 3.0
    assert ctrl.run(rows) is None


def test_run_with_changed_value_restarts_from_beginning() -> None:
    signal = _make_active([0.0, 1.0, 2.0, 3.0], [5.0, 9.0, 5.0, 9.0])
    ctrl = SearchController()
    rows_a = [SearchRow(signal=signal, operator=SearchOperator.EQ, value=5.0)]
    assert ctrl.run(rows_a) == 0.0
    rows_b = [SearchRow(signal=signal, operator=SearchOperator.EQ, value=9.0)]
    # Different criteria — must not continue from rows_a's last match (0.0).
    assert ctrl.run(rows_b) == 1.0


def test_run_with_changed_operator_restarts_from_beginning() -> None:
    signal = _make_active([0.0, 1.0, 2.0, 3.0], [5.0, 5.0, 5.0, 5.0])
    ctrl = SearchController()
    rows_eq = [SearchRow(signal=signal, operator=SearchOperator.EQ, value=5.0)]
    assert ctrl.run(rows_eq) == 0.0
    rows_ge = [SearchRow(signal=signal, operator=SearchOperator.GE, value=5.0)]
    assert ctrl.run(rows_ge) == 0.0  # restarted, not continuing from 0.0 as `after`


def test_reset_forces_next_run_to_restart_from_beginning() -> None:
    signal = _make_active([0.0, 1.0, 2.0], [5.0, 5.0, 5.0])
    rows = [SearchRow(signal=signal, operator=SearchOperator.EQ, value=5.0)]
    ctrl = SearchController()
    assert ctrl.run(rows) == 0.0
    ctrl.reset()
    assert ctrl.run(rows) == 0.0


def test_run_no_match_then_repeated_click_stays_no_match() -> None:
    signal = _make_active([0.0, 1.0, 2.0], [1.0, 1.0, 1.0])
    rows = [SearchRow(signal=signal, operator=SearchOperator.EQ, value=99.0)]
    ctrl = SearchController()
    assert ctrl.run(rows) is None
    assert ctrl.run(rows) is None
