"""Shared icon-loading helpers, used by both MainWindow's toolbar/menu icons
and per-row widgets like VisibilityToggleButton (#133) that need the same
light/dark-aware asset loading but can't import from main_window.py (which
already imports from view/widgets — a reverse import would be circular).
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

_ICONS_DIR = Path(__file__).parent.parent.parent / "resources" / "icons"


def _load_icon(name: str) -> QIcon:
    icon = QIcon()
    icon.addFile(str(_ICONS_DIR / f"{name}.png"), QSize(32, 32))
    icon.addFile(str(_ICONS_DIR / f"{name}@2x.png"), QSize(64, 64))
    return icon


def _icon_suffix() -> str:
    """Return "_light" unless the OS explicitly reports a dark color scheme.

    The unsuffixed icons are light-gray and meant for dark backgrounds; the
    "_light" variants are dark-gray and meant for light backgrounds. Detected
    once at startup; an "Unknown" report (e.g. on platforms without theme
    support) falls back to the light-mode icons, since light mode is the more
    common default.
    """
    scheme = QApplication.styleHints().colorScheme()
    return "" if scheme == Qt.ColorScheme.Dark else "_light"
