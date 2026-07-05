"""make_splitter — a QSplitter with a thin, visible handle line."""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSplitter


def make_splitter(orientation: Qt.Orientation) -> QSplitter:
    """Splitter with a thin visible handle line."""
    s = QSplitter(orientation)
    s.setHandleWidth(3)
    s.setStyleSheet("QSplitter::handle { background: palette(mid); }")
    return s
