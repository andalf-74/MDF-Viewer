"""Shared icon-loading helpers, used by both MainWindow's toolbar/menu icons
and per-row widgets like VisibilityToggleButton (#133) that need the same
theme-aware asset loading but can't import from main_window.py (which
already imports from view/widgets — a reverse import would be circular).

Icons are single stroke-based SVGs (#165) using `stroke="currentColor"` (and,
for a couple of filled glyphs, `fill="currentColor"`) with no color baked in —
Qt's SVG renderer doesn't understand the CSS `currentColor` keyword, so
`_load_icon()` substitutes it for a real hex color before rendering, picked
by the same light/dark detection the old per-file PNG variants used.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtWidgets import QApplication

_ICONS_DIR = Path(__file__).parent.parent.parent / "resources" / "icons"

# Icon stroke colors: light-gray for dark toolbar backgrounds, dark-gray for
# light ones — matching the old PNG variants' contrast intent.
_ICON_COLOR_FOR_DARK_BG = "#f0f0ec"
_ICON_COLOR_FOR_LIGHT_BG = "#2a2a28"

_ICON_SIZES = (24, 48)


def _load_icon(name: str) -> QIcon:
    color = _icon_color()
    svg_text = (_ICONS_DIR / f"{name}.svg").read_text(encoding="utf-8")
    svg_text = svg_text.replace("currentColor", color)
    svg_bytes = QByteArray(svg_text.encode("utf-8"))
    renderer = QSvgRenderer(svg_bytes)

    icon = QIcon()
    for size in _ICON_SIZES:
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        icon.addPixmap(pixmap)
    return icon


def _icon_color() -> str:
    """Return the stroke color for the current OS color scheme.

    The dark-background color is used only when the OS explicitly reports a
    dark color scheme; an "Unknown" report (e.g. on platforms without theme
    support) falls back to the light-background color, since light mode is
    the more common default. Detected once at startup.
    """
    scheme = QApplication.styleHints().colorScheme()
    return _ICON_COLOR_FOR_DARK_BG if scheme == Qt.ColorScheme.Dark else _ICON_COLOR_FOR_LIGHT_BG
