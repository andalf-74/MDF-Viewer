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

def test_swatches_show_default_colors(dlg: PreferencesDialog) -> None:
    assert dlg._swatch_c1.rgb() == DEFAULT_CURSOR_COLOR_C1
    assert dlg._swatch_c2.rgb() == DEFAULT_CURSOR_COLOR_C2
    assert dlg._swatch_cl.rgb() == DEFAULT_CURSOR_COLOR_CL
    assert dlg._swatch_cr.rgb() == DEFAULT_CURSOR_COLOR_CR


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

def test_line_boost_spinbox_initialised_from_settings(
    qtbot: QtBot, settings: Settings
) -> None:
    settings.selected_line_boost = 4
    dlg = PreferencesDialog(settings)
    qtbot.addWidget(dlg)
    assert dlg._line_boost.value() == 4


def test_line_boost_spinbox_default_is_1(dlg: PreferencesDialog) -> None:
    assert dlg._line_boost.value() == 1


def test_line_boost_apply_saves_to_settings(
    dlg: PreferencesDialog, settings: Settings
) -> None:
    dlg._line_boost.setValue(3)
    dlg._apply()
    assert settings.selected_line_boost == 3


def test_line_boost_apply_zero_allowed(
    dlg: PreferencesDialog, settings: Settings
) -> None:
    dlg._line_boost.setValue(0)
    dlg._apply()
    assert settings.selected_line_boost == 0
