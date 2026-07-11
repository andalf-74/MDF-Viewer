"""Tests for AppController.

All dependencies (loader + views) are mocked so no QApplication or real file
is needed. The controller is pure coordination logic — tests verify that it
calls the right methods on the right objects in the right order.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, call

import numpy as np
import pytest
from PyQt6.QtGui import QColor

from mdf_viewer.controller.app_controller import AppController, _COLOR_PALETTE
from mdf_viewer.errors import MdfLoadError
from mdf_viewer.model.loaded_measurement import LoadedMeasurement
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
    plot = MagicMock()
    # Sane iterable/None defaults for capture_config's stripe walk (#106) —
    # a bare MagicMock() isn't iterable, which would break every test that
    # doesn't itself care about stripes but still exercises capture_config.
    plot.get_stripes.return_value = []
    plot.get_stripe_sizes.return_value = []
    plot.get_active_stripe.return_value = None
    plot.get_stripe_for_signal.return_value = None
    return {
        "loader": loader,
        "browser": MagicMock(),
        "plot": plot,
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
    deps["browser"].populate_all.assert_called_once_with([("M1", groups)])


@pytest.mark.requirement("REQ-FILE-012")
def test_load_file_updates_info_box(ctrl: AppController, deps: dict) -> None:
    info = _make_measurement_info()
    deps["loader"].measurement_info.return_value = info
    ctrl.load_file("test.mf4")
    (measurement,) = ctrl.measurements
    deps["info_box"].set_measurements.assert_called_once_with([measurement], measurement)


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
    set_pos = [i for i, c in enumerate(info_box.mock_calls) if "set_measurements" in str(c)]
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
    deps["signal_info"].set_metadata.assert_called_once_with(
        sig.metadata, display_name=sig.metadata.name,
    )


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
    deps["plot"].swimlanes.assert_called_once_with(ctrl.current_workspace.active)


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
    a, b, c = ctrl.current_workspace.active
    ctrl.reorder_signals([c, a, b])
    assert ctrl.current_workspace.active == [c, a, b]


def test_reorder_signals_preserves_identity(ctrl: AppController, deps: dict) -> None:
    deps["loader"].load_signal.return_value = (_make_signal_data(), _make_metadata())
    ctrl.add_signal(0, 0)
    original = ctrl.current_workspace.active[0]
    ctrl.reorder_signals([original])
    assert ctrl.current_workspace.active[0] is original


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
    a, b = ctrl.current_workspace.active
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
    stub = SimpleNamespace(metadata=SimpleNamespace(name="a.b.PosADP"), measurement=None)
    assert formatter(stub) == "PosADP"


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
    stub = SimpleNamespace(metadata=SimpleNamespace(name="any.name"), measurement=None)
    assert formatter(stub) == "any.name"


@pytest.mark.requirement("REQ-PLOT-306")
def test_display_name_no_prefix_with_one_measurement(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader()])
    ctrl2.replace_measurements(["a.mf4"])
    ctrl2.add_signal(0, 1)
    (sig,) = ctrl2.active_signals
    assert ctrl2._format_display_name(sig) == sig.metadata.name


@pytest.mark.requirement("REQ-PLOT-306")
def test_display_name_prefixed_with_multiple_measurements(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader(), _make_pool_loader()])
    ctrl2.replace_measurements(["a.mf4"])
    ctrl2.add_measurements(["b.mf4"])
    m1, m2 = ctrl2.measurements
    ctrl2.add_signal(0, 1, measurement=m1)
    ctrl2.add_signal(0, 1, measurement=m2)
    sig1, sig2 = ctrl2.active_signals
    assert ctrl2._format_display_name(sig1) == f"[{m1.label}] {sig1.metadata.name}"
    assert ctrl2._format_display_name(sig2) == f"[{m2.label}] {sig2.metadata.name}"


@pytest.mark.requirement("REQ-PLOT-307")
def test_display_name_prefix_wraps_already_shortened_name(tmp_path, deps: dict) -> None:
    from mdf_viewer.settings import Settings
    s = Settings(path=tmp_path / "s.json")
    s.display_name_rule_enabled = True
    s.display_name_separator = "."
    s.display_name_direction = "right"
    s.display_name_segments = 1
    loader_a, loader_b = _make_pool_loader(), _make_pool_loader()
    loader_a.load_signal.return_value = (
        _make_signal_data(), _make_metadata("a.b.PosADP", gi=0, ci=1),
    )
    loader_b.load_signal.return_value = (
        _make_signal_data(), _make_metadata("a.b.PosADP", gi=0, ci=1),
    )
    ctrl2 = _make_ctrl_with_loaders(deps, [loader_a, loader_b])
    ctrl2._settings = s
    ctrl2.replace_measurements(["a.mf4"])
    ctrl2.add_measurements(["b.mf4"])
    m1, m2 = ctrl2.measurements
    ctrl2.add_signal(0, 1, measurement=m1)
    (sig,) = ctrl2.active_signals

    assert ctrl2._format_display_name(sig) == f"[{m1.label}] PosADP"


@pytest.mark.requirement("REQ-PLOT-306")
def test_display_name_unaffected_by_own_measurement_prefix_when_multi_but_no_measurement(
    deps: dict,
) -> None:
    """A signal with no measurement attached (legacy/back-compat add_signal
    path) is never prefixed, even once the pool has >1 measurement."""
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader(), _make_pool_loader()])
    ctrl2.replace_measurements(["a.mf4"])
    ctrl2.add_measurements(["b.mf4"])
    stub = SimpleNamespace(metadata=SimpleNamespace(name="sig"), measurement=None)
    assert ctrl2._format_display_name(stub) == "sig"


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
    assert ctrl.current_workspace.selected_signals == [sig]


def test_set_selected_signal_none_clears_selected_signals_list(ctrl: AppController) -> None:
    ctrl.set_selected_signal(None)
    assert ctrl.current_workspace.selected_signals == []


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
    assert ctrl.current_workspace.selected_signals == actives


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
    ctrl.current_workspace.selected_signals = [unknown]
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


@pytest.mark.requirement("REQ-FILE-032")
def test_find_similar_signal_by_name_delegates_to_loader(ctrl: AppController, deps: dict) -> None:
    meta = _make_metadata("FZGG_NAB_AKT\\ETKC:1", gi=0, ci=3)
    deps["loader"].find_similar_signal_by_name.return_value = [meta]
    result = ctrl.find_similar_signal_by_name("FZGG_NAB_AKT\\XCP:1")
    deps["loader"].find_similar_signal_by_name.assert_called_once_with("FZGG_NAB_AKT\\XCP:1")
    assert result == [meta]


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
# Multi-measurement pool (#101)
# ---------------------------------------------------------------------------

def _make_pool_loader() -> MagicMock:
    loader = MagicMock()
    loader.channel_tree.return_value = []
    loader.measurement_info.return_value = _make_measurement_info()
    loader.load_signal.return_value = (_make_signal_data(), _make_metadata())
    loader.is_open = True
    return loader


def _make_ctrl_with_loaders(deps: dict, loaders: list) -> AppController:
    """Build an AppController whose loader_factory hands out *loaders* in order."""
    it = iter(loaders)
    return AppController(
        loader=deps["loader"],
        signal_browser=deps["browser"],
        plot_area=deps["plot"],
        active_signals_table=deps["table"],
        measurement_info_box=deps["info_box"],
        signal_info_box=deps["signal_info"],
        loader_factory=lambda: next(it),
    )


@pytest.mark.requirement("REQ-FILE-021")
def test_replace_measurements_populates_pool(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader(), _make_pool_loader()])
    result = ctrl2.replace_measurements(["a.mf4", "b.mf4"])
    assert ctrl2.measurement_count == 2
    assert len(result.succeeded) == 2
    assert not result.failed


@pytest.mark.requirement("REQ-FILE-027")
def test_replace_measurements_uses_load_order_short_names(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader(), _make_pool_loader()])
    result = ctrl2.replace_measurements(["run.mf4", "sub/run.mf4"])
    labels = [m.label for m in result.succeeded]
    assert labels == ["M1", "M2"]


@pytest.mark.requirement("REQ-FILE-027")
def test_add_after_close_never_reuses_a_vacated_default_name(deps: dict) -> None:
    """Regression: closing measurements used to let their default names get
    reused, colliding with a still-loaded one (found live-testing #103)."""
    ctrl2 = _make_ctrl_with_loaders(
        deps,
        [_make_pool_loader(), _make_pool_loader(), _make_pool_loader(),
         _make_pool_loader(), _make_pool_loader()],
    )
    ctrl2.replace_measurements(["a.mf4", "b.mf4", "c.mf4"])  # M1, M2, M3
    m1, m2, m3 = ctrl2.measurements
    ctrl2.rename_measurement(m1, "Bla")
    ctrl2.close_measurement(m1)  # only m2 (M2), m3 (M3) remain
    ctrl2.close_measurement(m2)  # only m3 (M3) remains

    result = ctrl2.add_measurements(["d.mf4", "e.mf4"])

    labels = [m.label for m in result.succeeded]
    assert labels == ["M4", "M5"]


@pytest.mark.requirement("REQ-FILE-027")
def test_load_order_counter_resets_on_replace(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(
        deps, [_make_pool_loader(), _make_pool_loader(), _make_pool_loader()],
    )
    ctrl2.replace_measurements(["a.mf4", "b.mf4"])  # M1, M2
    ctrl2.close_measurement(ctrl2.measurements[0])

    result = ctrl2.replace_measurements(["c.mf4"])  # fresh start

    labels = [m.label for m in result.succeeded]
    assert labels == ["M1"]


@pytest.mark.requirement("REQ-FILE-021")
def test_replace_measurements_discards_previous_pool(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(
        deps, [_make_pool_loader(), _make_pool_loader(), _make_pool_loader()],
    )
    ctrl2.replace_measurements(["a.mf4"])
    assert ctrl2.measurement_count == 1
    ctrl2.replace_measurements(["b.mf4", "c.mf4"])
    assert ctrl2.measurement_count == 2


@pytest.mark.requirement("REQ-FILE-023")
def test_replace_measurements_collects_failures(deps: dict) -> None:
    bad = MagicMock()
    bad.open.side_effect = MdfLoadError("bad file")
    good = _make_pool_loader()
    ctrl2 = _make_ctrl_with_loaders(deps, [bad, good])
    result = ctrl2.replace_measurements(["bad.mf4", "good.mf4"])
    assert len(result.succeeded) == 1
    assert len(result.failed) == 1
    assert result.failed[0][0] == "bad.mf4"
    assert ctrl2.measurement_count == 1


@pytest.mark.requirement("REQ-FILE-021")
def test_replace_measurements_clears_current_tab_signals(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader(), _make_pool_loader()])
    ctrl2.replace_measurements(["a.mf4"])
    ctrl2.add_signal(0, 1)
    assert ctrl2.active_signals != []
    ctrl2.replace_measurements(["b.mf4"])
    assert ctrl2.active_signals == []


@pytest.mark.requirement("REQ-FILE-022")
def test_add_measurements_does_not_touch_existing_signals(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader(), _make_pool_loader()])
    ctrl2.replace_measurements(["a.mf4"])
    ctrl2.add_signal(0, 1)
    existing = ctrl2.active_signals
    ctrl2.add_measurements(["b.mf4"])
    assert ctrl2.measurement_count == 2
    assert ctrl2.active_signals == existing


@pytest.mark.requirement("REQ-FILE-024")
def test_add_measurements_failure_does_not_affect_existing_pool(deps: dict) -> None:
    bad = MagicMock()
    bad.open.side_effect = MdfLoadError("bad file")
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader(), bad])
    ctrl2.replace_measurements(["a.mf4"])
    result = ctrl2.add_measurements(["bad.mf4"])
    assert len(result.failed) == 1
    assert ctrl2.measurement_count == 1


@pytest.mark.requirement("REQ-FILE-028")
def test_measurement_has_signals_true_when_active(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader()])
    ctrl2.replace_measurements(["a.mf4"])
    (m1,) = ctrl2.measurements
    ctrl2.add_signal(0, 1, measurement=m1)
    assert ctrl2.measurement_has_signals(m1) is True


@pytest.mark.requirement("REQ-FILE-028")
def test_measurement_has_signals_false_when_none_active(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader()])
    ctrl2.replace_measurements(["a.mf4"])
    (m1,) = ctrl2.measurements
    assert ctrl2.measurement_has_signals(m1) is False


@pytest.mark.requirement("REQ-FILE-028")
def test_measurement_has_signals_scoped_to_its_own_measurement(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader(), _make_pool_loader()])
    ctrl2.replace_measurements(["a.mf4"])
    ctrl2.add_measurements(["b.mf4"])
    m1, m2 = ctrl2.measurements
    ctrl2.add_signal(0, 1, measurement=m1)
    assert ctrl2.measurement_has_signals(m2) is False


@pytest.mark.requirement("REQ-FILE-028")
def test_close_measurement_removes_only_its_own_signals(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader(), _make_pool_loader()])
    ctrl2.replace_measurements(["a.mf4"])
    ctrl2.add_measurements(["b.mf4"])
    m1, m2 = ctrl2.measurements
    ctrl2.add_signal(0, 1, measurement=m1)
    ctrl2.add_signal(0, 2, measurement=m2)
    assert len(ctrl2.active_signals) == 2

    ctrl2.close_measurement(m1)

    assert ctrl2.measurement_count == 1
    assert ctrl2.measurements == [m2]
    remaining = ctrl2.active_signals
    assert len(remaining) == 1
    assert remaining[0].measurement is m2


@pytest.mark.requirement("REQ-PLOT-020")
def test_add_signal_duplicate_check_is_measurement_scoped(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader(), _make_pool_loader()])
    ctrl2.replace_measurements(["a.mf4"])
    ctrl2.add_measurements(["b.mf4"])
    m1, m2 = ctrl2.measurements
    assert ctrl2.add_signal(0, 1, measurement=m1) is True
    # Same (group_index, channel_index) from a *different* measurement is not a duplicate.
    assert ctrl2.add_signal(0, 1, measurement=m2) is True
    assert len(ctrl2.active_signals) == 2


@pytest.mark.requirement("REQ-PLOT-020")
def test_add_signal_duplicate_check_still_applies_within_same_measurement(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader()])
    ctrl2.replace_measurements(["a.mf4"])
    (m1,) = ctrl2.measurements
    assert ctrl2.add_signal(0, 1, measurement=m1) is True
    assert ctrl2.add_signal(0, 1, measurement=m1) is False
    assert len(ctrl2.active_signals) == 1


def test_add_signal_without_measurement_resolves_sole_pool_entry(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader()])
    ctrl2.replace_measurements(["a.mf4"])
    (m1,) = ctrl2.measurements
    ctrl2.add_signal(0, 1)
    assert ctrl2.active_signals[0].measurement is m1


@pytest.mark.requirement("REQ-FILE-031")
def test_find_signal_by_name_searches_pool_union(deps: dict) -> None:
    loader_a = _make_pool_loader()
    loader_b = _make_pool_loader()
    meta_a = _make_metadata("speed", gi=0, ci=1)
    meta_b = _make_metadata("speed", gi=0, ci=5)
    loader_a.find_signal_by_name.return_value = [meta_a]
    loader_b.find_signal_by_name.return_value = [meta_b]
    ctrl2 = _make_ctrl_with_loaders(deps, [loader_a, loader_b])
    ctrl2.replace_measurements(["a.mf4"])
    ctrl2.add_measurements(["b.mf4"])

    result = ctrl2.find_signal_by_name("speed")

    assert result == [meta_a, meta_b]


@pytest.mark.requirement("REQ-FILE-031")
def test_find_signal_locations_by_name_tags_each_candidate(deps: dict) -> None:
    loader_a = _make_pool_loader()
    loader_b = _make_pool_loader()
    meta_a = _make_metadata("speed", gi=0, ci=1)
    meta_b = _make_metadata("speed", gi=0, ci=5)
    loader_a.find_signal_by_name.return_value = [meta_a]
    loader_b.find_signal_by_name.return_value = [meta_b]
    ctrl2 = _make_ctrl_with_loaders(deps, [loader_a, loader_b])
    ctrl2.replace_measurements(["a.mf4"])
    ctrl2.add_measurements(["b.mf4"])
    m1, m2 = ctrl2.measurements

    result = ctrl2.find_signal_locations_by_name("speed")

    assert result == [(m1, meta_a), (m2, meta_b)]


def test_find_signal_locations_by_name_empty_pool(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [])
    assert ctrl2.find_signal_locations_by_name("speed") == []


@pytest.mark.requirement("REQ-FILE-032")
def test_find_similar_signal_locations_by_name_tags_each_candidate(deps: dict) -> None:
    loader_a = _make_pool_loader()
    meta_a = _make_metadata("a\\ETKC:1", gi=0, ci=1)
    loader_a.find_similar_signal_by_name.return_value = [meta_a]
    ctrl2 = _make_ctrl_with_loaders(deps, [loader_a])
    ctrl2.replace_measurements(["a.mf4"])
    (m1,) = ctrl2.measurements

    result = ctrl2.find_similar_signal_locations_by_name("a\\XCP:1")

    assert result == [(m1, meta_a)]


def test_measurement_count_and_measurements_are_empty_initially(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [])
    assert ctrl2.measurement_count == 0
    assert ctrl2.measurements == []


@pytest.mark.requirement("REQ-BROWSER-050")
def test_measurement_at_returns_pool_entry(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader(), _make_pool_loader()])
    ctrl2.replace_measurements(["a.mf4"])
    ctrl2.add_measurements(["b.mf4"])
    m1, m2 = ctrl2.measurements
    assert ctrl2.measurement_at(0) is m1
    assert ctrl2.measurement_at(1) is m2


def test_measurement_at_out_of_range_returns_none(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [])
    assert ctrl2.measurement_at(0) is None
    assert ctrl2.measurement_at(-1) is None


@pytest.mark.requirement("REQ-BROWSER-010")
def test_replace_measurements_populates_browser_with_every_measurement(deps: dict) -> None:
    loader_a, loader_b = _make_pool_loader(), _make_pool_loader()
    groups_a, groups_b = [object()], [object()]
    loader_a.channel_tree.return_value = groups_a
    loader_b.channel_tree.return_value = groups_b
    ctrl2 = _make_ctrl_with_loaders(deps, [loader_a, loader_b])
    ctrl2.replace_measurements(["run1.mf4", "run2.mf4"])
    deps["browser"].populate_all.assert_called_with([("M1", groups_a), ("M2", groups_b)])


@pytest.mark.requirement("REQ-BROWSER-010")
def test_add_measurements_repopulates_browser_with_every_measurement(deps: dict) -> None:
    loader_a, loader_b = _make_pool_loader(), _make_pool_loader()
    groups_a, groups_b = [object()], [object()]
    loader_a.channel_tree.return_value = groups_a
    loader_b.channel_tree.return_value = groups_b
    ctrl2 = _make_ctrl_with_loaders(deps, [loader_a, loader_b])
    ctrl2.replace_measurements(["run1.mf4"])
    deps["browser"].populate_all.reset_mock()
    ctrl2.add_measurements(["run2.mf4"])
    deps["browser"].populate_all.assert_called_once_with([("M1", groups_a), ("M2", groups_b)])


@pytest.mark.requirement("REQ-FILE-028")
def test_close_measurement_updates_browser_to_remaining_measurement(deps: dict) -> None:
    loader_a = _make_pool_loader()
    loader_b = _make_pool_loader()
    groups_b = [object()]
    loader_b.channel_tree.return_value = groups_b
    ctrl2 = _make_ctrl_with_loaders(deps, [loader_a, loader_b])
    ctrl2.replace_measurements(["a.mf4"])
    ctrl2.add_measurements(["b.mf4"])
    m1, m2 = ctrl2.measurements

    ctrl2.close_measurement(m1)

    deps["browser"].populate_all.assert_called_with([(m2.label, groups_b)])


@pytest.mark.requirement("REQ-FILE-028")
def test_close_last_measurement_empties_browser(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader()])
    ctrl2.replace_measurements(["a.mf4"])
    (m1,) = ctrl2.measurements
    deps["browser"].populate_all.reset_mock()

    ctrl2.close_measurement(m1)

    deps["browser"].populate_all.assert_called_with([])


@pytest.mark.requirement("REQ-PLOT-301")
def test_replace_measurements_refreshes_axes_on_every_tab(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader()])
    plot2, table2 = MagicMock(), MagicMock()
    ctrl2.create_tab(plot2, table2)

    ctrl2.replace_measurements(["a.mf4"])

    deps["plot"].refresh_measurement_axes.assert_called_with(ctrl2.measurements, False)
    plot2.refresh_measurement_axes.assert_called_with(ctrl2.measurements, False)


@pytest.mark.requirement("REQ-PLOT-301")
def test_add_measurements_refreshes_axes_on_every_tab(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader(), _make_pool_loader()])
    plot2, table2 = MagicMock(), MagicMock()
    ctrl2.create_tab(plot2, table2)
    ctrl2.replace_measurements(["a.mf4"])
    deps["plot"].refresh_measurement_axes.reset_mock()
    plot2.refresh_measurement_axes.reset_mock()

    ctrl2.add_measurements(["b.mf4"])

    deps["plot"].refresh_measurement_axes.assert_called_with(ctrl2.measurements, False)
    plot2.refresh_measurement_axes.assert_called_with(ctrl2.measurements, False)


@pytest.mark.requirement("REQ-PLOT-301")
def test_close_measurement_refreshes_axes_on_every_tab(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader()])
    plot2, table2 = MagicMock(), MagicMock()
    ctrl2.create_tab(plot2, table2)
    ctrl2.replace_measurements(["a.mf4"])
    (m1,) = ctrl2.measurements
    deps["plot"].refresh_measurement_axes.reset_mock()
    plot2.refresh_measurement_axes.reset_mock()

    ctrl2.close_measurement(m1)

    deps["plot"].refresh_measurement_axes.assert_called_with([], False)
    plot2.refresh_measurement_axes.assert_called_with([], False)


# ---------------------------------------------------------------------------
# Primary Measurement and rename (#103)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-317")
def test_primary_measurement_defaults_to_first_loaded(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader(), _make_pool_loader()])
    ctrl2.replace_measurements(["a.mf4", "b.mf4"])
    m1, m2 = ctrl2.measurements
    assert ctrl2.primary_measurement is m1


@pytest.mark.requirement("REQ-PLOT-317")
def test_primary_measurement_none_when_nothing_loaded(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [])
    assert ctrl2.primary_measurement is None


@pytest.mark.requirement("REQ-PLOT-319")
def test_set_primary_measurement_reorders_axis_push(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader(), _make_pool_loader()])
    ctrl2.replace_measurements(["a.mf4", "b.mf4"])
    m1, m2 = ctrl2.measurements

    ctrl2.set_primary_measurement(m2)

    assert ctrl2.primary_measurement is m2
    deps["plot"].refresh_measurement_axes.assert_called_with([m2, m1], False)


@pytest.mark.requirement("REQ-PLOT-317")
def test_set_primary_measurement_ignores_unknown_measurement(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader()])
    ctrl2.replace_measurements(["a.mf4"])
    (m1,) = ctrl2.measurements
    foreign = LoadedMeasurement(loader=_make_pool_loader(), info=_make_measurement_info(), label="X")

    ctrl2.set_primary_measurement(foreign)

    assert ctrl2.primary_measurement is m1


@pytest.mark.requirement("REQ-PLOT-321")
def test_close_measurement_reassigns_primary_to_first_loaded_remainder(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(
        deps, [_make_pool_loader(), _make_pool_loader(), _make_pool_loader()],
    )
    ctrl2.replace_measurements(["a.mf4"])
    ctrl2.add_measurements(["b.mf4", "c.mf4"])
    m1, m2, m3 = ctrl2.measurements
    assert ctrl2.primary_measurement is m1

    ctrl2.close_measurement(m1)

    assert ctrl2.primary_measurement is m2


@pytest.mark.requirement("REQ-PLOT-321")
def test_close_last_measurement_leaves_no_primary(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader()])
    ctrl2.replace_measurements(["a.mf4"])
    (m1,) = ctrl2.measurements

    ctrl2.close_measurement(m1)

    assert ctrl2.primary_measurement is None


@pytest.mark.requirement("REQ-PLOT-321")
def test_closing_non_primary_measurement_leaves_primary_unchanged(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader(), _make_pool_loader()])
    ctrl2.replace_measurements(["a.mf4"])
    ctrl2.add_measurements(["b.mf4"])
    m1, m2 = ctrl2.measurements

    ctrl2.close_measurement(m2)

    assert ctrl2.primary_measurement is m1


@pytest.mark.requirement("REQ-PLOT-322")
def test_replace_measurements_resets_primary_to_first_of_new_set(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(
        deps, [_make_pool_loader(), _make_pool_loader(), _make_pool_loader()],
    )
    ctrl2.replace_measurements(["a.mf4"])
    ctrl2.add_measurements(["b.mf4"])
    m1, m2 = ctrl2.measurements
    ctrl2.set_primary_measurement(m2)
    assert ctrl2.primary_measurement is m2

    ctrl2.replace_measurements(["c.mf4"])

    (m3,) = ctrl2.measurements
    assert ctrl2.primary_measurement is m3


@pytest.mark.requirement("REQ-PLOT-322")
def test_add_measurements_does_not_change_existing_primary(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader(), _make_pool_loader()])
    ctrl2.replace_measurements(["a.mf4"])
    (m1,) = ctrl2.measurements

    ctrl2.add_measurements(["b.mf4"])

    assert ctrl2.primary_measurement is m1


@pytest.mark.requirement("REQ-PLOT-317")
def test_add_measurements_establishes_primary_when_pool_was_empty(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader()])
    assert ctrl2.primary_measurement is None

    ctrl2.add_measurements(["a.mf4"])

    (m1,) = ctrl2.measurements
    assert ctrl2.primary_measurement is m1


@pytest.mark.requirement("REQ-FILE-027")
def test_rename_measurement_succeeds(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader()])
    ctrl2.replace_measurements(["a.mf4"])
    (m1,) = ctrl2.measurements

    assert ctrl2.rename_measurement(m1, "Engine Run") is True
    assert m1.label == "Engine Run"


@pytest.mark.requirement("REQ-FILE-027")
def test_rename_measurement_rejects_duplicate(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader(), _make_pool_loader()])
    ctrl2.replace_measurements(["a.mf4"])
    ctrl2.add_measurements(["b.mf4"])
    m1, m2 = ctrl2.measurements

    assert ctrl2.rename_measurement(m2, "M1") is False
    assert m2.label == "M2"


@pytest.mark.requirement("REQ-FILE-027")
def test_rename_measurement_allows_renaming_to_its_own_current_name(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader()])
    ctrl2.replace_measurements(["a.mf4"])
    (m1,) = ctrl2.measurements

    assert ctrl2.rename_measurement(m1, "M1") is True
    assert m1.label == "M1"


# ---------------------------------------------------------------------------
# Measurement Synchronization (#102)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-310")
def test_toggle_measurements_synchronized_flips_state(ctrl: AppController) -> None:
    assert ctrl.is_measurements_synchronized is False
    ctrl.toggle_measurements_synchronized()
    assert ctrl.is_measurements_synchronized is True
    ctrl.toggle_measurements_synchronized()
    assert ctrl.is_measurements_synchronized is False


@pytest.mark.requirement("REQ-PLOT-313")
def test_toggle_measurements_synchronized_reaches_every_tab(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader(), _make_pool_loader()])
    plot2, table2 = MagicMock(), MagicMock()
    ctrl2.create_tab(plot2, table2)
    ctrl2.replace_measurements(["a.mf4", "b.mf4"])
    deps["plot"].refresh_measurement_axes.reset_mock()
    plot2.refresh_measurement_axes.reset_mock()

    ctrl2.toggle_measurements_synchronized()

    deps["plot"].refresh_measurement_axes.assert_called_with(ctrl2.measurements, True)
    plot2.refresh_measurement_axes.assert_called_with(ctrl2.measurements, True)


@pytest.mark.requirement("REQ-PLOT-310")
def test_replace_measurements_resets_synchronized_state(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader(), _make_pool_loader()])
    ctrl2.replace_measurements(["a.mf4"])
    ctrl2.toggle_measurements_synchronized()
    assert ctrl2.is_measurements_synchronized is True

    ctrl2.replace_measurements(["b.mf4"])

    assert ctrl2.is_measurements_synchronized is False


@pytest.mark.requirement("REQ-PLOT-315")
def test_add_measurements_does_not_reset_synchronized_state(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader(), _make_pool_loader()])
    ctrl2.replace_measurements(["a.mf4"])
    ctrl2.toggle_measurements_synchronized()
    assert ctrl2.is_measurements_synchronized is True

    ctrl2.add_measurements(["b.mf4"])

    assert ctrl2.is_measurements_synchronized is True


@pytest.mark.requirement("REQ-FILE-031")
def test_on_measurement_offset_changed_refreshes_only_that_measurements_signals(
    deps: dict,
) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader(), _make_pool_loader()])
    ctrl2.replace_measurements(["a.mf4"])
    ctrl2.add_measurements(["b.mf4"])
    m1, m2 = ctrl2.measurements
    ctrl2.add_signal(0, 1, measurement=m1)
    ctrl2.add_signal(0, 1, measurement=m2)
    sig1, sig2 = ctrl2.active_signals
    deps["plot"].refresh_signal_data.reset_mock()

    ctrl2.on_measurement_offset_changed(m1)

    deps["plot"].refresh_signal_data.assert_called_once_with(sig1)


@pytest.mark.requirement("REQ-FILE-031")
def test_on_measurement_offset_changed_reaches_every_tab(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader()])
    ctrl2.replace_measurements(["a.mf4"])
    (m1,) = ctrl2.measurements

    plot2, table2 = MagicMock(), MagicMock()
    ctrl2.create_tab(plot2, table2)
    ctrl2.add_signal(0, 1, measurement=m1)
    (sig_in_tab2,) = ctrl2.active_signals

    ctrl2.on_measurement_offset_changed(m1)

    plot2.refresh_signal_data.assert_called_once_with(sig_in_tab2)


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


@pytest.mark.requirement("REQ-FILE-031")
def test_restore_signals_4tuple_routes_to_named_measurement(deps: dict) -> None:
    loader_a = _make_pool_loader()
    loader_b = _make_pool_loader()
    loader_a.load_signal.return_value = (_make_signal_data(), _make_metadata("a", gi=0, ci=1))
    loader_b.load_signal.return_value = (_make_signal_data(), _make_metadata("b", gi=0, ci=1))
    ctrl2 = _make_ctrl_with_loaders(deps, [loader_a, loader_b])
    ctrl2.replace_measurements(["a.mf4"])
    ctrl2.add_measurements(["b.mf4"])
    m1, m2 = ctrl2.measurements

    snap_a, snap_b = _make_snapshot("a"), _make_snapshot("b")
    ctrl2.restore_signals([(snap_a, 0, 1, m1), (snap_b, 0, 1, m2)])

    assert [s.measurement for s in ctrl2.active_signals] == [m1, m2]


@pytest.mark.requirement("REQ-FILE-090")
def test_restore_signals_routes_into_named_stripe(ctrl: AppController, deps: dict) -> None:
    """A snapshot's stripe_name (#106) routes the re-added signal into the
    matching stripe by name, rather than whatever stripe is currently
    active — the same routing `add_signal(stripe=...)` already supports
    for drag-and-drop."""
    meta = _make_metadata("rpm", gi=0, ci=5)
    deps["loader"].load_signal.return_value = (_make_signal_data(), meta)
    stripe_a, stripe_b = MagicMock(), MagicMock()
    stripe_a.name, stripe_b.name = "Vibration", "Temp"
    deps["plot"].get_stripes.return_value = [stripe_a, stripe_b]
    snap = _make_snapshot("rpm", stripe_name="Temp")

    ctrl.restore_signals([(snap, 0, 5)])

    deps["plot"].add_signal.assert_called_once()
    _, kwargs = deps["plot"].add_signal.call_args
    assert kwargs["stripe"] is stripe_b


@pytest.mark.requirement("REQ-FILE-090")
def test_restore_signals_no_stripe_name_defaults_to_none(ctrl: AppController, deps: dict) -> None:
    meta = _make_metadata("rpm", gi=0, ci=5)
    deps["loader"].load_signal.return_value = (_make_signal_data(), meta)
    stripe_a = MagicMock()
    stripe_a.name = "Vibration"
    deps["plot"].get_stripes.return_value = [stripe_a]
    snap = _make_snapshot("rpm")  # stripe_name defaults to ""

    ctrl.restore_signals([(snap, 0, 5)])

    _, kwargs = deps["plot"].add_signal.call_args
    assert kwargs["stripe"] is None


@pytest.mark.requirement("REQ-FILE-090")
def test_restore_signals_unmatched_stripe_name_defaults_to_none(ctrl: AppController, deps: dict) -> None:
    meta = _make_metadata("rpm", gi=0, ci=5)
    deps["loader"].load_signal.return_value = (_make_signal_data(), meta)
    stripe_a = MagicMock()
    stripe_a.name = "Vibration"
    deps["plot"].get_stripes.return_value = [stripe_a]
    snap = _make_snapshot("rpm", stripe_name="Nonexistent")

    ctrl.restore_signals([(snap, 0, 5)])

    _, kwargs = deps["plot"].add_signal.call_args
    assert kwargs["stripe"] is None


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
    assert config.tabs[0].x_range == (0.0, 5.0)


@pytest.mark.requirement("REQ-FILE-092")
def test_capture_config_measurement_path(ctrl: AppController, deps: dict, tmp_path) -> None:
    meas = tmp_path / "meas.mf4"
    deps["plot"].get_zoom_state.return_value = _make_zoom_state()
    deps["plot"].get_axis_grouping.return_value = ([], [])
    deps["loader"].is_open = True
    deps["loader"]._path = meas
    config = ctrl.capture_config(tmp_path / "session.mvc")
    assert config.measurements[0].path == str(meas)


@pytest.mark.requirement("REQ-FILE-092")
def test_capture_config_captures_every_loaded_measurement(
    deps: dict, tmp_path
) -> None:
    """capture_config() (#106 M2) captures the full measurement pool, not
    just the first one."""
    loader_a, loader_b = _make_pool_loader(), _make_pool_loader()
    meas_a, meas_b = tmp_path / "a.mf4", tmp_path / "b.mf4"
    loader_a._path = meas_a
    loader_b._path = meas_b
    ctrl2 = _make_ctrl_with_loaders(deps, [loader_a, loader_b])
    ctrl2.replace_measurements([str(meas_a)])
    ctrl2.add_measurements([str(meas_b)])
    deps["plot"].get_zoom_state.return_value = _make_zoom_state()
    deps["plot"].get_axis_grouping.return_value = ([], [])

    config = ctrl2.capture_config(tmp_path / "session.mvc")

    assert [m.path for m in config.measurements] == [str(meas_a), str(meas_b)]
    assert [m.label for m in config.measurements] == ["M1", "M2"]


@pytest.mark.requirement("REQ-FILE-092")
def test_capture_config_primary_measurement_index(deps: dict, tmp_path) -> None:
    loader_a, loader_b = _make_pool_loader(), _make_pool_loader()
    ctrl2 = _make_ctrl_with_loaders(deps, [loader_a, loader_b])
    ctrl2.replace_measurements(["a.mf4"])
    ctrl2.add_measurements(["b.mf4"])
    m1, m2 = ctrl2.measurements
    ctrl2.set_primary_measurement(m2)
    deps["plot"].get_zoom_state.return_value = _make_zoom_state()
    deps["plot"].get_axis_grouping.return_value = ([], [])

    config = ctrl2.capture_config(tmp_path / "session.mvc")

    assert config.primary_measurement_index == 1


@pytest.mark.requirement("REQ-FILE-092")
def test_capture_config_measurements_synchronized_flag(deps: dict, tmp_path) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader(), _make_pool_loader()])
    ctrl2.replace_measurements(["a.mf4"])
    ctrl2.add_measurements(["b.mf4"])
    ctrl2.toggle_measurements_synchronized()
    deps["plot"].get_zoom_state.return_value = _make_zoom_state()
    deps["plot"].get_axis_grouping.return_value = ([], [])

    config = ctrl2.capture_config(tmp_path / "session.mvc")

    assert config.measurements_synchronized is True


def test_capture_config_no_file_open(ctrl: AppController, deps: dict, tmp_path) -> None:
    deps["plot"].get_zoom_state.return_value = _make_zoom_state()
    deps["plot"].get_axis_grouping.return_value = ([], [])
    deps["loader"].is_open = False
    config = ctrl.capture_config(tmp_path / "session.mvc")
    assert config.measurements == ()


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
    assert config.tabs[0].cursor_mode == "TWO"
    assert config.tabs[0].cursor_positions == (1.0, 4.0)


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


@pytest.mark.requirement("REQ-FILE-090")
def test_capture_config_captures_stripe_layout(ctrl: AppController, deps: dict, tmp_path) -> None:
    stripe1, stripe2 = MagicMock(), MagicMock()
    stripe1.name = "Vibration"
    stripe2.name = "Temp"
    deps["plot"].get_stripes.return_value = [stripe1, stripe2]
    deps["plot"].get_stripe_sizes.return_value = [300, 150]
    deps["plot"].get_active_stripe.return_value = stripe2
    deps["plot"].get_zoom_state.return_value = _make_zoom_state()
    deps["plot"].get_axis_grouping.return_value = ([], [])

    config = ctrl.capture_config(tmp_path / "session.mvc")

    tab = config.tabs[0]
    assert [s.name for s in tab.stripes] == ["Vibration", "Temp"]
    assert [s.size for s in tab.stripes] == [300, 150]
    assert tab.active_stripe_index == 1


@pytest.mark.requirement("REQ-FILE-090")
def test_capture_config_signal_stripe_index(ctrl: AppController, deps: dict, tmp_path) -> None:
    stripe1, stripe2 = MagicMock(), MagicMock()
    stripe1.name = "Stripe 1"
    stripe2.name = "Stripe 2"
    deps["plot"].get_stripes.return_value = [stripe1, stripe2]
    deps["plot"].get_stripe_sizes.return_value = [1, 1]
    deps["plot"].get_active_stripe.return_value = stripe1
    deps["plot"].get_zoom_state.return_value = _make_zoom_state()
    deps["plot"].get_axis_grouping.return_value = ([], [])

    ctrl.add_signal(0, 1)
    deps["plot"].get_stripe_for_signal.return_value = stripe2

    config = ctrl.capture_config(tmp_path / "session.mvc")

    assert config.tabs[0].signals[0].stripe_index == 1


@pytest.mark.requirement("REQ-FILE-090")
def test_capture_config_signal_measurement_index(deps: dict, tmp_path) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader(), _make_pool_loader()])
    ctrl2.replace_measurements(["a.mf4"])
    ctrl2.add_measurements(["b.mf4"])
    m1, m2 = ctrl2.measurements
    ctrl2.add_signal(0, 1, measurement=m2)
    deps["plot"].get_zoom_state.return_value = _make_zoom_state()
    deps["plot"].get_axis_grouping.return_value = ([], [])

    config = ctrl2.capture_config(tmp_path / "session.mvc")

    assert config.tabs[0].signals[0].measurement_index == 1


def _make_bare_tab_plot() -> MagicMock:
    plot = MagicMock()
    plot.get_stripes.return_value = []
    plot.get_stripe_sizes.return_value = []
    plot.get_active_stripe.return_value = None
    plot.get_stripe_for_signal.return_value = None
    plot.get_zoom_state.return_value = _make_zoom_state()
    plot.get_axis_grouping.return_value = ([], [])
    return plot


@pytest.mark.requirement("REQ-FILE-091")
def test_capture_config_multiple_tabs_with_names(ctrl: AppController, deps: dict, tmp_path) -> None:
    plot2, table2 = _make_bare_tab_plot(), MagicMock()
    ctrl.create_tab(plot2, table2)
    deps["plot"].get_zoom_state.return_value = _make_zoom_state()
    deps["plot"].get_axis_grouping.return_value = ([], [])

    config = ctrl.capture_config(tmp_path / "session.mvc", tab_names=["Engine", "Chassis"])

    assert [t.name for t in config.tabs] == ["Engine", "Chassis"]


@pytest.mark.requirement("REQ-FILE-091")
def test_capture_config_default_tab_names_when_omitted(
    ctrl: AppController, deps: dict, tmp_path
) -> None:
    deps["plot"].get_zoom_state.return_value = _make_zoom_state()
    deps["plot"].get_axis_grouping.return_value = ([], [])
    config = ctrl.capture_config(tmp_path / "session.mvc")
    assert config.tabs[0].name == "Tab 1"


@pytest.mark.requirement("REQ-FILE-091")
def test_capture_config_active_tab_index(ctrl: AppController, deps: dict, tmp_path) -> None:
    plot2, table2 = _make_bare_tab_plot(), MagicMock()
    ctrl.create_tab(plot2, table2)  # becomes the active tab
    deps["plot"].get_zoom_state.return_value = _make_zoom_state()
    deps["plot"].get_axis_grouping.return_value = ([], [])

    config = ctrl.capture_config(tmp_path / "session.mvc")

    assert config.active_tab_index == 1


@pytest.mark.requirement("REQ-FILE-090")
def test_snapshot_active_signals_captures_stripe_name(ctrl: AppController, deps: dict) -> None:
    stripe = MagicMock()
    stripe.name = "Vibration"
    deps["plot"].get_stripe_for_signal.return_value = stripe
    ctrl.add_signal(0, 1)
    (snap,) = ctrl.snapshot_active_signals()
    assert snap.stripe_name == "Vibration"


@pytest.mark.requirement("REQ-FILE-090")
def test_snapshot_active_signals_stripe_name_empty_when_no_stripe(
    ctrl: AppController, deps: dict
) -> None:
    ctrl.add_signal(0, 1)
    (snap,) = ctrl.snapshot_active_signals()
    assert snap.stripe_name == ""


# ---------------------------------------------------------------------------
# restore_measurements (#106 Phase 1)
# ---------------------------------------------------------------------------

def _make_measurement_config(path="a.mf4", label="M1", offset_s=0.0):
    from mdf_viewer.model.viewer_config import MeasurementConfig
    return MeasurementConfig(path=path, label=label, offset_s=offset_s)


@pytest.mark.requirement("REQ-FILE-092")
def test_restore_measurements_all_succeed(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader(), _make_pool_loader()])
    configs = [
        _make_measurement_config("a.mf4", "Engine", 0.0),
        _make_measurement_config("b.mf4", "Chassis", 2.5),
    ]

    results = ctrl2.restore_measurements(configs, primary_index=0, synchronized=True)

    assert all(r is not None for r in results)
    assert [m.label for m in ctrl2.measurements] == ["Engine", "Chassis"]
    assert ctrl2.measurements[1].offset_s == 2.5
    assert ctrl2.primary_measurement is ctrl2.measurements[0]
    assert ctrl2.is_measurements_synchronized is True


@pytest.mark.requirement("REQ-FILE-098")
def test_restore_measurements_partial_failure_preserves_index_alignment(deps: dict) -> None:
    good_a = _make_pool_loader()
    bad = MagicMock()
    bad.open.side_effect = MdfLoadError("missing")
    good_c = _make_pool_loader()
    ctrl2 = _make_ctrl_with_loaders(deps, [good_a, bad, good_c])
    configs = [
        _make_measurement_config("a.mf4", "M1"),
        _make_measurement_config("missing.mf4", "M2"),
        _make_measurement_config("c.mf4", "M3"),
    ]

    results = ctrl2.restore_measurements(configs, primary_index=0, synchronized=False)

    assert results[0] is not None
    assert results[1] is None
    assert results[2] is not None
    assert [m.label for m in ctrl2.measurements] == ["M1", "M3"]


@pytest.mark.requirement("REQ-FILE-098")
def test_restore_measurements_primary_falls_back_when_primary_slot_failed(deps: dict) -> None:
    bad = MagicMock()
    bad.open.side_effect = MdfLoadError("missing")
    good = _make_pool_loader()
    ctrl2 = _make_ctrl_with_loaders(deps, [bad, good])
    configs = [
        _make_measurement_config("missing.mf4", "M1"),
        _make_measurement_config("b.mf4", "M2"),
    ]

    ctrl2.restore_measurements(configs, primary_index=0, synchronized=False)

    assert ctrl2.primary_measurement is ctrl2.measurements[0]
    assert ctrl2.primary_measurement.label == "M2"


@pytest.mark.requirement("REQ-FILE-098")
def test_restore_measurements_all_fail_leaves_no_primary(deps: dict) -> None:
    bad_a, bad_b = MagicMock(), MagicMock()
    bad_a.open.side_effect = MdfLoadError("missing")
    bad_b.open.side_effect = MdfLoadError("missing")
    ctrl2 = _make_ctrl_with_loaders(deps, [bad_a, bad_b])
    configs = [_make_measurement_config("a.mf4"), _make_measurement_config("b.mf4")]

    results = ctrl2.restore_measurements(configs, primary_index=0, synchronized=False)

    assert results == [None, None]
    assert ctrl2.measurements == []
    assert ctrl2.primary_measurement is None


@pytest.mark.requirement("REQ-FILE-027")
def test_restore_measurements_resets_load_counter_and_add_continues_after(deps: dict) -> None:
    """A later add_measurements() after a session restore must never
    reissue a default name already used by the restored session, the
    same monotonic-counter guarantee as close-then-add (#103)."""
    ctrl2 = _make_ctrl_with_loaders(
        deps, [_make_pool_loader(), _make_pool_loader(), _make_pool_loader()],
    )
    configs = [_make_measurement_config("a.mf4", "M1"), _make_measurement_config("b.mf4", "M2")]
    ctrl2.restore_measurements(configs, primary_index=0, synchronized=False)

    result = ctrl2.add_measurements(["c.mf4"])

    assert result.succeeded[0].label == "M3"


@pytest.mark.requirement("REQ-FILE-092")
def test_restore_measurements_refreshes_browser_and_info_box(deps: dict) -> None:
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader()])
    configs = [_make_measurement_config("a.mf4", "M1")]

    ctrl2.restore_measurements(configs, primary_index=0, synchronized=False)

    deps["browser"].populate_all.assert_called()
    deps["info_box"].set_measurements.assert_called()


# ---------------------------------------------------------------------------
# restore_config
# ---------------------------------------------------------------------------

def _make_viewer_config(**kwargs):
    """Build a single-tab ViewerConfig; kwargs may name either a TabConfig
    field (signals, x_range, y_ranges, merged_groups, synced_groups,
    cursor_mode, cursor_positions, selected_signal) or a top-level
    ViewerConfig field — routed to the right dataclass automatically.

    For convenience, merged_groups/synced_groups/selected_signal/y_ranges
    may still be given as bare signal-name strings / a name-keyed dict
    (as before SignalRef existed) — auto-wrapped into
    SignalRef(name=..., measurement_index=0), the single-measurement
    default. Pass real SignalRef instances directly to test
    measurement-aware disambiguation (#106 M6, REQ-FILE-093)."""
    from mdf_viewer.config_manager import CONFIG_FORMAT_VERSION
    from mdf_viewer.model.viewer_config import (
        MeasurementConfig, SignalRef, StripeConfig, TabConfig, ViewerConfig,
    )

    def _ref(x):
        return x if isinstance(x, SignalRef) else SignalRef(name=x, measurement_index=0)

    tab_field_names = {
        "signals", "x_range", "y_ranges", "merged_groups", "synced_groups",
        "cursor_mode", "cursor_positions", "selected_signal",
        "page_splitter_sizes", "ast_column_widths",
    }
    tab_defaults = dict(
        name="Tab 1",
        stripes=(StripeConfig(name="Stripe 1", size=1),),
        active_stripe_index=0,
        signals=(),
        x_range=(0.0, 10.0),
        y_ranges=(),
        merged_groups=(),
        synced_groups=(),
        cursor_mode="HIDDEN",
        cursor_positions=(0.0, 0.0),
        selected_signal=None,
    )
    top_defaults = dict(
        format_version=CONFIG_FORMAT_VERSION,
        measurements=(MeasurementConfig(path="/x.mf4", label="M1", offset_s=0.0),),
        primary_measurement_index=0,
        measurements_synchronized=False,
        active_tab_index=0,
        display_name_separator=".",
        display_name_direction="right",
        display_name_segments=1,
    )
    for key, value in kwargs.items():
        if key in ("merged_groups", "synced_groups"):
            value = tuple(tuple(_ref(n) for n in g) for g in value)
        elif key == "selected_signal" and value is not None:
            value = _ref(value)
        elif key == "y_ranges" and isinstance(value, dict):
            value = tuple((_ref(n), rng) for n, rng in value.items())
        if key in tab_field_names:
            tab_defaults[key] = value
        else:
            top_defaults[key] = value
    return ViewerConfig(tabs=(TabConfig(**tab_defaults),), **top_defaults)


@pytest.mark.requirement("REQ-PLOT-036")
def test_restore_config_calls_restore_axis_grouping(ctrl: AppController, deps: dict) -> None:
    config = _make_viewer_config(
        merged_groups=(("a", "b"),),
    )
    ctrl.restore_config(config, {})
    deps["plot"].restore_axis_grouping.assert_called_once()


@pytest.mark.requirement("REQ-FILE-061")
def test_restore_config_calls_set_zoom_state(ctrl: AppController, deps: dict) -> None:
    config = _make_viewer_config()
    ctrl.restore_config(config, {})
    deps["plot"].set_zoom_state.assert_called_once()


@pytest.mark.requirement("REQ-FILE-061")
def test_restore_config_calls_cursor_restore(ctrl: AppController, deps: dict) -> None:
    from unittest.mock import MagicMock
    cursor = MagicMock()
    ctrl.set_cursor_controller(cursor)
    config = _make_viewer_config(cursor_mode="ONE", cursor_positions=(2.5, 0.0))
    ctrl.restore_config(config, {})
    cursor.restore.assert_called_once_with({"mode": "ONE", "positions": [2.5, 0.0]})


@pytest.mark.requirement("REQ-FILE-061")
def test_restore_config_sets_selection(ctrl: AppController, deps: dict) -> None:
    meta = _make_metadata("RPM", gi=0, ci=1)
    deps["loader"].load_signal.return_value = (_make_signal_data(), meta)
    snap = _make_snapshot("RPM")
    config = _make_viewer_config(selected_signal="RPM")
    ctrl.restore_config(config, {0: [(snap, 0, 1)]})
    assert ctrl.selected_signal is not None
    assert ctrl.selected_signal.metadata.name == "RPM"


def test_restore_config_no_settings_does_not_crash(ctrl: AppController, deps: dict) -> None:
    """No Settings wired in (settings=None) must not crash (#89)."""
    config = _make_viewer_config()
    ctrl.restore_config(config, {})  # must not raise


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
    ctrl_with_settings.restore_config(config, {})
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
    ctrl_with_settings.restore_config(config, {})
    deps["table"].set_name_formatter.assert_called_once()


# ---------------------------------------------------------------------------
# restore_config — multi-tab (#106 M6)
# ---------------------------------------------------------------------------

def _wrap_tab_field(key, value):
    """Apply the same bare-name → SignalRef convenience wrapping
    _make_viewer_config() does, for helpers that build a TabConfig
    override directly via dataclasses.replace() instead."""
    from mdf_viewer.model.viewer_config import SignalRef

    def _ref(x):
        return x if isinstance(x, SignalRef) else SignalRef(name=x, measurement_index=0)

    if key in ("merged_groups", "synced_groups"):
        return tuple(tuple(_ref(n) for n in g) for g in value)
    if key == "selected_signal" and value is not None:
        return _ref(value)
    if key == "y_ranges" and isinstance(value, dict):
        return tuple((_ref(n), rng) for n, rng in value.items())
    return value


def _two_tab_viewer_config(**tab2_overrides):
    """Build a 2-tab ViewerConfig from _make_viewer_config()'s single tab,
    with the second tab's fields overridable independently — used to
    confirm restore_config() applies each tab's own saved state rather
    than reusing tab 1's for every tab."""
    import dataclasses
    config = _make_viewer_config()
    tab1 = config.tabs[0]
    tab2_overrides = {k: _wrap_tab_field(k, v) for k, v in tab2_overrides.items()}
    tab2 = dataclasses.replace(tab1, name="Tab 2", **tab2_overrides)
    return dataclasses.replace(config, tabs=(tab1, tab2))


@pytest.mark.requirement("REQ-FILE-094")
def test_restore_config_restores_every_tabs_axis_grouping(ctrl: AppController, deps: dict) -> None:
    plot2, table2 = MagicMock(), MagicMock()
    plot2.get_stripes.return_value = []
    ctrl.create_tab(plot2, table2)

    config = _two_tab_viewer_config(merged_groups=(("c", "d"),))
    config = _replace_tab(config, 0, merged_groups=(("a", "b"),))

    ctrl.restore_config(config, {})

    deps["plot"].restore_axis_grouping.assert_called_once()
    plot2.restore_axis_grouping.assert_called_once()
    assert deps["plot"].restore_axis_grouping.call_args[0][0] == [[("a", None), ("b", None)]]
    assert plot2.restore_axis_grouping.call_args[0][0] == [[("c", None), ("d", None)]]


@pytest.mark.requirement("REQ-FILE-094")
def test_restore_config_restores_every_tabs_zoom(ctrl: AppController, deps: dict) -> None:
    plot2, table2 = MagicMock(), MagicMock()
    plot2.get_stripes.return_value = []
    ctrl.create_tab(plot2, table2)

    config = _two_tab_viewer_config(x_range=(5.0, 15.0))
    config = _replace_tab(config, 0, x_range=(0.0, 10.0))

    ctrl.restore_config(config, {})

    deps["plot"].set_zoom_state.assert_called_once()
    plot2.set_zoom_state.assert_called_once()
    assert deps["plot"].set_zoom_state.call_args[0][0].x_range == (0.0, 10.0)
    assert plot2.set_zoom_state.call_args[0][0].x_range == (5.0, 15.0)


@pytest.mark.requirement("REQ-FILE-091")
def test_restore_config_restores_active_stripe_per_tab(ctrl: AppController, deps: dict) -> None:
    stripe0a, stripe0b = MagicMock(), MagicMock()
    deps["plot"].get_stripes.return_value = [stripe0a, stripe0b]
    plot2, table2 = MagicMock(), MagicMock()
    stripe1a, stripe1b = MagicMock(), MagicMock()
    plot2.get_stripes.return_value = [stripe1a, stripe1b]
    ctrl.create_tab(plot2, table2)

    config = _two_tab_viewer_config(active_stripe_index=0)
    config = _replace_tab(config, 0, active_stripe_index=1)

    ctrl.restore_config(config, {})

    deps["plot"].set_active_stripe.assert_called_once_with(stripe0b)
    plot2.set_active_stripe.assert_called_once_with(stripe1a)


@pytest.mark.requirement("REQ-FILE-091")
def test_restore_config_restores_active_tab_index(ctrl: AppController, deps: dict) -> None:
    import dataclasses
    plot2, table2 = MagicMock(), MagicMock()
    plot2.get_stripes.return_value = []
    ctrl.create_tab(plot2, table2)  # tab 1 now active

    config = _two_tab_viewer_config()
    config = dataclasses.replace(config, active_tab_index=0)

    ctrl.restore_config(config, {})

    assert ctrl.current_workspace.plot is deps["plot"]


def _replace_tab(config, index: int, **overrides):
    import dataclasses
    overrides = {k: _wrap_tab_field(k, v) for k, v in overrides.items()}
    tabs = list(config.tabs)
    tabs[index] = dataclasses.replace(tabs[index], **overrides)
    return dataclasses.replace(config, tabs=tuple(tabs))


@pytest.mark.requirement("REQ-FILE-094")
def test_restore_config_tab_index_beyond_workspaces_is_skipped(
    ctrl: AppController, deps: dict
) -> None:
    """A saved session with more tabs than currently exist (e.g. restore_config
    called before _build_tab_skeletons finished, or a defensive bounds-check)
    must not crash — extra tab configs are silently skipped."""
    config = _two_tab_viewer_config()  # 2 tabs saved, only 1 workspace exists
    ctrl.restore_config(config, {})  # must not raise
    deps["plot"].restore_axis_grouping.assert_called_once()


@pytest.mark.requirement("REQ-FILE-093")
def test_restore_config_with_real_measurements_does_not_hash_measurement(deps: dict) -> None:
    """LoadedMeasurement is a plain, unhashable @dataclass (mutable,
    field-equality __eq__, no unsafe_hash) — restore_config()'s
    measurement-aware disambiguation must never put a LoadedMeasurement
    directly into a dict/set key (id() instead), or this raises
    TypeError with any *real* multi-measurement pool. A bare MagicMock
    stand-in wouldn't catch this (MagicMock is hashable by default), so
    this test deliberately uses the real loader-pool machinery."""
    from mdf_viewer.model.viewer_config import SignalRef

    loader_a = _make_pool_loader()
    loader_b = _make_pool_loader()
    loader_a.load_signal.return_value = (_make_signal_data(), _make_metadata("RPM", gi=0, ci=1))
    loader_b.load_signal.return_value = (_make_signal_data(), _make_metadata("RPM", gi=0, ci=1))
    ctrl2 = _make_ctrl_with_loaders(deps, [loader_a, loader_b])
    ctrl2.replace_measurements(["a.mf4"])
    ctrl2.add_measurements(["b.mf4"])
    m1, m2 = ctrl2.measurements

    snap_a, snap_b = _make_snapshot("RPM"), _make_snapshot("RPM")
    resolved = {0: [(snap_a, 0, 1, m1), (snap_b, 0, 1, m2)]}

    config = _make_viewer_config(
        merged_groups=(
            (SignalRef(name="RPM", measurement_index=0), SignalRef(name="RPM", measurement_index=1)),
        ),
        y_ranges=((SignalRef(name="RPM", measurement_index=0), (1.0, 2.0)),),
        selected_signal=SignalRef(name="RPM", measurement_index=1),
    )

    ctrl2.restore_config(config, resolved, [m1, m2])  # must not raise TypeError


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
    # add_signal() itself already calls get_stripe_for_signal (to resolve
    # which segment the new row belongs to) — reset before exercising the
    # method under test so the assertion below is only about this call.
    deps["plot"].get_stripe_for_signal.reset_mock()
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


@pytest.mark.requirement("REQ-PLOT-202")
def test_move_signals_to_stripe_updates_table_too(ctrl: AppController, deps: dict) -> None:
    # #100 postmortem: moving a signal must also update the AST's own
    # stripe-membership tracking, not just the plot's — otherwise deleting
    # the signal's old (now plot-side-empty) stripe orphans its AST row.
    ctrl.add_signal(0, 1)
    stripe = MagicMock()
    ctrl.move_signals_to_stripe(ctrl.active_signals, stripe)
    deps["table"].move_to_stripe.assert_called_once_with(ctrl.active_signals, stripe)


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


@pytest.mark.requirement("REQ-PLOT-191")
def test_move_signals_to_new_stripe_updates_table_too(ctrl: AppController, deps: dict) -> None:
    new_stripe = MagicMock()
    deps["plot"].create_stripe.return_value = new_stripe
    ctrl.add_signal(0, 1)
    ctrl.move_signals_to_new_stripe(ctrl.active_signals)
    deps["table"].move_to_stripe.assert_called_once_with(ctrl.active_signals, new_stripe)


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


# ---------------------------------------------------------------------------
# create_tab / switch_tab / remove_tab (#99 Main Widget Tabs)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-240")
def test_create_tab_adds_workspace_and_makes_it_active(ctrl: AppController) -> None:
    plot2, table2 = MagicMock(), MagicMock()
    workspace = ctrl.create_tab(plot2, table2)
    assert len(ctrl._workspaces) == 2
    assert ctrl.current_workspace is workspace
    assert ctrl.current_workspace.plot is plot2
    assert ctrl.current_workspace.table is table2


@pytest.mark.requirement("REQ-PLOT-245")
def test_create_tab_pushes_current_measurement_axes_to_new_tab(deps: dict) -> None:
    """A newly created tab must show the same per-measurement axis rows as
    every other open tab immediately, not just after the next pool-mutating
    event (add/replace/close/rename/sync-toggle/primary-change) happens to
    fire (#124)."""
    ctrl2 = _make_ctrl_with_loaders(deps, [_make_pool_loader()])
    ctrl2.replace_measurements(["a.mf4"])

    plot2, table2 = MagicMock(), MagicMock()
    ctrl2.create_tab(plot2, table2)

    plot2.refresh_measurement_axes.assert_called_with(ctrl2.measurements, False)


@pytest.mark.requirement("REQ-PLOT-241")
def test_create_tab_starts_with_no_active_signals(ctrl: AppController) -> None:
    ctrl.add_signal(0, 1)
    assert ctrl.active_signals != []
    ctrl.create_tab(MagicMock(), MagicMock())
    assert ctrl.active_signals == []


@pytest.mark.requirement("REQ-PLOT-231")
def test_tabs_isolate_active_signals(ctrl: AppController, deps: dict) -> None:
    """Adding a signal in tab A must not appear in tab B, and vice versa."""
    _two_distinct_signals(deps)
    ctrl.add_signal(0, 1)
    tab_a_signals = list(ctrl.active_signals)

    ctrl.create_tab(MagicMock(), MagicMock())
    ctrl.add_signal(0, 2)
    tab_b_signals = list(ctrl.active_signals)

    assert tab_a_signals != tab_b_signals
    ctrl.switch_tab(0)
    assert ctrl.active_signals == tab_a_signals
    ctrl.switch_tab(1)
    assert ctrl.active_signals == tab_b_signals


@pytest.mark.requirement("REQ-BROWSER-040")
def test_same_channel_can_be_active_in_two_tabs(ctrl: AppController) -> None:
    """REQ-BROWSER-040's 'already active' check is scoped to the current tab."""
    added_in_tab_a = ctrl.add_signal(0, 1)
    ctrl.create_tab(MagicMock(), MagicMock())
    added_in_tab_b = ctrl.add_signal(0, 1)
    assert added_in_tab_a is True
    assert added_in_tab_b is True


def test_tabs_isolate_selection(ctrl: AppController) -> None:
    ctrl.add_signal(0, 1)
    sig_a = ctrl.active_signals[0]
    ctrl.set_selected_signal(sig_a)

    ctrl.create_tab(MagicMock(), MagicMock())
    assert ctrl.selected_signal is None
    ctrl.add_signal(0, 1)
    sig_b = ctrl.active_signals[0]
    ctrl.set_selected_signal(sig_b)

    ctrl.switch_tab(0)
    assert ctrl.selected_signal is sig_a
    ctrl.switch_tab(1)
    assert ctrl.selected_signal is sig_b


def test_switch_tab_out_of_range_is_noop(ctrl: AppController) -> None:
    original = ctrl.current_workspace
    ctrl.switch_tab(5)
    assert ctrl.current_workspace is original
    ctrl.switch_tab(-1)
    assert ctrl.current_workspace is original


@pytest.mark.requirement("REQ-PLOT-254")
def test_remove_tab_refuses_when_only_one_tab(ctrl: AppController) -> None:
    ctrl.remove_tab(0)
    assert len(ctrl._workspaces) == 1


@pytest.mark.requirement("REQ-PLOT-254")
def test_remove_tab_clears_signals_even_when_only_one_tab(ctrl: AppController, deps: dict) -> None:
    """Closing the last tab keeps its TabWorkspace alive (current_workspace
    must never be empty) rather than dropping it, but "close anyway" must
    still discard its content — a stale, still-populated workspace left
    behind here is what caused the view to reuse a widget that, before this
    fix, still looked "active" even though the tab had supposedly been
    closed (#130, found live-testing #124)."""
    sig = ActiveSignal(data=_make_signal_data(), metadata=_make_metadata(), color=QColor(255, 0, 0))
    ctrl.current_workspace.active.append(sig)

    ctrl.remove_tab(0)

    assert len(ctrl._workspaces) == 1
    assert ctrl.current_workspace.active == []
    deps["plot"].remove_signal.assert_called_once_with(sig)
    deps["table"].clear.assert_called_once()


def test_remove_tab_removes_workspace(ctrl: AppController) -> None:
    workspace_a = ctrl.current_workspace
    ctrl.create_tab(MagicMock(), MagicMock())
    workspace_b = ctrl.current_workspace
    ctrl.remove_tab(1)
    assert list(ctrl._workspaces) == [workspace_a]
    assert ctrl.current_workspace is workspace_a
    assert workspace_b not in ctrl._workspaces


def test_remove_tab_removes_signals_still_active_in_it(ctrl: AppController) -> None:
    """Closing a tab that still has signals in it (the view allows this after
    a confirmation prompt) must run each one through the normal remove_signal
    pipeline, not just drop the TabWorkspace — otherwise every curve/ViewBox/
    axis in that tab's plot leaks silently (found while scanning for the same
    leak class as the stripe/signal-lifecycle bugs in plot_stripe.py, #120)."""
    plot_b, table_b = MagicMock(), MagicMock()
    ctrl.create_tab(plot_b, table_b)
    workspace_b = ctrl.current_workspace
    sig = ActiveSignal(data=_make_signal_data(), metadata=_make_metadata(), color=QColor(255, 0, 0))
    workspace_b.active.append(sig)

    ctrl.remove_tab(1)

    plot_b.remove_signal.assert_called_once_with(sig)
    table_b.clear.assert_called_once()


def test_refresh_display_names_updates_every_tab_table(ctrl: AppController, deps: dict) -> None:
    """Display-name shortening is a global preference (REQ-PLOT-160) — every
    tab's table gets the new formatter, not just the currently active one."""
    table2 = MagicMock()
    ctrl.create_tab(MagicMock(), table2)
    ctrl.switch_tab(0)
    ctrl.refresh_display_names()
    deps["table"].set_name_formatter.assert_called_once()
    table2.set_name_formatter.assert_called_once()


@pytest.mark.requirement("REQ-PLOT-252")
def test_tab_has_signals_false_when_empty(ctrl: AppController) -> None:
    assert ctrl.tab_has_signals(0) is False


@pytest.mark.requirement("REQ-PLOT-252")
def test_tab_has_signals_true_after_add(ctrl: AppController) -> None:
    ctrl.add_signal(0, 1)
    assert ctrl.tab_has_signals(0) is True


def test_tab_has_signals_checks_specific_tab_not_current(ctrl: AppController) -> None:
    ctrl.add_signal(0, 1)
    ctrl.create_tab(MagicMock(), MagicMock())
    assert ctrl.tab_has_signals(0) is True
    assert ctrl.tab_has_signals(1) is False


def test_tab_has_signals_out_of_range_is_false(ctrl: AppController) -> None:
    assert ctrl.tab_has_signals(5) is False
    assert ctrl.tab_has_signals(-1) is False


# ---------------------------------------------------------------------------
# EventBus tab field (#99)
# ---------------------------------------------------------------------------

def test_signal_added_event_carries_originating_tab(ctrl: AppController) -> None:
    workspace_a = ctrl.current_workspace
    seen = []
    ctrl.events.signal_added.connect(seen.append)
    ctrl.add_signal(0, 1)
    assert seen[0].tab is workspace_a


def test_signal_added_event_tab_follows_active_tab(ctrl: AppController, deps: dict) -> None:
    _two_distinct_signals(deps)
    workspace_b = ctrl.create_tab(MagicMock(), MagicMock())
    seen = []
    ctrl.events.signal_added.connect(seen.append)
    ctrl.add_signal(0, 2)
    assert seen[0].tab is workspace_b


def test_file_loaded_event_carries_current_tab(ctrl: AppController) -> None:
    seen = []
    ctrl.events.file_loaded.connect(seen.append)
    ctrl.load_file("test.mf4")
    assert seen[0].tab is ctrl.current_workspace


def test_selection_changed_event_carries_originating_tab(ctrl: AppController) -> None:
    workspace_a = ctrl.current_workspace
    ctrl.add_signal(0, 1)
    seen = []
    ctrl.events.selection_changed.connect(seen.append)
    ctrl.set_selected_signal(ctrl.active_signals[0])
    assert seen[0].tab is workspace_a


def test_cursor_moved_event_stays_tagged_with_originating_tab_after_switch() -> None:
    """Regression for the closure-binding trap (#99): a background tab's
    CursorController firing set_position_changed_callback must still tag
    the event with its OWN tab, not whichever tab is active when it fires."""
    loader = MagicMock()
    controller = AppController(
        loader=loader,
        signal_browser=MagicMock(),
        plot_area=MagicMock(),
        active_signals_table=MagicMock(),
        measurement_info_box=MagicMock(),
        signal_info_box=MagicMock(),
    )
    workspace_a = controller.current_workspace
    cursor_ctrl_a = MagicMock()
    controller.set_cursor_controller(cursor_ctrl_a)
    callback_a = cursor_ctrl_a.set_position_changed_callback.call_args[0][0]

    workspace_b = controller.create_tab(MagicMock(), MagicMock())
    cursor_ctrl_b = MagicMock()
    controller.set_cursor_controller(cursor_ctrl_b)
    callback_b = cursor_ctrl_b.set_position_changed_callback.call_args[0][0]

    # Tab B is now active, but tab A's own callback fires (e.g. a queued
    # signal from before the switch) — it must still tag tab A.
    seen = []
    controller.events.cursor_moved.connect(seen.append)
    callback_a([1.0, 2.0], "TWO")
    assert seen[0].tab is workspace_a

    callback_b([3.0, 4.0], "TWO")
    assert seen[1].tab is workspace_b


# ---------------------------------------------------------------------------
# reorder_tabs (#99 drag-to-reorder resync, REQ-PLOT-243)
# ---------------------------------------------------------------------------

def test_reorder_tabs_resyncs_workspace_order(ctrl: AppController) -> None:
    plot_a = ctrl.current_workspace.plot
    workspace_b = ctrl.create_tab(MagicMock(), MagicMock())
    plot_b = workspace_b.plot

    ctrl.reorder_tabs([plot_b, plot_a])

    assert ctrl._workspaces[0].plot is plot_b
    assert ctrl._workspaces[1].plot is plot_a


def test_reorder_tabs_keeps_active_workspace_pointed_at_same_tab(ctrl: AppController) -> None:
    workspace_a = ctrl.current_workspace
    plot_a = workspace_a.plot
    workspace_b = ctrl.create_tab(MagicMock(), MagicMock())  # tab B now active
    plot_b = workspace_b.plot

    ctrl.reorder_tabs([plot_b, plot_a])

    assert ctrl.current_workspace is workspace_b


def test_reorder_tabs_active_tab_follows_its_new_position(ctrl: AppController) -> None:
    workspace_a = ctrl.current_workspace
    plot_a = workspace_a.plot
    workspace_b = ctrl.create_tab(MagicMock(), MagicMock())
    plot_b = workspace_b.plot
    ctrl.switch_tab(0)  # tab A active again, now at index 0

    ctrl.reorder_tabs([plot_b, plot_a])  # A moves to index 1

    assert ctrl.current_workspace is workspace_a
    assert ctrl._active_tab_index == 1


# ---------------------------------------------------------------------------
# switch_tab restores the shared drawer's per-tab selection (#99 M7, REQ-PLOT-233)
# ---------------------------------------------------------------------------

def test_switch_tab_restores_previously_selected_signal_in_drawer(
    ctrl: AppController, deps: dict
) -> None:
    ctrl.add_signal(0, 1)
    sig_a = ctrl.active_signals[0]
    ctrl.set_selected_signal(sig_a)
    deps["signal_info"].reset_mock()

    ctrl.create_tab(MagicMock(), MagicMock())
    ctrl.switch_tab(0)

    deps["signal_info"].set_metadata.assert_called_once_with(
        sig_a.metadata, display_name=sig_a.metadata.name,
    )


def test_switch_tab_clears_drawer_when_tab_has_no_selection(
    ctrl: AppController, deps: dict
) -> None:
    ctrl.add_signal(0, 1)
    ctrl.set_selected_signal(ctrl.active_signals[0])
    ctrl.create_tab(MagicMock(), MagicMock())  # tab B: nothing selected
    deps["signal_info"].reset_mock()

    ctrl.switch_tab(1)

    deps["signal_info"].clear.assert_called_once()
    deps["signal_info"].set_metadata.assert_not_called()


def test_switch_tab_does_not_change_either_tabs_selection(ctrl: AppController) -> None:
    ctrl.add_signal(0, 1)
    sig_a = ctrl.active_signals[0]
    ctrl.set_selected_signal(sig_a)
    ctrl.create_tab(MagicMock(), MagicMock())

    ctrl.switch_tab(0)
    ctrl.switch_tab(1)

    assert ctrl._workspaces[0].selected is sig_a
    assert ctrl._workspaces[1].selected is None


def test_switch_tab_out_of_range_does_not_touch_drawer(
    ctrl: AppController, deps: dict
) -> None:
    ctrl.add_signal(0, 1)
    ctrl.set_selected_signal(ctrl.active_signals[0])
    deps["signal_info"].reset_mock()

    ctrl.switch_tab(5)

    deps["signal_info"].set_metadata.assert_not_called()
    deps["signal_info"].clear.assert_not_called()
