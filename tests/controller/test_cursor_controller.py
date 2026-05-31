"""Tests for CursorController — pure unit tests, no QApplication needed."""

from __future__ import annotations

from unittest.mock import MagicMock, call

import numpy as np
import pytest
from PyQt6.QtGui import QColor

from mdf_viewer.controller.cursor_controller import (
    CursorController,
    CursorMode,
    _fmt,
    _interpolate,
)
from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.view_model.active_signal import ActiveSignal


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_active(name: str = "sig") -> ActiveSignal:
    t = np.linspace(0.0, 1.0, 101)
    data = SignalData(timestamps=t, samples=np.sin(2 * np.pi * t))
    meta = SignalMetadata(name=name, unit="V", group_index=0, channel_index=0)
    return ActiveSignal(data=data, metadata=meta, color=QColor(255, 0, 0))


@pytest.fixture()
def view() -> MagicMock:
    v = MagicMock()
    # cursor_moved must behave like a real signal for .connect()
    v.cursor_moved = MagicMock()
    v.cursor_moved.connect = MagicMock()
    return v


@pytest.fixture()
def table() -> MagicMock:
    return MagicMock()


@pytest.fixture()
def ctrl(view: MagicMock, table: MagicMock) -> CursorController:
    return CursorController(
        cursor_view=view,
        get_x_range=lambda: (0.0, 1.0),
        active_signals_table=table,
    )


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

def test_initial_mode_is_hidden(ctrl: CursorController) -> None:
    assert ctrl.mode == CursorMode.HIDDEN


def test_connects_to_cursor_moved(view: MagicMock, table: MagicMock) -> None:
    view.cursor_moved.connect.assert_not_called()
    CursorController(view, lambda: (0.0, 1.0), table)
    view.cursor_moved.connect.assert_called_once()


# ---------------------------------------------------------------------------
# toggle cycle
# ---------------------------------------------------------------------------

def test_toggle_hidden_to_one(ctrl: CursorController, view: MagicMock) -> None:
    ctrl.toggle()
    assert ctrl.mode == CursorMode.ONE
    view.apply_mode.assert_called_with(CursorMode.ONE, ctrl._positions)


def test_toggle_one_to_two(ctrl: CursorController) -> None:
    ctrl.toggle()
    ctrl.toggle()
    assert ctrl.mode == CursorMode.TWO


def test_toggle_two_to_hidden(ctrl: CursorController) -> None:
    ctrl.toggle()
    ctrl.toggle()
    ctrl.toggle()
    assert ctrl.mode == CursorMode.HIDDEN


def test_toggle_shows_cursor_columns_when_active(
    ctrl: CursorController, table: MagicMock
) -> None:
    ctrl.toggle()
    table.show_cursor_columns.assert_called_with(True)


def test_toggle_hides_cursor_columns_when_hidden(
    ctrl: CursorController, table: MagicMock
) -> None:
    ctrl.toggle()
    ctrl.toggle()
    ctrl.toggle()
    # Last call should be hide
    table.show_cursor_columns.assert_called_with(False)


def test_toggle_calls_apply_mode_on_view(
    ctrl: CursorController, view: MagicMock
) -> None:
    ctrl.toggle()
    view.apply_mode.assert_called_once()


# ---------------------------------------------------------------------------
# Initial cursor placement
# ---------------------------------------------------------------------------

def test_first_toggle_places_cursor_at_x_min() -> None:
    view = MagicMock()
    view.cursor_moved = MagicMock()
    view.cursor_moved.connect = MagicMock()
    ctrl = CursorController(view, lambda: (2.5, 7.5), MagicMock())
    ctrl.toggle()
    assert ctrl._positions[0] == pytest.approx(2.5)


def test_first_toggle_places_second_cursor_at_10_percent_span() -> None:
    view = MagicMock()
    view.cursor_moved = MagicMock()
    view.cursor_moved.connect = MagicMock()
    ctrl = CursorController(view, lambda: (0.0, 10.0), MagicMock())
    ctrl.toggle()
    assert ctrl._positions[1] == pytest.approx(1.0)  # 10% of span


def test_subsequent_toggles_use_remembered_positions(
    ctrl: CursorController,
) -> None:
    ctrl.toggle()  # HIDDEN → ONE, positions initialized
    ctrl._positions[0] = 0.42
    ctrl.toggle()  # ONE → TWO
    ctrl.toggle()  # TWO → HIDDEN
    ctrl.toggle()  # HIDDEN → ONE again
    assert ctrl._positions[0] == pytest.approx(0.42)


# ---------------------------------------------------------------------------
# reset
# ---------------------------------------------------------------------------

def test_reset_causes_reinitialisation_on_next_toggle(ctrl: CursorController) -> None:
    ctrl.toggle()  # ONE
    ctrl._positions[0] = 0.99
    ctrl.toggle()  # TWO
    ctrl.toggle()  # HIDDEN

    # Now change the range and reset
    new_range = (5.0, 10.0)
    ctrl2 = CursorController(
        MagicMock(**{"cursor_moved.connect": MagicMock()}),
        lambda: new_range,
        MagicMock(),
    )
    ctrl2.toggle()
    ctrl2._positions[0] = 0.99
    ctrl2.reset()
    ctrl2.toggle()
    assert ctrl2._positions[0] == pytest.approx(5.0)


def test_reset_hides_cursors_if_active(ctrl: CursorController, view: MagicMock) -> None:
    ctrl.toggle()
    ctrl.reset()
    assert ctrl.mode == CursorMode.HIDDEN
    view.apply_mode.assert_called_with(CursorMode.HIDDEN, ctrl._positions)


def test_reset_hides_cursor_columns(ctrl: CursorController, table: MagicMock) -> None:
    ctrl.toggle()
    ctrl.reset()
    table.show_cursor_columns.assert_called_with(False)


# ---------------------------------------------------------------------------
# on_cursor_dragged
# ---------------------------------------------------------------------------

def test_dragging_updates_position(ctrl: CursorController) -> None:
    ctrl.toggle()
    ctrl._on_cursor_dragged(0, 0.75)
    assert ctrl._positions[0] == pytest.approx(0.75)


def test_dragging_updates_table(ctrl: CursorController, table: MagicMock) -> None:
    active = _make_active()
    ctrl.on_signal_added(active)
    ctrl.toggle()
    ctrl._on_cursor_dragged(0, 0.5)
    table.update_cursor_values.assert_called()


# ---------------------------------------------------------------------------
# Signal list management
# ---------------------------------------------------------------------------

def test_on_signal_added_refreshes_labels(ctrl: CursorController, view: MagicMock) -> None:
    ctrl.toggle()
    active = _make_active()
    ctrl.on_signal_added(active)
    view.update_labels.assert_called()


def test_on_signal_removed_calls_view(ctrl: CursorController, view: MagicMock) -> None:
    active = _make_active()
    ctrl.on_signal_added(active)
    ctrl.on_signal_removed(active)
    view.remove_labels_for.assert_called_with(active)


def test_on_all_signals_cleared(ctrl: CursorController, view: MagicMock) -> None:
    ctrl.on_signal_added(_make_active("a"))
    ctrl.on_signal_added(_make_active("b"))
    ctrl.on_all_signals_cleared()
    view.clear_labels.assert_called_once()


# ---------------------------------------------------------------------------
# Table value computation
# ---------------------------------------------------------------------------

def test_table_values_updated_on_drag(ctrl: CursorController, table: MagicMock) -> None:
    active = _make_active()
    ctrl.on_signal_added(active)
    ctrl.toggle()  # ONE
    ctrl._on_cursor_dragged(0, 0.25)  # sin(2π·0.25) = 1.0
    table.update_cursor_values.assert_called()
    args = table.update_cursor_values.call_args[0]
    assert args[0] is active
    # c1 should be ~1.0
    assert float(args[1]) == pytest.approx(1.0, abs=0.01)


def test_delta_is_empty_in_one_mode(ctrl: CursorController, table: MagicMock) -> None:
    active = _make_active()
    ctrl.on_signal_added(active)
    ctrl.toggle()  # ONE
    ctrl._on_cursor_dragged(0, 0.25)
    args = table.update_cursor_values.call_args[0]
    assert args[3] == ""  # delta is empty with one cursor


def test_delta_computed_in_two_mode(ctrl: CursorController, table: MagicMock) -> None:
    active = _make_active()
    ctrl.on_signal_added(active)
    ctrl.toggle()  # ONE
    ctrl.toggle()  # TWO
    ctrl._positions[0] = 0.0   # sin(0) = 0
    ctrl._positions[1] = 0.25  # sin(π/2) = 1
    ctrl._on_cursor_dragged(1, 0.25)
    args = table.update_cursor_values.call_args[0]
    delta = float(args[3])
    assert delta == pytest.approx(1.0, abs=0.01)


# ---------------------------------------------------------------------------
# _interpolate helper
# ---------------------------------------------------------------------------

def test_interpolate_at_exact_timestamp() -> None:
    active = _make_active()
    result = _interpolate(active, 0.0)
    assert result == pytest.approx(0.0, abs=1e-9)


def test_interpolate_midpoint() -> None:
    active = _make_active()
    result = _interpolate(active, 0.25)
    assert result == pytest.approx(1.0, abs=0.01)  # sin(π/2) ≈ 1


def test_interpolate_out_of_range_returns_none() -> None:
    active = _make_active()
    assert _interpolate(active, -0.1) is None
    assert _interpolate(active, 1.1) is None


# ---------------------------------------------------------------------------
# _fmt helper
# ---------------------------------------------------------------------------

def test_fmt_none_is_empty() -> None:
    assert _fmt(None) == ""


def test_fmt_float() -> None:
    assert _fmt(1.23456789) == "1.23457"


def test_fmt_zero() -> None:
    assert _fmt(0.0) == "0"
