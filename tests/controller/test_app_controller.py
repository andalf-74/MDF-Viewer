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
from mdf_viewer.model.measurement import MeasurementInfo
from mdf_viewer.model.mdf_loader import MdfLoadError
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
