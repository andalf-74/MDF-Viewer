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

@pytest.mark.requirement("REQ-FILE-012")
def test_load_file_calls_loader_open(ctrl: AppController, deps: dict) -> None:
    ctrl.load_file("test.mf4")
    deps["loader"].open.assert_called_once_with("test.mf4")


@pytest.mark.requirement("REQ-FILE-012")
def test_load_file_populates_browser(ctrl: AppController, deps: dict) -> None:
    groups = [MagicMock()]
    deps["loader"].channel_tree.return_value = groups
    ctrl.load_file("test.mf4")
    deps["browser"].populate.assert_called_once_with(groups)


@pytest.mark.requirement("REQ-FILE-012")
def test_load_file_updates_info_box(ctrl: AppController, deps: dict) -> None:
    info = _make_measurement_info()
    deps["loader"].measurement_info.return_value = info
    ctrl.load_file("test.mf4")
    deps["info_box"].set_info.assert_called_once_with(info)


@pytest.mark.requirement("REQ-FILE-012")
def test_load_file_clears_browser_first(ctrl: AppController, deps: dict) -> None:
    ctrl.load_file("test.mf4")
    # clear() must be called before populate()
    browser = deps["browser"]
    clear_pos = [i for i, c in enumerate(browser.mock_calls) if c == call.clear()]
    pop_pos = [i for i, c in enumerate(browser.mock_calls) if "populate" in str(c)]
    assert clear_pos and pop_pos
    assert clear_pos[0] < pop_pos[0]


@pytest.mark.requirement("REQ-FILE-012")
def test_load_file_clears_info_box_first(ctrl: AppController, deps: dict) -> None:
    ctrl.load_file("test.mf4")
    info_box = deps["info_box"]
    clear_pos = [i for i, c in enumerate(info_box.mock_calls) if c == call.clear()]
    set_pos = [i for i, c in enumerate(info_box.mock_calls) if "set_info" in str(c)]
    assert clear_pos and set_pos
    assert clear_pos[0] < set_pos[0]


@pytest.mark.requirement("REQ-PLOT-021")
@pytest.mark.requirement("REQ-FILE-012")
@pytest.mark.requirement("REQ-FILE-010")
def test_load_file_resets_color_index(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    ctrl.load_file("test.mf4")
    # After reload, next signal should get the first palette color again
    ctrl.add_signal(0, 1)
    first_color = QColor(*_COLOR_PALETTE[0])
    assert ctrl.active_signals[0].color == first_color


@pytest.mark.requirement("REQ-FILE-012")
@pytest.mark.requirement("REQ-FILE-010")
def test_load_file_removes_existing_signals(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    ctrl.load_file("test.mf4")
    assert ctrl.active_signals == []


@pytest.mark.requirement("REQ-FILE-012")
@pytest.mark.requirement("REQ-FILE-010")
def test_load_file_clears_selection(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    ctrl.set_selected_signal(ctrl.active_signals[0])
    ctrl.load_file("test.mf4")
    assert ctrl.selected_signal is None


@pytest.mark.requirement("REQ-FILE-041")
@pytest.mark.requirement("REQ-FILE-040")
def test_load_file_propagates_mdf_load_error(ctrl: AppController, deps: dict) -> None:
    deps["loader"].open.side_effect = MdfLoadError("bad file")
    with pytest.raises(MdfLoadError):
        ctrl.load_file("bad.mf4")


@pytest.mark.requirement("REQ-FILE-041")
def test_load_file_clears_ui_even_on_error(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    deps["loader"].open.side_effect = MdfLoadError("bad file")
    with pytest.raises(MdfLoadError):
        ctrl.load_file("bad.mf4")
    assert ctrl.active_signals == []
    deps["browser"].clear.assert_called()


@pytest.mark.requirement("REQ-FILE-053")
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


@pytest.mark.requirement("REQ-FILE-053")
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


@pytest.mark.requirement("REQ-PLOT-020")
@pytest.mark.requirement("REQ-BROWSER-040")
@pytest.mark.requirement("REQ-MDF-034")
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


@pytest.mark.requirement("REQ-PLOT-021")
def test_add_signal_assigns_color(ctrl: AppController) -> None:
    ctrl.add_signal(0, 1)
    assert isinstance(ctrl.active_signals[0].color, QColor)


@pytest.mark.requirement("REQ-PLOT-021")
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


@pytest.mark.requirement("REQ-PLOT-020")
def test_add_signal_returns_false_for_duplicate(ctrl: AppController) -> None:
    ctrl.add_signal(0, 1)
    result = ctrl.add_signal(0, 1)
    assert result is False


@pytest.mark.requirement("REQ-BROWSER-041")
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


@pytest.mark.requirement("REQ-PLOT-025")
def test_remove_signal_clears_selection_when_selected(
    ctrl: AppController, deps: dict
) -> None:
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    ctrl.set_selected_signal(sig)
    ctrl.remove_signal(sig)
    assert ctrl.selected_signal is None
    deps["signal_info"].clear.assert_called()


@pytest.mark.requirement("REQ-PLOT-025")
def test_remove_signal_keeps_selection_for_other(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    sigs = ctrl.active_signals
    ctrl.set_selected_signal(sigs[1])
    ctrl.remove_signal(sigs[0])
    assert ctrl.selected_signal is sigs[1]


@pytest.mark.requirement("REQ-PLOT-023")
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


@pytest.mark.requirement("REQ-PLOT-025")
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


@pytest.mark.requirement("REQ-PLOT-150")
def test_set_selected_signal_calls_set_metadata(
    ctrl: AppController, deps: dict
) -> None:
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    ctrl.set_selected_signal(sig)
    deps["signal_info"].set_metadata.assert_called_once_with(sig.metadata)


@pytest.mark.requirement("REQ-PLOT-152")
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

@pytest.mark.requirement("REQ-PLOT-120")
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

@pytest.mark.requirement("REQ-PLOT-022")
def test_add_signal_sets_step_mode_false_for_float_signal(ctrl: AppController) -> None:
    ctrl.add_signal(0, 1)  # _make_metadata() has is_integer=False
    assert ctrl.active_signals[0].step_mode is False


@pytest.mark.requirement("REQ-PLOT-022")
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


@pytest.mark.requirement("REQ-PLOT-120")
def test_toggle_step_mode_flips_flag(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    active = ctrl.active_signals[0]
    original = active.step_mode
    ctrl.toggle_step_mode(active)
    assert active.step_mode is not original


@pytest.mark.requirement("REQ-PLOT-120")
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

@pytest.mark.requirement("REQ-PLOT-141")
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


@pytest.mark.requirement("REQ-PLOT-141")
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


@pytest.mark.requirement("REQ-PLOT-023")
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

@pytest.mark.requirement("REQ-PLOT-122")
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

@pytest.mark.requirement("REQ-PLOT-122")
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


@pytest.mark.requirement("REQ-PLOT-122")
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


@pytest.mark.requirement("REQ-PLOT-122")
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


@pytest.mark.requirement("REQ-PLOT-023")
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

@pytest.mark.requirement("REQ-PLOT-152")
def test_on_multi_selection_true_calls_show_multi(ctrl: AppController, deps: dict) -> None:
    ctrl.on_multi_selection(True)
    deps["signal_info"].show_multi_selection.assert_called_once()


@pytest.mark.requirement("REQ-PLOT-152")
def test_on_multi_selection_false_does_not_call_show_multi(
    ctrl: AppController, deps: dict
) -> None:
    ctrl.on_multi_selection(False)
    deps["signal_info"].show_multi_selection.assert_not_called()


# ---------------------------------------------------------------------------
# swimlanes
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-055")
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


@pytest.mark.requirement("REQ-PLOT-055")
def test_swimlanes_returns_false_when_no_signals(ctrl: AppController, deps: dict) -> None:
    deps["plot"].swimlanes.return_value = False
    assert ctrl.swimlanes() is False


# ---------------------------------------------------------------------------
# reorder_signals
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-142")
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


@pytest.mark.requirement("REQ-PLOT-042")
def test_add_signal_calls_refresh_z_order(ctrl: AppController, deps: dict) -> None:
    deps["loader"].load_signal.return_value = (_make_signal_data(), _make_metadata())
    deps["plot"].reset_mock()
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    deps["plot"].set_selected_signals.assert_called_with(
        [], all_signals=[sig], top_first=True
    )


@pytest.mark.requirement("REQ-PLOT-142")
def test_reorder_signals_calls_refresh_z_order(ctrl: AppController, deps: dict) -> None:
    deps["loader"].load_signal.side_effect = [
        (_make_signal_data(), _make_metadata("a", ci=0)),
        (_make_signal_data(), _make_metadata("b", ci=1)),
    ]
    ctrl.add_signal(0, 0)
    ctrl.add_signal(0, 1)
    a, b = ctrl._active
    deps["plot"].reset_mock()
    ctrl.reorder_signals([b, a])
    deps["plot"].set_selected_signals.assert_called_with(
        [], all_signals=[b, a], top_first=True
    )


@pytest.mark.requirement("REQ-PLOT-042")
def test_refresh_z_order_uses_signal_z_order_from_settings(
    tmp_path, deps: dict
) -> None:
    from mdf_viewer.settings import Settings
    s = Settings(path=tmp_path / "s.json")
    s.signal_z_order = "bottom_first"
    ctrl_with_settings = AppController(
        loader=deps["loader"],
        signal_browser=deps["browser"],
        plot_area=deps["plot"],
        active_signals_table=deps["table"],
        measurement_info_box=deps["info_box"],
        signal_info_box=deps["signal_info"],
        settings=s,
    )
    deps["loader"].load_signal.return_value = (_make_signal_data(), _make_metadata())
    ctrl_with_settings.add_signal(0, 1)
    sig = ctrl_with_settings.active_signals[0]
    deps["plot"].reset_mock()
    ctrl_with_settings.refresh_z_order()
    deps["plot"].set_selected_signals.assert_called_with(
        [], all_signals=[sig], top_first=False
    )


@pytest.mark.requirement("REQ-PLOT-044")
def test_refresh_z_order_pushes_line_boost_from_settings(
    tmp_path, deps: dict
) -> None:
    from mdf_viewer.settings import Settings
    s = Settings(path=tmp_path / "s.json")
    s.selected_line_boost = 3
    ctrl_with_settings = AppController(
        loader=deps["loader"],
        signal_browser=deps["browser"],
        plot_area=deps["plot"],
        active_signals_table=deps["table"],
        measurement_info_box=deps["info_box"],
        signal_info_box=deps["signal_info"],
        settings=s,
    )
    deps["plot"].reset_mock()
    ctrl_with_settings.refresh_z_order()
    deps["plot"].set_selected_line_boost.assert_called_with(3)


@pytest.mark.requirement("REQ-PLOT-044")
def test_refresh_z_order_pushes_default_boost_without_settings(deps: dict) -> None:
    ctrl = AppController(
        loader=deps["loader"],
        signal_browser=deps["browser"],
        plot_area=deps["plot"],
        active_signals_table=deps["table"],
        measurement_info_box=deps["info_box"],
        signal_info_box=deps["signal_info"],
    )
    deps["plot"].reset_mock()
    ctrl.refresh_z_order()
    deps["plot"].set_selected_line_boost.assert_called_with(1)


# ---------------------------------------------------------------------------
# refresh_display_names
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-160")
def test_refresh_display_names_calls_set_name_formatter(
    ctrl: AppController, deps: dict
) -> None:
    ctrl.refresh_display_names()
    deps["table"].set_name_formatter.assert_called_once()


@pytest.mark.requirement("REQ-PLOT-160")
def test_refresh_display_names_formatter_applies_rule(tmp_path, deps: dict) -> None:
    from mdf_viewer.settings import Settings
    s = Settings(path=tmp_path / "s.json")
    s.display_name_rule_enabled = True
    s.display_name_separator = "."
    s.display_name_direction = "right"
    s.display_name_segments = 1
    ctrl_with_settings = AppController(
        loader=deps["loader"],
        signal_browser=deps["browser"],
        plot_area=deps["plot"],
        active_signals_table=deps["table"],
        measurement_info_box=deps["info_box"],
        signal_info_box=deps["signal_info"],
        settings=s,
    )
    ctrl_with_settings.refresh_display_names()
    formatter = deps["table"].set_name_formatter.call_args[0][0]
    assert formatter("a.b.PosADP") == "PosADP"


@pytest.mark.requirement("REQ-PLOT-161")
def test_refresh_display_names_identity_without_settings(deps: dict) -> None:
    ctrl = AppController(
        loader=deps["loader"],
        signal_browser=deps["browser"],
        plot_area=deps["plot"],
        active_signals_table=deps["table"],
        measurement_info_box=deps["info_box"],
        signal_info_box=deps["signal_info"],
    )
    ctrl.refresh_display_names()
    formatter = deps["table"].set_name_formatter.call_args[0][0]
    assert formatter("any.name") == "any.name"


# ---------------------------------------------------------------------------
# set_selected_signal — Properties tab integration
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-120")
def test_set_selected_signal_calls_set_properties(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    ctrl.set_selected_signal(sig)
    deps["signal_info"].set_properties.assert_called_once_with(
        sig.display_mode, sig.marker_shape, sig.line_width, sig.line_style
    )


@pytest.mark.requirement("REQ-PLOT-120")
def test_set_selected_signal_enables_properties(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    ctrl.set_selected_signal(sig)
    deps["signal_info"].enable_properties.assert_called_with(True)


@pytest.mark.requirement("REQ-PLOT-152")
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
# set_selected_signal — enum options (REQ-PLOT-130/131)
# ---------------------------------------------------------------------------

def _make_enum_metadata(name: str = "ign", gi: int = 0, ci: int = 1) -> SignalMetadata:
    return SignalMetadata(
        name=name, unit="", group_index=gi, channel_index=ci,
        enum_map={0: "OFF", 1: "ON"},
    )


@pytest.mark.requirement("REQ-PLOT-130")
def test_set_selected_signal_enum_signal_shows_enum_options(ctrl: AppController, deps: dict) -> None:
    deps["loader"].load_signal.return_value = (_make_signal_data(), _make_enum_metadata())
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    ctrl.set_selected_signal(sig)
    deps["signal_info"].set_enum_options.assert_called_once_with(
        sig.enum_display_table, sig.enum_display_cursor, sig.enum_display_yaxis
    )


@pytest.mark.requirement("REQ-PLOT-131")
def test_set_selected_signal_non_enum_signal_hides_enum_options(ctrl: AppController, deps: dict) -> None:
    # _make_metadata() has no enum_map
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    ctrl.set_selected_signal(sig)
    deps["signal_info"].set_enum_options.assert_called_once_with(None, None, None)


@pytest.mark.requirement("REQ-PLOT-131")
def test_set_selected_signal_none_hides_enum_options(ctrl: AppController, deps: dict) -> None:
    ctrl.set_selected_signal(None)
    deps["signal_info"].set_enum_options.assert_not_called()


@pytest.mark.requirement("REQ-PLOT-130")
def test_on_enum_table_requested_sets_field(ctrl: AppController, deps: dict) -> None:
    deps["loader"].load_signal.return_value = (_make_signal_data(), _make_enum_metadata())
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    ctrl.set_selected_signal(sig)
    ctrl.on_enum_table_requested(False)
    assert sig.enum_display_table is False


@pytest.mark.requirement("REQ-PLOT-130")
def test_on_enum_cursor_requested_sets_field(ctrl: AppController, deps: dict) -> None:
    deps["loader"].load_signal.return_value = (_make_signal_data(), _make_enum_metadata())
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    ctrl.set_selected_signal(sig)
    ctrl.on_enum_cursor_requested(True)
    assert sig.enum_display_cursor is True


@pytest.mark.requirement("REQ-PLOT-130")
def test_on_enum_yaxis_requested_sets_field_and_calls_plot(ctrl: AppController, deps: dict) -> None:
    deps["loader"].load_signal.return_value = (_make_signal_data(), _make_enum_metadata())
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    ctrl.set_selected_signal(sig)
    ctrl.on_enum_yaxis_requested(True)
    assert sig.enum_display_yaxis is True
    deps["plot"].set_enum_display_yaxis.assert_called_once_with(sig, True)


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


@pytest.mark.requirement("REQ-PLOT-140")
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
    deps["signal_info"].set_properties.assert_called_with("line", "circle", 1, "solid")


@pytest.mark.requirement("REQ-PLOT-140")
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
    deps["signal_info"].set_properties.assert_called_with(None, "circle", 1, "solid")


@pytest.mark.requirement("REQ-PLOT-122")
def test_set_multi_selected_enables_properties_tab(
    ctrl: AppController, deps: dict
) -> None:
    ctrl.add_signal(0, 1)
    ctrl.set_multi_selected(ctrl.active_signals)
    deps["signal_info"].enable_properties.assert_called_with(True)


# ---------------------------------------------------------------------------
# on_display_mode_requested
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-120")
def test_on_display_mode_requested_updates_active(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    ctrl.set_selected_signal(sig)
    ctrl.on_display_mode_requested("line_marker")
    assert sig.display_mode == "line_marker"


@pytest.mark.requirement("REQ-PLOT-120")
def test_on_display_mode_requested_calls_plot(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    ctrl.set_selected_signal(sig)
    ctrl.on_display_mode_requested("marker")
    deps["plot"].set_display_mode.assert_called_once_with(sig, "marker", sig.marker_shape)


@pytest.mark.requirement("REQ-PLOT-023")
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

@pytest.mark.requirement("REQ-PLOT-120")
def test_on_marker_shape_requested_updates_active(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    sig.display_mode = "line_marker"
    ctrl.set_selected_signal(sig)
    ctrl.on_marker_shape_requested("diamond")
    assert sig.marker_shape == "diamond"


@pytest.mark.requirement("REQ-PLOT-121")
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


@pytest.mark.requirement("REQ-PLOT-121")
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

@pytest.mark.requirement("REQ-PLOT-120")
def test_on_line_width_requested_calls_plot(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    ctrl.set_selected_signal(sig)
    deps["plot"].reset_mock()
    ctrl.on_line_width_requested(4)
    deps["plot"].set_line_width.assert_called_once_with(sig, 4)


@pytest.mark.requirement("REQ-PLOT-023")
def test_on_line_width_requested_ignored_for_inactive(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    ctrl.set_selected_signal(sig)
    ctrl.remove_signal(sig)
    deps["plot"].reset_mock()
    ctrl.on_line_width_requested(3)
    deps["plot"].set_line_width.assert_not_called()


@pytest.mark.requirement("REQ-PLOT-120")
def test_set_selected_signal_passes_line_width_to_info_box(
    ctrl: AppController, deps: dict
) -> None:
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    sig.line_width = 3
    ctrl.set_selected_signal(sig)
    deps["signal_info"].set_properties.assert_called_with("line", "circle", 3, "solid")


@pytest.mark.requirement("REQ-PLOT-140")
def test_set_multi_selected_passes_shared_line_width(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    sigs = ctrl.active_signals
    for s in sigs:
        s.line_width = 2
    ctrl.set_multi_selected(sigs)
    deps["signal_info"].set_properties.assert_called_with("line", "circle", 2, "solid")


@pytest.mark.requirement("REQ-PLOT-140")
def test_set_multi_selected_none_width_when_mismatched(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    sigs = ctrl.active_signals
    sigs[0].line_width = 1
    sigs[1].line_width = 3
    ctrl.set_multi_selected(sigs)
    call_args = deps["signal_info"].set_properties.call_args
    assert call_args[0][2] is None  # width arg is None


# ---------------------------------------------------------------------------
# on_line_style_requested
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-120")
def test_on_line_style_requested_calls_plot(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    ctrl.set_selected_signal(sig)
    deps["plot"].reset_mock()
    ctrl.on_line_style_requested("dashes")
    deps["plot"].set_line_style.assert_called_once_with(sig, "dashes")


@pytest.mark.requirement("REQ-PLOT-023")
def test_on_line_style_requested_ignored_for_inactive(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    ctrl.set_selected_signal(sig)
    ctrl.remove_signal(sig)
    deps["plot"].reset_mock()
    ctrl.on_line_style_requested("dots")
    deps["plot"].set_line_style.assert_not_called()


@pytest.mark.requirement("REQ-PLOT-140")
def test_set_multi_selected_passes_none_style_when_mismatched(
    ctrl: AppController, deps: dict
) -> None:
    deps["loader"].load_signal.side_effect = [
        (_make_signal_data(), _make_metadata("a", ci=1)),
        (_make_signal_data(), _make_metadata("b", ci=2)),
    ]
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    sigs = ctrl.active_signals
    sigs[0].line_style = "solid"
    sigs[1].line_style = "dashes"
    ctrl.set_multi_selected(sigs)
    call_args = deps["signal_info"].set_properties.call_args
    assert call_args[0][3] is None  # style arg is None


# ---------------------------------------------------------------------------
# set_selected_signals (PlotArea call)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-043")
def test_set_selected_signal_calls_plot_set_selected_signals(
    ctrl: AppController, deps: dict
) -> None:
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    deps["plot"].reset_mock()
    ctrl.set_selected_signal(sig)
    deps["plot"].set_selected_signals.assert_called_once_with(
        [sig], all_signals=[sig], top_first=True
    )


@pytest.mark.requirement("REQ-PLOT-043")
def test_set_selected_signal_none_clears_selection(
    ctrl: AppController, deps: dict
) -> None:
    ctrl.add_signal(0, 1)
    sig = ctrl.active_signals[0]
    ctrl.set_selected_signal(sig)
    deps["plot"].reset_mock()
    ctrl.set_selected_signal(None)
    deps["plot"].set_selected_signals.assert_called_once_with(
        [], all_signals=[sig], top_first=True
    )


@pytest.mark.requirement("REQ-PLOT-043")
def test_set_multi_selected_passes_signals_in_active_order(
    ctrl: AppController, deps: dict
) -> None:
    deps["loader"].load_signal.side_effect = [
        (_make_signal_data(), _make_metadata("a", ci=1)),
        (_make_signal_data(), _make_metadata("b", ci=2)),
    ]
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    sigs = ctrl.active_signals  # [a, b] — earliest first
    deps["plot"].reset_mock()
    ctrl.set_multi_selected(list(reversed(sigs)))  # pass in reverse order
    call_args = deps["plot"].set_selected_signals.call_args[0][0]
    assert call_args == sigs  # controller sorts by _active order



# ---------------------------------------------------------------------------
# snapshot_active_signals
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-FILE-061")
def test_snapshot_empty_when_no_signals(ctrl: AppController) -> None:
    assert ctrl.snapshot_active_signals() == []


@pytest.mark.requirement("REQ-FILE-061")
def test_snapshot_captures_one_signal(ctrl: AppController, deps: dict) -> None:
    deps["loader"].load_signal.return_value = (
        _make_signal_data(),
        _make_metadata("rpm", gi=0, ci=1),
    )
    ctrl.add_signal(0, 1)
    snaps = ctrl.snapshot_active_signals()
    assert len(snaps) == 1
    snap = snaps[0]
    assert snap.name == "rpm"
    assert len(snap.color) == 3
    assert snap.line_width == 1
    assert snap.line_style == "solid"
    assert snap.display_mode == "line"
    assert snap.marker_shape == "circle"
    assert snap.step_mode is False
    assert snap.enum_display_table is True
    assert snap.enum_display_cursor is False
    assert snap.enum_display_yaxis is False


@pytest.mark.requirement("REQ-FILE-061")
def test_snapshot_captures_multiple_signals_in_order(ctrl: AppController, deps: dict) -> None:
    deps["loader"].load_signal.side_effect = [
        (_make_signal_data(), _make_metadata("a", ci=1)),
        (_make_signal_data(), _make_metadata("b", ci=2)),
    ]
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    snaps = ctrl.snapshot_active_signals()
    assert [s.name for s in snaps] == ["a", "b"]


@pytest.mark.requirement("REQ-FILE-061")
def test_snapshot_color_is_rgb_tuple(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    snap = ctrl.snapshot_active_signals()[0]
    r, g, b = snap.color
    assert all(0 <= v <= 255 for v in (r, g, b))


# ---------------------------------------------------------------------------
# find_signal_by_name
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-MDF-060")
def test_find_signal_by_name_delegates_to_loader(ctrl: AppController, deps: dict) -> None:
    meta = _make_metadata("speed", gi=0, ci=3)
    deps["loader"].find_signal_by_name.return_value = [meta]
    result = ctrl.find_signal_by_name("speed")
    deps["loader"].find_signal_by_name.assert_called_once_with("speed")
    assert result == [meta]


@pytest.mark.requirement("REQ-MDF-060")
def test_find_signal_by_name_returns_empty_when_not_found(ctrl: AppController, deps: dict) -> None:
    deps["loader"].find_signal_by_name.return_value = []
    assert ctrl.find_signal_by_name("no_such") == []


@pytest.mark.requirement("REQ-PLOT-162")
def test_find_signal_by_name_ignores_display_shortening(tmp_path, deps: dict) -> None:
    """Display-name shortening only affects the table's shown text
    (set_name_formatter) — lookup must still use the caller's exact,
    unshortened name string."""
    from mdf_viewer.settings import Settings
    s = Settings(path=tmp_path / "s.json")
    s.display_name_rule_enabled = True
    s.display_name_separator = "."
    s.display_name_direction = "right"
    s.display_name_segments = 1
    ctrl_with_settings = AppController(
        loader=deps["loader"],
        signal_browser=deps["browser"],
        plot_area=deps["plot"],
        active_signals_table=deps["table"],
        measurement_info_box=deps["info_box"],
        signal_info_box=deps["signal_info"],
        settings=s,
    )
    ctrl_with_settings.refresh_display_names()
    full_name = "ZF_DTI._.AutoDiagPosition.PosADP"
    meta = _make_metadata(full_name, gi=0, ci=1)
    deps["loader"].find_signal_by_name.return_value = [meta]

    result = ctrl_with_settings.find_signal_by_name(full_name)

    deps["loader"].find_signal_by_name.assert_called_once_with(full_name)
    assert result == [meta]


# ---------------------------------------------------------------------------
# restore_signals
# ---------------------------------------------------------------------------

def _make_snapshot(name: str = "rpm", **kwargs):
    from mdf_viewer.controller.app_controller import ActiveSignalSnapshot
    defaults = dict(
        color=(200, 100, 50),
        line_width=2,
        line_style="dashes",
        display_mode="line_marker",
        marker_shape="square",
        step_mode=True,
        enum_display_table=False,
        enum_display_cursor=True,
        enum_display_yaxis=True,
    )
    defaults.update(kwargs)
    return ActiveSignalSnapshot(name=name, **defaults)


@pytest.mark.requirement("REQ-FILE-066")
@pytest.mark.requirement("REQ-FILE-031")
def test_restore_signals_adds_signal(ctrl: AppController, deps: dict) -> None:
    meta = _make_metadata("rpm", gi=0, ci=5)
    deps["loader"].load_signal.return_value = (_make_signal_data(), meta)
    snap = _make_snapshot("rpm")
    ctrl.restore_signals([(snap, 0, 5)])
    assert len(ctrl.active_signals) == 1
    assert ctrl.active_signals[0].metadata.name == "rpm"


@pytest.mark.requirement("REQ-FILE-061")
@pytest.mark.requirement("REQ-FILE-066")
def test_restore_signals_applies_color(ctrl: AppController, deps: dict) -> None:
    meta = _make_metadata("sig", gi=0, ci=1)
    deps["loader"].load_signal.return_value = (_make_signal_data(), meta)
    snap = _make_snapshot("sig", color=(10, 20, 30))
    ctrl.restore_signals([(snap, 0, 1)])
    active = ctrl.active_signals[0]
    assert (active.color.red(), active.color.green(), active.color.blue()) == (10, 20, 30)


@pytest.mark.requirement("REQ-FILE-061")
def test_restore_signals_calls_recolor_on_plot(ctrl: AppController, deps: dict) -> None:
    from PyQt6.QtGui import QColor
    meta = _make_metadata("sig", gi=0, ci=1)
    deps["loader"].load_signal.return_value = (_make_signal_data(), meta)
    snap = _make_snapshot("sig", color=(10, 20, 30))
    ctrl.restore_signals([(snap, 0, 1)])
    deps["plot"].recolor_signal.assert_called_once()
    args = deps["plot"].recolor_signal.call_args[0]
    assert isinstance(args[1], QColor)
    assert args[1].red() == 10


@pytest.mark.requirement("REQ-FILE-061")
def test_restore_signals_updates_table_swatch(ctrl: AppController, deps: dict) -> None:
    from PyQt6.QtGui import QColor
    meta = _make_metadata("sig", gi=0, ci=1)
    deps["loader"].load_signal.return_value = (_make_signal_data(), meta)
    snap = _make_snapshot("sig", color=(99, 88, 77))
    ctrl.restore_signals([(snap, 0, 1)])
    deps["table"].set_row_color.assert_called_once()
    args = deps["table"].set_row_color.call_args[0]
    assert isinstance(args[1], QColor)
    assert args[1].red() == 99


@pytest.mark.requirement("REQ-FILE-061")
def test_restore_signals_applies_line_width(ctrl: AppController, deps: dict) -> None:
    meta = _make_metadata("sig", gi=0, ci=1)
    deps["loader"].load_signal.return_value = (_make_signal_data(), meta)
    snap = _make_snapshot("sig", line_width=3)
    ctrl.restore_signals([(snap, 0, 1)])
    deps["plot"].set_line_width.assert_called_once()
    assert ctrl.active_signals[0].line_width == 3


@pytest.mark.requirement("REQ-FILE-061")
def test_restore_signals_applies_step_mode(ctrl: AppController, deps: dict) -> None:
    meta = _make_metadata("sig", gi=0, ci=1)
    deps["loader"].load_signal.return_value = (_make_signal_data(), meta)
    snap = _make_snapshot("sig", step_mode=True)
    ctrl.restore_signals([(snap, 0, 1)])
    deps["plot"].set_step_mode.assert_called_once()
    assert ctrl.active_signals[0].step_mode is True


@pytest.mark.requirement("REQ-PLOT-020")
def test_restore_signals_skips_duplicate(ctrl: AppController, deps: dict) -> None:
    meta = _make_metadata("rpm", gi=0, ci=1)
    deps["loader"].load_signal.return_value = (_make_signal_data(), meta)
    ctrl.add_signal(0, 1)  # already added
    initial_count = len(ctrl.active_signals)
    snap = _make_snapshot("rpm")
    ctrl.restore_signals([(snap, 0, 1)])
    # add_signal returns False for duplicate — no new signal added
    assert len(ctrl.active_signals) == initial_count


@pytest.mark.requirement("REQ-FILE-066")
def test_restore_signals_multiple_signals(ctrl: AppController, deps: dict) -> None:
    deps["loader"].load_signal.side_effect = [
        (_make_signal_data(), _make_metadata("a", gi=0, ci=1)),
        (_make_signal_data(), _make_metadata("b", gi=0, ci=2)),
    ]
    snaps = [_make_snapshot("a"), _make_snapshot("b")]
    ctrl.restore_signals([(snaps[0], 0, 1), (snaps[1], 0, 2)])
    assert [s.metadata.name for s in ctrl.active_signals] == ["a", "b"]


# ---------------------------------------------------------------------------
# snapshot includes group_name
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-FILE-061")
def test_snapshot_includes_group_name(ctrl: AppController, deps: dict) -> None:
    meta = SignalMetadata(name="rpm", unit="rpm", group_index=0, channel_index=1, group_name="Engine")
    deps["loader"].load_signal.return_value = (_make_signal_data(), meta)
    ctrl.add_signal(0, 1)
    snap = ctrl.snapshot_active_signals()[0]
    assert snap.group_name == "Engine"


@pytest.mark.requirement("REQ-FILE-061")
def test_snapshot_group_name_empty_when_not_set(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    snap = ctrl.snapshot_active_signals()[0]
    assert snap.group_name == ""


# ---------------------------------------------------------------------------
# current_config_path
# ---------------------------------------------------------------------------

def test_current_config_path_initially_none(ctrl: AppController) -> None:
    assert ctrl.current_config_path is None


def test_current_config_path_can_be_set(ctrl: AppController, tmp_path) -> None:
    p = tmp_path / "session.mvc"
    ctrl.current_config_path = p
    assert ctrl.current_config_path == p


@pytest.mark.requirement("REQ-FILE-012")
@pytest.mark.requirement("REQ-FILE-010")
def test_load_file_clears_config_path(ctrl: AppController, deps: dict, tmp_path) -> None:
    ctrl.current_config_path = tmp_path / "session.mvc"
    ctrl.load_file(tmp_path / "test.mf4")
    assert ctrl.current_config_path is None


# ---------------------------------------------------------------------------
# capture_config
# ---------------------------------------------------------------------------

def _make_zoom_state():
    from mdf_viewer.view_model.zoom_state import ZoomState
    return ZoomState(x_range=(0.0, 5.0), y_ranges={})


@pytest.mark.requirement("REQ-FILE-061")
def test_capture_config_returns_viewer_config(ctrl: AppController, deps: dict, tmp_path) -> None:
    from mdf_viewer.model.viewer_config import ViewerConfig
    deps["plot"].get_zoom_state.return_value = _make_zoom_state()
    deps["plot"].get_axis_grouping.return_value = ([], [])
    deps["loader"].is_open = True
    deps["loader"]._path = tmp_path / "test.mf4"
    config = ctrl.capture_config(tmp_path / "session.mvc")
    assert isinstance(config, ViewerConfig)


@pytest.mark.requirement("REQ-FILE-061")
def test_capture_config_x_range(ctrl: AppController, deps: dict, tmp_path) -> None:
    deps["plot"].get_zoom_state.return_value = _make_zoom_state()
    deps["plot"].get_axis_grouping.return_value = ([], [])
    deps["loader"].is_open = True
    deps["loader"]._path = tmp_path / "test.mf4"
    config = ctrl.capture_config(tmp_path / "session.mvc")
    assert config.x_range == (0.0, 5.0)


@pytest.mark.requirement("REQ-FILE-061")
def test_capture_config_measurement_path(ctrl: AppController, deps: dict, tmp_path) -> None:
    meas = tmp_path / "meas.mf4"
    deps["plot"].get_zoom_state.return_value = _make_zoom_state()
    deps["plot"].get_axis_grouping.return_value = ([], [])
    deps["loader"].is_open = True
    deps["loader"]._path = meas
    config = ctrl.capture_config(tmp_path / "session.mvc")
    assert config.measurement_path == str(meas)


def test_capture_config_no_file_open(ctrl: AppController, deps: dict, tmp_path) -> None:
    deps["plot"].get_zoom_state.return_value = _make_zoom_state()
    deps["plot"].get_axis_grouping.return_value = ([], [])
    deps["loader"].is_open = False
    config = ctrl.capture_config(tmp_path / "session.mvc")
    assert config.measurement_path == ""


@pytest.mark.requirement("REQ-FILE-061")
def test_capture_config_cursor_snapshot_used(ctrl: AppController, deps: dict, tmp_path) -> None:
    from unittest.mock import MagicMock
    cursor = MagicMock()
    cursor.snapshot.return_value = {"mode": "TWO", "positions": [1.0, 4.0]}
    ctrl.set_cursor_controller(cursor)
    deps["plot"].get_zoom_state.return_value = _make_zoom_state()
    deps["plot"].get_axis_grouping.return_value = ([], [])
    deps["loader"].is_open = False
    config = ctrl.capture_config(tmp_path / "session.mvc")
    assert config.cursor_mode == "TWO"
    assert config.cursor_positions == (1.0, 4.0)


@pytest.mark.requirement("REQ-FILE-061")
def test_capture_config_no_settings_uses_defaults(
    ctrl: AppController, deps: dict, tmp_path
) -> None:
    """No Settings wired in (settings=None) must not crash (#89)."""
    deps["plot"].get_zoom_state.return_value = _make_zoom_state()
    deps["plot"].get_axis_grouping.return_value = ([], [])
    deps["loader"].is_open = False
    config = ctrl.capture_config(tmp_path / "session.mvc")
    assert config.display_name_separator == "."
    assert config.display_name_direction == "right"
    assert config.display_name_segments == 1


@pytest.mark.requirement("REQ-FILE-061")
@pytest.mark.requirement("REQ-PLOT-170")
def test_capture_config_uses_settings_display_name_rule(deps: dict, tmp_path) -> None:
    """The session's shortening-rule *parameters* are captured from Settings (#89)."""
    from mdf_viewer.settings import Settings
    s = Settings(path=tmp_path / "s.json")
    s.display_name_separator = "_"
    s.display_name_direction = "left"
    s.display_name_segments = 4
    ctrl_with_settings = AppController(
        loader=deps["loader"],
        signal_browser=deps["browser"],
        plot_area=deps["plot"],
        active_signals_table=deps["table"],
        measurement_info_box=deps["info_box"],
        signal_info_box=deps["signal_info"],
        settings=s,
    )
    deps["plot"].get_zoom_state.return_value = _make_zoom_state()
    deps["plot"].get_axis_grouping.return_value = ([], [])
    deps["loader"].is_open = False
    config = ctrl_with_settings.capture_config(tmp_path / "session.mvc")
    assert config.display_name_separator == "_"
    assert config.display_name_direction == "left"
    assert config.display_name_segments == 4


# ---------------------------------------------------------------------------
# restore_config
# ---------------------------------------------------------------------------

def _make_viewer_config(**kwargs):
    from mdf_viewer.config_manager import CONFIG_FORMAT_VERSION
    from mdf_viewer.model.viewer_config import ViewerConfig
    defaults = dict(
        format_version=CONFIG_FORMAT_VERSION,
        measurement_path="/x.mf4",
        signals=(),
        x_range=(0.0, 10.0),
        y_ranges={},
        merged_groups=(),
        synced_groups=(),
        cursor_mode="HIDDEN",
        cursor_positions=(0.0, 0.0),
        selected_signal=None,
        display_name_separator=".",
        display_name_direction="right",
        display_name_segments=1,
    )
    defaults.update(kwargs)
    return ViewerConfig(**defaults)


@pytest.mark.requirement("REQ-PLOT-036")
def test_restore_config_calls_restore_axis_grouping(ctrl: AppController, deps: dict) -> None:
    config = _make_viewer_config(
        merged_groups=(("a", "b"),),
    )
    ctrl.restore_config(config, [])
    deps["plot"].restore_axis_grouping.assert_called_once()


@pytest.mark.requirement("REQ-FILE-061")
def test_restore_config_calls_set_zoom_state(ctrl: AppController, deps: dict) -> None:
    config = _make_viewer_config()
    ctrl.restore_config(config, [])
    deps["plot"].set_zoom_state.assert_called_once()


@pytest.mark.requirement("REQ-FILE-061")
def test_restore_config_calls_cursor_restore(ctrl: AppController, deps: dict) -> None:
    from unittest.mock import MagicMock
    cursor = MagicMock()
    ctrl.set_cursor_controller(cursor)
    config = _make_viewer_config(cursor_mode="ONE", cursor_positions=(2.5, 0.0))
    ctrl.restore_config(config, [])
    cursor.restore.assert_called_once_with({"mode": "ONE", "positions": [2.5, 0.0]})


@pytest.mark.requirement("REQ-FILE-061")
def test_restore_config_sets_selection(ctrl: AppController, deps: dict) -> None:
    meta = _make_metadata("RPM", gi=0, ci=1)
    deps["loader"].load_signal.return_value = (_make_signal_data(), meta)
    snap = _make_snapshot("RPM")
    config = _make_viewer_config(selected_signal="RPM")
    ctrl.restore_config(config, [(snap, 0, 1)])
    assert ctrl.selected_signal is not None
    assert ctrl.selected_signal.metadata.name == "RPM"


def test_restore_config_no_settings_does_not_crash(ctrl: AppController, deps: dict) -> None:
    """No Settings wired in (settings=None) must not crash (#89)."""
    config = _make_viewer_config()
    ctrl.restore_config(config, [])  # must not raise


@pytest.mark.requirement("REQ-PLOT-170")
def test_restore_config_applies_display_name_rule_to_settings(
    deps: dict, tmp_path
) -> None:
    """Restoring a session writes its saved shortening-rule parameters back
    into Settings — becoming the new global default too (#89)."""
    from mdf_viewer.settings import Settings
    s = Settings(path=tmp_path / "s.json")
    ctrl_with_settings = AppController(
        loader=deps["loader"],
        signal_browser=deps["browser"],
        plot_area=deps["plot"],
        active_signals_table=deps["table"],
        measurement_info_box=deps["info_box"],
        signal_info_box=deps["signal_info"],
        settings=s,
    )
    config = _make_viewer_config(
        display_name_separator="_",
        display_name_direction="left",
        display_name_segments=4,
    )
    ctrl_with_settings.restore_config(config, [])
    assert s.display_name_separator == "_"
    assert s.display_name_direction == "left"
    assert s.display_name_segments == 4


@pytest.mark.requirement("REQ-PLOT-160")
def test_restore_config_refreshes_display_names(deps: dict, tmp_path) -> None:
    from mdf_viewer.settings import Settings
    s = Settings(path=tmp_path / "s.json")
    ctrl_with_settings = AppController(
        loader=deps["loader"],
        signal_browser=deps["browser"],
        plot_area=deps["plot"],
        active_signals_table=deps["table"],
        measurement_info_box=deps["info_box"],
        signal_info_box=deps["signal_info"],
        settings=s,
    )
    config = _make_viewer_config()
    deps["table"].reset_mock()
    ctrl_with_settings.restore_config(config, [])
    deps["table"].set_name_formatter.assert_called_once()


# ---------------------------------------------------------------------------
# on_merge_y_axis_requested / on_sync_y_axis_requested — dual-group guard (#84)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-031")
def test_merge_y_axis_calls_merge_signals_when_ungrouped(ctrl: AppController, deps: dict) -> None:
    deps["plot"].get_group_type.return_value = None
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    ctrl.on_merge_y_axis_requested(ctrl.active_signals)
    deps["plot"].merge_signals.assert_called_once()


@pytest.mark.requirement("REQ-PLOT-033")
def test_merge_y_axis_rejected_when_signal_already_synced(
    ctrl: AppController, deps: dict
) -> None:
    deps["plot"].get_group_type.return_value = "synced"
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    ctrl.on_merge_y_axis_requested(ctrl.active_signals)
    deps["plot"].merge_signals.assert_not_called()


@pytest.mark.requirement("REQ-PLOT-032")
def test_sync_y_axis_calls_sync_signals_when_ungrouped(ctrl: AppController, deps: dict) -> None:
    deps["plot"].get_group_type.return_value = None
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    ctrl.on_sync_y_axis_requested(ctrl.active_signals)
    deps["plot"].sync_signals.assert_called_once()


@pytest.mark.requirement("REQ-PLOT-033")
def test_sync_y_axis_rejected_when_signal_already_merged(
    ctrl: AppController, deps: dict
) -> None:
    deps["plot"].get_group_type.return_value = "merged"
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    ctrl.on_sync_y_axis_requested(ctrl.active_signals)
    deps["plot"].sync_signals.assert_not_called()


@pytest.mark.requirement("REQ-PLOT-031")
@pytest.mark.requirement("REQ-PLOT-032")
def test_refresh_table_group_state_pushes_merged_and_synced_sets(
    ctrl: AppController, deps: dict
) -> None:
    deps["plot"].get_group_type.return_value = None
    deps["plot"].get_merged_signals.return_value = {"merged-marker"}
    deps["plot"].get_synced_signals.return_value = {"synced-marker"}
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    ctrl.on_merge_y_axis_requested(ctrl.active_signals)
    deps["table"].set_group_membership.assert_called_with({"merged-marker"}, {"synced-marker"})


# ---------------------------------------------------------------------------
# Plot Stripes
# ---------------------------------------------------------------------------

def test_add_signal_passes_stripe_through(ctrl: AppController, deps: dict) -> None:
    stripe = MagicMock()
    ctrl.add_signal(0, 1, stripe=stripe)
    deps["plot"].add_signal.assert_called_once()
    _, kwargs = deps["plot"].add_signal.call_args
    assert kwargs["stripe"] is stripe


def test_add_signal_defaults_stripe_to_none(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    _, kwargs = deps["plot"].add_signal.call_args
    assert kwargs["stripe"] is None


@pytest.mark.requirement("REQ-PLOT-190")
def test_create_stripe_delegates_to_plot(ctrl: AppController, deps: dict) -> None:
    deps["plot"].create_stripe.return_value = "new-stripe"
    assert ctrl.create_stripe() == "new-stripe"
    deps["plot"].create_stripe.assert_called_once()


@pytest.mark.requirement("REQ-PLOT-186")
def test_delete_stripe_refuses_last_stripe(ctrl: AppController, deps: dict) -> None:
    deps["plot"].get_stripes.return_value = ["only-stripe"]
    stripe = MagicMock()
    assert ctrl.delete_stripe(stripe) is False
    deps["plot"].delete_stripe.assert_not_called()


@pytest.mark.requirement("REQ-PLOT-194")
def test_delete_stripe_refuses_nonempty_without_force(ctrl: AppController, deps: dict) -> None:
    deps["plot"].get_stripes.return_value = ["s0", "s1"]
    deps["plot"].get_signals_in_stripe.return_value = ["sig"]
    stripe = MagicMock()
    assert ctrl.delete_stripe(stripe) is False
    deps["plot"].delete_stripe.assert_not_called()


def test_delete_stripe_deletes_directly_when_empty(ctrl: AppController, deps: dict) -> None:
    deps["plot"].get_stripes.return_value = ["s0", "s1"]
    deps["plot"].get_signals_in_stripe.return_value = []
    deps["plot"].delete_stripe.return_value = True
    stripe = MagicMock()
    assert ctrl.delete_stripe(stripe) is True
    deps["plot"].delete_stripe.assert_called_once_with(stripe)


@pytest.mark.requirement("REQ-PLOT-194")
def test_delete_stripe_with_force_removes_each_signal_via_full_pipeline(
    ctrl: AppController, deps: dict
) -> None:
    """Regression test: force-deleting a non-empty stripe must remove each
    signal via the full AppController.remove_signal pipeline (table row,
    cursor cleanup, active-list) — not just tear it down from the plot."""
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    stripe = MagicMock()
    deps["plot"].get_stripes.return_value = ["s0", "s1"]
    deps["plot"].get_signals_in_stripe.return_value = list(ctrl.active_signals)
    deps["plot"].delete_stripe.return_value = True

    assert ctrl.delete_stripe(stripe, force=True) is True

    assert ctrl.active_signals == []
    assert deps["table"].remove_row.call_count == 2
    deps["plot"].delete_stripe.assert_called_once_with(stripe)


def test_get_stripes_delegates_to_plot(ctrl: AppController, deps: dict) -> None:
    deps["plot"].get_stripes.return_value = ["s0", "s1"]
    assert ctrl.get_stripes() == ["s0", "s1"]


def test_get_stripe_for_signal_delegates_to_plot(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    active = ctrl.active_signals[0]
    deps["plot"].get_stripe_for_signal.return_value = "s0"
    assert ctrl.get_stripe_for_signal(active) == "s0"
    deps["plot"].get_stripe_for_signal.assert_called_once_with(active)


def test_get_signals_in_stripe_delegates_to_plot(ctrl: AppController, deps: dict) -> None:
    stripe = MagicMock()
    deps["plot"].get_signals_in_stripe.return_value = ["a", "b"]
    assert ctrl.get_signals_in_stripe(stripe) == ["a", "b"]
    deps["plot"].get_signals_in_stripe.assert_called_once_with(stripe)


@pytest.mark.requirement("REQ-PLOT-202")
def test_move_signals_to_stripe_calls_plot_per_signal(ctrl: AppController, deps: dict) -> None:
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    stripe = MagicMock()
    ctrl.move_signals_to_stripe(ctrl.active_signals, stripe)
    assert deps["plot"].move_signal_to_stripe.call_count == 2
    for active in ctrl.active_signals:
        deps["plot"].move_signal_to_stripe.assert_any_call(active, stripe)


def test_move_signals_to_stripe_refreshes_cursor_labels(
    ctrl: AppController, deps: dict
) -> None:
    cursor_ctrl = MagicMock()
    ctrl.set_cursor_controller(cursor_ctrl)
    ctrl.add_signal(0, 1)
    cursor_ctrl.reset_mock()
    ctrl.move_signals_to_stripe(ctrl.active_signals, MagicMock())
    cursor_ctrl.refresh.assert_called_once()


@pytest.mark.requirement("REQ-PLOT-191")
def test_move_signals_to_new_stripe_creates_then_moves(ctrl: AppController, deps: dict) -> None:
    new_stripe = MagicMock()
    deps["plot"].create_stripe.return_value = new_stripe
    ctrl.add_signal(0, 1)
    ctrl.move_signals_to_new_stripe(ctrl.active_signals)
    deps["plot"].create_stripe.assert_called_once()
    deps["plot"].move_signal_to_stripe.assert_called_once_with(ctrl.active_signals[0], new_stripe)


def test_move_signals_to_new_stripe_refreshes_cursor_labels(
    ctrl: AppController, deps: dict
) -> None:
    cursor_ctrl = MagicMock()
    ctrl.set_cursor_controller(cursor_ctrl)
    ctrl.add_signal(0, 1)
    cursor_ctrl.reset_mock()
    ctrl.move_signals_to_new_stripe(ctrl.active_signals)
    cursor_ctrl.refresh.assert_called_once()


# ---------------------------------------------------------------------------
# Zoom scope (All Stripes / Active Stripe toggle)
# ---------------------------------------------------------------------------

def _ctrl_with_zoom_scope(tmp_path, deps: dict, scope: str) -> AppController:
    from mdf_viewer.settings import Settings
    s = Settings(path=tmp_path / "s.json")
    s.zoom_scope = scope
    return AppController(
        loader=deps["loader"],
        signal_browser=deps["browser"],
        plot_area=deps["plot"],
        active_signals_table=deps["table"],
        measurement_info_box=deps["info_box"],
        signal_info_box=deps["signal_info"],
        settings=s,
    )


@pytest.mark.requirement("REQ-PLOT-057")
def test_zoom_to_fit_passes_all_stripes_true_by_default(
    ctrl: AppController, deps: dict
) -> None:
    ctrl.zoom_to_fit()
    deps["plot"].zoom_to_fit.assert_called_once_with(all_stripes=True)


@pytest.mark.requirement("REQ-PLOT-057")
def test_zoom_to_fit_passes_all_stripes_false_when_scope_is_active_stripe(
    tmp_path, deps: dict
) -> None:
    ctrl = _ctrl_with_zoom_scope(tmp_path, deps, "active_stripe")
    ctrl.zoom_to_fit()
    deps["plot"].zoom_to_fit.assert_called_once_with(all_stripes=False)


@pytest.mark.requirement("REQ-PLOT-057")
def test_zoom_y_to_view_passes_all_stripes_true_by_default(
    ctrl: AppController, deps: dict
) -> None:
    ctrl.zoom_y_to_view()
    deps["plot"].zoom_y_to_view.assert_called_once_with(all_stripes=True)


@pytest.mark.requirement("REQ-PLOT-057")
def test_zoom_y_to_view_passes_all_stripes_false_when_scope_is_active_stripe(
    tmp_path, deps: dict
) -> None:
    ctrl = _ctrl_with_zoom_scope(tmp_path, deps, "active_stripe")
    ctrl.zoom_y_to_view()
    deps["plot"].zoom_y_to_view.assert_called_once_with(all_stripes=False)


def test_zoom_to_fit_defaults_all_stripes_without_settings(deps: dict) -> None:
    ctrl_no_settings = AppController(
        loader=deps["loader"],
        signal_browser=deps["browser"],
        plot_area=deps["plot"],
        active_signals_table=deps["table"],
        measurement_info_box=deps["info_box"],
        signal_info_box=deps["signal_info"],
    )
    ctrl_no_settings.zoom_to_fit()
    deps["plot"].zoom_to_fit.assert_called_once_with(all_stripes=True)


# ---------------------------------------------------------------------------
# Event bus (#70)
# ---------------------------------------------------------------------------

def _two_distinct_signals(deps: dict) -> None:
    """Make deps["loader"] return metadata matching whatever indices are requested."""
    deps["loader"].load_signal.side_effect = (
        lambda gi, ci: (_make_signal_data(), _make_metadata(name=f"s{ci}", gi=gi, ci=ci))
    )


@pytest.mark.requirement("REQ-PLUGIN-010")
def test_load_file_emits_file_loaded(ctrl: AppController) -> None:
    seen = []
    ctrl.events.file_loaded.connect(seen.append)
    ctrl.load_file("test.mf4")
    assert len(seen) == 1
    assert seen[0].path == "test.mf4"


@pytest.mark.requirement("REQ-PLUGIN-020")
def test_add_signal_emits_signal_added(ctrl: AppController) -> None:
    seen = []
    ctrl.events.signal_added.connect(seen.append)
    ctrl.add_signal(0, 1)
    assert len(seen) == 1
    assert seen[0].signal is ctrl.active_signals[0]
    assert seen[0].stripe is None


@pytest.mark.requirement("REQ-PLUGIN-020")
def test_add_signal_passes_stripe_in_event(ctrl: AppController) -> None:
    stripe = MagicMock()
    seen = []
    ctrl.events.signal_added.connect(seen.append)
    ctrl.add_signal(0, 1, stripe=stripe)
    assert seen[0].stripe is stripe


@pytest.mark.requirement("REQ-PLUGIN-020")
def test_add_signal_duplicate_does_not_emit(ctrl: AppController) -> None:
    ctrl.add_signal(0, 1)
    seen = []
    ctrl.events.signal_added.connect(seen.append)
    ctrl.add_signal(0, 1)  # duplicate — no-op
    assert seen == []


@pytest.mark.requirement("REQ-PLUGIN-030")
def test_remove_signal_emits_signal_removed(ctrl: AppController) -> None:
    ctrl.add_signal(0, 1)
    active = ctrl.active_signals[0]
    seen = []
    ctrl.events.signal_removed.connect(seen.append)
    ctrl.remove_signal(active)
    assert len(seen) == 1
    assert seen[0].signal is active


@pytest.mark.requirement("REQ-PLUGIN-030")
def test_remove_signal_noop_does_not_emit(ctrl: AppController, deps: dict) -> None:
    other = ActiveSignal(data=_make_signal_data(), metadata=_make_metadata(), color=(1, 2, 3))
    seen = []
    ctrl.events.signal_removed.connect(seen.append)
    ctrl.remove_signal(other)  # not active — no-op
    assert seen == []


@pytest.mark.requirement("REQ-PLUGIN-030")
def test_remove_signals_emits_once_per_signal(ctrl: AppController, deps: dict) -> None:
    _two_distinct_signals(deps)
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    actives = list(ctrl.active_signals)
    seen = []
    ctrl.events.signal_removed.connect(seen.append)
    ctrl.remove_signals(actives)
    assert [e.signal for e in seen] == actives


@pytest.mark.requirement("REQ-PLUGIN-030")
def test_remove_all_emits_once_per_signal(ctrl: AppController, deps: dict) -> None:
    _two_distinct_signals(deps)
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    actives = list(ctrl.active_signals)
    seen = []
    ctrl.events.signal_removed.connect(seen.append)
    ctrl.remove_all()
    assert [e.signal for e in seen] == actives


@pytest.mark.requirement("REQ-PLUGIN-040")
def test_set_selected_signal_emits_selection_changed(ctrl: AppController) -> None:
    ctrl.add_signal(0, 1)
    active = ctrl.active_signals[0]
    seen = []
    ctrl.events.selection_changed.connect(seen.append)
    ctrl.set_selected_signal(active)
    assert len(seen) == 1
    assert seen[0].selected == [active]


@pytest.mark.requirement("REQ-PLUGIN-040")
def test_set_selected_signal_none_emits_empty_selection(ctrl: AppController) -> None:
    ctrl.add_signal(0, 1)
    ctrl.set_selected_signal(ctrl.active_signals[0])
    seen = []
    ctrl.events.selection_changed.connect(seen.append)
    ctrl.set_selected_signal(None)
    assert seen[0].selected == []


@pytest.mark.requirement("REQ-PLUGIN-040")
def test_set_multi_selected_emits_selection_changed(ctrl: AppController, deps: dict) -> None:
    _two_distinct_signals(deps)
    ctrl.add_signal(0, 1)
    ctrl.add_signal(0, 2)
    actives = list(ctrl.active_signals)
    seen = []
    ctrl.events.selection_changed.connect(seen.append)
    ctrl.set_multi_selected(actives)
    assert seen[0].selected == actives
