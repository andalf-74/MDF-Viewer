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
    DEFAULT_PLOT_BACKGROUND_COLOR,
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
# Tab-position memory (#169)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PREFS-010")
def test_defaults_to_first_tab(dlg: PreferencesDialog) -> None:
    assert dlg.current_tab_index == 0


@pytest.mark.requirement("REQ-PREFS-010")
def test_opens_on_given_initial_tab_index(qtbot: QtBot, settings: Settings) -> None:
    dlg = PreferencesDialog(settings, initial_tab_index=2)
    qtbot.addWidget(dlg)
    assert dlg._tabs.currentIndex() == 2


@pytest.mark.requirement("REQ-PREFS-012")
def test_current_tab_index_reflects_manual_switch(dlg: PreferencesDialog) -> None:
    dlg._tabs.setCurrentIndex(3)
    assert dlg.current_tab_index == 3


def test_swatches_each_have_a_distinct_tooltip(dlg: PreferencesDialog) -> None:
    """#129: icon-only color chips, no other text cue at all."""
    tooltips = {
        dlg._swatch_c1.toolTip(),
        dlg._swatch_c2.toolTip(),
        dlg._swatch_cl.toolTip(),
        dlg._swatch_cr.toolTip(),
        dlg._swatch_delta.toolTip(),
    }
    assert "" not in tooltips
    assert len(tooltips) == 5  # every swatch names its own cursor


def test_reset_button_tooltip_discloses_its_wider_scope(dlg: PreferencesDialog) -> None:
    """#129: the button resets more than colors (delta-time display, arrow-
    key step settings too) — worth disclosing since the label alone
    ("Reset to defaults") doesn't say that."""
    assert dlg._cursor_reset_btn.toolTip() != ""


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
# Plot background color swatch (#117)
# ---------------------------------------------------------------------------

def test_background_swatch_has_a_tooltip(dlg: PreferencesDialog) -> None:
    """#129: icon-only color chip, no other text cue at all."""
    assert dlg._swatch_bg.toolTip() != ""


@pytest.mark.requirement("REQ-PLOT-015")
def test_background_swatch_shows_default_color(dlg: PreferencesDialog) -> None:
    assert dlg._swatch_bg.rgb() == DEFAULT_PLOT_BACKGROUND_COLOR


@pytest.mark.requirement("REQ-PLOT-015")
def test_background_swatch_shows_saved_color(qtbot: QtBot, settings: Settings) -> None:
    settings.plot_background_color = (64, 64, 64)
    dlg = PreferencesDialog(settings)
    qtbot.addWidget(dlg)
    assert dlg._swatch_bg.rgb() == (64, 64, 64)


@pytest.mark.requirement("REQ-PLOT-015")
def test_apply_saves_background_color_to_settings(
    dlg: PreferencesDialog, settings: Settings
) -> None:
    dlg._swatch_bg.set_color(QColor(64, 64, 64))
    dlg._apply()
    assert settings.plot_background_color == (64, 64, 64)


@pytest.mark.requirement("REQ-PLOT-015")
def test_reset_restores_default_background_color(dlg: PreferencesDialog) -> None:
    dlg._swatch_bg.set_color(QColor(64, 64, 64))
    dlg._reset_plot_background_color()
    assert dlg._swatch_bg.rgb() == DEFAULT_PLOT_BACKGROUND_COLOR


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
# signal_browser_view_mode combo (#141)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-BROWSER-062")
def test_view_mode_combo_defaults_to_flat(dlg: PreferencesDialog) -> None:
    assert dlg._view_mode_combo.currentIndex() == 0
    assert dlg._view_mode_combo.currentText() == "Flat"


@pytest.mark.requirement("REQ-BROWSER-060")
def test_view_mode_combo_initialised_from_settings(qtbot: QtBot, settings: Settings) -> None:
    settings.signal_browser_view_mode = "tree"
    dlg = PreferencesDialog(settings)
    qtbot.addWidget(dlg)
    assert dlg._view_mode_combo.currentIndex() == 1
    assert dlg._view_mode_combo.currentText() == "Tree"


@pytest.mark.requirement("REQ-BROWSER-060")
def test_view_mode_combo_apply_saves_tree_to_settings(
    dlg: PreferencesDialog, settings: Settings
) -> None:
    dlg._view_mode_combo.setCurrentIndex(1)  # Tree
    dlg._apply()
    assert settings.signal_browser_view_mode == "tree"


@pytest.mark.requirement("REQ-BROWSER-062")
def test_view_mode_combo_apply_saves_flat_to_settings(
    dlg: PreferencesDialog, settings: Settings
) -> None:
    settings.signal_browser_view_mode = "tree"
    dlg._view_mode_combo.setCurrentIndex(0)  # Flat
    dlg._apply()
    assert settings.signal_browser_view_mode == "flat"


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


# ---------------------------------------------------------------------------
# Logging controls (#126)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-LOG-040")
def test_logging_checkbox_reflects_settings(qtbot: QtBot, settings: Settings) -> None:
    settings.logging_enabled = False
    dlg = PreferencesDialog(settings)
    qtbot.addWidget(dlg)
    assert dlg._logging_enabled.isChecked() is False


@pytest.mark.requirement("REQ-LOG-041")
def test_log_level_combo_reflects_settings(qtbot: QtBot, settings: Settings) -> None:
    settings.logging_level = "DEBUG"
    dlg = PreferencesDialog(settings)
    qtbot.addWidget(dlg)
    assert dlg._log_level.currentText() == "DEBUG"


@pytest.mark.requirement("REQ-LOG-041")
def test_log_level_combo_disabled_when_logging_already_disabled_on_open(
    qtbot: QtBot, settings: Settings
) -> None:
    """A freshly-constructed QCheckBox already unchecked doesn't emit
    `toggled` from .setChecked(False) — the initial disabled state must be
    set explicitly, not rely solely on the toggled connection."""
    settings.logging_enabled = False
    dlg = PreferencesDialog(settings)
    qtbot.addWidget(dlg)
    assert dlg._log_level.isEnabled() is False


@pytest.mark.requirement("REQ-LOG-041")
def test_log_level_combo_enabled_when_logging_enabled_on_open(
    dlg: PreferencesDialog,
) -> None:
    assert dlg._logging_enabled.isChecked() is True
    assert dlg._log_level.isEnabled() is True


def test_log_level_combo_toggles_live_with_checkbox(dlg: PreferencesDialog) -> None:
    dlg._logging_enabled.setChecked(False)
    assert dlg._log_level.isEnabled() is False
    dlg._logging_enabled.setChecked(True)
    assert dlg._log_level.isEnabled() is True


@pytest.mark.requirement("REQ-LOG-023")
def test_apply_saves_logging_settings(dlg: PreferencesDialog, settings: Settings) -> None:
    dlg._logging_enabled.setChecked(False)
    dlg._log_level.setCurrentText("ERROR")
    dlg._apply()
    assert settings.logging_enabled is False
    assert settings.logging_level == "ERROR"


@pytest.mark.requirement("REQ-LOG-042")
def test_open_log_folder_button_calls_open_log_folder(
    dlg: PreferencesDialog, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls = []
    monkeypatch.setattr(
        "mdf_viewer.view.preferences_dialog.open_log_folder",
        lambda s: calls.append(s),
    )
    dlg._open_log_folder_btn.click()
    assert calls == [settings]


def test_step_unit_tooltip_explains_xaxis_meaning(dlg: PreferencesDialog) -> None:
    tooltip = dlg._step_unit.toolTip()
    assert tooltip != ""
    assert "X-Axis" in tooltip
