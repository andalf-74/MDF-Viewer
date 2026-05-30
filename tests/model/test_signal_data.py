"""Tests for SignalData — verifies the pure-data invariants."""

from __future__ import annotations

import numpy as np
import pytest

from mdf_viewer.model.signal_data import SignalData


def test_sample_count_matches_array_length() -> None:
    data = SignalData(
        timestamps=np.array([0.0, 0.1, 0.2]),
        samples=np.array([1.0, 2.0, 3.0]),
    )
    assert data.sample_count == 3


def test_mismatched_lengths_raise() -> None:
    with pytest.raises(ValueError):
        SignalData(
            timestamps=np.array([0.0, 0.1]),
            samples=np.array([1.0, 2.0, 3.0]),
        )
