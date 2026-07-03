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
    _fmt_value,
)
from mdf_viewer.model.interpolate import interpolate as _interpolate
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
    # Signals must behave like real signals for .connect()
    for sig in ("cursor_moved", "cursor_clicked", "delta_line_moved", "cursor_fetch_requested", "delta_fetch_requested"):
        mock_sig = MagicMock()
        mock_sig.connect = MagicMock()
        setattr(v, sig, mock_sig)
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

@pytest.mark.requirement("REQ-PLOT-070")
def test_initial_mode_is_hidden(ctrl: CursorController) -> None:
    assert ctrl.mode == CursorMode.HIDDEN


def test_connects_to_cursor_moved(view: MagicMock, table: MagicMock) -> None:
    view.cursor_moved.connect.assert_not_called()
    CursorController(view, lambda: (0.0, 1.0), table)
    view.cursor_moved.connect.assert_called_once()


# ---------------------------------------------------------------------------
# toggle cycle
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-071")
def test_toggle_hidden_to_one(ctrl: CursorController, view: MagicMock) -> None:
    ctrl.toggle()
    assert ctrl.mode == CursorMode.ONE
    view.apply_mode.assert_called_with(CursorMode.ONE, ctrl._positions)


@pytest.mark.requirement("REQ-PLOT-071")
def test_toggle_one_to_two(ctrl: CursorController) -> None:
    ctrl.toggle()
    ctrl.toggle()
    assert ctrl.mode == CursorMode.TWO


@pytest.mark.requirement("REQ-PLOT-071")
def test_toggle_two_to_hidden(ctrl: CursorController) -> None:
    ctrl.toggle()
    ctrl.toggle()
    ctrl.toggle()
    assert ctrl.mode == CursorMode.HIDDEN


@pytest.mark.requirement("REQ-PLOT-071")
def test_toggle_shows_cursor_columns_when_active(
    ctrl: CursorController, table: MagicMock
) -> None:
    ctrl.toggle()
    table.show_cursor_columns.assert_called_with(True)


@pytest.mark.requirement("REQ-PLOT-071")
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

@pytest.mark.requirement("REQ-PLOT-073")
def test_first_toggle_places_cursor_at_25_percent() -> None:
    view = MagicMock()
    view.cursor_moved = MagicMock()
    view.cursor_moved.connect = MagicMock()
    ctrl = CursorController(view, lambda: (0.0, 10.0), MagicMock(), lambda: [])
    ctrl.toggle()
    assert ctrl._positions[0] == pytest.approx(2.5)  # 25% of span


@pytest.mark.requirement("REQ-PLOT-073")
def test_first_toggle_places_second_cursor_at_75_percent() -> None:
    view = MagicMock()
    view.cursor_moved = MagicMock()
    view.cursor_moved.connect = MagicMock()
    ctrl = CursorController(view, lambda: (0.0, 10.0), MagicMock(), lambda: [])
    ctrl.toggle()
    assert ctrl._positions[1] == pytest.approx(7.5)  # 75% of span


@pytest.mark.requirement("REQ-PLOT-073")
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

@pytest.mark.requirement("REQ-PLOT-074")
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


@pytest.mark.requirement("REQ-PLOT-074")
def test_reset_hides_cursors_if_active(ctrl: CursorController, view: MagicMock) -> None:
    ctrl.toggle()
    ctrl.reset()
    assert ctrl.mode == CursorMode.HIDDEN
    view.apply_mode.assert_called_with(CursorMode.HIDDEN, ctrl._positions)


@pytest.mark.requirement("REQ-PLOT-074")
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


@pytest.mark.requirement("REQ-PLOT-080")
def test_dragging_updates_table(view: MagicMock, table: MagicMock) -> None:
    active = _make_active()
    ctrl = _make_ctrl(view, table, signals=[active])
    ctrl.toggle()
    ctrl._on_cursor_dragged(0, 0.5)
    table.update_cursor_values.assert_called()


# ---------------------------------------------------------------------------
# Signal list management
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-080")
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

@pytest.mark.requirement("REQ-PLOT-080")
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


@pytest.mark.requirement("REQ-PLOT-100")
def test_delta_is_empty_in_one_mode(view: MagicMock, table: MagicMock) -> None:
    active = _make_active()
    ctrl = _make_ctrl(view, table, signals=[active])
    ctrl.toggle()  # ONE
    ctrl._on_cursor_dragged(0, 0.25)
    args = table.update_cursor_values.call_args[0]
    assert args[3] == ""  # delta is empty with one cursor


@pytest.mark.requirement("REQ-PLOT-104")
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

@pytest.mark.requirement("REQ-PLOT-083")
def test_interpolate_at_exact_timestamp() -> None:
    active = _make_active()
    result = _interpolate(active, 0.0)
    assert result == pytest.approx(0.0, abs=1e-9)


@pytest.mark.requirement("REQ-PLOT-083")
def test_interpolate_midpoint() -> None:
    active = _make_active()
    result = _interpolate(active, 0.25)
    assert result == pytest.approx(1.0, abs=0.01)  # sin(π/2) ≈ 1


@pytest.mark.requirement("REQ-PLOT-082")
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
# _fmt_value helper
# ---------------------------------------------------------------------------

_ENUM = {0: "OFF", 1: "ACC", 2: "RUN"}


def test_fmt_value_none_is_empty() -> None:
    assert _fmt_value(None, _ENUM, True) == ""


@pytest.mark.requirement("REQ-PLOT-084")
def test_fmt_value_enum_display_on_shows_label() -> None:
    assert _fmt_value(2.0, _ENUM, True) == "RUN (2)"


@pytest.mark.requirement("REQ-PLOT-084")
def test_fmt_value_enum_display_off_shows_raw() -> None:
    assert _fmt_value(2.0, _ENUM, False) == "2"


@pytest.mark.requirement("REQ-PLOT-084")
def test_fmt_value_empty_enum_map_shows_raw() -> None:
    assert _fmt_value(2.0, {}, True) == "2"


@pytest.mark.requirement("REQ-PLOT-084")
def test_fmt_value_unknown_key_falls_back_to_raw() -> None:
    assert _fmt_value(99.0, _ENUM, True) == "99"


@pytest.mark.requirement("REQ-PLOT-084")
def test_fmt_value_rounds_to_nearest_int_for_lookup() -> None:
    assert _fmt_value(1.9, _ENUM, True) == "RUN (2)"


@pytest.mark.requirement("REQ-PLOT-084")
def test_fmt_value_no_enum_formats_as_float() -> None:
    assert _fmt_value(1.23456789, {}, True) == "1.23457"


# ---------------------------------------------------------------------------
# cursor refresh — enum signal cursor values
# ---------------------------------------------------------------------------

def _make_enum_active(enum_display_table: bool = True) -> ActiveSignal:
    t = np.array([0.0, 1.0, 2.0, 3.0])
    samples = np.array([0.0, 1.0, 2.0, 1.0])
    data = SignalData(timestamps=t, samples=samples)
    meta = SignalMetadata(
        name="ign",
        unit="",
        group_index=0,
        channel_index=0,
        enum_map={0: "OFF", 1: "ACC", 2: "RUN"},
    )
    active = ActiveSignal(data=data, metadata=meta, color=QColor(255, 0, 0))
    active.enum_display_table = enum_display_table
    return active


@pytest.mark.requirement("REQ-PLOT-084")
def test_cursor_value_shows_enum_label(view: MagicMock, table: MagicMock) -> None:
    active = _make_enum_active(enum_display_table=True)
    ctrl = _make_ctrl(view, table, signals=[active])
    ctrl.toggle()

    c1_text = table.update_cursor_values.call_args[0][1]
    assert "OFF" in c1_text or "ACC" in c1_text or "RUN" in c1_text


@pytest.mark.requirement("REQ-PLOT-084")
def test_cursor_value_raw_when_enum_display_off(view: MagicMock, table: MagicMock) -> None:
    active = _make_enum_active(enum_display_table=False)
    ctrl = _make_ctrl(view, table, signals=[active])
    ctrl.toggle()

    c1_text = table.update_cursor_values.call_args[0][1]
    # Should be a plain number, not contain a label
    assert "OFF" not in c1_text
    assert "ACC" not in c1_text
    assert "RUN" not in c1_text


@pytest.mark.requirement("REQ-PLOT-104")
def test_delta_column_always_numeric_for_enum_signal(view: MagicMock, table: MagicMock) -> None:
    active = _make_enum_active(enum_display_table=True)
    ctrl = _make_ctrl(view, table, signals=[active], x_range=(0.0, 3.0))
    ctrl.toggle()
    ctrl.toggle()  # TWO mode

    delta_text = table.update_cursor_values.call_args[0][3]
    # delta must be a number (possibly empty), never a label
    assert "OFF" not in delta_text
    assert "RUN" not in delta_text
    if delta_text:
        float(delta_text)  # must parse as a number


# ---------------------------------------------------------------------------
# _place_initial_positions — always uses get_x_range (the current view span)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-073")
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


@pytest.mark.requirement("REQ-PLOT-073")
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

@pytest.mark.requirement("REQ-PLOT-071")
def test_press_cursor1_from_hidden_goes_to_one(ctrl: CursorController) -> None:
    ctrl.press_cursor1()
    assert ctrl.mode == CursorMode.ONE


@pytest.mark.requirement("REQ-PLOT-071")
def test_press_cursor1_from_one_goes_to_hidden(ctrl: CursorController) -> None:
    ctrl.press_cursor1()
    ctrl.press_cursor1()
    assert ctrl.mode == CursorMode.HIDDEN


@pytest.mark.requirement("REQ-PLOT-071")
def test_press_cursor1_from_two_goes_to_one(ctrl: CursorController) -> None:
    ctrl.toggle()  # ONE
    ctrl.toggle()  # TWO
    ctrl.press_cursor1()
    assert ctrl.mode == CursorMode.ONE


@pytest.mark.requirement("REQ-PLOT-073")
def test_press_cursor1_initializes_positions(ctrl: CursorController) -> None:
    ctrl.press_cursor1()
    assert ctrl._initialized is True


def test_press_cursor1_calls_view(ctrl: CursorController, view: MagicMock) -> None:
    ctrl.press_cursor1()
    view.apply_mode.assert_called_with(CursorMode.ONE, ctrl._positions)


# ---------------------------------------------------------------------------
# press_cursor2 (comma key)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-071")
def test_press_cursor2_from_hidden_goes_to_two(ctrl: CursorController) -> None:
    ctrl.press_cursor2()
    assert ctrl.mode == CursorMode.TWO


@pytest.mark.requirement("REQ-PLOT-071")
def test_press_cursor2_from_one_goes_to_two(ctrl: CursorController) -> None:
    ctrl.toggle()  # ONE
    ctrl.press_cursor2()
    assert ctrl.mode == CursorMode.TWO


@pytest.mark.requirement("REQ-PLOT-071")
def test_press_cursor2_from_two_goes_to_hidden(ctrl: CursorController) -> None:
    ctrl.press_cursor2()  # TWO
    ctrl.press_cursor2()  # HIDDEN
    assert ctrl.mode == CursorMode.HIDDEN


@pytest.mark.requirement("REQ-PLOT-073")
def test_press_cursor2_initializes_positions(ctrl: CursorController) -> None:
    ctrl.press_cursor2()
    assert ctrl._initialized is True


@pytest.mark.requirement("REQ-PLOT-071")
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


@pytest.mark.requirement("REQ-PLOT-073")
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


@pytest.mark.requirement("REQ-PLOT-073")
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


# ---------------------------------------------------------------------------
# Cursor mode (1/2 vs L/R)
# ---------------------------------------------------------------------------

def _make_ctrl_mode(
    view: MagicMock,
    table: MagicMock,
    mode: str,
    x_range: tuple[float, float] = (0.0, 1.0),
    signals: list | None = None,
) -> CursorController:
    return CursorController(
        cursor_view=view,
        get_x_range=lambda: x_range,
        active_signals_table=table,
        get_active_signals=lambda: (signals or []),
        get_cursor_mode=lambda: mode,
    )


@pytest.mark.requirement("REQ-PLOT-072")
def test_12_mode_sets_cursor_1_2_headers(view: MagicMock, table: MagicMock) -> None:
    ctrl = _make_ctrl_mode(view, table, "1/2")
    ctrl.toggle()
    table.set_cursor_column_headers.assert_called_with("Cursor 1", "Cursor 2")


@pytest.mark.requirement("REQ-PLOT-072")
def test_lr_mode_sets_cursor_lr_headers(view: MagicMock, table: MagicMock) -> None:
    ctrl = _make_ctrl_mode(view, table, "L/R")
    ctrl.toggle()
    table.set_cursor_column_headers.assert_called_with("Cursor L", "Cursor R")


@pytest.mark.requirement("REQ-PLOT-072")
def test_lr_mode_left_idx_follows_position(view: MagicMock, table: MagicMock) -> None:
    ctrl = _make_ctrl_mode(view, table, "L/R")
    ctrl.toggle()   # ONE
    ctrl.toggle()   # TWO
    ctrl._positions = [0.7, 0.3]  # cursor 1 (at 0.3) is left
    ctrl._on_cursor_dragged(0, 0.7)
    assert ctrl._left_idx == 1


@pytest.mark.requirement("REQ-PLOT-072")
def test_lr_mode_tie_keeps_left_idx(view: MagicMock, table: MagicMock) -> None:
    ctrl = _make_ctrl_mode(view, table, "L/R")
    ctrl.toggle()   # ONE
    ctrl.toggle()   # TWO
    ctrl._positions = [0.3, 0.7]
    ctrl._on_cursor_dragged(0, 0.3)
    assert ctrl._left_idx == 0     # cursor 0 is left
    ctrl._positions = [0.5, 0.5]
    ctrl._on_cursor_dragged(1, 0.5)
    assert ctrl._left_idx == 0     # tie: keep previous assignment


@pytest.mark.requirement("REQ-PLOT-072")
def test_lr_mode_single_cursor_is_always_left(view: MagicMock, table: MagicMock) -> None:
    active = _make_active()
    ctrl = _make_ctrl_mode(view, table, "L/R", signals=[active])
    ctrl.toggle()  # ONE
    args = table.update_cursor_values.call_args[0]
    assert args[2] == ""   # Cursor R column is empty
    assert args[3] == ""   # delta is empty


@pytest.mark.requirement("REQ-PLOT-104")
def test_12_mode_delta_is_c2_minus_c1(view: MagicMock, table: MagicMock) -> None:
    active = _make_active()
    ctrl = _make_ctrl_mode(view, table, "1/2", signals=[active])
    ctrl.toggle()   # ONE
    ctrl.toggle()   # TWO
    ctrl._positions[0] = 0.0    # sin(0) = 0
    ctrl._positions[1] = 0.25   # sin(π/2) ≈ 1
    ctrl._on_cursor_dragged(1, 0.25)
    delta = float(table.update_cursor_values.call_args[0][3])
    assert delta == pytest.approx(1.0, abs=0.01)


@pytest.mark.requirement("REQ-PLOT-104")
def test_lr_mode_delta_is_r_minus_l(view: MagicMock, table: MagicMock) -> None:
    active = _make_active()
    ctrl = _make_ctrl_mode(view, table, "L/R", signals=[active])
    ctrl.toggle()   # ONE
    ctrl.toggle()   # TWO
    # cursor 1 (at 0.0) is left, cursor 0 (at 0.25) is right → R - L = 1 - 0 = 1
    ctrl._positions[0] = 0.25
    ctrl._positions[1] = 0.0
    ctrl._on_cursor_dragged(0, 0.25)
    delta = float(table.update_cursor_values.call_args[0][3])
    assert delta == pytest.approx(1.0, abs=0.01)


@pytest.mark.requirement("REQ-PLOT-072")
def test_set_line_colors_called_on_refresh(view: MagicMock, table: MagicMock) -> None:
    ctrl = _make_ctrl_mode(view, table, "1/2")
    ctrl.toggle()
    view.set_line_colors.assert_called()


@pytest.mark.requirement("REQ-PLOT-072")
def test_get_cursor_colors_called_on_refresh(view: MagicMock, table: MagicMock) -> None:
    custom = ((1, 2, 3), (4, 5, 6), (7, 8, 9), (10, 11, 12))
    calls = []
    ctrl = CursorController(
        cursor_view=view,
        get_x_range=lambda: (0.0, 1.0),
        active_signals_table=table,
        get_cursor_colors=lambda: (calls.append(1) or custom),
    )
    ctrl.toggle()
    assert calls, "get_cursor_colors was not called during refresh"
    view.set_line_colors.assert_called_with(custom[0], custom[1])


@pytest.mark.requirement("REQ-PLOT-072")
def test_get_cursor_colors_used_in_lr_mode(view: MagicMock, table: MagicMock) -> None:
    custom = ((1, 2, 3), (4, 5, 6), (7, 8, 9), (10, 11, 12))
    ctrl = CursorController(
        cursor_view=view,
        get_x_range=lambda: (0.0, 1.0),
        active_signals_table=table,
        get_cursor_mode=lambda: "L/R",
        get_cursor_colors=lambda: custom,
    )
    ctrl.toggle()  # ONE — single cursor uses cl and cr
    view.set_line_colors.assert_called_with(custom[2], custom[3])


@pytest.mark.requirement("REQ-PLOT-072")
def test_get_cursor_colors_defaults_when_omitted(view: MagicMock, table: MagicMock) -> None:
    ctrl = CursorController(
        cursor_view=view,
        get_x_range=lambda: (0.0, 1.0),
        active_signals_table=table,
    )
    ctrl.toggle()
    view.set_line_colors.assert_called()


@pytest.mark.requirement("REQ-PLOT-073")
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


# ---------------------------------------------------------------------------
# Delta-time
# ---------------------------------------------------------------------------

def _make_ctrl_delta(view, table, show=True, color=(200, 200, 200)):
    return CursorController(
        cursor_view=view,
        get_x_range=lambda: (0.0, 1.0),
        active_signals_table=table,
        get_show_delta_time=lambda: show,
        get_delta_time_color=lambda: color,
    )


@pytest.mark.requirement("REQ-PLOT-100")
def test_delta_time_not_shown_in_one_mode(view: MagicMock, table: MagicMock) -> None:
    ctrl = _make_ctrl_delta(view, table)
    ctrl.toggle()  # ONE
    view.update_delta_time.assert_called_with(
        x1=pytest.approx(0.0, abs=1.0),
        x2=pytest.approx(0.0, abs=1.0),
        delta_t_str="",
        y_pos=None,
        show=False,
        color=(0, 0, 0),
    )


@pytest.mark.requirement("REQ-PLOT-100")
def test_delta_time_shown_in_two_mode(view: MagicMock, table: MagicMock) -> None:
    ctrl = _make_ctrl_delta(view, table)
    ctrl.toggle()  # ONE
    ctrl.toggle()  # TWO
    call_kwargs = view.update_delta_time.call_args[1]
    assert call_kwargs["show"] is True
    assert "Δt" in call_kwargs["delta_t_str"]


@pytest.mark.requirement("REQ-PLOT-101")
def test_delta_time_hidden_when_show_false(view: MagicMock, table: MagicMock) -> None:
    ctrl = _make_ctrl_delta(view, table, show=False)
    ctrl.toggle()  # ONE
    ctrl.toggle()  # TWO
    call_kwargs = view.update_delta_time.call_args[1]
    assert call_kwargs["show"] is False


@pytest.mark.requirement("REQ-PLOT-101")
def test_delta_time_color_passed_to_view(view: MagicMock, table: MagicMock) -> None:
    ctrl = _make_ctrl_delta(view, table, color=(1, 2, 3))
    ctrl.toggle()  # ONE
    ctrl.toggle()  # TWO
    call_kwargs = view.update_delta_time.call_args[1]
    assert call_kwargs["color"] == (1, 2, 3)


@pytest.mark.requirement("REQ-PLOT-101")
def test_delta_column_header_set_in_two_mode(view: MagicMock, table: MagicMock) -> None:
    ctrl = _make_ctrl_delta(view, table)
    ctrl.toggle()  # ONE
    ctrl._positions[1] = 0.5
    ctrl.toggle()  # TWO
    calls = [str(c) for c in table.set_delta_column_header.call_args_list]
    assert any("Δt" in c for c in calls)


@pytest.mark.requirement("REQ-PLOT-101")
def test_delta_column_header_reset_when_not_two(view: MagicMock, table: MagicMock) -> None:
    ctrl = _make_ctrl_delta(view, table)
    ctrl.toggle()  # ONE
    table.set_delta_column_header.assert_called_with("Δ")


@pytest.mark.requirement("REQ-PLOT-102")
def test_delta_y_pos_remembered_after_drag(view: MagicMock, table: MagicMock) -> None:
    ctrl = _make_ctrl_delta(view, table)
    ctrl._on_delta_line_dragged(0.42)
    assert ctrl._delta_y_pos == pytest.approx(0.42)


@pytest.mark.requirement("REQ-PLOT-074")
@pytest.mark.requirement("REQ-PLOT-102")
def test_delta_y_pos_reset_on_file_load(view: MagicMock, table: MagicMock) -> None:
    ctrl = _make_ctrl_delta(view, table)
    ctrl._on_delta_line_dragged(0.42)
    ctrl.reset()
    assert ctrl._delta_y_pos is None


# ---------------------------------------------------------------------------
# Fetch — cursor chevron clicked
# ---------------------------------------------------------------------------

def _make_ctrl_fetch(
    view: MagicMock,
    table: MagicMock,
    x_range: tuple[float, float] = (0.0, 10.0),
    y_range: tuple[float, float] = (-1.0, 1.0),
) -> CursorController:
    return CursorController(
        cursor_view=view,
        get_x_range=lambda: x_range,
        active_signals_table=table,
        get_y_range=lambda: y_range,
    )


@pytest.mark.requirement("REQ-PLOT-111")
def test_fetch_cursor_sets_position_to_clicked_x(
    view: MagicMock, table: MagicMock
) -> None:
    ctrl = _make_ctrl_fetch(view, table, x_range=(0.0, 10.0))
    ctrl.toggle()
    ctrl._on_cursor_fetch(0, 1.23)
    assert ctrl._positions[0] == pytest.approx(1.23)


@pytest.mark.requirement("REQ-PLOT-111")
def test_fetch_cursor_calls_apply_mode(view: MagicMock, table: MagicMock) -> None:
    ctrl = _make_ctrl_fetch(view, table)
    ctrl.toggle()
    view.apply_mode.reset_mock()
    ctrl._on_cursor_fetch(0, 3.0)
    view.apply_mode.assert_called_once_with(CursorMode.ONE, ctrl._positions)


@pytest.mark.requirement("REQ-PLOT-111")
def test_fetch_cursor_calls_update_labels(view: MagicMock, table: MagicMock) -> None:
    ctrl = _make_ctrl_fetch(view, table)
    ctrl.toggle()
    view.update_labels.reset_mock()
    ctrl._on_cursor_fetch(0, 3.0)
    view.update_labels.assert_called()


@pytest.mark.requirement("REQ-PLOT-111")
def test_fetch_cursor_index_1(view: MagicMock, table: MagicMock) -> None:
    ctrl = _make_ctrl_fetch(view, table, x_range=(0.0, 10.0))
    ctrl.toggle()  # ONE
    ctrl.toggle()  # TWO
    ctrl._on_cursor_fetch(1, 7.5)
    assert ctrl._positions[1] == pytest.approx(7.5)


# ---------------------------------------------------------------------------
# Fetch — delta-time chevron clicked
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-112")
def test_fetch_delta_sets_position_to_clicked_y(
    view: MagicMock, table: MagicMock
) -> None:
    ctrl = _make_ctrl_fetch(view, table)
    ctrl._on_delta_fetch(0.42)
    assert ctrl._delta_y_pos == pytest.approx(0.42)


@pytest.mark.requirement("REQ-PLOT-112")
def test_fetch_delta_triggers_refresh(view: MagicMock, table: MagicMock) -> None:
    ctrl = _make_ctrl_fetch(view, table)
    ctrl.toggle()  # ONE
    ctrl.toggle()  # TWO
    view.update_delta_time.reset_mock()
    ctrl._on_delta_fetch(0.5)
    view.update_delta_time.assert_called()


# ---------------------------------------------------------------------------
# set_cursor_names — called during refresh
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-072")
def test_set_cursor_names_called_on_refresh_12_mode(
    view: MagicMock, table: MagicMock
) -> None:
    ctrl = _make_ctrl_mode(view, table, "1/2")
    ctrl.toggle()
    view.set_cursor_names.assert_called_with("Cursor 1", "Cursor 2")


@pytest.mark.requirement("REQ-PLOT-072")
def test_set_cursor_names_called_on_refresh_lr_mode(
    view: MagicMock, table: MagicMock
) -> None:
    ctrl = _make_ctrl_mode(view, table, "L/R")
    ctrl.toggle()
    view.set_cursor_names.assert_called_with("Cursor L", "Cursor R")


# ---------------------------------------------------------------------------
# Active cursor tracking
# ---------------------------------------------------------------------------

def test_active_cursor_none_initially(ctrl: CursorController) -> None:
    assert ctrl._active_cursor_idx is None


@pytest.mark.requirement("REQ-PLOT-090")
def test_active_cursor_set_to_0_on_toggle_to_one(ctrl: CursorController) -> None:
    ctrl.toggle()  # HIDDEN → ONE
    assert ctrl._active_cursor_idx == 0


@pytest.mark.requirement("REQ-PLOT-093")
def test_active_cursor_set_to_none_on_toggle_to_hidden(ctrl: CursorController) -> None:
    ctrl.toggle()   # ONE
    ctrl.toggle()   # TWO
    ctrl.toggle()   # HIDDEN
    assert ctrl._active_cursor_idx is None


@pytest.mark.requirement("REQ-PLOT-090")
def test_active_cursor_set_on_drag(ctrl: CursorController) -> None:
    ctrl.toggle()  # ONE
    ctrl.toggle()  # TWO
    ctrl._on_cursor_dragged(1, 0.8)
    assert ctrl._active_cursor_idx == 1


@pytest.mark.requirement("REQ-PLOT-090")
def test_active_cursor_set_on_click(ctrl: CursorController) -> None:
    ctrl.toggle()  # ONE
    ctrl.toggle()  # TWO
    ctrl._on_cursor_clicked(1)
    assert ctrl._active_cursor_idx == 1


@pytest.mark.requirement("REQ-PLOT-074")
def test_active_cursor_reset_on_file_load(ctrl: CursorController) -> None:
    ctrl.toggle()
    ctrl._on_cursor_clicked(0)
    ctrl.reset()
    assert ctrl._active_cursor_idx is None


# ---------------------------------------------------------------------------
# press_left / press_right — sample mode
# ---------------------------------------------------------------------------

def _make_ctrl_step(
    view: MagicMock,
    table: MagicMock,
    unit: str = "samples",
    samples: int = 1,
    pixels: int = 1,
    time_ms: float = 10.0,
    x_per_pixel: float = 0.01,
) -> CursorController:
    return CursorController(
        cursor_view=view,
        get_x_range=lambda: (0.0, 1.0),
        active_signals_table=table,
        get_cursor_step_unit=lambda: unit,
        get_cursor_step_samples=lambda: samples,
        get_cursor_step_pixels=lambda: pixels,
        get_cursor_step_time_ms=lambda: time_ms,
        get_x_per_pixel=lambda: x_per_pixel,
    )


@pytest.mark.requirement("REQ-PLOT-090")
def test_press_right_samples_moves_to_next_sample(
    view: MagicMock, table: MagicMock
) -> None:
    active = _make_active()
    ctrl = CursorController(
        cursor_view=view,
        get_x_range=lambda: (0.0, 1.0),
        active_signals_table=table,
        get_active_signals=lambda: [active],
        get_cursor_step_unit=lambda: "samples",
        get_cursor_step_samples=lambda: 1,
    )
    ctrl.toggle()  # ONE → active_cursor_idx = 0
    ctrl._positions[0] = 0.0  # exactly at first sample
    ctrl.press_right()
    assert ctrl._positions[0] > 0.0


@pytest.mark.requirement("REQ-PLOT-090")
def test_press_left_samples_moves_to_prev_sample(
    view: MagicMock, table: MagicMock
) -> None:
    active = _make_active()
    ctrl = CursorController(
        cursor_view=view,
        get_x_range=lambda: (0.0, 1.0),
        active_signals_table=table,
        get_active_signals=lambda: [active],
        get_cursor_step_unit=lambda: "samples",
        get_cursor_step_samples=lambda: 1,
    )
    ctrl.toggle()  # ONE
    ctrl._positions[0] = 0.5
    ctrl.press_left()
    assert ctrl._positions[0] < 0.5


@pytest.mark.requirement("REQ-PLOT-092")
def test_press_right_stops_at_last_sample(
    view: MagicMock, table: MagicMock
) -> None:
    active = _make_active()
    ts_last = float(active.data.timestamps[-1])
    ctrl = CursorController(
        cursor_view=view,
        get_x_range=lambda: (0.0, 1.0),
        active_signals_table=table,
        get_active_signals=lambda: [active],
        get_cursor_step_unit=lambda: "samples",
        get_cursor_step_samples=lambda: 1,
    )
    ctrl.toggle()
    ctrl._positions[0] = ts_last
    ctrl.press_right()
    assert ctrl._positions[0] == pytest.approx(ts_last)


@pytest.mark.requirement("REQ-PLOT-092")
def test_press_left_stops_at_first_sample(
    view: MagicMock, table: MagicMock
) -> None:
    active = _make_active()
    ts_first = float(active.data.timestamps[0])
    ctrl = CursorController(
        cursor_view=view,
        get_x_range=lambda: (0.0, 1.0),
        active_signals_table=table,
        get_active_signals=lambda: [active],
        get_cursor_step_unit=lambda: "samples",
        get_cursor_step_samples=lambda: 1,
    )
    ctrl.toggle()
    ctrl._positions[0] = ts_first
    ctrl.press_left()
    assert ctrl._positions[0] == pytest.approx(ts_first)


@pytest.mark.requirement("REQ-PLOT-090")
def test_press_right_samples_n_steps(
    view: MagicMock, table: MagicMock
) -> None:
    active = _make_active()  # 101 samples over [0, 1], step = 0.01
    ctrl = CursorController(
        cursor_view=view,
        get_x_range=lambda: (0.0, 1.0),
        active_signals_table=table,
        get_active_signals=lambda: [active],
        get_cursor_step_unit=lambda: "samples",
        get_cursor_step_samples=lambda: 3,
    )
    ctrl.toggle()
    ctrl._positions[0] = 0.0
    ctrl.press_right()
    assert ctrl._positions[0] == pytest.approx(0.03, abs=1e-9)


@pytest.mark.requirement("REQ-PLOT-093")
def test_press_right_no_effect_when_hidden(
    view: MagicMock, table: MagicMock
) -> None:
    active = _make_active()
    ctrl = CursorController(
        cursor_view=view,
        get_x_range=lambda: (0.0, 1.0),
        active_signals_table=table,
        get_active_signals=lambda: [active],
        get_cursor_step_unit=lambda: "samples",
        get_cursor_step_samples=lambda: 1,
    )
    ctrl._positions[0] = 0.5
    ctrl.press_right()  # HIDDEN — no effect
    assert ctrl._positions[0] == pytest.approx(0.5)


@pytest.mark.requirement("REQ-PLOT-093")
def test_press_right_no_effect_when_no_active_cursor_in_two_mode(
    view: MagicMock, table: MagicMock
) -> None:
    active = _make_active()
    ctrl = CursorController(
        cursor_view=view,
        get_x_range=lambda: (0.0, 1.0),
        active_signals_table=table,
        get_active_signals=lambda: [active],
        get_cursor_step_unit=lambda: "samples",
        get_cursor_step_samples=lambda: 1,
    )
    ctrl.toggle()  # ONE (sets active_cursor_idx = 0)
    ctrl.toggle()  # TWO
    ctrl._active_cursor_idx = None  # simulate: no cursor touched yet
    ctrl._positions[0] = 0.5
    ctrl.press_right()
    assert ctrl._positions[0] == pytest.approx(0.5)


@pytest.mark.requirement("REQ-PLOT-090")
def test_press_right_time_mode(view: MagicMock, table: MagicMock) -> None:
    active = _make_active()
    ctrl = CursorController(
        cursor_view=view,
        get_x_range=lambda: (0.0, 1.0),
        active_signals_table=table,
        get_active_signals=lambda: [active],
        get_cursor_step_unit=lambda: "time",
        get_cursor_step_time_ms=lambda: 100.0,  # 100 ms = 0.1 s
    )
    ctrl.toggle()
    ctrl._positions[0] = 0.0
    ctrl.press_right()
    assert ctrl._positions[0] == pytest.approx(0.1)


@pytest.mark.requirement("REQ-PLOT-090")
def test_press_right_pixels_mode(view: MagicMock, table: MagicMock) -> None:
    active = _make_active()
    ctrl = CursorController(
        cursor_view=view,
        get_x_range=lambda: (0.0, 1.0),
        active_signals_table=table,
        get_active_signals=lambda: [active],
        get_cursor_step_unit=lambda: "pixels",
        get_cursor_step_pixels=lambda: 5,
        get_x_per_pixel=lambda: 0.02,  # 5 px * 0.02 = 0.1 s
    )
    ctrl.toggle()
    ctrl._positions[0] = 0.0
    ctrl.press_right()
    assert ctrl._positions[0] == pytest.approx(0.1)


# ---------------------------------------------------------------------------
# Stepping's reference-signal selection (REQ-PLOT-091)
# ---------------------------------------------------------------------------

def _make_active_spaced(name: str, n: int) -> ActiveSignal:
    """A signal spanning [0, 1] with a fixed raster of 1/(n-1) — used to tell
    which signal a stepping test actually used as its reference, by its
    distinct sample spacing."""
    t = np.linspace(0.0, 1.0, n)
    data = SignalData(timestamps=t, samples=np.zeros(n))
    meta = SignalMetadata(name=name, unit="", group_index=0, channel_index=0)
    return ActiveSignal(data=data, metadata=meta, color=QColor(255, 0, 0))


@pytest.mark.requirement("REQ-PLOT-091")
def test_press_right_samples_uses_selected_signal_over_first_active(
    view: MagicMock, table: MagicMock
) -> None:
    coarse = _make_active_spaced("coarse", 11)  # spacing 0.1
    fine = _make_active_spaced("fine", 101)      # spacing 0.01
    ctrl = CursorController(
        cursor_view=view,
        get_x_range=lambda: (0.0, 1.0),
        active_signals_table=table,
        get_active_signals=lambda: [coarse, fine],
        get_selected_signal=lambda: fine,
        get_cursor_step_unit=lambda: "samples",
        get_cursor_step_samples=lambda: 1,
    )
    ctrl.toggle()
    ctrl._positions[0] = 0.0
    ctrl.press_right()
    assert ctrl._positions[0] == pytest.approx(0.01)  # fine's spacing, not coarse's


@pytest.mark.requirement("REQ-PLOT-091")
def test_press_right_samples_falls_back_to_first_active_when_none_selected(
    view: MagicMock, table: MagicMock
) -> None:
    coarse = _make_active_spaced("coarse", 11)
    fine = _make_active_spaced("fine", 101)
    ctrl = CursorController(
        cursor_view=view,
        get_x_range=lambda: (0.0, 1.0),
        active_signals_table=table,
        get_active_signals=lambda: [coarse, fine],
        get_selected_signal=lambda: None,
        get_cursor_step_unit=lambda: "samples",
        get_cursor_step_samples=lambda: 1,
    )
    ctrl.toggle()
    ctrl._positions[0] = 0.0
    ctrl.press_right()
    assert ctrl._positions[0] == pytest.approx(0.1)  # coarse (first active)'s spacing


@pytest.mark.requirement("REQ-PLOT-091")
def test_press_right_samples_noop_when_no_signal_at_all(
    view: MagicMock, table: MagicMock
) -> None:
    ctrl = CursorController(
        cursor_view=view,
        get_x_range=lambda: (0.0, 1.0),
        active_signals_table=table,
        get_active_signals=lambda: [],
        get_selected_signal=lambda: None,
        get_cursor_step_unit=lambda: "samples",
        get_cursor_step_samples=lambda: 1,
    )
    ctrl.toggle()
    ctrl._positions[0] = 0.5
    ctrl.press_right()
    assert ctrl._positions[0] == pytest.approx(0.5)
