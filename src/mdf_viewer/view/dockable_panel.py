"""DockablePanel — a pin/hover collapsible panel docked to a window edge.

Wraps a content widget in a shell with a pin-toggle chevron button. When
pinned, the panel is a normal widget the owner docks into a splitter (via
``dock_callback``, called on re-pin — the owner knows the splitter layout
and sizing, this class does not). When unpinned, the panel floats as an
overlay on ``overlay_parent``, hidden until the mouse hovers near the
panel's edge, then slides in/out with a short animation.

Extracted from MainWindow's original left-panel-only implementation
(#98) so the same mechanism can be reused, mirrored, for a right-edge
panel without duplicating the geometry/animation math.
"""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QPoint,
    QPropertyAnimation,
    Qt,
    QTimer,
)
from PyQt6.QtGui import QCursor, QFont
from PyQt6.QtWidgets import QHBoxLayout, QToolButton, QVBoxLayout, QWidget

_HOVER_PX = 10          # distance from the edge that triggers the drawer to slide out
_HOVER_HYSTERESIS_PX = 20  # extra distance past the panel before it slides back in
_ANIM_MS = 200          # slide animation duration in ms


class DockablePanel(QWidget):
    """Collapsible panel: pinned (docked) or unpinned (hover-reveal overlay)."""

    def __init__(
        self,
        content: QWidget,
        edge: Qt.Edge,
        overlay_parent: QWidget,
        dock_callback: Callable[["DockablePanel"], None],
        default_width: int = 260,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        if edge not in (Qt.Edge.LeftEdge, Qt.Edge.RightEdge):
            raise ValueError("DockablePanel only supports LeftEdge/RightEdge")
        self._edge = edge
        self._overlay_parent = overlay_parent
        self._dock_callback = dock_callback
        self._panel_w = default_width
        self._pinned = True
        self._drawer_shown = False

        self.setAutoFillBackground(True)  # opaque over content when floating

        self._pin_button = QToolButton()
        self._pin_button.setFixedHeight(32)
        self._pin_button.setAutoRaise(True)
        _font = QFont()
        _font.setPointSize(16)
        self._pin_button.setFont(_font)
        self._pin_button.clicked.connect(self.toggle_pin)

        pin_row = QHBoxLayout()
        pin_row.setContentsMargins(0, 0, 0, 0)
        if edge == Qt.Edge.LeftEdge:
            pin_row.addStretch()
            pin_row.addWidget(self._pin_button)
        else:
            pin_row.addWidget(self._pin_button)
            pin_row.addStretch()

        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)
        vbox.addLayout(pin_row)
        vbox.addWidget(content)

        self._update_pin_button()

        self._hover_timer = QTimer(self)
        self._hover_timer.setInterval(50)
        self._hover_timer.timeout.connect(self._check_hover)

        self._anim = QPropertyAnimation(self, b"pos", self)
        self._anim.setDuration(_ANIM_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------

    @property
    def pinned(self) -> bool:
        return self._pinned

    @property
    def width_px(self) -> int:
        return self._panel_w

    def set_width(self, width: int) -> None:
        self._panel_w = width

    # ------------------------------------------------------------------
    # Pin / drawer toggle
    # ------------------------------------------------------------------

    def toggle_pin(self) -> None:
        if self._pinned:
            # Record current width before removing from its splitter.
            self._panel_w = self.width()
            self._pinned = False
            self._update_pin_button()
            # Re-parent to the overlay host as a floating overlay.
            self.setParent(self._overlay_parent)
            self.resize(self._panel_w, self._overlay_parent.height())
            self._position(shown=False, parent_width=self._overlay_parent.width())
            self.show()
            self.raise_()
            self._hover_timer.start()
            self._drawer_shown = False
        else:
            self._anim.stop()
            self._hover_timer.stop()
            self._pinned = True
            self._drawer_shown = False
            self._update_pin_button()
            self._dock_callback(self)

    def set_pinned(self, pinned: bool) -> None:
        if pinned != self._pinned:
            self.toggle_pin()

    def _update_pin_button(self) -> None:
        if self._edge == Qt.Edge.LeftEdge:
            self._pin_button.setText("‹" if self._pinned else "›")
        else:
            self._pin_button.setText("›" if self._pinned else "‹")
        self._pin_button.setToolTip("Collapse panel" if self._pinned else "Pin panel")

    # ------------------------------------------------------------------
    # Geometry (unpinned/overlay mode only)
    # ------------------------------------------------------------------

    def update_geometry(self, parent_width: int, parent_height: int) -> None:
        """Keep the floating overlay sized/positioned; called by the owner
        on resize/show. No-op while pinned (the host splitter manages
        geometry then)."""
        if self._pinned:
            return
        self.resize(self._panel_w, parent_height)
        if self._anim.state() != QAbstractAnimation.State.Running:
            self._position(self._drawer_shown, parent_width)

    def _position(self, shown: bool, parent_width: int) -> None:
        if self._edge == Qt.Edge.LeftEdge:
            x = 0 if shown else -self._panel_w
        else:
            x = parent_width - self._panel_w if shown else parent_width
        self.move(x, 0)

    def _slide(self, show: bool) -> None:
        self._anim.stop()
        self._drawer_shown = show
        parent_width = self._overlay_parent.width()
        if self._edge == Qt.Edge.LeftEdge:
            end = QPoint(0, 0) if show else QPoint(-self._panel_w, 0)
        else:
            end = (
                QPoint(parent_width - self._panel_w, 0)
                if show
                else QPoint(parent_width, 0)
            )
        if self.pos() == end:
            return
        self._anim.setStartValue(self.pos())
        self._anim.setEndValue(end)
        self._anim.start()

    def _check_hover(self) -> None:
        if self._pinned:
            return
        x = self._overlay_parent.mapFromGlobal(QCursor.pos()).x()
        parent_width = self._overlay_parent.width()
        if self._edge == Qt.Edge.LeftEdge:
            near_edge = x < _HOVER_PX
            far_from_edge = x > self._panel_w + _HOVER_HYSTERESIS_PX
        else:
            near_edge = x > parent_width - _HOVER_PX
            far_from_edge = x < parent_width - self._panel_w - _HOVER_HYSTERESIS_PX
        if not self._drawer_shown and near_edge:
            self._slide(show=True)
        elif self._drawer_shown and far_from_edge:
            self._slide(show=False)
