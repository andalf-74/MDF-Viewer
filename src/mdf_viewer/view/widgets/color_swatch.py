"""ColorSwatch — a flat, clickable colored rectangle widget."""

from __future__ import annotations

from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QPushButton, QWidget


class ColorSwatch(QPushButton):
    """A flat, clickable colored rectangle used as a signal color indicator."""

    def __init__(self, color: QColor, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(20, 16)
        self.setFlat(True)
        self.set_color(color)

    def set_color(self, color: QColor) -> None:
        self._color = color
        self.setStyleSheet(
            f"background-color: {color.name()};"
            "border: 1px solid #666;"
            "border-radius: 2px;"
        )

    @property
    def color(self) -> QColor:
        return self._color
