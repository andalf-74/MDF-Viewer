"""Tests for MeasurementInfoBox and SignalInfoBox."""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QLabel
from pytestqt.qtbot import QtBot

from mdf_viewer.model.measurement import MeasurementInfo
from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.view.measurement_info_box import (
    MeasurementInfoBox,
    _format_duration,
)
from mdf_viewer.view.signal_info_box import SignalInfoBox


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _form_texts(box) -> list[str]:
    """Return all QLabel texts inside the form content widget."""
    return [w.text() for w in box._content.findChildren(QLabel)]


def _all_texts(texts: list[str]) -> str:
    return " ".join(texts)


# ---------------------------------------------------------------------------
# MeasurementInfoBox – initial state
# ---------------------------------------------------------------------------

@pytest.fixture()
def mbox(qtbot: QtBot) -> MeasurementInfoBox:
    w = MeasurementInfoBox()
    qtbot.addWidget(w)
    return w


def test_mbox_placeholder_shown_initially(mbox: MeasurementInfoBox) -> None:
    assert mbox._stack.currentIndex() == 0


def test_mbox_form_empty_initially(mbox: MeasurementInfoBox) -> None:
    assert mbox._form.rowCount() == 0


# ---------------------------------------------------------------------------
# MeasurementInfoBox – set_info
# ---------------------------------------------------------------------------

def _full_info(**kwargs) -> MeasurementInfo:
    defaults = dict(
        file_name="test.mf4",
        mdf_version="4.10",
        author="Alice",
        recorded_at="2026-05-31 12:00:00",
        duration_s=10.5,
        comment="Test recording",
    )
    defaults.update(kwargs)
    return MeasurementInfo(**defaults)


def test_mbox_set_info_switches_to_form(mbox: MeasurementInfoBox) -> None:
    mbox.set_info(_full_info())
    assert mbox._stack.currentIndex() == 1


def test_mbox_set_info_shows_file_name(mbox: MeasurementInfoBox) -> None:
    mbox.set_info(_full_info(file_name="recording.mf4"))
    assert "recording.mf4" in _all_texts(_form_texts(mbox))


def test_mbox_set_info_shows_version(mbox: MeasurementInfoBox) -> None:
    mbox.set_info(_full_info(mdf_version="4.10"))
    assert "4.10" in _all_texts(_form_texts(mbox))


def test_mbox_set_info_shows_author(mbox: MeasurementInfoBox) -> None:
    mbox.set_info(_full_info(author="Bob"))
    assert "Bob" in _all_texts(_form_texts(mbox))


def test_mbox_set_info_omits_empty_author(mbox: MeasurementInfoBox) -> None:
    mbox.set_info(_full_info(author=""))
    assert "Author" not in _all_texts(_form_texts(mbox))


def test_mbox_set_info_shows_recorded_at(mbox: MeasurementInfoBox) -> None:
    mbox.set_info(_full_info(recorded_at="2026-01-01 09:00:00"))
    assert "2026-01-01" in _all_texts(_form_texts(mbox))


def test_mbox_set_info_omits_empty_recorded_at(mbox: MeasurementInfoBox) -> None:
    mbox.set_info(_full_info(recorded_at=""))
    assert "Recorded" not in _all_texts(_form_texts(mbox))


def test_mbox_set_info_shows_duration(mbox: MeasurementInfoBox) -> None:
    mbox.set_info(_full_info(duration_s=10.5))
    assert "10.500 s" in _all_texts(_form_texts(mbox))


def test_mbox_set_info_omits_none_duration(mbox: MeasurementInfoBox) -> None:
    mbox.set_info(_full_info(duration_s=None))
    assert "Duration" not in _all_texts(_form_texts(mbox))


def test_mbox_set_info_shows_comment(mbox: MeasurementInfoBox) -> None:
    mbox.set_info(_full_info(comment="My comment"))
    assert "My comment" in _all_texts(_form_texts(mbox))


def test_mbox_set_info_strips_xml_from_comment(mbox: MeasurementInfoBox) -> None:
    mbox.set_info(_full_info(comment="<HDcomment><TX>Clean text</TX></HDcomment>"))
    texts = _all_texts(_form_texts(mbox))
    assert "Clean text" in texts
    assert "<TX>" not in texts


def test_mbox_set_info_omits_empty_comment(mbox: MeasurementInfoBox) -> None:
    mbox.set_info(_full_info(comment=""))
    assert "Comment" not in _all_texts(_form_texts(mbox))


def test_mbox_set_info_shows_extra_fields(mbox: MeasurementInfoBox) -> None:
    info = MeasurementInfo(file_name="x.mf4", extra={"project": "DemoProject"})
    mbox.set_info(info)
    texts = _all_texts(_form_texts(mbox))
    assert "project" in texts
    assert "DemoProject" in texts


def test_mbox_set_info_replaces_previous(mbox: MeasurementInfoBox) -> None:
    mbox.set_info(_full_info(file_name="first.mf4"))
    mbox.set_info(_full_info(file_name="second.mf4"))
    texts = _all_texts(_form_texts(mbox))
    assert "second.mf4" in texts
    assert "first.mf4" not in texts


# ---------------------------------------------------------------------------
# MeasurementInfoBox – clear
# ---------------------------------------------------------------------------

def test_mbox_clear_shows_placeholder(mbox: MeasurementInfoBox) -> None:
    mbox.set_info(_full_info())
    mbox.clear()
    assert mbox._stack.currentIndex() == 0


def test_mbox_clear_removes_form_rows(mbox: MeasurementInfoBox) -> None:
    mbox.set_info(_full_info())
    mbox.clear()
    assert mbox._form.rowCount() == 0


# ---------------------------------------------------------------------------
# _format_duration
# ---------------------------------------------------------------------------

def test_format_duration_seconds() -> None:
    assert _format_duration(5.123) == "5.123 s"


def test_format_duration_minutes() -> None:
    result = _format_duration(90.0)
    assert "1 min" in result
    assert "30.000 s" in result


def test_format_duration_exactly_60s() -> None:
    result = _format_duration(60.0)
    assert "1 min" in result


# ---------------------------------------------------------------------------
# SignalInfoBox – initial state
# ---------------------------------------------------------------------------

@pytest.fixture()
def sbox(qtbot: QtBot) -> SignalInfoBox:
    w = SignalInfoBox()
    qtbot.addWidget(w)
    return w


def test_sbox_placeholder_shown_initially(sbox: SignalInfoBox) -> None:
    assert sbox._stack.currentIndex() == 0


def test_sbox_form_empty_initially(sbox: SignalInfoBox) -> None:
    assert sbox._form.rowCount() == 0


# ---------------------------------------------------------------------------
# SignalInfoBox – set_metadata
# ---------------------------------------------------------------------------

def _make_meta(**kwargs) -> SignalMetadata:
    defaults = dict(
        name="voltage",
        unit="V",
        comment="main supply",
        sample_count=1000,
        min_value=-1.5,
        max_value=1.5,
    )
    defaults.update(kwargs)
    return SignalMetadata(**defaults)


def test_sbox_set_metadata_switches_to_form(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta())
    assert sbox._stack.currentIndex() == 1


def test_sbox_set_metadata_shows_name(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta(name="engine_speed"))
    assert "engine_speed" in _all_texts(_form_texts(sbox))


def test_sbox_set_metadata_shows_unit(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta(unit="rpm"))
    assert "rpm" in _all_texts(_form_texts(sbox))


def test_sbox_set_metadata_omits_empty_unit(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta(unit=""))
    assert "Unit" not in _all_texts(_form_texts(sbox))


def test_sbox_set_metadata_shows_sample_count(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta(sample_count=12345))
    assert "12,345" in _all_texts(_form_texts(sbox))


def test_sbox_set_metadata_omits_none_sample_count(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta(sample_count=None))
    assert "Samples" not in _all_texts(_form_texts(sbox))


def test_sbox_set_metadata_shows_min_max(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta(min_value=-3.14, max_value=3.14))
    texts = _all_texts(_form_texts(sbox))
    assert "-3.14" in texts
    assert "3.14" in texts


def test_sbox_set_metadata_omits_none_min_max(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta(min_value=None, max_value=None))
    texts = _all_texts(_form_texts(sbox))
    assert "Min" not in texts
    assert "Max" not in texts


def test_sbox_set_metadata_shows_data_type(sbox: SignalInfoBox) -> None:
    meta = SignalMetadata(name="gear", data_type="uint8", is_integer=True)
    sbox.set_metadata(meta)
    assert "uint8" in _all_texts(_form_texts(sbox))


def test_sbox_set_metadata_omits_empty_data_type(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta())  # data_type="" by default
    assert "Data type" not in _all_texts(_form_texts(sbox))


def test_sbox_set_metadata_shows_comment(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta(comment="measured at pin 3"))
    assert "measured at pin 3" in _all_texts(_form_texts(sbox))


def test_sbox_set_metadata_omits_empty_comment(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta(comment=""))
    assert "Comment" not in _all_texts(_form_texts(sbox))


def test_sbox_set_metadata_shows_extra_fields(sbox: SignalInfoBox) -> None:
    meta = SignalMetadata(name="x", extra={"source": "CAN1"})
    sbox.set_metadata(meta)
    texts = _all_texts(_form_texts(sbox))
    assert "source" in texts
    assert "CAN1" in texts


def test_sbox_set_metadata_replaces_previous(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta(name="first"))
    sbox.set_metadata(_make_meta(name="second"))
    texts = _all_texts(_form_texts(sbox))
    assert "second" in texts
    assert "first" not in texts


# ---------------------------------------------------------------------------
# SignalInfoBox – clear
# ---------------------------------------------------------------------------

def test_sbox_clear_shows_placeholder(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta())
    sbox.clear()
    assert sbox._stack.currentIndex() == 0


def test_sbox_clear_removes_form_rows(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta())
    sbox.clear()
    assert sbox._form.rowCount() == 0


# ---------------------------------------------------------------------------
# SignalInfoBox – Properties tab
# ---------------------------------------------------------------------------

def test_sbox_has_two_tabs(sbox: SignalInfoBox) -> None:
    assert sbox._tabs.count() == 2


def test_sbox_properties_tab_disabled_initially(sbox: SignalInfoBox) -> None:
    assert not sbox._tabs.isTabEnabled(1)


def test_sbox_enable_properties_enables_tab(sbox: SignalInfoBox) -> None:
    sbox.enable_properties(True)
    assert sbox._tabs.isTabEnabled(1)


def test_sbox_enable_properties_disables_tab(sbox: SignalInfoBox) -> None:
    sbox.enable_properties(True)
    sbox.enable_properties(False)
    assert not sbox._tabs.isTabEnabled(1)


def test_sbox_clear_disables_properties_tab(sbox: SignalInfoBox) -> None:
    sbox.enable_properties(True)
    sbox.clear()
    assert not sbox._tabs.isTabEnabled(1)


def test_sbox_set_properties_sets_line_mode(sbox: SignalInfoBox) -> None:
    sbox.set_properties("line", "circle")
    assert sbox._props_widget._mode_combo.currentIndex() == 0


def test_sbox_set_properties_sets_line_marker_mode(sbox: SignalInfoBox) -> None:
    sbox.set_properties("line_marker", "circle")
    assert sbox._props_widget._mode_combo.currentIndex() == 1


def test_sbox_set_properties_sets_marker_only_mode(sbox: SignalInfoBox) -> None:
    sbox.set_properties("marker", "circle")
    assert sbox._props_widget._mode_combo.currentIndex() == 2


def test_sbox_set_properties_none_mode_shows_blank(sbox: SignalInfoBox) -> None:
    sbox.set_properties(None, "circle")
    assert sbox._props_widget._mode_combo.currentIndex() == -1


def test_sbox_set_properties_sets_shape(sbox: SignalInfoBox) -> None:
    sbox.set_properties("line_marker", "diamond")
    assert sbox._props_widget._shape_combo.currentIndex() == 2  # diamond is index 2


def test_sbox_set_properties_none_shape_shows_blank(sbox: SignalInfoBox) -> None:
    sbox.set_properties("line_marker", None)
    assert sbox._props_widget._shape_combo.currentIndex() == -1


def test_sbox_set_properties_line_mode_disables_shape(sbox: SignalInfoBox) -> None:
    sbox.enable_properties(True)  # enable tab so parent isn't disabled
    sbox.set_properties("line", "circle")
    assert not sbox._props_widget._shape_combo.isEnabled()


def test_sbox_set_properties_marker_mode_enables_shape(sbox: SignalInfoBox) -> None:
    sbox.enable_properties(True)  # enable tab so parent isn't disabled
    sbox.set_properties("marker", "circle")
    assert sbox._props_widget._shape_combo.isEnabled()


def test_sbox_display_mode_requested_emitted(sbox: SignalInfoBox, qtbot: QtBot) -> None:
    sbox.set_properties("line", "circle")
    with qtbot.waitSignal(sbox.display_mode_requested, timeout=1000) as blocker:
        sbox._props_widget._mode_combo.setCurrentIndex(1)  # line_marker
    assert blocker.args == ["line_marker"]


def test_sbox_marker_shape_requested_emitted(sbox: SignalInfoBox, qtbot: QtBot) -> None:
    sbox.set_properties("line_marker", "circle")
    with qtbot.waitSignal(sbox.marker_shape_requested, timeout=1000) as blocker:
        sbox._props_widget._shape_combo.setCurrentIndex(1)  # square
    assert blocker.args == ["square"]


def test_sbox_no_signal_emitted_when_setting_programmatically(
    sbox: SignalInfoBox, qtbot: QtBot
) -> None:
    emitted: list = []
    sbox.display_mode_requested.connect(emitted.append)
    sbox.marker_shape_requested.connect(emitted.append)
    sbox.set_properties("line_marker", "diamond")
    assert emitted == []
