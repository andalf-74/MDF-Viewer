"""Tests for nearest_instant_by_value() / step_by_axis_value() (#86)."""

from __future__ import annotations

import numpy as np
import pytest
from PyQt6.QtGui import QColor

from mdf_viewer.model.axis_cursor import (
    nearest_instant_by_value,
    step_by_axis_value,
    time_to_axis_render_x,
)
from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.view_model.active_signal import ActiveSignal


def _make_axis(t: list[float], values: list[float]) -> ActiveSignal:
    data = SignalData(timestamps=np.array(t), samples=np.array(values))
    meta = SignalMetadata(name="axis")
    return ActiveSignal(data=data, metadata=meta, color=QColor(255, 0, 0))


def test_time_to_axis_render_x_interpolates() -> None:
    axis = _make_axis([0.0, 1.0, 2.0], [10.0, 20.0, 30.0])
    assert time_to_axis_render_x(axis, 0.5) == 15.0


def test_time_to_axis_render_x_clamps_out_of_range() -> None:
    axis = _make_axis([0.0, 1.0, 2.0], [10.0, 20.0, 30.0])
    assert time_to_axis_render_x(axis, -5.0) == 10.0
    assert time_to_axis_render_x(axis, 5.0) == 30.0


def test_time_to_axis_render_x_empty_axis_returns_zero() -> None:
    axis = _make_axis([], [])
    assert time_to_axis_render_x(axis, 1.0) == 0.0


@pytest.mark.requirement("REQ-XAXIS-041")
def test_nearest_instant_finds_exact_match() -> None:
    axis = _make_axis([0.0, 1.0, 2.0, 3.0], [0.0, 5.0, 10.0, 15.0])
    assert nearest_instant_by_value(axis, 10.0, current_time=0.0) == 2.0


@pytest.mark.requirement("REQ-XAXIS-041")
def test_nearest_instant_ties_break_by_nearest_current_time() -> None:
    # Value 5.0 occurs at t=1.0 and t=3.0 (a standstill/repeat) — with
    # current_time closer to 3.0, that instant should win the tie.
    axis = _make_axis([0.0, 1.0, 2.0, 3.0], [0.0, 5.0, 10.0, 5.0])
    assert nearest_instant_by_value(axis, 5.0, current_time=2.9) == 3.0
    assert nearest_instant_by_value(axis, 5.0, current_time=0.1) == 1.0


@pytest.mark.requirement("REQ-XAXIS-043")
def test_dragging_within_standstill_span_stays_pinned_to_current() -> None:
    # A flat span (standstill) at value 5.0 from t=1..3 — dragging anywhere
    # within it, when the cursor is already at t=2.0, resolves back to 2.0
    # (the nearest-to-current tie-break), i.e. the cursor cannot be dragged
    # to a different instant within the flat span at all.
    axis = _make_axis([0.0, 1.0, 2.0, 3.0, 4.0], [0.0, 5.0, 5.0, 5.0, 10.0])
    assert nearest_instant_by_value(axis, 5.0, current_time=2.0) == 2.0


def test_nearest_instant_with_no_current_time_takes_first_match() -> None:
    axis = _make_axis([0.0, 1.0, 2.0, 3.0], [0.0, 5.0, 10.0, 5.0])
    assert nearest_instant_by_value(axis, 5.0, current_time=None) == 1.0


def test_nearest_instant_empty_axis_falls_back_to_current_time() -> None:
    axis = _make_axis([], [])
    assert nearest_instant_by_value(axis, 5.0, current_time=3.0) == 3.0
    assert nearest_instant_by_value(axis, 5.0, current_time=None) == 0.0


@pytest.mark.requirement("REQ-XAXIS-050")
def test_step_by_axis_value_advances_until_amount_exceeded() -> None:
    axis = _make_axis([0.0, 1.0, 2.0, 3.0, 4.0], [0.0, 1.0, 2.0, 3.0, 10.0])
    # From t=0 (value 0.0), stepping forward by >=5.0 skips 1/2/3 and lands on t=4.
    assert step_by_axis_value(axis, current_time=0.0, direction=1, amount=5.0) == 4.0


@pytest.mark.requirement("REQ-XAXIS-051")
def test_step_by_axis_value_skips_standstill_span() -> None:
    # A near-flat span (0.3, well under the 4.0 threshold) at t=1..3, then a
    # real jump to 10.0 at t=4 — stepping must skip past the standstill
    # instants entirely rather than stopping at the first tiny change.
    axis = _make_axis([0.0, 1.0, 2.0, 3.0, 4.0], [0.0, 0.3, 0.3, 0.3, 10.0])
    assert step_by_axis_value(axis, current_time=0.0, direction=1, amount=4.0) == 4.0


def test_step_by_axis_value_clamps_at_boundary() -> None:
    axis = _make_axis([0.0, 1.0, 2.0], [0.0, 1.0, 2.0])
    assert step_by_axis_value(axis, current_time=2.0, direction=1, amount=100.0) == 2.0
    assert step_by_axis_value(axis, current_time=0.0, direction=-1, amount=100.0) == 0.0


def test_step_by_axis_value_backward() -> None:
    axis = _make_axis([0.0, 1.0, 2.0, 3.0], [10.0, 9.0, 8.0, 0.0])
    # From t=3 (value 0.0) stepping backward: t=2 (value 8.0) already
    # exceeds the amount=5.0 threshold from the fixed starting value, so
    # stepping stops there rather than continuing to t=0.
    assert step_by_axis_value(axis, current_time=3.0, direction=-1, amount=5.0) == 2.0


def test_step_by_axis_value_empty_axis_is_noop() -> None:
    axis = _make_axis([], [])
    assert step_by_axis_value(axis, current_time=3.0, direction=1, amount=1.0) == 3.0
