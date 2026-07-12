"""VisibilityToggleButton — a flat, icon-based eye button toggling a signal's
visibility in the Active Signals Table (#133).
"""

from __future__ import annotations

from PyQt6.QtWidgets import QPushButton, QWidget

from mdf_viewer.view.widgets.icons import _icon_suffix, _load_icon


class VisibilityToggleButton(QPushButton):
    """A flat, clickable eye icon — open when visible, closed when hidden."""

    def __init__(self, visible: bool, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFixedSize(20, 16)
        self.setFlat(True)
        self.set_visible_state(visible)

    def set_visible_state(self, visible: bool) -> None:
        self._visible = visible
        suffix = _icon_suffix()
        name = f"eye_open{suffix}" if visible else f"eye_hidden{suffix}"
        self.setIcon(_load_icon(name))

    @property
    def visible_state(self) -> bool:
        return self._visible
