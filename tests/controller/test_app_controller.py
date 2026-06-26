"""Tests for AppController.

All dependencies (loader + views) are mocked so no QApplication or real file
is needed. The controller is pure coordination logic — tests verify that it
calls the right methods on the right objects in the right order.
"""

from __future__ import annotations

from unittest.mock import MagicMock, call

import numpy as np
import pytest
from PyQt6.QtGui import QColor

from mdf_viewer.controller.app_controller import AppController, _COLOR_PALETTE
from mdf_viewer.errors import MdfLoadError
from mdf_viewer.model.measurement import MeasurementInfo
from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.view_model.active_signal import ActiveSignal


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_signal_data() -> SignalData:
    t = np.array([0.0, 0.5, 1.0])
    return SignalData(timestamps=t, samples=np.sin(t))


def _make_metadata(name: str = "sig", gi: int = 0, ci: int = 1) -> SignalMetadata:
    return SignalMetadata(name=name, unit="V", group_index=gi, channel_index=ci)


def _make_measurement_info() -> MeasurementInfo:
    return MeasurementInfo(file_name="test.mf4", mdf_version="4.10")


@pytest.fixture()
def deps() -> dict:
    loader = MagicMock()
    loader.channel_tree.return_value = []
    loader.measurement_info.return_value = _make_measurement_info()
    loader.load_signal.return_value = (_make_signal_data(), _make_metadata())
    return {
        "loader": loader,
        "browser": MagicMock(),
        "plot": MagicMock(),
        "table": MagicMock(),
        "info_box": MagicMock(),
        "signal_info": MagicMock(),
    }


@pytest.fixture()
def ctrl(deps: dict) -> AppController:
    return AppController(
        loader=deps["loader"],
        signal_browser=deps["browser"],
        plot_area=deps["plot"],
        active_signals_table=deps["table"],
        measurement_info_box=deps["info_box"],
        signal_info_box=deps["signal_info"],
    )


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

def test_initially_no_active_signals(ctrl: AppController) -> None:
    assert ctrl.active_signals == []


def test_initially_no_selection(ctrl: AppController) -> None:
    assert ctrl.selected_signal is None


# ---------------------------------------------------------------------------
# load_file
# ---------------------------------------------------------------------------

def test_load_file_calls_loader_open(ctrl: AppController, deps: dict) -> None:
    ctrl.load_file("test.mf4")
    deps["loader"].open.assert_called_once_with("test.mf4")


def test_load_file_populates_browser(ctrl: AppController, deps: dict) -> None:
    groups = [MagicMock()]
    deps["loader"].channel_tree.return_value = groups
    ctrl.load_file("test.mf4")
    deps["browser"].populate.assert_called_once_with(groups)


def test_load_file_updates_info_box(ctrl: AppController, deps: dict) -> None:
    info = _make_measurement_info()
    deps["loader"].measurement_info.return_value = info
    ctrl.load_file("test.mf4")
    deps["info_box"].set_info.assert_called_once_with(info)


def test_load_file_clears_browser_first(ctrl: AppController, deps: dict) -> None:
    ctrl.load_file("test.mf4")
    # clear() must be called before populate()
    browser = deps["browser"]
    clear_pos = [i for i, c in enumerate(browser.mock_calls) if c == call.clear()]
    pop_pos = [i for i, c in enumerate(browser.mock_calls) if "populate" in str(c)]
    assert clear_pos and pop_pos
    assert clear_pos[0] < pop_pos[0]


def test_load_file_clears_info_box_first(ctrl: AppController, deps: dict) -> None:
    ctrl.load_file("test.mf4")
    info_box = deps["info_box"]
    clear_pos = [i for i, c in enumerate(info_box.mock_calls) if c == call.clear()]
    set_pos = [i for i, c in enumerate(info_box.mock_calls) if "set_info" in str(c)]
    assert clear_pos and set_pos
    assert clear_pos[0] < set_pos[0]


def test_load_file_resets_color_index(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    ctrl.load_file("test.mf4")
    # After reload, next signal should get the first palette color again
    ctrl.add_signal(0, 1)
    first_color = QColor(*_COLOR_PALETTE[0])
    assert ctrl.active_signals[0].color == first_color


def test_load_file_removes_existing_signals(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    ctrl.load_file("test.mf4")
    assert ctrl.active_signals == []


def test_load_file_clears_selection(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    ctrl.set_selected_signal(ctrl.active_signals[0])
    ctrl.load_file("test.mf4")
    assert ctrl.selected_signal is None


def test_load_file_propagates_mdf_load_error(ctrl: AppController, deps: dict) -> None:
    deps["loader"].open.side_effect = MdfLoadError("bad file")
    with pytest.raises(MdfLoadError):
        ctrl.load_file("bad.mf4")


def test_load_file_clears_ui_even_on_error(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    deps["loader"].open.side_effect = MdfLoadError("bad file")
    with pytest.raises(MdfLoadError):
        ctrl.load_file("bad.mf4")
    assert ctrl.active_signals == []
    deps["browser"].clear.assert_called()


def test_load_file_adds_to_recent_on_success(deps: dict) -> None:
    settings = MagicMock()
    ctrl = AppController(
        loader=deps["loader"],
        signal_browser=deps["browser"],
        plot_area=deps["plot"],
        active_signals_table=deps["table"],
        measurement_info_box=deps["info_box"],
        signal_info_box=deps["signal_info"],
        settings=settings,
    )
    ctrl.load_file("test.mf4")
    settings.add_recent.assert_called_once_with("test.mf4")


def test_load_file_does_not_add_to_recent_on_failure(deps: dict) -> None:
    settings = MagicMock()
    deps["loader"].open.side_effect = MdfLoadError("bad file")
    ctrl = AppController(
        loader=deps["loader"],
        signal_browser=deps["browser"],
        plot_area=deps["plot"],
        active_signals_table=deps["table"],
        measurement_info_box=deps["info_box"],
        signal_info_box=deps["signal_info"],
        settings=settings,
    )
    with pytest.raises(MdfLoadError):
        ctrl.load_file("bad.mf4")
    settings.add_recent.assert_not_called()


def test_load_file_without_settings_does_not_crash(
    ctrl: AppController, deps: dict
) -> None:
    ctrl.load_file("test.mf4")  # no settings injected — must not raise


# ---------------------------------------------------------------------------
# add_signal
# ---------------------------------------------------------------------------

def test_add_signal_appends_to_active_list(ctrl: AppController) -> None:
    ctrl.add_signal(0, 1)
    assert len(ctrl.active_signals) == 1


def test_add_signal_duplicate_is_noop(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 1)
    assert len(ctrl.active_signals) == 1
    deps["plot"].add_signal.assert_called_once()
    deps["table"].add_row.assert_called_once()


def test_add_signal_calls_plot_add_signal(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    deps["plot"].add_signal.assert_called_once()
    active = deps["plot"].add_signal.call_args[0][0]
    assert isinstance(active, ActiveSignal)


def test_add_signal_calls_table_add_row(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    deps["table"].add_row.assert_called_once()
    active = deps["table"].add_row.call_args[0][0]
    assert isinstance(active, ActiveSignal)


def test_add_signal_assigns_color(ctrl: AppController) -> None:
    ctrl.add_signal(0, 1)
    assert isinstance(ctrl.active_signals[0].color, QColor)


def test_add_signal_colors_cycle_through_palette(ctrl: AppController, deps: dict) -> None:
    # Return metadata whose indices match the request so the duplicate guard
    # doesn't block distinct channels.
    deps["loader"].load_signal.side_effect = (
        lambda gi, ci: (_make_signal_data(), _make_metadata(name=f"s{ci}", gi=gi, ci=ci))
    )
    for i in range(len(_COLOR_PALETTE) + 1):
        ctrl.add_signal(0, i)
    colors = [s.color for s in ctrl.active_signals]
    expected_first = QColor(*_COLOR_PALETTE[0])
    expected_second = QColor(*_COLOR_PALETTE[1])
    assert colors[0] == expected_first
    assert colors[1] == expected_second
    # Index wraps around
    assert colors[len(_COLOR_PALETTE)] == expected_first


def test_add_signal_stores_correct_metadata(ctrl: AppController, deps: dict) -> None:
    meta = _make_metadata("voltage", gi=2, ci=3)
    deps["loader"].load_signal.return_value = (_make_signal_data(), meta)
    ctrl.add_signal(2, 3)
    assert ctrl.active_signals[0].metadata.name == "voltage"


def test_add_signal_returns_true_when_added(ctrl: AppController) -> None:
    result = ctrl.add_signal(0, 1)
    assert result is True


def test_add_signal_returns_false_for_duplicate(ctrl: AppController) -> None:
    ctrl.add_signal(0, 1)
    result = ctrl.add_signal(0, 1)
    assert result is False


def test_add_signal_propagates_mdf_load_error(ctrl: AppController, deps: dict) -> None:
    deps["loader"].load_signal.side_effect = MdfLoadError("bad channel")
    with pytest.raises(MdfLoadError):
        ctrl.add_signal(0, 99)
    assert ctrl.active_signals == []


# ---------------------------------------------------------------------------
# remove_signal
# ---------------------------------------------------------------------------

def test_remove_signal_removes_from_active_list(ctrl: AppController) -> None:
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    ctrl.remove_signal(sig)
    assert ctrl.active_signals == []


def test_remove_signal_calls_plot_remove(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    ctrl.remove_signal(sig)
    deps["plot"].remove_signal.assert_called_once_with(sig)


def test_remove_signal_calls_table_remove_row(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    ctrl.remove_signal(sig)
    deps["table"].remove_row.assert_called_once_with(sig)


def test_remove_signal_clears_selection_when_selected(
    ctrl: AppController, deps: dict
) -> None:
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    ctrl.set_selected_signal(sig)
    ctrl.remove_signal(sig)
    assert ctrl.selected_signal is None
    deps["signal_info"].clear.assert_called()


def test_remove_signal_keeps_selection_for_other(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    sigs = ctrl.active_signals
    ctrl.set_selected_signal(sigs[1])
    ctrl.remove_signal(sigs[0])
    assert ctrl.selected_signal is sigs[1]


def test_remove_signal_noop_when_not_active(ctrl: AppController, deps: dict) -> None:
    stranger = ActiveSignal(
        data=_make_signal_data(),
        metadata=_make_metadata(),
        color=QColor(0, 0, 0),
    )
    ctrl.remove_signal(stranger)  # must not raise
    deps["plot"].remove_signal.assert_not_called()


# ---------------------------------------------------------------------------
# remove_all
# ---------------------------------------------------------------------------

def test_remove_all_clears_active_list(ctrl: AppController) -> None:
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    ctrl.remove_all()
    assert ctrl.active_signals == []


def test_remove_all_calls_plot_remove_for_each(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    sigs = list(ctrl.active_signals)
    ctrl.remove_all()
    assert deps["plot"].remove_signal.call_count == 2
    deps["plot"].remove_signal.assert_any_call(sigs[0])
    deps["plot"].remove_signal.assert_any_call(sigs[1])


def test_remove_all_clears_table(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    ctrl.remove_all()
    deps["table"].clear.assert_called()


def test_remove_all_clears_selection(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    ctrl.set_selected_signal(ctrl.active_signals[0])
    ctrl.remove_all()
    assert ctrl.selected_signal is None


def test_remove_all_on_empty_is_noop(ctrl: AppController, deps: dict) -> None:
    ctrl.remove_all()  # must not raise
    deps["plot"].remove_signal.assert_not_called()


# ---------------------------------------------------------------------------
# set_selected_signal
# ---------------------------------------------------------------------------

def test_set_selected_signal_updates_property(ctrl: AppController) -> None:
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    ctrl.set_selected_signal(sig)
    assert ctrl.selected_signal is sig


def test_set_selected_signal_calls_set_metadata(
    ctrl: AppController, deps: dict
) -> None:
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    ctrl.set_selected_signal(sig)
    deps["signal_info"].set_metadata.assert_called_once_with(sig.metadata)


def test_set_selected_signal_none_calls_clear(
    ctrl: AppController, deps: dict
) -> None:
    ctrl.set_selected_signal(None)
    deps["signal_info"].clear.assert_called_once()


def test_set_selected_signal_none_clears_property(ctrl: AppController) -> None:
    ctrl.add_signal(0, 1)
    ctrl.set_selected_signal(ctrl.active_signals[0])
    ctrl.set_selected_signal(None)
    assert ctrl.selected_signal is None


# ---------------------------------------------------------------------------
# Y-grid
# ---------------------------------------------------------------------------

def test_on_y_grid_toggled_enables_grid_on_selected(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    ctrl.set_selected_signal(sig)
    ctrl.on_y_grid_toggled(True)
    deps["plot"].set_y_grid.assert_called_with(sig, True)


def test_on_y_grid_toggled_no_selected_does_not_crash(ctrl: AppController, deps: dict) -> None:
    ctrl.on_y_grid_toggled(True)  # nothing selected — must not raise
    deps["plot"].set_y_grid.assert_not_called()


def test_on_y_grid_toggled_disabled_removes_grid(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    ctrl.set_selected_signal(sig)
    ctrl.on_y_grid_toggled(True)
    deps["plot"].reset_mock()
    ctrl.on_y_grid_toggled(False)
    deps["plot"].set_y_grid.assert_called_with(sig, False)


def test_set_selected_signal_moves_grid(ctrl: AppController, deps: dict) -> None:
    deps["loader"].load_signal.side_effect = [
        (_make_signal_data(), _make_metadata(name="a", gi=0, ci=1)),
        (_make_signal_data(), _make_metadata(name="b", gi=0, ci=2)),
    ]
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    sig_a, sig_b = ctrl.active_signals

    ctrl.set_selected_signal(sig_a)
    ctrl.on_y_grid_toggled(True)
    deps["plot"].reset_mock()

    ctrl.set_selected_signal(sig_b)
    calls = deps["plot"].set_y_grid.call_args_list
    assert calls[0] == call(sig_a, False)
    assert calls[1] == call(sig_b, True)


def test_set_selected_signal_none_removes_grid(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    ctrl.set_selected_signal(sig)
    ctrl.on_y_grid_toggled(True)
    deps["plot"].reset_mock()
    ctrl.set_selected_signal(None)
    deps["plot"].set_y_grid.assert_called_once_with(sig, False)


# ---------------------------------------------------------------------------
# recolor_signal
# ---------------------------------------------------------------------------

def test_recolor_signal_calls_plot(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    active = ctrl.active_signals[0]
    new_color = QColor(0, 200, 100)
    ctrl.recolor_signal(active, new_color)
    deps["plot"].recolor_signal.assert_called_once_with(active, new_color)


def test_recolor_signal_notifies_cursor_ctrl(ctrl: AppController, deps: dict) -> None:
    cursor_ctrl = MagicMock()
    ctrl.set_cursor_controller(cursor_ctrl)
    ctrl.add_signal(0, 1)
    active = ctrl.active_signals[0]
    new_color = QColor(0, 200, 100)
    ctrl.recolor_signal(active, new_color)
    cursor_ctrl.recolor_signal.assert_called_once_with(active, new_color)


def test_recolor_signal_without_cursor_ctrl_does_not_crash(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    active = ctrl.active_signals[0]
    ctrl.recolor_signal(active, QColor(0, 200, 100))  # no cursor_ctrl set — must not raise


# ---------------------------------------------------------------------------
# toggle_step_mode
# ---------------------------------------------------------------------------

def test_add_signal_sets_step_mode_false_for_float_signal(ctrl: AppController) -> None:
    ctrl.add_signal(0, 1)  # _make_metadata() has is_integer=False
    assert ctrl.active_signals[0].step_mode is False


def test_add_signal_sets_step_mode_true_for_integer_signal(deps: dict) -> None:
    meta = SignalMetadata(name="gear", unit="", group_index=0, channel_index=1, is_integer=True)
    deps["loader"].load_signal.return_value = (_make_signal_data(), meta)
    ctrl = AppController(
        loader=deps["loader"], signal_browser=deps["browser"], plot_area=deps["plot"],
        active_signals_table=deps["table"], measurement_info_box=deps["info_box"],
        signal_info_box=deps["signal_info"],
    )
    ctrl.add_signal(0, 1)
    assert ctrl.active_signals[0].step_mode is True


def test_toggle_step_mode_flips_flag(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    active = ctrl.active_signals[0]
    original = active.step_mode
    ctrl.toggle_step_mode(active)
    assert active.step_mode is not original


def test_toggle_step_mode_calls_plot(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    active = ctrl.active_signals[0]
    ctrl.toggle_step_mode(active)
    deps["plot"].set_step_mode.assert_called_once_with(active, active.step_mode)


# ---------------------------------------------------------------------------
# is_file_loaded
# ---------------------------------------------------------------------------

def test_is_file_loaded_delegates_to_loader(ctrl: AppController, deps: dict) -> None:
    deps["loader"].is_open = True
    assert ctrl.is_file_loaded is True
    deps["loader"].is_open = False
    assert ctrl.is_file_loaded is False


def test_toggle_step_mode_noop_for_unknown_signal(ctrl: AppController, deps: dict) -> None:
    t = np.array([0.0, 1.0])
    unknown = ActiveSignal(
        data=SignalData(timestamps=t, samples=t),
        metadata=_make_metadata(),
        color=QColor(0, 0, 255),
    )
    ctrl.toggle_step_mode(unknown)  # must not raise
    deps["plot"].set_step_mode.assert_not_called()


# ---------------------------------------------------------------------------
# remove_signals
# ---------------------------------------------------------------------------

def test_remove_signals_removes_all(ctrl: AppController, deps: dict) -> None:
    deps["loader"].load_signal.side_effect = [
        (_make_signal_data(), _make_metadata("a", ci=1)),
        (_make_signal_data(), _make_metadata("b", ci=2)),
    ]
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    actives = ctrl.active_signals
    ctrl.remove_signals(actives)
    assert ctrl.active_signals == []


def test_remove_signals_calls_plot_remove_for_each(ctrl: AppController, deps: dict) -> None:
    deps["loader"].load_signal.side_effect = [
        (_make_signal_data(), _make_metadata("a", ci=1)),
        (_make_signal_data(), _make_metadata("b", ci=2)),
    ]
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    actives = list(ctrl.active_signals)
    deps["plot"].reset_mock()
    ctrl.remove_signals(actives)
    assert deps["plot"].remove_signal.call_count == 2


def test_remove_signals_refreshes_cursors_once(ctrl: AppController, deps: dict) -> None:
    cursor_ctrl = MagicMock()
    ctrl.set_cursor_controller(cursor_ctrl)
    deps["loader"].load_signal.side_effect = [
        (_make_signal_data(), _make_metadata("a", ci=1)),
        (_make_signal_data(), _make_metadata("b", ci=2)),
    ]
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    cursor_ctrl.reset_mock()
    ctrl.remove_signals(ctrl.active_signals)
    assert cursor_ctrl.refresh.call_count == 1


def test_remove_signals_skips_unknown(ctrl: AppController, deps: dict) -> None:
    t = np.array([0.0, 1.0])
    unknown = ActiveSignal(
        data=SignalData(timestamps=t, samples=t),
        metadata=_make_metadata(),
        color=QColor(0, 0, 255),
    )
    ctrl.remove_signals([unknown])  # must not raise
    deps["plot"].remove_signal.assert_not_called()


# ---------------------------------------------------------------------------
# recolor_signals
# ---------------------------------------------------------------------------

def test_recolor_signals_calls_plot_for_each(ctrl: AppController, deps: dict) -> None:
    deps["loader"].load_signal.side_effect = [
        (_make_signal_data(), _make_metadata("a", ci=1)),
        (_make_signal_data(), _make_metadata("b", ci=2)),
    ]
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    actives = ctrl.active_signals
    new_color = QColor(0, 200, 100)
    deps["plot"].reset_mock()
    ctrl.recolor_signals(actives, new_color)
    assert deps["plot"].recolor_signal.call_count == 2


# ---------------------------------------------------------------------------
# set_step_modes
# ---------------------------------------------------------------------------

def test_set_step_modes_enables_all(ctrl: AppController, deps: dict) -> None:
    deps["loader"].load_signal.side_effect = [
        (_make_signal_data(), _make_metadata("a", ci=1)),
        (_make_signal_data(), _make_metadata("b", ci=2)),
    ]
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    actives = ctrl.active_signals
    ctrl.set_step_modes(actives, True)
    assert all(a.step_mode for a in actives)


def test_set_step_modes_disables_all(ctrl: AppController, deps: dict) -> None:
    deps["loader"].load_signal.side_effect = [
        (_make_signal_data(), _make_metadata("a", ci=1)),
        (_make_signal_data(), _make_metadata("b", ci=2)),
    ]
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    actives = ctrl.active_signals
    ctrl.set_step_modes(actives, True)
    ctrl.set_step_modes(actives, False)
    assert not any(a.step_mode for a in actives)


def test_set_step_modes_calls_plot_for_each(ctrl: AppController, deps: dict) -> None:
    deps["loader"].load_signal.side_effect = [
        (_make_signal_data(), _make_metadata("a", ci=1)),
        (_make_signal_data(), _make_metadata("b", ci=2)),
    ]
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    actives = ctrl.active_signals
    deps["plot"].reset_mock()
    ctrl.set_step_modes(actives, True)
    assert deps["plot"].set_step_mode.call_count == 2


def test_set_step_modes_skips_unknown(ctrl: AppController, deps: dict) -> None:
    t = np.array([0.0, 1.0])
    unknown = ActiveSignal(
        data=SignalData(timestamps=t, samples=t),
        metadata=_make_metadata(),
        color=QColor(0, 0, 255),
    )
    ctrl.set_step_modes([unknown], True)  # must not raise
    deps["plot"].set_step_mode.assert_not_called()


# ---------------------------------------------------------------------------
# on_multi_selection
# ---------------------------------------------------------------------------

def test_on_multi_selection_true_calls_show_multi(ctrl: AppController, deps: dict) -> None:
    ctrl.on_multi_selection(True)
    deps["signal_info"].show_multi_selection.assert_called_once()


def test_on_multi_selection_false_does_not_call_show_multi(
    ctrl: AppController, deps: dict
) -> None:
    ctrl.on_multi_selection(False)
    deps["signal_info"].show_multi_selection.assert_not_called()


# ---------------------------------------------------------------------------
# swimlanes
# ---------------------------------------------------------------------------

def test_swimlanes_calls_plot_with_active_list(ctrl: AppController, deps: dict) -> None:
    deps["loader"].load_signal.side_effect = [
        (_make_signal_data(), _make_metadata("a", ci=0)),
        (_make_signal_data(), _make_metadata("b", ci=1)),
    ]
    ctrl.add_signal(0, 0)
    ctrl.add_signal(0, 1)
    deps["plot"].swimlanes.return_value = True
    result = ctrl.swimlanes()
    assert result is True
    deps["plot"].swimlanes.assert_called_once_with(ctrl._active)


def test_swimlanes_returns_false_when_no_signals(ctrl: AppController, deps: dict) -> None:
    deps["plot"].swimlanes.return_value = False
    assert ctrl.swimlanes() is False


# ---------------------------------------------------------------------------
# reorder_signals
# ---------------------------------------------------------------------------

def test_reorder_signals_updates_active_order(ctrl: AppController, deps: dict) -> None:
    deps["loader"].load_signal.side_effect = [
        (_make_signal_data(), _make_metadata("a", ci=0)),
        (_make_signal_data(), _make_metadata("b", ci=1)),
        (_make_signal_data(), _make_metadata("c", ci=2)),
    ]
    ctrl.add_signal(0, 0)
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    a, b, c = ctrl._active
    ctrl.reorder_signals([c, a, b])
    assert ctrl._active == [c, a, b]


def test_reorder_signals_preserves_identity(ctrl: AppController, deps: dict) -> None:
    deps["loader"].load_signal.return_value = (_make_signal_data(), _make_metadata())
    ctrl.add_signal(0, 0)
    original = ctrl._active[0]
    ctrl.reorder_signals([original])
    assert ctrl._active[0] is original


# ---------------------------------------------------------------------------
# set_selected_signal — Properties tab integration
# ---------------------------------------------------------------------------

def test_set_selected_signal_calls_set_properties(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    ctrl.set_selected_signal(sig)
    deps["signal_info"].set_properties.assert_called_once_with(
        sig.display_mode, sig.marker_shape, sig.line_width
    )


def test_set_selected_signal_enables_properties(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    ctrl.set_selected_signal(sig)
    deps["signal_info"].enable_properties.assert_called_with(True)


def test_set_selected_signal_none_disables_properties(ctrl: AppController, deps: dict) -> None:
    ctrl.set_selected_signal(None)
    # clear() is called; enable_properties is NOT called for None
    deps["signal_info"].clear.assert_called()
    for c in deps["signal_info"].enable_properties.call_args_list:
        assert c != call(True)


def test_set_selected_signal_updates_selected_signals_list(ctrl: AppController) -> None:
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    ctrl.set_selected_signal(sig)
    assert ctrl._selected_signals == [sig]


def test_set_selected_signal_none_clears_selected_signals_list(ctrl: AppController) -> None:
    ctrl.set_selected_signal(None)
    assert ctrl._selected_signals == []


# ---------------------------------------------------------------------------
# set_multi_selected
# ---------------------------------------------------------------------------

def test_set_multi_selected_stores_signals(ctrl: AppController, deps: dict) -> None:
    deps["loader"].load_signal.side_effect = [
        (_make_signal_data(), _make_metadata("a", ci=1)),
        (_make_signal_data(), _make_metadata("b", ci=2)),
    ]
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    actives = ctrl.active_signals
    ctrl.set_multi_selected(actives)
    assert ctrl._selected_signals == actives


def test_set_multi_selected_calls_set_properties_with_matching_mode(
    ctrl: AppController, deps: dict
) -> None:
    deps["loader"].load_signal.side_effect = [
        (_make_signal_data(), _make_metadata("a", ci=1)),
        (_make_signal_data(), _make_metadata("b", ci=2)),
    ]
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    actives = ctrl.active_signals
    # Both default to "line" / "circle"
    ctrl.set_multi_selected(actives)
    deps["signal_info"].set_properties.assert_called_with("line", "circle", 1)


def test_set_multi_selected_passes_none_for_mismatched_mode(
    ctrl: AppController, deps: dict
) -> None:
    deps["loader"].load_signal.side_effect = [
        (_make_signal_data(), _make_metadata("a", ci=1)),
        (_make_signal_data(), _make_metadata("b", ci=2)),
    ]
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    actives = ctrl.active_signals
    actives[0].display_mode = "line"
    actives[1].display_mode = "marker"
    ctrl.set_multi_selected(actives)
    deps["signal_info"].set_properties.assert_called_with(None, "circle", 1)


def test_set_multi_selected_enables_properties_tab(
    ctrl: AppController, deps: dict
) -> None:
    ctrl.add_signal(0, 1)
    ctrl.set_multi_selected(ctrl.active_signals)
    deps["signal_info"].enable_properties.assert_called_with(True)


# ---------------------------------------------------------------------------
# on_display_mode_requested
# ---------------------------------------------------------------------------

def test_on_display_mode_requested_updates_active(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    ctrl.set_selected_signal(sig)
    ctrl.on_display_mode_requested("line_marker")
    assert sig.display_mode == "line_marker"


def test_on_display_mode_requested_calls_plot(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    ctrl.set_selected_signal(sig)
    ctrl.on_display_mode_requested("marker")
    deps["plot"].set_display_mode.assert_called_once_with(sig, "marker", sig.marker_shape)


def test_on_display_mode_requested_skips_unknown(ctrl: AppController, deps: dict) -> None:
    t = np.array([0.0, 1.0])
    unknown = ActiveSignal(
        data=SignalData(timestamps=t, samples=t),
        metadata=_make_metadata(),
        color=QColor(0, 0, 255),
    )
    ctrl._selected_signals = [unknown]
    ctrl.on_display_mode_requested("marker")  # must not raise
    deps["plot"].set_display_mode.assert_not_called()


# ---------------------------------------------------------------------------
# on_marker_shape_requested
# ---------------------------------------------------------------------------

def test_on_marker_shape_requested_updates_active(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    sig.display_mode = "line_marker"
    ctrl.set_selected_signal(sig)
    ctrl.on_marker_shape_requested("diamond")
    assert sig.marker_shape == "diamond"


def test_on_marker_shape_requested_calls_plot_when_not_line(
    ctrl: AppController, deps: dict
) -> None:
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    sig.display_mode = "line_marker"
    ctrl.set_selected_signal(sig)
    deps["plot"].reset_mock()
    ctrl.on_marker_shape_requested("square")
    deps["plot"].set_display_mode.assert_called_once_with(sig, "line_marker", "square")


def test_on_marker_shape_requested_no_plot_call_in_line_mode(
    ctrl: AppController, deps: dict
) -> None:
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    sig.display_mode = "line"
    ctrl.set_selected_signal(sig)
    deps["plot"].reset_mock()
    ctrl.on_marker_shape_requested("square")
    deps["plot"].set_display_mode.assert_not_called()


# ---------------------------------------------------------------------------
# on_line_width_requested
# ---------------------------------------------------------------------------

def test_on_line_width_requested_calls_plot(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    ctrl.set_selected_signal(sig)
    deps["plot"].reset_mock()
    ctrl.on_line_width_requested(4)
    deps["plot"].set_line_width.assert_called_once_with(sig, 4)


def test_on_line_width_requested_ignored_for_inactive(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    ctrl.set_selected_signal(sig)
    ctrl.remove_signal(sig)
    deps["plot"].reset_mock()
    ctrl.on_line_width_requested(3)
    deps["plot"].set_line_width.assert_not_called()


def test_set_selected_signal_passes_line_width_to_info_box(
    ctrl: AppController, deps: dict
) -> None:
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    sig.line_width = 3
    ctrl.set_selected_signal(sig)
    deps["signal_info"].set_properties.assert_called_with("line", "circle", 3)


def test_set_multi_selected_passes_shared_line_width(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    sigs = ctrl.active_signals
    for s in sigs:
        s.line_width = 2
    ctrl.set_multi_selected(sigs)
    deps["signal_info"].set_properties.assert_called_with("line", "circle", 2)


def test_set_multi_selected_none_width_when_mismatched(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    sigs = ctrl.active_signals
    sigs[0].line_width = 1
    sigs[1].line_width = 3
    ctrl.set_multi_selected(sigs)
    call_args = deps["signal_info"].set_properties.call_args
    assert call_args[0][2] is None  # width arg is None

