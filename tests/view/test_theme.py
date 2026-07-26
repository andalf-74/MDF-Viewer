"""Tests for the app-chrome design tokens (#153-#158)."""

from __future__ import annotations

import re

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QLabel

from mdf_viewer.controller.app_controller import _COLOR_PALETTE
from mdf_viewer.view import theme

_HEX_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def test_accent_tokens_are_valid_hex_colors():
    assert _HEX_RE.match(theme.ACCENT)
    assert _HEX_RE.match(theme.ACCENT_DIM)


def test_accent_distinct_from_every_trace_color():
    accent_rgb = tuple(int(theme.ACCENT[i:i + 2], 16) for i in (1, 3, 5))
    assert accent_rgb not in _COLOR_PALETTE


def test_monospace_font_is_fixed_pitch(qtbot):
    font = theme.monospace_font()
    assert isinstance(font, QFont)
    # Under the offscreen QPA platform (tests/conftest.py's default — see
    # memory/feedback_qt_offscreen_tests.md) Qt's font matching doesn't
    # populate fixedPitch()/styleHint() metadata, so check the family name
    # too rather than relying on those alone.
    assert (
        font.fixedPitch()
        or font.styleHint() == QFont.StyleHint.Monospace
        or "mono" in font.family().lower()
    )


def test_monospace_font_applies_requested_point_size(qtbot):
    font = theme.monospace_font(point_size=14)
    assert font.pointSize() == 14


def test_style_section_header_sets_weight_and_spacing(qtbot):
    label = QLabel("Info")
    theme.style_section_header(label)
    assert label.font().weight() == QFont.Weight.DemiBold
    assert label.font().letterSpacing() != 100.0  # Qt default is 100%


def test_style_section_header_underlines_with_accent(qtbot):
    label = QLabel("Info")
    theme.style_section_header(label)
    assert theme.ACCENT in label.styleSheet()
