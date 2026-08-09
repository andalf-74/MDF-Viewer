"""Tests for XAxisSignalPickerDialog (#86)."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pytestqt.qtbot import QtBot

from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.view.xaxis_signal_picker_dialog import XAxisSignalPickerDialog


def _meta(name: str = "speed", gi: int = 0, ci: int = 1) -> SignalMetadata:
    return SignalMetadata(name=name, group_index=gi, channel_index=ci)


def _measurement(label: str = "M1") -> MagicMock:
    return MagicMock(label=label)


@pytest.mark.requirement("REQ-XAXIS-012")
def test_shows_all_candidates(qtbot: QtBot) -> None:
    candidates = [(_measurement(), _meta("speed")), (_measurement(), _meta("distance"))]
    dlg = XAxisSignalPickerDialog(candidates)
    qtbot.addWidget(dlg)
    assert dlg._proxy.rowCount() == 2


def test_first_candidate_is_preselected(qtbot: QtBot) -> None:
    candidates = [(_measurement(), _meta("speed")), (_measurement(), _meta("distance"))]
    dlg = XAxisSignalPickerDialog(candidates)
    qtbot.addWidget(dlg)
    assert dlg._list.currentIndex().row() == 0


def test_selected_returns_none_before_accept(qtbot: QtBot) -> None:
    dlg = XAxisSignalPickerDialog([(_measurement(), _meta())])
    qtbot.addWidget(dlg)
    assert dlg.selected() is None


def test_accept_returns_selected_measurement_and_metadata(qtbot: QtBot) -> None:
    m0, meta0 = _measurement(), _meta("speed")
    m1, meta1 = _measurement(), _meta("distance")
    dlg = XAxisSignalPickerDialog([(m0, meta0), (m1, meta1)])
    qtbot.addWidget(dlg)
    dlg._list.setCurrentIndex(dlg._proxy.index(1, 0))
    dlg._on_accept()
    assert dlg.selected() == (m1, meta1)


def test_double_click_selects_and_accepts(qtbot: QtBot) -> None:
    m0, meta0 = _measurement(), _meta("speed")
    dlg = XAxisSignalPickerDialog([(m0, meta0)])
    qtbot.addWidget(dlg)
    dlg._on_double_click(dlg._proxy.index(0, 0))
    assert dlg.selected() == (m0, meta0)


def test_single_measurement_shows_raw_name_only(qtbot: QtBot) -> None:
    m0 = _measurement("M1")
    dlg = XAxisSignalPickerDialog([(m0, _meta("speed"))])
    qtbot.addWidget(dlg)
    assert dlg._proxy.index(0, 0).data() == "speed"


@pytest.mark.requirement("REQ-XAXIS-012")
def test_multi_measurement_shows_measurement_label(qtbot: QtBot) -> None:
    m0, m1 = _measurement("M1"), _measurement("M2")
    dlg = XAxisSignalPickerDialog([(m0, _meta("speed")), (m1, _meta("distance"))])
    qtbot.addWidget(dlg)
    assert dlg._proxy.index(0, 0).data() == "[M1] speed"
    assert dlg._proxy.index(1, 0).data() == "[M2] distance"


def test_empty_candidates_no_crash(qtbot: QtBot) -> None:
    dlg = XAxisSignalPickerDialog([])
    qtbot.addWidget(dlg)
    assert dlg._proxy.rowCount() == 0
    dlg._on_accept()  # must not raise with no current index
    assert dlg.selected() is None


# ---------------------------------------------------------------------------
# Filtering (borrowed from the Signal Browser's filter mechanism)
# ---------------------------------------------------------------------------

def _candidates() -> list:
    return [
        (_measurement("M1"), _meta("engine_speed")),
        (_measurement("M1"), _meta("vehicle_speed")),
        (_measurement("M1"), _meta("driven_distance")),
    ]


def test_filter_substring_narrows_list(qtbot: QtBot) -> None:
    dlg = XAxisSignalPickerDialog(_candidates())
    qtbot.addWidget(dlg)
    dlg._filter_edit.setText("speed")
    dlg._apply_filter()
    assert dlg._proxy.rowCount() == 2


def test_filter_wildcard_narrows_list(qtbot: QtBot) -> None:
    dlg = XAxisSignalPickerDialog(_candidates())
    qtbot.addWidget(dlg)
    dlg._filter_edit.setText("*distance")
    dlg._apply_filter()
    assert dlg._proxy.rowCount() == 1
    assert dlg._proxy.index(0, 0).data() == "driven_distance"


def test_filter_case_insensitive(qtbot: QtBot) -> None:
    dlg = XAxisSignalPickerDialog(_candidates())
    qtbot.addWidget(dlg)
    dlg._filter_edit.setText("ENGINE")
    dlg._apply_filter()
    assert dlg._proxy.rowCount() == 1


def test_filter_matches_measurement_prefix(qtbot: QtBot) -> None:
    candidates = [(_measurement("M1"), _meta("speed")), (_measurement("M2"), _meta("speed"))]
    dlg = XAxisSignalPickerDialog(candidates)
    qtbot.addWidget(dlg)
    dlg._filter_edit.setText("M2")
    dlg._apply_filter()
    assert dlg._proxy.rowCount() == 1
    assert dlg._proxy.index(0, 0).data() == "[M2] speed"


def test_clearing_filter_restores_full_list(qtbot: QtBot) -> None:
    dlg = XAxisSignalPickerDialog(_candidates())
    qtbot.addWidget(dlg)
    dlg._filter_edit.setText("engine")
    dlg._apply_filter()
    assert dlg._proxy.rowCount() == 1
    dlg._filter_edit.setText("")
    dlg._apply_filter()
    assert dlg._proxy.rowCount() == 3


def test_filter_typing_debounced(qtbot: QtBot) -> None:
    """The filter isn't applied synchronously on every keystroke — it's
    debounced via a timer, matching the Signal Browser's own behavior."""
    dlg = XAxisSignalPickerDialog(_candidates())
    qtbot.addWidget(dlg)
    dlg._filter_edit.setText("engine")
    assert dlg._proxy.rowCount() == 3  # not yet applied
    qtbot.wait(dlg._filter_timer.interval() + 50)
    assert dlg._proxy.rowCount() == 1
