"""Tests for CursorController — pure unit tests, no QApplication needed."""

from __future__ import annotations

from unittest.mock import MagicMock

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
        get_active_signals=lambda: [],
    )


def _make_ctrl(
    view: MagicMock,
    table: MagicMock,
    signals: list | None = None,
    x_range: tuple[float, float] = (0.0, 1.0),
) -> CursorController:
    sigs = signals or []
    return CursorController(
        cursor_view=view,
        get_x_range=lambda: x_range,
        active_signals_table=table,
        get_active_signals=lambda: sigs,
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

def test_first_toggle_places_cursor_at_25_percent() -> None:
    view = MagicMock()
    view.cursor_moved = MagicMock()
    view.cursor_moved.connect = MagicMock()
    ctrl = CursorController(view, lambda: (0.0, 10.0), MagicMock(), lambda: [])
    ctrl.toggle()
    assert ctrl._positions[0] == pytest.approx(2.5)  # 25% of span


def test_first_toggle_places_second_cursor_at_75_percent() -> None:
    view = MagicMock()
    view.cursor_moved = MagicMock()
    view.cursor_moved.connect = MagicMock()
    ctrl = CursorController(view, lambda: (0.0, 10.0), MagicMock(), lambda: [])
    ctrl.toggle()
    assert ctrl._positions[1] == pytest.approx(7.5)  # 75% of span


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
        lambda: [],
    )
    ctrl2.toggle()
    ctrl2._positions[0] = 0.99
    ctrl2.reset()
    ctrl2.toggle()
    assert ctrl2._positions[0] == pytest.approx(6.25)  # 25% of (5, 10)


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


def test_dragging_updates_table(view: MagicMock, table: MagicMock) -> None:
    active = _make_active()
    ctrl = _make_ctrl(view, table, signals=[active])
    ctrl.toggle()
    ctrl._on_cursor_dragged(0, 0.5)
    table.update_cursor_values.assert_called()


# ---------------------------------------------------------------------------
# Signal list management
# ---------------------------------------------------------------------------

def test_refresh_updates_labels(view: MagicMock, table: MagicMock) -> None:
    active = _make_active()
    ctrl = _make_ctrl(view, table, signals=[active])
    ctrl.toggle()
    view.update_labels.reset_mock()
    ctrl.refresh()
    view.update_labels.assert_called()


def test_on_signal_removed_calls_view(ctrl: CursorController, view: MagicMock) -> None:
    active = _make_active()
    ctrl.on_signal_removed(active)
    view.remove_labels_for.assert_called_with(active)


def test_on_all_signals_cleared(ctrl: CursorController, view: MagicMock) -> None:
    ctrl.on_all_signals_cleared()
    view.clear_labels.assert_called_once()


# ---------------------------------------------------------------------------
# Table value computation
# ---------------------------------------------------------------------------

def test_table_values_updated_on_drag(view: MagicMock, table: MagicMock) -> None:
    active = _make_active()
    ctrl = _make_ctrl(view, table, signals=[active])
    ctrl.toggle()  # ONE
    ctrl._on_cursor_dragged(0, 0.25)  # sin(2π·0.25) = 1.0
    table.update_cursor_values.assert_called()
    args = table.update_cursor_values.call_args[0]
    assert args[0] is active
    # c1 should be ~1.0
    assert float(args[1]) == pytest.approx(1.0, abs=0.01)


def test_delta_is_empty_in_one_mode(view: MagicMock, table: MagicMock) -> None:
    active = _make_active()
    ctrl = _make_ctrl(view, table, signals=[active])
    ctrl.toggle()  # ONE
    ctrl._on_cursor_dragged(0, 0.25)
    args = table.update_cursor_values.call_args[0]
    assert args[3] == ""  # delta is empty with one cursor


def test_delta_computed_in_two_mode(view: MagicMock, table: MagicMock) -> None:
    active = _make_active()
    ctrl = _make_ctrl(view, table, signals=[active])
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


# ---------------------------------------------------------------------------
# _place_initial_positions — always uses get_x_range (the current view span)
# ---------------------------------------------------------------------------

def test_first_toggle_uses_get_x_range(view: MagicMock, table: MagicMock) -> None:
    ctrl = CursorController(
        cursor_view=view,
        get_x_range=lambda: (2.0, 4.0),
        active_signals_table=table,
    )
    ctrl.toggle()

    positions = view.apply_mode.call_args[0][1]
    assert positions[0] == pytest.approx(2.5)   # 25% of (2, 4)
    assert positions[1] == pytest.approx(3.5)   # 75% of (2, 4)


def test_first_toggle_uses_get_x_range_even_with_signals(
    view: MagicMock, table: MagicMock
) -> None:
    # Signal timestamps span 5–10; view range is 0–1. Cursors should use view range.
    t = np.linspace(5.0, 10.0, 50)
    active = ActiveSignal(
        data=SignalData(timestamps=t, samples=np.zeros(50)),
        metadata=SignalMetadata(name="s", unit="", group_index=0, channel_index=0),
        color=QColor(255, 0, 0),
    )
    ctrl = _make_ctrl(view, table, signals=[active], x_range=(0.0, 1.0))
    ctrl.toggle()

    positions = view.apply_mode.call_args[0][1]
    assert positions[0] == pytest.approx(0.25)  # 25% of (0, 1)
    assert positions[1] == pytest.approx(0.75)  # 75% of (0, 1)


# ---------------------------------------------------------------------------
# press_cursor1 (dot key)
# ---------------------------------------------------------------------------

def test_press_cursor1_from_hidden_goes_to_one(ctrl: CursorController) -> None:
    ctrl.press_cursor1()
    assert ctrl.mode == CursorMode.ONE


def test_press_cursor1_from_one_goes_to_hidden(ctrl: CursorController) -> None:
    ctrl.press_cursor1()
    ctrl.press_cursor1()
    assert ctrl.mode == CursorMode.HIDDEN


def test_press_cursor1_from_two_goes_to_one(ctrl: CursorController) -> None:
    ctrl.toggle()  # ONE
    ctrl.toggle()  # TWO
    ctrl.press_cursor1()
    assert ctrl.mode == CursorMode.ONE


def test_press_cursor1_initializes_positions(ctrl: CursorController) -> None:
    ctrl.press_cursor1()
    assert ctrl._initialized is True


def test_press_cursor1_calls_view(ctrl: CursorController, view: MagicMock) -> None:
    ctrl.press_cursor1()
    view.apply_mode.assert_called_with(CursorMode.ONE, ctrl._positions)


# ---------------------------------------------------------------------------
# press_cursor2 (comma key)
# ---------------------------------------------------------------------------

def test_press_cursor2_from_hidden_goes_to_two(ctrl: CursorController) -> None:
    ctrl.press_cursor2()
    assert ctrl.mode == CursorMode.TWO


def test_press_cursor2_from_one_goes_to_two(ctrl: CursorController) -> None:
    ctrl.toggle()  # ONE
    ctrl.press_cursor2()
    assert ctrl.mode == CursorMode.TWO


def test_press_cursor2_from_two_goes_to_hidden(ctrl: CursorController) -> None:
    ctrl.press_cursor2()  # TWO
    ctrl.press_cursor2()  # HIDDEN
    assert ctrl.mode == CursorMode.HIDDEN


def test_press_cursor2_initializes_positions(ctrl: CursorController) -> None:
    ctrl.press_cursor2()
    assert ctrl._initialized is True


def test_press_cursor2_shows_cursor_columns(
    ctrl: CursorController, table: MagicMock
) -> None:
    ctrl.press_cursor2()
    table.show_cursor_columns.assert_called_with(True)


# ---------------------------------------------------------------------------
# zoom_to_cursors
# ---------------------------------------------------------------------------

def test_zoom_to_cursors_returns_none_when_hidden(ctrl: CursorController) -> None:
    assert ctrl.zoom_to_cursors() is None


def test_zoom_to_cursors_returns_none_in_one_mode(ctrl: CursorController) -> None:
    ctrl.toggle()  # ONE
    assert ctrl.zoom_to_cursors() is None


def test_zoom_to_cursors_returns_ordered_span_in_two_mode(ctrl: CursorController) -> None:
    ctrl.toggle()   # ONE
    ctrl.toggle()   # TWO — places cursors at x_min and x_min + 10% span
    x_min, x_max = ctrl.zoom_to_cursors()
    assert x_min < x_max


def test_zoom_to_cursors_orders_positions(ctrl: CursorController) -> None:
    ctrl.toggle()
    ctrl.toggle()  # TWO
    # Force positions so cursor 2 is left of cursor 1.
    ctrl._positions = [0.8, 0.2]
    x_min, x_max = ctrl.zoom_to_cursors()
    assert x_min == 0.2
    assert x_max == 0.8


# ---------------------------------------------------------------------------
# mode_changed callback
# ---------------------------------------------------------------------------

def test_mode_changed_callback_fired_on_toggle(ctrl: CursorController) -> None:
    seen = []
    ctrl.set_mode_changed_callback(seen.append)
    ctrl.toggle()
    assert seen == [CursorMode.ONE]


def test_mode_changed_callback_fired_on_each_toggle(ctrl: CursorController) -> None:
    seen = []
    ctrl.set_mode_changed_callback(seen.append)
    ctrl.toggle()   # ONE
    ctrl.toggle()   # TWO
    ctrl.toggle()   # HIDDEN
    assert seen == [CursorMode.ONE, CursorMode.TWO, CursorMode.HIDDEN]


def test_mode_changed_callback_fired_on_reset(ctrl: CursorController) -> None:
    seen = []
    ctrl.toggle()  # ONE — so reset has something to do
    ctrl.set_mode_changed_callback(seen.append)
    ctrl.reset()
    assert seen == [CursorMode.HIDDEN]


def test_mode_changed_callback_not_fired_on_reset_when_already_hidden(
    ctrl: CursorController,
) -> None:
    seen = []
    ctrl.set_mode_changed_callback(seen.append)
    ctrl.reset()  # already HIDDEN — no state change, no callback
    assert seen == []


# ---------------------------------------------------------------------------
# Cursor persistence
# ---------------------------------------------------------------------------

def _make_ctrl_persistent(
    view: MagicMock,
    table: MagicMock,
    persistent: bool,
    x_range: tuple[float, float] = (0.0, 1.0),
) -> CursorController:
    return CursorController(
        cursor_view=view,
        get_x_range=lambda: x_range,
        active_signals_table=table,
        get_active_signals=lambda: [],
        get_cursor_persistent=lambda: persistent,
    )


def test_persistence_on_keeps_positions_after_hide_show(
    view: MagicMock, table: MagicMock
) -> None:
    ctrl = _make_ctrl_persistent(view, table, persistent=True)
    ctrl.toggle()             # HIDDEN → ONE; placed at 25%/75%
    ctrl._positions[0] = 0.42
    ctrl.toggle()             # ONE → TWO
    ctrl.toggle()             # TWO → HIDDEN
    ctrl.toggle()             # HIDDEN → ONE; persistence=on → keep positions
    assert ctrl._positions[0] == pytest.approx(0.42)


def test_persistence_off_repositions_cursors_on_show(
    view: MagicMock, table: MagicMock
) -> None:
    ctrl = _make_ctrl_persistent(view, table, persistent=False, x_range=(0.0, 10.0))
    ctrl.toggle()             # HIDDEN → ONE; placed at 2.5/7.5
    ctrl._positions[0] = 9.0
    ctrl.toggle()             # ONE → TWO
    ctrl.toggle()             # TWO → HIDDEN
    ctrl.toggle()             # HIDDEN → ONE; persistence=off → reposition
    assert ctrl._positions[0] == pytest.approx(2.5)


def test_persistence_defaults_to_on(view: MagicMock, table: MagicMock) -> None:
    ctrl = CursorController(
        cursor_view=view,
        get_x_range=lambda: (0.0, 1.0),
        active_signals_table=table,
    )
    ctrl.toggle()
    ctrl._positions[0] = 0.99
    ctrl.toggle()   # TWO
    ctrl.toggle()   # HIDDEN
    ctrl.toggle()   # ONE — should keep 0.99
    assert ctrl._positions[0] == pytest.approx(0.99)
