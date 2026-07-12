"""Tests for MeasurementMappingDialog (#105)."""

from __future__ import annotations

import pytest
from pytestqt.qtbot import QtBot

from mdf_viewer.model.loaded_measurement import LoadedMeasurement
from mdf_viewer.model.mdf_loader import MdfLoader
from mdf_viewer.model.measurement import MeasurementInfo
from mdf_viewer.model.viewer_config import MeasurementConfig
from mdf_viewer.view.measurement_mapping_dialog import MeasurementMappingDialog


def _config(label: str, path: str = "") -> MeasurementConfig:
    return MeasurementConfig(path=path, label=label, offset_s=0.0)


def _measurement(label: str) -> LoadedMeasurement:
    return LoadedMeasurement(loader=MdfLoader(), info=MeasurementInfo(file_name="x.mf4"), label=label)


def _make_dialog(qtbot: QtBot, configs: list, live: list) -> MeasurementMappingDialog:
    dlg = MeasurementMappingDialog(configs, live, None)
    qtbot.addWidget(dlg)
    return dlg


@pytest.mark.requirement("REQ-FILE-113")
def test_defaults_to_position_order(qtbot: QtBot) -> None:
    configs = [_config("M1"), _config("M2")]
    live = [_measurement("A"), _measurement("B")]
    dlg = _make_dialog(qtbot, configs, live)
    assert dlg.mapping() == live


@pytest.mark.requirement("REQ-FILE-113")
def test_defaults_to_none_when_no_measurement_at_position(qtbot: QtBot) -> None:
    configs = [_config("M1"), _config("M2"), _config("M3")]
    live = [_measurement("A")]
    dlg = _make_dialog(qtbot, configs, live)
    assert dlg.mapping() == [live[0], None, None]


@pytest.mark.requirement("REQ-FILE-112")
def test_no_config_slots_produces_no_rows(qtbot: QtBot) -> None:
    dlg = _make_dialog(qtbot, [], [_measurement("A")])
    assert dlg.mapping() == []
    assert dlg._combos == []


@pytest.mark.requirement("REQ-FILE-113")
def test_every_row_always_offers_every_live_measurement(qtbot: QtBot) -> None:
    configs = [_config("M1"), _config("M2")]
    a, b = _measurement("A"), _measurement("B")
    dlg = _make_dialog(qtbot, configs, [a, b])
    # Row 0 defaults to A, row 1 defaults to B — but both live measurements
    # must still be selectable from *either* row, unconditionally.
    for combo in dlg._combos:
        assert combo.findData(a) != -1
        assert combo.findData(b) != -1
        assert combo.findData(None) != -1


@pytest.mark.requirement("REQ-FILE-113")
def test_picking_an_already_assigned_measurement_overrides_the_other_row(
    qtbot: QtBot,
) -> None:
    configs = [_config("M1"), _config("M2")]
    a, b = _measurement("A"), _measurement("B")
    dlg = _make_dialog(qtbot, configs, [a, b])
    # Row 0 defaults to A, row 1 defaults to B. Directly pick B for row 0.
    dlg._combos[0].setCurrentIndex(dlg._combos[0].findData(b))
    # The newer selection wins; row 1 is reset to None rather than B
    # disappearing from row 0's own choices.
    assert dlg.mapping() == [b, None]
    # B is still selectable from row 1 afterward, per REQ-FILE-113.
    assert dlg._combos[1].findData(b) != -1


@pytest.mark.requirement("REQ-FILE-113")
def test_stolen_row_can_reclaim_the_measurement_afterward(qtbot: QtBot) -> None:
    configs = [_config("M1"), _config("M2")]
    a, b = _measurement("A"), _measurement("B")
    dlg = _make_dialog(qtbot, configs, [a, b])
    dlg._combos[0].setCurrentIndex(dlg._combos[0].findData(b))
    assert dlg.mapping() == [b, None]

    # Row 1 can pick B right back, which steals it from row 0 in turn.
    dlg._combos[1].setCurrentIndex(dlg._combos[1].findData(b))
    assert dlg.mapping() == [None, b]


def test_mapping_reflects_manual_selection(qtbot: QtBot) -> None:
    configs = [_config("M1")]
    a, b = _measurement("A"), _measurement("B")
    dlg = _make_dialog(qtbot, configs, [a, b])
    dlg._combos[0].setCurrentIndex(dlg._combos[0].findData(b))
    assert dlg.mapping() == [b]


def test_row_label_shows_slot_name_and_recorded_file(qtbot: QtBot) -> None:
    from PyQt6.QtWidgets import QLabel
    configs = [_config("M1", path="C:/data/baseline.mf4")]
    dlg = _make_dialog(qtbot, configs, [])
    label_texts = [w.text() for w in dlg.findChildren(QLabel)]
    assert any('"M1"' in t and "baseline.mf4" in t for t in label_texts)


def test_row_label_handles_missing_recorded_path(qtbot: QtBot) -> None:
    from PyQt6.QtWidgets import QLabel
    configs = [_config("M1", path="")]
    dlg = _make_dialog(qtbot, configs, [])
    label_texts = [w.text() for w in dlg.findChildren(QLabel)]
    assert any("no file recorded" in t for t in label_texts)
