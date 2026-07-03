"""Tests for PreferencesDialog — cursor color swatches."""

from __future__ import annotations

from pathlib import Path

import pytest
from pytestqt.qtbot import QtBot

from PyQt6.QtGui import QColor

from mdf_viewer.settings import (
    DEFAULT_CURSOR_COLOR_C1,
    DEFAULT_CURSOR_COLOR_C2,
    DEFAULT_CURSOR_COLOR_CL,
    DEFAULT_CURSOR_COLOR_CR,
    Settings,
)
from mdf_viewer.view.preferences_dialog import PreferencesDialog


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(path=tmp_path / "settings.json")


@pytest.fixture()
def dlg(qtbot: QtBot, settings: Settings) -> PreferencesDialog:
    d = PreferencesDialog(settings)
    qtbot.addWidget(d)
    return d


# ---------------------------------------------------------------------------
# Swatches initialised from settings
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-072")
def test_swatches_show_default_colors(dlg: PreferencesDialog) -> None:
    assert dlg._swatch_c1.rgb() == DEFAULT_CURSOR_COLOR_C1
    assert dlg._swatch_c2.rgb() == DEFAULT_CURSOR_COLOR_C2
    assert dlg._swatch_cl.rgb() == DEFAULT_CURSOR_COLOR_CL
    assert dlg._swatch_cr.rgb() == DEFAULT_CURSOR_COLOR_CR


@pytest.mark.requirement("REQ-PLOT-072")
def test_swatches_show_saved_colors(qtbot: QtBot, settings: Settings) -> None:
    settings.cursor_color_c1 = (1, 2, 3)
    settings.cursor_color_cr = (10, 11, 12)
    dlg = PreferencesDialog(settings)
    qtbot.addWidget(dlg)
    assert dlg._swatch_c1.rgb() == (1, 2, 3)
    assert dlg._swatch_cr.rgb() == (10, 11, 12)


# ---------------------------------------------------------------------------
# Reset to defaults
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-072")
def test_reset_restores_all_default_colors(dlg: PreferencesDialog) -> None:
    dlg._swatch_c1.set_color(QColor(1, 2, 3))
    dlg._swatch_c2.set_color(QColor(4, 5, 6))
    dlg._swatch_cl.set_color(QColor(7, 8, 9))
    dlg._swatch_cr.set_color(QColor(10, 11, 12))

    dlg._reset_cursor_colors()

    assert dlg._swatch_c1.rgb() == DEFAULT_CURSOR_COLOR_C1
    assert dlg._swatch_c2.rgb() == DEFAULT_CURSOR_COLOR_C2
    assert dlg._swatch_cl.rgb() == DEFAULT_CURSOR_COLOR_CL
    assert dlg._swatch_cr.rgb() == DEFAULT_CURSOR_COLOR_CR


# ---------------------------------------------------------------------------
# _apply saves to settings
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-072")
def test_apply_saves_colors_to_settings(dlg: PreferencesDialog, settings: Settings) -> None:
    dlg._swatch_c1.set_color(QColor(10, 20, 30))
    dlg._swatch_c2.set_color(QColor(40, 50, 60))
    dlg._swatch_cl.set_color(QColor(70, 80, 90))
    dlg._swatch_cr.set_color(QColor(100, 110, 120))

    dlg._apply()

    assert settings.cursor_color_c1 == (10, 20, 30)
    assert settings.cursor_color_c2 == (40, 50, 60)
    assert settings.cursor_color_cl == (70, 80, 90)
    assert settings.cursor_color_cr == (100, 110, 120)


# ---------------------------------------------------------------------------
# selected_line_boost spinbox
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-044")
def test_line_boost_spinbox_initialised_from_settings(
    qtbot: QtBot, settings: Settings
) -> None:
    settings.selected_line_boost = 4
    dlg = PreferencesDialog(settings)
    qtbot.addWidget(dlg)
    assert dlg._line_boost.value() == 4


@pytest.mark.requirement("REQ-PLOT-044")
def test_line_boost_spinbox_default_is_1(dlg: PreferencesDialog) -> None:
    assert dlg._line_boost.value() == 1


@pytest.mark.requirement("REQ-PLOT-044")
def test_line_boost_apply_saves_to_settings(
    dlg: PreferencesDialog, settings: Settings
) -> None:
    dlg._line_boost.setValue(3)
    dlg._apply()
    assert settings.selected_line_boost == 3


@pytest.mark.requirement("REQ-PLOT-044")
def test_line_boost_apply_zero_allowed(
    dlg: PreferencesDialog, settings: Settings
) -> None:
    dlg._line_boost.setValue(0)
    dlg._apply()
    assert settings.selected_line_boost == 0


# ---------------------------------------------------------------------------
# Display name rule controls in Signals tab
# ---------------------------------------------------------------------------

def test_display_name_controls_present(dlg: PreferencesDialog) -> None:
    from mdf_viewer.view._display_name_controls import DisplayNameRuleControls
    assert isinstance(dlg._display_name_controls, DisplayNameRuleControls)


@pytest.mark.requirement("REQ-PLOT-160")
def test_display_name_controls_init_from_settings(
    qtbot: QtBot, settings: Settings
) -> None:
    settings.display_name_rule_enabled = True
    settings.display_name_separator = "_"
    settings.display_name_segments = 3
    dlg = PreferencesDialog(settings)
    qtbot.addWidget(dlg)
    c = dlg._display_name_controls
    assert c._enabled.isChecked() is True
    assert c._separator.text() == "_"
    assert c._segments.value() == 3


@pytest.mark.requirement("REQ-PLOT-160")
def test_display_name_apply_saves_to_settings(
    dlg: PreferencesDialog, settings: Settings
) -> None:
    dlg._display_name_controls._enabled.setChecked(True)
    dlg._display_name_controls._separator.setText("/")
    dlg._display_name_controls._segments.setValue(2)
    dlg._apply()
    assert settings.display_name_rule_enabled is True
    assert settings.display_name_separator == "/"
    assert settings.display_name_segments == 2


def test_display_name_preview_name_used(qtbot: QtBot, settings: Settings) -> None:
    dlg = PreferencesDialog(settings, preview_name="a.b.c")
    qtbot.addWidget(dlg)
    assert dlg._preview_name == "a.b.c"


def test_display_name_fallback_preview_when_none(qtbot: QtBot, settings: Settings) -> None:
    from mdf_viewer.view.preferences_dialog import _FALLBACK_PREVIEW
    dlg = PreferencesDialog(settings)
    qtbot.addWidget(dlg)
    assert dlg._preview_name == _FALLBACK_PREVIEW


# show_only_selected_y_axis checkbox


@pytest.mark.requirement("REQ-PLOT-045")
def test_show_only_selected_y_axis_default_unchecked(dlg: PreferencesDialog) -> None:
    assert dlg._show_only_selected_y_axis.isChecked() is False


@pytest.mark.requirement("REQ-PLOT-045")
def test_show_only_selected_y_axis_initialised_from_settings(
    qtbot: QtBot, settings: Settings
) -> None:
    settings.show_only_selected_y_axis = True
    dlg = PreferencesDialog(settings)
    qtbot.addWidget(dlg)
    assert dlg._show_only_selected_y_axis.isChecked() is True


@pytest.mark.requirement("REQ-PLOT-045")
def test_show_only_selected_y_axis_apply_saves_to_settings(
    dlg: PreferencesDialog, settings: Settings
) -> None:
    dlg._show_only_selected_y_axis.setChecked(True)
    dlg._apply()
    assert settings.show_only_selected_y_axis is True


@pytest.mark.requirement("REQ-PLOT-045")
def test_show_only_selected_y_axis_apply_false_saves_to_settings(
    dlg: PreferencesDialog, settings: Settings
) -> None:
    settings.show_only_selected_y_axis = True
    dlg._show_only_selected_y_axis.setChecked(False)
    dlg._apply()
    assert settings.show_only_selected_y_axis is False


# ---------------------------------------------------------------------------
# keep_signals_on_load radio buttons
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-FILE-030")
def test_keep_signals_default_radio_is_always(dlg: PreferencesDialog) -> None:
    assert dlg._keep_always.isChecked() is True
    assert dlg._keep_ask.isChecked() is False
    assert dlg._keep_never.isChecked() is False


@pytest.mark.requirement("REQ-FILE-030")
def test_keep_signals_radio_reflects_ask_setting(
    qtbot: QtBot, settings: Settings
) -> None:
    settings.keep_signals_on_load = "ask"
    dlg = PreferencesDialog(settings)
    qtbot.addWidget(dlg)
    assert dlg._keep_ask.isChecked() is True


@pytest.mark.requirement("REQ-FILE-030")
def test_keep_signals_radio_reflects_never_setting(
    qtbot: QtBot, settings: Settings
) -> None:
    settings.keep_signals_on_load = "never"
    dlg = PreferencesDialog(settings)
    qtbot.addWidget(dlg)
    assert dlg._keep_never.isChecked() is True


@pytest.mark.requirement("REQ-FILE-030")
def test_keep_signals_apply_saves_ask(dlg: PreferencesDialog, settings: Settings) -> None:
    dlg._keep_ask.setChecked(True)
    dlg._apply()
    assert settings.keep_signals_on_load == "ask"


@pytest.mark.requirement("REQ-FILE-030")
def test_keep_signals_apply_saves_never(dlg: PreferencesDialog, settings: Settings) -> None:
    dlg._keep_never.setChecked(True)
    dlg._apply()
    assert settings.keep_signals_on_load == "never"


@pytest.mark.requirement("REQ-FILE-030")
def test_keep_signals_apply_saves_always(
    dlg: PreferencesDialog, settings: Settings
) -> None:
    settings.keep_signals_on_load = "never"
    dlg._keep_always.setChecked(True)
    dlg._apply()
    assert settings.keep_signals_on_load == "always"
