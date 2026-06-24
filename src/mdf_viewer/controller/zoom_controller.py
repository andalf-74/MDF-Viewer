"""ZoomController — undo/redo history for plot zoom gestures and toolbar actions."""

from __future__ import annotations

from typing import Callable

_GESTURE_DEBOUNCE_MS = 300


class ZoomController:
    """Manages undo/redo stacks for zoom state (X range + per-signal Y ranges).

    Design note — why _stable_state:
    PyQtGraph fires sigRangeChanged *synchronously inside* setRange / showAxRect,
    so by the time _on_range_changed is called the view has already moved.
    Capturing the current state there would record the post-change position as the
    undo target, which is wrong.  Instead we keep _stable_state — the state that
    was captured the last time the view came to rest.  _on_range_changed uses that
    as the pre-gesture baseline.  _on_gesture_end refreshes _stable_state after
    the debounce timer fires (i.e., once the user has stopped interacting).
    """

    def __init__(
        self,
        plot_area,
        get_active_signals: Callable[[], list],
        get_max_steps: Callable[[], int],
        _timer=None,
    ) -> None:
        self._plot_area = plot_area
        self._get_active_signals = get_active_signals
        self._get_max_steps = get_max_steps

        self._undo_stack: list = []
        self._redo_stack: list = []
        self._stable_state = None   # view state while at rest; None until first idle
        self._in_gesture: bool = False
        self._pre_gesture_state = None
        self._ignore_range_changed: bool = False

        if _timer is None:
            from PyQt6.QtCore import QTimer
            self._timer = QTimer()
            self._timer.setSingleShot(True)
            self._timer.setInterval(_GESTURE_DEBOUNCE_MS)
            self._timer.timeout.connect(self._on_gesture_end)
        else:
            self._timer = _timer

        plot_area.range_changed.connect(self._on_range_changed)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def before_discrete_action(self) -> None:
        """Call immediately before a toolbar zoom is applied.

        Captures the current state onto the undo stack and suppresses the
        range_changed events that the zoom action will fire.
        """
        state = self._plot_area.get_zoom_state(self._get_active_signals())
        self._push_undo(state)
        self._redo_stack.clear()
        self._ignore_range_changed = True
        self._timer.stop()
        self._in_gesture = False
        self._pre_gesture_state = None

    def after_discrete_action(self) -> None:
        """Call immediately after a toolbar zoom has been applied."""
        self._ignore_range_changed = False
        self._stable_state = self._plot_area.get_zoom_state(self._get_active_signals())

    def undo(self) -> None:
        """Restore the previous zoom state."""
        if not self._undo_stack:
            return
        current = self._plot_area.get_zoom_state(self._get_active_signals())
        self._redo_stack.append(current)
        state = self._undo_stack.pop()
        self._ignore_range_changed = True
        self._timer.stop()
        self._in_gesture = False
        self._pre_gesture_state = None
        self._plot_area.set_zoom_state(state, self._get_active_signals())
        self._ignore_range_changed = False
        self._stable_state = state

    def redo(self) -> None:
        """Re-apply the most recently undone zoom state."""
        if not self._redo_stack:
            return
        current = self._plot_area.get_zoom_state(self._get_active_signals())
        self._push_undo(current)
        state = self._redo_stack.pop()
        self._ignore_range_changed = True
        self._timer.stop()
        self._in_gesture = False
        self._pre_gesture_state = None
        self._plot_area.set_zoom_state(state, self._get_active_signals())
        self._ignore_range_changed = False
        self._stable_state = state

    def clear(self) -> None:
        """Clear both stacks and cancel any in-progress gesture (e.g. on file load)."""
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._stable_state = None
        self._in_gesture = False
        self._pre_gesture_state = None
        self._timer.stop()

    @property
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _on_range_changed(self) -> None:
        if self._ignore_range_changed:
            return
        if not self._in_gesture:
            # Gesture just started.  Use _stable_state (captured last time the view
            # was at rest) as the pre-gesture baseline — not the current state, which
            # has already been mutated by the time this handler fires.
            self._pre_gesture_state = self._stable_state
            self._in_gesture = True
        self._timer.start()  # reset debounce

    def _on_gesture_end(self) -> None:
        self._in_gesture = False
        if self._pre_gesture_state is not None:
            self._push_undo(self._pre_gesture_state)
            self._redo_stack.clear()
        self._pre_gesture_state = None
        # Refresh the stable state now that the view has come to rest.
        self._stable_state = self._plot_area.get_zoom_state(self._get_active_signals())

    def _push_undo(self, state) -> None:
        self._undo_stack.append(state)
        max_steps = self._get_max_steps()
        if len(self._undo_stack) > max_steps:
            self._undo_stack = self._undo_stack[-max_steps:]
