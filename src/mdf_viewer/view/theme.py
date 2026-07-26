"""App-chrome design tokens (#153-#158).

A small, named token set threaded through the app chrome (toolbar, panels,
Active Signals Table, menus) — replacing scattered ad hoc `setStyleSheet()`
literals and the stock Qt palette blue with one deliberate accent that
echoes the plot canvas's instrument identity, without touching the canvas
itself.

Plain module-level constants, not a class or Settings lookup, so a future
user-configurable color scheme can localize itself to this module instead
of a rewrite — see the #153 planning discussion for that direction; nothing
here is configurable yet.
"""

from __future__ import annotations

from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import QLabel

# Deliberately distinct from every color in AppController._COLOR_PALETTE
# (the 8-color signal trace palette), so a chrome highlight is never
# mistaken for a signal trace. Chosen to hold WCAG UI-component contrast
# (>=3:1) against both a light and a dark OS palette background, since
# chrome still follows the OS light/dark palette rather than forcing one.
ACCENT = "#B8860B"

# Lower-emphasis variant for hairline rules/borders that should read as
# subordinate to a full ACCENT highlight (e.g. Info-panel group dividers).
ACCENT_DIM = "#8A6508"

# Text color to pair with an ACCENT-filled background (e.g. selected table
# rows) — ACCENT is too light for white text to hold 4.5:1 contrast.
ACCENT_TEXT = "black"


def style_section_header(label: QLabel) -> None:
    """Apply the shared panel section-header treatment (#154): semi-bold
    weight and slight letter-spacing (both QFont-level — Qt Style Sheets
    have no `letter-spacing` property) plus a thin accent-colored
    underline, distinct from the regular-weight `"Label:"` field rows
    beneath it (which stay plain bold, unchanged by this)."""
    font = label.font()
    font.setWeight(QFont.Weight.DemiBold)
    font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 105)
    label.setFont(font)
    label.setStyleSheet(f"border-bottom: 1px solid {ACCENT}; padding-bottom: 2px;")


def monospace_font(point_size: int | None = None) -> QFont:
    """Platform monospace font for numeric readouts (cursor values, axis
    ticks, Signal Statistics figures) — never applied app-wide, only to
    the numbers a user compares at a glance, where tabular alignment
    actually helps scanning."""
    font = QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont)
    if point_size is not None:
        font.setPointSize(point_size)
    return font
