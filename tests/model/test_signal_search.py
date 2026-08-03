"""Tests for model.signal_search (#110).

Covers REQ-SEARCH-030 (last-known-value/zero-order-hold), REQ-SEARCH-031
(scan grid = fastest raster among included rows), REQ-SEARCH-032 (shared
display-time timeline), and REQ-SEARCH-041 (strict > on `after`).
"""

from __future__ import annotations

import numpy as np
import pytest
from PyQt6.QtGui import QColor

from mdf_viewer.model.loaded_measurement import LoadedMeasurement
from mdf_viewer.model.mdf_loader import MdfLoader
from mdf_viewer.model.measurement import MeasurementInfo
from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.model.signal_search import SearchOperator, SearchRow, find_match
from mdf_viewer.view_model.active_signal import ActiveSignal


def _make_active(
    timestamps: list[float],
    samples: list[float],
    measurement: LoadedMeasurement | None = None,
) -> ActiveSignal:
    data = SignalData(timestamps=np.array(timestamps), samples=np.array(samples))
    meta = SignalMetadata(name="sig")
    return ActiveSignal(data=data, metadata=meta, color=QColor(255, 0, 0), measurement=measurement)


def test_find_match_empty_rows_returns_none() -> None:
    assert find_match([], after=None) is None


def test_find_match_single_signal_equals() -> None:
    signal = _make_active([0.0, 1.0, 2.0, 3.0], [0.0, 5.0, 8.0, 5.0])
    rows = [SearchRow(signal=signal, operator=SearchOperator.EQ, value=8.0)]
    assert find_match(rows, after=None) == 2.0


def test_find_match_greater_than() -> None:
    signal = _make_active([0.0, 1.0, 2.0, 3.0], [0.0, 1500.0, 3500.0, 4000.0])
    rows = [SearchRow(signal=signal, operator=SearchOperator.GT, value=3000.0)]
    assert find_match(rows, after=None) == 2.0


@pytest.mark.requirement("REQ-SEARCH-030")
@pytest.mark.requirement("REQ-SEARCH-031")
def test_find_match_and_conjunction_uses_zero_order_hold_on_slower_signal() -> None:
    # A ticks every 10ms, B every 100ms — B's value at t=30ms must be its
    # last-known value from t=0ms (zero-order-hold), not interpolated.
    a = _make_active([0.0, 0.01, 0.02, 0.03, 0.04], [0.0, 1.0, 5.0, 5.0, 5.0])
    b = _make_active([0.0, 0.1, 0.2], [1.0, 9.0, 9.0])
    rows = [
        SearchRow(signal=a, operator=SearchOperator.EQ, value=5.0),
        SearchRow(signal=b, operator=SearchOperator.GT, value=7.0),
    ]
    # b's value is held at 1.0 (its t=0 sample) all the way until t=0.1,
    # so "b > 7" never holds while a first equals 5 at t=0.02.
    assert find_match(rows, after=None) is None

    b_early_high = _make_active([0.0, 0.1, 0.2], [9.0, 1.0, 1.0])
    rows2 = [
        SearchRow(signal=a, operator=SearchOperator.EQ, value=5.0),
        SearchRow(signal=b_early_high, operator=SearchOperator.GT, value=7.0),
    ]
    # Now b is held at 9.0 (from t=0) when a first equals 5 at t=0.02.
    assert find_match(rows2, after=None) == 0.02


def test_find_match_row_before_its_first_sample_never_matches() -> None:
    # Mismatched-measurement lengths (REQ-SEARCH-024): the fast reference
    # scans back before the slow row-signal's first sample even exists.
    # Rate gap is large and unambiguous so this doesn't hinge on
    # floating-point tie-breaking between the two rates.
    fast = _make_active([0.0, 0.001, 0.002, 0.003, 0.004], [1.0, 1.0, 1.0, 1.0, 1.0])
    late_start = _make_active([0.05, 0.06], [1.0, 1.0])
    rows = [
        SearchRow(signal=fast, operator=SearchOperator.EQ, value=1.0),
        SearchRow(signal=late_start, operator=SearchOperator.EQ, value=1.0),
    ]
    assert find_match(rows, after=None) is None


def test_find_match_holds_last_value_forever_past_last_sample() -> None:
    signal = _make_active([0.0, 0.01], [1.0, 9.0])
    other = _make_active([0.0, 0.01, 0.02, 0.03], [0.0, 0.0, 0.0, 0.0])
    rows = [
        SearchRow(signal=signal, operator=SearchOperator.EQ, value=9.0),
        SearchRow(signal=other, operator=SearchOperator.EQ, value=0.0),
    ]
    # signal's last sample (9.0 at t=0.01) is held through t=0.02 and 0.03.
    assert find_match(rows, after=None) == 0.01


def test_find_match_after_filters_strictly_greater() -> None:
    signal = _make_active([0.0, 1.0, 2.0, 3.0], [5.0, 5.0, 5.0, 5.0])
    rows = [SearchRow(signal=signal, operator=SearchOperator.EQ, value=5.0)]
    assert find_match(rows, after=0.0) == 1.0
    # Re-running with the new match as `after` must not re-find it.
    assert find_match(rows, after=3.0) is None


def test_find_match_zero_sample_row_signal_never_matches() -> None:
    reference = _make_active([0.0, 1.0, 2.0], [1.0, 1.0, 1.0])
    empty = _make_active([], [])
    rows = [
        SearchRow(signal=reference, operator=SearchOperator.EQ, value=1.0),
        SearchRow(signal=empty, operator=SearchOperator.EQ, value=1.0),
    ]
    assert find_match(rows, after=None) is None


def test_find_match_scans_along_fastest_raster_among_included_rows_only() -> None:
    # A transient spike on the fast signal, invisible if the scan grid were
    # driven by the slow signal instead (REQ-SEARCH-031).
    fast = _make_active([0.0, 0.01, 0.02, 0.03, 0.04], [0.0, 0.0, 99.0, 0.0, 0.0])
    slow = _make_active([0.0, 0.1], [1.0, 1.0])
    rows = [
        SearchRow(signal=fast, operator=SearchOperator.EQ, value=99.0),
        SearchRow(signal=slow, operator=SearchOperator.EQ, value=1.0),
    ]
    assert find_match(rows, after=None) == 0.02


@pytest.mark.requirement("REQ-SEARCH-032")
def test_find_match_respects_measurement_offset() -> None:
    measurement = LoadedMeasurement(
        loader=MdfLoader(), info=MeasurementInfo(file_name="run1.mf4"), label="run1", offset_s=100.0,
    )
    signal = _make_active([0.0, 1.0, 2.0], [0.0, 42.0, 0.0], measurement=measurement)
    rows = [SearchRow(signal=signal, operator=SearchOperator.EQ, value=42.0)]
    # Raw match is at t=1.0; display time shifts it by the offset.
    assert find_match(rows, after=None) == 101.0
