"""Tests for MeasurementInfoBox and SignalInfoBox."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from PyQt6.QtWidgets import QLabel
from pytestqt.qtbot import QtBot

from mdf_viewer.model.measurement import MeasurementInfo
from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.view.measurement_info_box import (
    MeasurementInfoBox,
    _format_duration,
)
from mdf_viewer.view.signal_info_box import SignalInfoBox, _format_raster


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


@pytest.mark.requirement("REQ-MDF-050")
def test_mbox_set_info_switches_to_form(mbox: MeasurementInfoBox) -> None:
    mbox.set_info(_full_info())
    assert mbox._stack.currentIndex() == 1


@pytest.mark.requirement("REQ-MDF-050")
def test_mbox_set_info_shows_file_name(mbox: MeasurementInfoBox) -> None:
    mbox.set_info(_full_info(file_name="recording.mf4"))
    assert "recording.mf4" in _all_texts(_form_texts(mbox))


@pytest.mark.requirement("REQ-MDF-050")
def test_mbox_set_info_shows_version(mbox: MeasurementInfoBox) -> None:
    mbox.set_info(_full_info(mdf_version="4.10"))
    assert "4.10" in _all_texts(_form_texts(mbox))


@pytest.mark.requirement("REQ-MDF-050")
def test_mbox_set_info_shows_author(mbox: MeasurementInfoBox) -> None:
    mbox.set_info(_full_info(author="Bob"))
    assert "Bob" in _all_texts(_form_texts(mbox))


@pytest.mark.requirement("REQ-MDF-051")
def test_mbox_set_info_omits_empty_author(mbox: MeasurementInfoBox) -> None:
    mbox.set_info(_full_info(author=""))
    assert "Author" not in _all_texts(_form_texts(mbox))


@pytest.mark.requirement("REQ-MDF-050")
def test_mbox_set_info_shows_recorded_at(mbox: MeasurementInfoBox) -> None:
    mbox.set_info(_full_info(recorded_at="2026-01-01 09:00:00"))
    assert "2026-01-01" in _all_texts(_form_texts(mbox))


@pytest.mark.requirement("REQ-MDF-051")
def test_mbox_set_info_omits_empty_recorded_at(mbox: MeasurementInfoBox) -> None:
    mbox.set_info(_full_info(recorded_at=""))
    assert "Recorded" not in _all_texts(_form_texts(mbox))


@pytest.mark.requirement("REQ-MDF-050")
def test_mbox_set_info_shows_duration(mbox: MeasurementInfoBox) -> None:
    mbox.set_info(_full_info(duration_s=10.5))
    assert "10.500 s" in _all_texts(_form_texts(mbox))


@pytest.mark.requirement("REQ-MDF-051")
def test_mbox_set_info_omits_none_duration(mbox: MeasurementInfoBox) -> None:
    mbox.set_info(_full_info(duration_s=None))
    assert "Duration" not in _all_texts(_form_texts(mbox))


@pytest.mark.requirement("REQ-MDF-050")
def test_mbox_set_info_shows_comment(mbox: MeasurementInfoBox) -> None:
    mbox.set_info(_full_info(comment="My comment"))
    assert "My comment" in _all_texts(_form_texts(mbox))


@pytest.mark.requirement("REQ-MDF-050")
def test_mbox_set_info_strips_xml_from_comment(mbox: MeasurementInfoBox) -> None:
    mbox.set_info(_full_info(comment="<HDcomment><TX>Clean text</TX></HDcomment>"))
    texts = _all_texts(_form_texts(mbox))
    assert "Clean text" in texts
    assert "<TX>" not in texts


@pytest.mark.requirement("REQ-MDF-051")
def test_mbox_set_info_omits_empty_comment(mbox: MeasurementInfoBox) -> None:
    mbox.set_info(_full_info(comment=""))
    assert "Comment" not in _all_texts(_form_texts(mbox))


@pytest.mark.requirement("REQ-MDF-050")
def test_mbox_set_info_shows_extra_fields(mbox: MeasurementInfoBox) -> None:
    info = MeasurementInfo(file_name="x.mf4", extra={"project": "DemoProject"})
    mbox.set_info(info)
    texts = _all_texts(_form_texts(mbox))
    assert "project" in texts
    assert "DemoProject" in texts


@pytest.mark.requirement("REQ-FILE-012")
def test_mbox_set_info_replaces_previous(mbox: MeasurementInfoBox) -> None:
    mbox.set_info(_full_info(file_name="first.mf4"))
    mbox.set_info(_full_info(file_name="second.mf4"))
    texts = _all_texts(_form_texts(mbox))
    assert "second.mf4" in texts
    assert "first.mf4" not in texts


# ---------------------------------------------------------------------------
# MeasurementInfoBox – clear
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-FILE-012")
def test_mbox_clear_shows_placeholder(mbox: MeasurementInfoBox) -> None:
    mbox.set_info(_full_info())
    mbox.clear()
    assert mbox._stack.currentIndex() == 0


@pytest.mark.requirement("REQ-FILE-012")
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


@pytest.mark.requirement("REQ-PLOT-152")
def test_sbox_placeholder_shown_initially(sbox: SignalInfoBox) -> None:
    assert sbox._stack.currentIndex() == 0


@pytest.mark.requirement("REQ-PLOT-152")
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


@pytest.mark.requirement("REQ-PLOT-150")
def test_sbox_set_metadata_switches_to_form(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta())
    assert sbox._stack.currentIndex() == 1


@pytest.mark.requirement("REQ-PLOT-150")
def test_sbox_set_metadata_shows_name(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta(name="engine_speed"))
    assert "engine_speed" in _all_texts(_form_texts(sbox))


@pytest.mark.requirement("REQ-PLOT-306")
def test_sbox_set_metadata_display_name_overrides_name_row(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta(name="engine_speed"), display_name="[run1] engine_speed")
    texts = _all_texts(_form_texts(sbox))
    assert "[run1] engine_speed" in texts
    assert "Name: engine_speed" not in texts


@pytest.mark.requirement("REQ-PLOT-306")
def test_sbox_set_metadata_no_display_name_shows_raw_name(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta(name="engine_speed"), display_name=None)
    assert "engine_speed" in _all_texts(_form_texts(sbox))


@pytest.mark.requirement("REQ-PLOT-150")
def test_sbox_set_metadata_shows_unit(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta(unit="rpm"))
    assert "rpm" in _all_texts(_form_texts(sbox))


@pytest.mark.requirement("REQ-PLOT-150")
def test_sbox_set_metadata_omits_empty_unit(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta(unit=""))
    assert "Unit" not in _all_texts(_form_texts(sbox))


@pytest.mark.requirement("REQ-PLOT-150")
def test_sbox_set_metadata_shows_sample_count(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta(sample_count=12345))
    assert "12,345" in _all_texts(_form_texts(sbox))


@pytest.mark.requirement("REQ-PLOT-150")
def test_sbox_set_metadata_omits_none_sample_count(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta(sample_count=None))
    assert "Samples" not in _all_texts(_form_texts(sbox))


@pytest.mark.requirement("REQ-PLOT-150")
def test_sbox_set_metadata_shows_min_max(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta(min_value=-3.14, max_value=3.14))
    texts = _all_texts(_form_texts(sbox))
    assert "-3.14" in texts
    assert "3.14" in texts


@pytest.mark.requirement("REQ-PLOT-150")
def test_sbox_set_metadata_omits_none_min_max(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta(min_value=None, max_value=None))
    texts = _all_texts(_form_texts(sbox))
    assert "Min" not in texts
    assert "Max" not in texts


@pytest.mark.requirement("REQ-PLOT-150")
def test_sbox_set_metadata_shows_data_type(sbox: SignalInfoBox) -> None:
    meta = SignalMetadata(name="gear", data_type="uint8", is_integer=True)
    sbox.set_metadata(meta)
    assert "uint8" in _all_texts(_form_texts(sbox))


@pytest.mark.requirement("REQ-PLOT-150")
def test_sbox_set_metadata_omits_empty_data_type(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta())  # data_type="" by default
    assert "Data type" not in _all_texts(_form_texts(sbox))


@pytest.mark.requirement("REQ-PLOT-150")
def test_sbox_set_metadata_shows_comment(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta(comment="measured at pin 3"))
    assert "measured at pin 3" in _all_texts(_form_texts(sbox))


@pytest.mark.requirement("REQ-PLOT-150")
def test_sbox_set_metadata_omits_empty_comment(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta(comment=""))
    assert "Comment" not in _all_texts(_form_texts(sbox))


@pytest.mark.requirement("REQ-PLOT-151")
def test_sbox_set_metadata_shows_fixed_raster(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta(sample_count=100, raster_s=0.01))
    assert "10 ms" in _all_texts(_form_texts(sbox))


@pytest.mark.requirement("REQ-PLOT-151")
def test_sbox_set_metadata_shows_raster_in_seconds_above_500ms(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta(sample_count=100, raster_s=1.0))
    assert "1 s" in _all_texts(_form_texts(sbox))


@pytest.mark.requirement("REQ-PLOT-151")
def test_sbox_set_metadata_shows_variable_raster(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta(sample_count=100, raster_s=None))
    assert "variable" in _all_texts(_form_texts(sbox))


@pytest.mark.requirement("REQ-PLOT-151")
def test_sbox_set_metadata_omits_raster_for_single_sample(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta(sample_count=1, raster_s=None))
    assert "Raster" not in _all_texts(_form_texts(sbox))


@pytest.mark.requirement("REQ-PLOT-151")
def test_sbox_set_metadata_omits_raster_when_sample_count_none(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta(sample_count=None, raster_s=None))
    assert "Raster" not in _all_texts(_form_texts(sbox))


# ---------------------------------------------------------------------------
# _format_raster
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-151")
def test_format_raster_milliseconds() -> None:
    assert _format_raster(0.01) == "10 ms"


@pytest.mark.requirement("REQ-PLOT-151")
def test_format_raster_boundary_500ms() -> None:
    assert _format_raster(0.5) == "500 ms"


@pytest.mark.requirement("REQ-PLOT-151")
def test_format_raster_above_500ms_shows_seconds() -> None:
    assert _format_raster(0.501) == "0.501 s"


@pytest.mark.requirement("REQ-PLOT-151")
def test_format_raster_large_value_seconds() -> None:
    assert _format_raster(1.0) == "1 s"


@pytest.mark.requirement("REQ-PLOT-150")
def test_sbox_set_metadata_shows_extra_fields(sbox: SignalInfoBox) -> None:
    meta = SignalMetadata(name="x", extra={"source": "CAN1"})
    sbox.set_metadata(meta)
    texts = _all_texts(_form_texts(sbox))
    assert "source" in texts
    assert "CAN1" in texts


@pytest.mark.requirement("REQ-PLOT-152")
def test_sbox_set_metadata_replaces_previous(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta(name="first"))
    sbox.set_metadata(_make_meta(name="second"))
    texts = _all_texts(_form_texts(sbox))
    assert "second" in texts
    assert "first" not in texts


# ---------------------------------------------------------------------------
# SignalInfoBox – clear
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-152")
def test_sbox_clear_shows_placeholder(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta())
    sbox.clear()
    assert sbox._stack.currentIndex() == 0


@pytest.mark.requirement("REQ-PLOT-152")
def test_sbox_clear_removes_form_rows(sbox: SignalInfoBox) -> None:
    sbox.set_metadata(_make_meta())
    sbox.clear()
    assert sbox._form.rowCount() == 0


# ---------------------------------------------------------------------------
# SignalInfoBox – Info/Properties sections (#98: vertical splitter, not tabs)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-226")
def test_sbox_has_info_and_properties_sections(sbox: SignalInfoBox) -> None:
    assert sbox._splitter.count() == 2


@pytest.mark.requirement("REQ-PLOT-152")
def test_sbox_properties_section_disabled_initially(sbox: SignalInfoBox) -> None:
    assert not sbox._props_widget.isEnabled()


@pytest.mark.requirement("REQ-PLOT-227")
def test_sbox_set_splitter_sizes_restores_inner_split(sbox: SignalInfoBox) -> None:
    with patch.object(sbox._splitter, "setSizes") as mock_set_sizes:
        sbox.set_splitter_sizes([50, 200])
    mock_set_sizes.assert_called_once_with([50, 200])


@pytest.mark.requirement("REQ-PLOT-120")
def test_sbox_enable_properties_enables_section(sbox: SignalInfoBox) -> None:
    sbox.enable_properties(True)
    assert sbox._props_widget.isEnabled()


@pytest.mark.requirement("REQ-PLOT-120")
def test_sbox_enable_properties_disables_section(sbox: SignalInfoBox) -> None:
    sbox.enable_properties(True)
    sbox.enable_properties(False)
    assert not sbox._props_widget.isEnabled()


@pytest.mark.requirement("REQ-PLOT-152")
def test_sbox_clear_disables_properties_section(sbox: SignalInfoBox) -> None:
    sbox.enable_properties(True)
    sbox.clear()
    assert not sbox._props_widget.isEnabled()


@pytest.mark.requirement("REQ-PLOT-120")
def test_sbox_set_properties_sets_line_mode(sbox: SignalInfoBox) -> None:
    sbox.set_properties("line", "circle")
    assert sbox._props_widget._mode_combo.currentIndex() == 0


@pytest.mark.requirement("REQ-PLOT-120")
def test_sbox_set_properties_sets_line_marker_mode(sbox: SignalInfoBox) -> None:
    sbox.set_properties("line_marker", "circle")
    assert sbox._props_widget._mode_combo.currentIndex() == 1


@pytest.mark.requirement("REQ-PLOT-120")
def test_sbox_set_properties_sets_marker_only_mode(sbox: SignalInfoBox) -> None:
    sbox.set_properties("marker", "circle")
    assert sbox._props_widget._mode_combo.currentIndex() == 2


@pytest.mark.requirement("REQ-PLOT-140")
def test_sbox_set_properties_none_mode_shows_blank(sbox: SignalInfoBox) -> None:
    sbox.set_properties(None, "circle")
    assert sbox._props_widget._mode_combo.currentIndex() == -1


@pytest.mark.requirement("REQ-PLOT-120")
def test_sbox_set_properties_sets_shape(sbox: SignalInfoBox) -> None:
    sbox.set_properties("line_marker", "diamond")
    assert sbox._props_widget._shape_combo.currentIndex() == 2  # diamond is index 2


@pytest.mark.requirement("REQ-PLOT-140")
def test_sbox_set_properties_none_shape_shows_blank(sbox: SignalInfoBox) -> None:
    sbox.set_properties("line_marker", None)
    assert sbox._props_widget._shape_combo.currentIndex() == -1


@pytest.mark.requirement("REQ-PLOT-121")
def test_sbox_set_properties_line_mode_disables_shape(sbox: SignalInfoBox) -> None:
    sbox.enable_properties(True)  # enable tab so parent isn't disabled
    sbox.set_properties("line", "circle")
    assert not sbox._props_widget._shape_combo.isEnabled()


@pytest.mark.requirement("REQ-PLOT-121")
def test_sbox_set_properties_marker_mode_enables_shape(sbox: SignalInfoBox) -> None:
    sbox.enable_properties(True)  # enable tab so parent isn't disabled
    sbox.set_properties("marker", "circle")
    assert sbox._props_widget._shape_combo.isEnabled()


@pytest.mark.requirement("REQ-PLOT-120")
def test_sbox_display_mode_requested_emitted(sbox: SignalInfoBox, qtbot: QtBot) -> None:
    sbox.set_properties("line", "circle")
    with qtbot.waitSignal(sbox.display_mode_requested, timeout=1000) as blocker:
        sbox._props_widget._mode_combo.setCurrentIndex(1)  # line_marker
    assert blocker.args == ["line_marker"]


@pytest.mark.requirement("REQ-PLOT-120")
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


@pytest.mark.requirement("REQ-PLOT-120")
def test_sbox_set_properties_sets_line_width(sbox: SignalInfoBox) -> None:
    sbox.set_properties("line", "circle", 3)
    assert sbox._props_widget._width_spin.value() == 3


@pytest.mark.requirement("REQ-PLOT-140")
def test_sbox_set_properties_none_width_shows_mixed(sbox: SignalInfoBox) -> None:
    sbox.set_properties("line", "circle", None)
    assert sbox._props_widget._width_spin.value() == 0
    assert sbox._props_widget._width_spin.text() == "—"


@pytest.mark.requirement("REQ-PLOT-120")
def test_sbox_line_width_requested_emitted(sbox: SignalInfoBox, qtbot: QtBot) -> None:
    sbox.set_properties("line", "circle", 2)
    with qtbot.waitSignal(sbox.line_width_requested, timeout=1000) as blocker:
        sbox._props_widget._width_spin.setValue(4)
    assert blocker.args == [4]


def test_sbox_line_width_not_emitted_for_mixed_sentinel(sbox: SignalInfoBox, qtbot: QtBot) -> None:
    sbox.set_properties("line", "circle", 3)
    emitted: list = []
    sbox.line_width_requested.connect(emitted.append)
    sbox._props_widget._width_spin.setValue(0)  # mixed sentinel
    assert emitted == []


def test_sbox_no_line_width_signal_when_setting_programmatically(
    sbox: SignalInfoBox, qtbot: QtBot
) -> None:
    emitted: list = []
    sbox.line_width_requested.connect(emitted.append)
    sbox.set_properties("line", "circle", 3)
    assert emitted == []


@pytest.mark.requirement("REQ-PLOT-120")
def test_sbox_set_properties_sets_line_style(sbox: SignalInfoBox) -> None:
    sbox.set_properties("line", "circle", 1, "dashes")
    assert sbox._props_widget._style_combo.currentIndex() == 1  # dashes is index 1


@pytest.mark.requirement("REQ-PLOT-140")
def test_sbox_set_properties_none_style_shows_blank(sbox: SignalInfoBox) -> None:
    sbox.set_properties("line", "circle", 1, None)
    assert sbox._props_widget._style_combo.currentIndex() == -1


@pytest.mark.requirement("REQ-PLOT-120")
def test_sbox_line_style_requested_emitted(sbox: SignalInfoBox, qtbot: QtBot) -> None:
    sbox.set_properties("line", "circle", 1, "solid")
    with qtbot.waitSignal(sbox.line_style_requested, timeout=1000) as blocker:
        sbox._props_widget._style_combo.setCurrentIndex(2)  # dots
    assert blocker.args == ["dots"]


@pytest.mark.requirement("REQ-PLOT-121")
def test_sbox_line_style_disabled_in_marker_only_mode(sbox: SignalInfoBox) -> None:
    sbox.enable_properties(True)
    sbox.set_properties("marker", "circle", 1, "solid")
    assert not sbox._props_widget._style_combo.isEnabled()


@pytest.mark.requirement("REQ-PLOT-121")
def test_sbox_line_style_enabled_in_line_mode(sbox: SignalInfoBox) -> None:
    sbox.enable_properties(True)
    sbox.set_properties("line", "circle", 1, "solid")
    assert sbox._props_widget._style_combo.isEnabled()


@pytest.mark.requirement("REQ-PLOT-121")
def test_sbox_line_style_enabled_in_line_marker_mode(sbox: SignalInfoBox) -> None:
    sbox.enable_properties(True)
    sbox.set_properties("line_marker", "circle", 1, "solid")
    assert sbox._props_widget._style_combo.isEnabled()


def test_sbox_no_line_style_signal_when_setting_programmatically(
    sbox: SignalInfoBox, qtbot: QtBot
) -> None:
    emitted: list = []
    sbox.line_style_requested.connect(emitted.append)
    sbox.set_properties("line", "circle", 1, "dashes")
    assert emitted == []


# ---------------------------------------------------------------------------
# SignalInfoBox – enum label toggles (REQ-PLOT-130/131)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-131")
def test_sbox_enum_options_hidden_initially(sbox: SignalInfoBox) -> None:
    assert sbox._props_widget._enum_container.isHidden()
    assert sbox._props_widget._enum_label.isHidden()


@pytest.mark.requirement("REQ-PLOT-130")
def test_sbox_set_enum_options_shows_and_checks_boxes(sbox: SignalInfoBox) -> None:
    sbox.set_enum_options(True, False, True)
    assert not sbox._props_widget._enum_container.isHidden()
    assert sbox._props_widget._enum_table_check.isChecked() is True
    assert sbox._props_widget._enum_cursor_check.isChecked() is False
    assert sbox._props_widget._enum_yaxis_check.isChecked() is True


@pytest.mark.requirement("REQ-PLOT-131")
def test_sbox_set_enum_options_none_hides_section(sbox: SignalInfoBox) -> None:
    sbox.set_enum_options(True, True, True)
    sbox.set_enum_options(None, None, None)
    assert sbox._props_widget._enum_container.isHidden()


@pytest.mark.requirement("REQ-PLOT-131")
def test_sbox_clear_hides_enum_section(sbox: SignalInfoBox) -> None:
    sbox.set_enum_options(True, True, True)
    sbox.clear()
    assert sbox._props_widget._enum_container.isHidden()


@pytest.mark.requirement("REQ-PLOT-130")
def test_sbox_enum_table_requested_emitted(sbox: SignalInfoBox, qtbot: QtBot) -> None:
    sbox.set_enum_options(False, False, False)
    with qtbot.waitSignal(sbox.enum_table_requested, timeout=1000) as blocker:
        sbox._props_widget._enum_table_check.setChecked(True)
    assert blocker.args == [True]


@pytest.mark.requirement("REQ-PLOT-130")
def test_sbox_enum_cursor_requested_emitted(sbox: SignalInfoBox, qtbot: QtBot) -> None:
    sbox.set_enum_options(False, False, False)
    with qtbot.waitSignal(sbox.enum_cursor_requested, timeout=1000) as blocker:
        sbox._props_widget._enum_cursor_check.setChecked(True)
    assert blocker.args == [True]


@pytest.mark.requirement("REQ-PLOT-130")
def test_sbox_enum_yaxis_requested_emitted(sbox: SignalInfoBox, qtbot: QtBot) -> None:
    sbox.set_enum_options(False, False, False)
    with qtbot.waitSignal(sbox.enum_yaxis_requested, timeout=1000) as blocker:
        sbox._props_widget._enum_yaxis_check.setChecked(True)
    assert blocker.args == [True]


def test_sbox_no_enum_signal_emitted_when_setting_programmatically(
    sbox: SignalInfoBox, qtbot: QtBot
) -> None:
    emitted: list = []
    sbox.enum_table_requested.connect(emitted.append)
    sbox.enum_cursor_requested.connect(emitted.append)
    sbox.enum_yaxis_requested.connect(emitted.append)
    sbox.set_enum_options(True, False, True)
    assert emitted == []
