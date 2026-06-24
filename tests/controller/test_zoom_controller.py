"""Tests for ZoomController — pure unit tests, no QApplication needed."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from mdf_viewer.controller.zoom_controller import ZoomController
from mdf_viewer.view_model.zoom_state import ZoomState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _state(x=(0.0, 10.0), y_ranges=None) -> ZoomState:
    return ZoomState(x_range=x, y_ranges=y_ranges or {})


def _make_plot_area(x=(0.0, 10.0), y_ranges=None):
    pa = MagicMock()
    pa.range_changed = MagicMock()
    pa.range_changed.connect = MagicMock()
    pa.get_zoom_state.return_value = _state(x, y_ranges)
    return pa


def _make_ctrl(plot_area=None, active_signals=None, max_steps=10):
    timer = MagicMock()
    pa = plot_area or _make_plot_area()
    ctrl = ZoomController(
        plot_area=pa,
        get_active_signals=lambda: active_signals or [],
        get_max_steps=lambda: max_steps,
        _timer=timer,
    )
    return ctrl, pa, timer


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

def test_connects_range_changed_on_init():
    pa = _make_plot_area()
    ctrl, _, _ = _make_ctrl(plot_area=pa)
    pa.range_changed.connect.assert_called_once_with(ctrl._on_range_changed)


def test_initially_empty_stacks():
    ctrl, _, _ = _make_ctrl()
    assert not ctrl.can_undo
    assert not ctrl.can_redo


def test_stable_state_initially_none():
    ctrl, _, _ = _make_ctrl()
    assert ctrl._stable_state is None


# ---------------------------------------------------------------------------
# Gesture coalescing — stable_state design
# ---------------------------------------------------------------------------

def test_first_range_change_uses_stable_state_as_pre_gesture():
    """_pre_gesture_state must be the stable (pre-gesture) snapshot, not the
    already-mutated current state."""
    pa = _make_plot_area()
    ctrl, _, _ = _make_ctrl(plot_area=pa)
    pre = _state((1.0, 5.0))
    ctrl._stable_state = pre

    ctrl._on_range_changed()

    assert ctrl._pre_gesture_state is pre


def test_subsequent_range_changes_do_not_overwrite_pre_gesture_state():
    pa = _make_plot_area()
    ctrl, _, timer = _make_ctrl(plot_area=pa)
    ctrl._stable_state = _state((0.0, 10.0))
    ctrl._on_range_changed()
    first_pre = ctrl._pre_gesture_state

    ctrl._on_range_changed()

    assert ctrl._pre_gesture_state is first_pre
    assert timer.start.call_count == 2


def test_gesture_end_pushes_stable_state_to_undo():
    pa = _make_plot_area(x=(5.0, 15.0))  # current (post-gesture) state
    ctrl, _, _ = _make_ctrl(plot_area=pa)
    pre = _state((0.0, 10.0))
    ctrl._stable_state = pre

    ctrl._on_range_changed()
    ctrl._on_gesture_end()

    assert ctrl.can_undo
    assert ctrl._undo_stack[0] is pre


def test_gesture_end_refreshes_stable_state():
    pa = _make_plot_area(x=(5.0, 15.0))
    ctrl, _, _ = _make_ctrl(plot_area=pa)
    ctrl._stable_state = _state((0.0, 10.0))

    ctrl._on_range_changed()
    ctrl._on_gesture_end()

    # stable_state should now reflect the post-gesture position
    assert ctrl._stable_state.x_range == (5.0, 15.0)


def test_gesture_end_clears_redo_stack():
    ctrl, pa, _ = _make_ctrl()
    ctrl._stable_state = _state()
    ctrl._redo_stack.append(_state((99.0, 100.0)))

    ctrl._on_range_changed()
    ctrl._on_gesture_end()

    assert not ctrl.can_redo


def test_gesture_end_clears_pre_gesture_state():
    ctrl, _, _ = _make_ctrl()
    ctrl._stable_state = _state()
    ctrl._on_range_changed()
    ctrl._on_gesture_end()
    assert ctrl._pre_gesture_state is None


def test_gesture_end_with_no_stable_state_skips_push():
    """If stable_state is still None (first gesture ever), nothing is pushed."""
    ctrl, pa, _ = _make_ctrl()
    # _stable_state remains None

    ctrl._on_range_changed()
    ctrl._on_gesture_end()

    assert not ctrl.can_undo


def test_in_gesture_flag_cleared_on_gesture_end():
    ctrl, _, _ = _make_ctrl()
    ctrl._stable_state = _state()
    ctrl._on_range_changed()
    assert ctrl._in_gesture
    ctrl._on_gesture_end()
    assert not ctrl._in_gesture


# ---------------------------------------------------------------------------
# Undo / redo
# ---------------------------------------------------------------------------

def test_undo_restores_previous_state():
    pa = _make_plot_area(x=(0.0, 10.0))
    sig = MagicMock()
    ctrl, _, _ = _make_ctrl(plot_area=pa, active_signals=[sig])

    old_state = _state((0.0, 5.0), {sig: (0.0, 1.0)})
    ctrl._undo_stack.append(old_state)

    ctrl.undo()

    pa.set_zoom_state.assert_called_once_with(old_state, [sig])
    assert not ctrl.can_undo


def test_undo_saves_current_state_to_redo():
    pa = _make_plot_area(x=(0.0, 10.0))
    ctrl, _, _ = _make_ctrl(plot_area=pa)
    ctrl._undo_stack.append(_state((0.0, 5.0)))

    ctrl.undo()

    assert ctrl.can_redo
    assert ctrl._redo_stack[0].x_range == (0.0, 10.0)


def test_undo_updates_stable_state():
    pa = _make_plot_area()
    ctrl, _, _ = _make_ctrl(plot_area=pa)
    restored = _state((0.0, 5.0))
    ctrl._undo_stack.append(restored)

    ctrl.undo()

    assert ctrl._stable_state is restored


def test_undo_when_empty_is_noop():
    pa = _make_plot_area()
    ctrl, _, _ = _make_ctrl(plot_area=pa)
    ctrl.undo()
    pa.set_zoom_state.assert_not_called()


def test_redo_restores_undone_state():
    pa = _make_plot_area(x=(0.0, 10.0))
    ctrl, _, _ = _make_ctrl(plot_area=pa)
    redo_state = _state((5.0, 15.0))
    ctrl._redo_stack.append(redo_state)

    ctrl.redo()

    pa.set_zoom_state.assert_called_once_with(redo_state, [])


def test_redo_saves_current_state_to_undo():
    pa = _make_plot_area(x=(0.0, 10.0))
    ctrl, _, _ = _make_ctrl(plot_area=pa)
    ctrl._redo_stack.append(_state((5.0, 15.0)))

    ctrl.redo()

    assert ctrl.can_undo
    assert ctrl._undo_stack[0].x_range == (0.0, 10.0)


def test_redo_updates_stable_state():
    pa = _make_plot_area()
    ctrl, _, _ = _make_ctrl(plot_area=pa)
    redone = _state((5.0, 15.0))
    ctrl._redo_stack.append(redone)

    ctrl.redo()

    assert ctrl._stable_state is redone


def test_redo_when_empty_is_noop():
    pa = _make_plot_area()
    ctrl, _, _ = _make_ctrl(plot_area=pa)
    ctrl.redo()
    pa.set_zoom_state.assert_not_called()


def test_undo_suppresses_range_changed():
    """set_zoom_state fires range_changed; undo must not treat that as a new gesture."""
    pa = _make_plot_area(x=(0.0, 10.0))
    ctrl, _, _ = _make_ctrl(plot_area=pa)
    ctrl._undo_stack.append(_state((0.0, 5.0)))

    def fake_set_zoom_state(state, signals):
        ctrl._on_range_changed()

    pa.set_zoom_state.side_effect = fake_set_zoom_state
    ctrl.undo()

    assert not ctrl._in_gesture
    assert ctrl._pre_gesture_state is None


def test_redo_suppresses_range_changed():
    pa = _make_plot_area(x=(0.0, 10.0))
    ctrl, _, _ = _make_ctrl(plot_area=pa)
    ctrl._redo_stack.append(_state((5.0, 15.0)))

    def fake_set_zoom_state(state, signals):
        ctrl._on_range_changed()

    pa.set_zoom_state.side_effect = fake_set_zoom_state
    ctrl.redo()

    assert not ctrl._in_gesture
    assert ctrl._pre_gesture_state is None


# ---------------------------------------------------------------------------
# Discrete action guard
# ---------------------------------------------------------------------------

def test_before_discrete_action_pushes_current_state_to_undo():
    pa = _make_plot_area(x=(0.0, 10.0))
    ctrl, _, timer = _make_ctrl(plot_area=pa)
    ctrl._redo_stack.append(_state((99.0, 100.0)))

    ctrl.before_discrete_action()

    assert ctrl.can_undo
    assert ctrl._undo_stack[0].x_range == (0.0, 10.0)
    assert not ctrl.can_redo
    timer.stop.assert_called()


def test_before_discrete_action_suppresses_range_changed():
    pa = _make_plot_area()
    ctrl, _, _ = _make_ctrl(plot_area=pa)
    ctrl.before_discrete_action()

    ctrl._on_range_changed()

    assert not ctrl._in_gesture
    assert ctrl._pre_gesture_state is None


def test_after_discrete_action_restores_range_changed_and_updates_stable():
    pa = _make_plot_area(x=(5.0, 15.0))
    ctrl, _, _ = _make_ctrl(plot_area=pa)
    ctrl.before_discrete_action()
    ctrl.after_discrete_action()

    assert not ctrl._ignore_range_changed
    assert ctrl._stable_state.x_range == (5.0, 15.0)

    # Now range changes should be captured as a new gesture
    ctrl._on_range_changed()
    assert ctrl._in_gesture


# ---------------------------------------------------------------------------
# Max history depth
# ---------------------------------------------------------------------------

def test_max_steps_1_keeps_only_last_entry():
    ctrl, _, _ = _make_ctrl(max_steps=1)
    ctrl._push_undo(_state((0.0, 5.0)))
    ctrl._push_undo(_state((5.0, 10.0)))

    assert len(ctrl._undo_stack) == 1
    assert ctrl._undo_stack[0].x_range == (5.0, 10.0)


def test_max_steps_3_trims_oldest():
    ctrl, _, _ = _make_ctrl(max_steps=3)
    states = [_state((float(i), float(i + 1))) for i in range(5)]
    for s in states:
        ctrl._push_undo(s)

    assert len(ctrl._undo_stack) == 3
    assert ctrl._undo_stack == states[-3:]


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------

def test_clear_empties_both_stacks_and_resets_state():
    ctrl, _, timer = _make_ctrl()
    ctrl._undo_stack.append(_state((0.0, 1.0)))
    ctrl._redo_stack.append(_state((1.0, 2.0)))
    ctrl._stable_state = _state((2.0, 3.0))
    ctrl._in_gesture = True
    ctrl._pre_gesture_state = _state((3.0, 4.0))

    ctrl.clear()

    assert not ctrl.can_undo
    assert not ctrl.can_redo
    assert ctrl._stable_state is None
    assert not ctrl._in_gesture
    assert ctrl._pre_gesture_state is None
    timer.stop.assert_called()
