"""Tests for highest_rate_signal() (#146, extracted for #110 reuse)."""

from __future__ import annotations

import numpy as np
from PyQt6.QtGui import QColor

from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.model.signal_rate import highest_rate_signal
from mdf_viewer.view_model.active_signal import ActiveSignal


def _make_active(timestamps: list[float]) -> ActiveSignal:
    t = np.array(timestamps)
    y = np.zeros_like(t)
    data = SignalData(timestamps=t, samples=y)
    meta = SignalMetadata(name="sig")
    return ActiveSignal(data=data, metadata=meta, color=QColor(255, 0, 0))


def test_highest_rate_signal_picks_fastest_raster() -> None:
    slow = _make_active([0.0, 0.1, 0.2])  # 10 Hz
    fast = _make_active([0.0, 0.01, 0.02, 0.03])  # 100 Hz
    assert highest_rate_signal([slow, fast]) is fast


def test_highest_rate_signal_empty_list_returns_none() -> None:
    assert highest_rate_signal([]) is None


def test_highest_rate_signal_ties_keep_first_candidate() -> None:
    a = _make_active([0.0, 1.0])
    b = _make_active([0.0, 1.0])
    assert highest_rate_signal([a, b]) is a


def test_highest_rate_signal_single_sample_signal_rates_lowest() -> None:
    single = _make_active([0.0])
    multi = _make_active([0.0, 1.0, 2.0])
    assert highest_rate_signal([single, multi]) is multi
    assert highest_rate_signal([single]) is single
