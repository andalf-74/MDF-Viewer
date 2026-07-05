"""Tests for CursorStripesView — cross-stripe cursor/label/delta-line behavior.

Covers what moved out of CursorView (labels, nearest-cursor tracking) plus
what's genuinely new for multi-stripe support: lockstep cursor-line dragging
across stripes (REQ-PLOT-182), delta-time line routed to only the active
stripe with independently-remembered positions (REQ-PLOT-105/183), and
stripe add/remove lifecycle. Uses real PlotStripe instances (not a stub) so
tests exercise the actual register_drag_claimant/plot_item wiring.
"""

from __future__ import annotations

import numpy as np
import pytest
import pyqtgraph as pg
from PyQt6.QtGui import QColor
from pytestqt.qtbot import QtBot

from mdf_viewer.controller.cursor_controller import CursorMode
from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.view.cursors import CursorStripesView
from mdf_viewer.view.plot_stripe import PlotStripe
from mdf_viewer.view_model.active_signal import ActiveSignal


def _make_active(name: str = "sig", color: QColor | None = None) -> ActiveSignal:
    t = np.linspace(0.0, 1.0, 101)
    data = SignalData(timestamps=t, samples=np.sin(2 * np.pi * t))
    meta = SignalMetadata(name=name, unit="V", group_index=0, channel_index=0)
    return ActiveSignal(data=data, metadata=meta, color=color or QColor(255, 85, 85))


def _set_view_range(stripe: PlotStripe, x: tuple, y: tuple) -> None:
    """Set a stripe's ViewBox range with no padding so viewRange() matches exactly."""
    stripe.plot_item.vb.setRange(xRange=x, yRange=y, padding=0)


@pytest.fixture()
def stripe(qtbot: QtBot) -> PlotStripe:
    s = PlotStripe()
    qtbot.addWidget(s)
    return s


@pytest.fixture()
def stripe2(qtbot: QtBot) -> PlotStripe:
    s = PlotStripe()
    qtbot.addWidget(s)
    return s


@pytest.fixture()
def sv(stripe: PlotStripe) -> CursorStripesView:
    v = CursorStripesView()
    v.add_stripe(stripe)
    return v


# ---------------------------------------------------------------------------
# Construction / stripe lifecycle
# ---------------------------------------------------------------------------

def test_no_labels_initially(sv: CursorStripesView) -> None:
    assert len(sv._labels) == 0


def test_add_stripe_registers_drag_claimant(sv: CursorStripesView, stripe: PlotStripe) -> None:
    view = sv._per_stripe[stripe]
    assert view in stripe._drag_claimants


def test_add_stripe_applies_current_mode_and_positions(
    sv: CursorStripesView, stripe2: PlotStripe
) -> None:
    sv.apply_mode(CursorMode.TWO, [0.3, 0.7])
    sv.add_stripe(stripe2)
    view2 = sv._per_stripe[stripe2]
    assert view2._lines[0].value() == pytest.approx(0.3)
    assert view2._lines[1].value() == pytest.approx(0.7)
    assert view2._lines[0].isVisible()
    assert view2._lines[1].isVisible()


def test_first_added_stripe_becomes_active(sv: CursorStripesView, stripe: PlotStripe) -> None:
    assert sv._active_stripe is stripe


def test_remove_stripe_cleans_up_bookkeeping(
    sv: CursorStripesView, stripe: PlotStripe
) -> None:
    sv.remove_stripe(stripe)
    assert stripe not in sv._per_stripe
    assert stripe not in sv._mouse_proxies


def test_remove_active_stripe_reassigns_active(
    sv: CursorStripesView, stripe: PlotStripe, stripe2: PlotStripe
) -> None:
    sv.add_stripe(stripe2)
    sv.remove_stripe(stripe)
    assert sv._active_stripe is stripe2


def test_set_active_stripe_updates_state(sv: CursorStripesView, stripe2: PlotStripe) -> None:
    sv.add_stripe(stripe2)
    sv.set_active_stripe(stripe2)
    assert sv._active_stripe is stripe2


# ---------------------------------------------------------------------------
# update_labels (lifted from CursorView, unchanged logic)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-080")
def test_update_labels_creates_label_for_signal(
    sv: CursorStripesView, stripe: PlotStripe
) -> None:
    active = _make_active()
    stripe.add_signal(active)
    sv.apply_mode(CursorMode.ONE, [0.25, 0.75])
    sv.update_labels([active], [0.25, 0.75], CursorMode.ONE)
    assert len(sv._labels) == 1


@pytest.mark.requirement("REQ-PLOT-080")
def test_update_labels_two_mode_creates_two_per_signal(
    sv: CursorStripesView, stripe: PlotStripe
) -> None:
    active = _make_active()
    stripe.add_signal(active)
    sv.apply_mode(CursorMode.TWO, [0.25, 0.75])
    sv.update_labels([active], [0.25, 0.75], CursorMode.TWO)
    assert len(sv._labels) == 2


@pytest.mark.requirement("REQ-PLOT-080")
def test_update_labels_multiple_signals(sv: CursorStripesView, stripe: PlotStripe) -> None:
    sigs = [_make_active(f"s{i}") for i in range(3)]
    for s in sigs:
        stripe.add_signal(s)
    sv.apply_mode(CursorMode.ONE, [0.5, 0.8])
    sv.update_labels(sigs, [0.5, 0.8], CursorMode.ONE)
    assert len(sv._labels) == 3


@pytest.mark.requirement("REQ-PLOT-080")
def test_update_labels_removes_stale_labels(sv: CursorStripesView, stripe: PlotStripe) -> None:
    sigs = [_make_active("a"), _make_active("b")]
    for s in sigs:
        stripe.add_signal(s)
    sv.apply_mode(CursorMode.ONE, [0.5, 0.8])
    sv.update_labels(sigs, [0.5, 0.8], CursorMode.ONE)
    assert len(sv._labels) == 2
    sv.update_labels(sigs[:1], [0.5, 0.8], CursorMode.ONE)
    assert len(sv._labels) == 1


@pytest.mark.requirement("REQ-PLOT-082")
def test_update_labels_out_of_range_hides_label(
    sv: CursorStripesView, stripe: PlotStripe
) -> None:
    active = _make_active()
    stripe.add_signal(active)
    sv.apply_mode(CursorMode.ONE, [5.0, 6.0])
    sv.update_labels([active], [5.0, 6.0], CursorMode.ONE)
    assert all(not lbl.isVisible() for lbl, _ in sv._labels.values())


def test_update_labels_skips_signal_without_view_box(sv: CursorStripesView) -> None:
    active = _make_active()  # never added to a stripe -> view_box is None
    sv.apply_mode(CursorMode.ONE, [0.25, 0.75])
    sv.update_labels([active], [0.25, 0.75], CursorMode.ONE)
    assert len(sv._labels) == 0


@pytest.mark.requirement("REQ-PLOT-080")
def test_labels_still_correct_for_signal_in_second_stripe(
    sv: CursorStripesView, stripe2: PlotStripe
) -> None:
    """Labels use active.view_box directly, so they're correct regardless of
    which stripe actually owns the signal — this is the whole reason label
    logic didn't need to change at all for multi-stripe support."""
    sv.add_stripe(stripe2)
    active = _make_active()
    stripe2.add_signal(active)
    sv.apply_mode(CursorMode.ONE, [0.25, 0.75])
    sv.update_labels([active], [0.25, 0.75], CursorMode.ONE)
    lbl, vb = sv._labels[(0, active)]
    assert vb is active.view_box


# ---------------------------------------------------------------------------
# Label visibility rules / nearest-cursor tracking
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-080")
def test_one_mode_label_always_visible(sv: CursorStripesView, stripe: PlotStripe) -> None:
    active = _make_active()
    stripe.add_signal(active)
    sv.apply_mode(CursorMode.ONE, [0.25, 0.75])
    sv.update_labels([active], [0.25, 0.75], CursorMode.ONE)
    lbl, _ = sv._labels[(0, active)]
    assert lbl.isVisible()


@pytest.mark.requirement("REQ-PLOT-070")
def test_hidden_mode_labels_not_visible(sv: CursorStripesView, stripe: PlotStripe) -> None:
    active = _make_active()
    stripe.add_signal(active)
    sv.apply_mode(CursorMode.ONE, [0.25, 0.75])
    sv.update_labels([active], [0.25, 0.75], CursorMode.ONE)
    sv.apply_mode(CursorMode.HIDDEN, [0.25, 0.75])
    for lbl, _ in sv._labels.values():
        assert not lbl.isVisible()


@pytest.mark.requirement("REQ-PLOT-081")
def test_nearest_cursor_defaults_to_0(sv: CursorStripesView) -> None:
    assert sv._nearest_cursor == 0


@pytest.mark.requirement("REQ-PLOT-081")
def test_mouse_move_nearer_to_cursor_1_updates_nearest(
    sv: CursorStripesView, stripe: PlotStripe
) -> None:
    _set_view_range(stripe, (0.0, 10.0), (-1.0, 1.0))
    sv.apply_mode(CursorMode.TWO, [2.0, 8.0])
    scene_pos = stripe.plot_item.vb.mapViewToScene(pg.Point(9.0, 0.0))
    sv._on_mouse_moved(stripe, (scene_pos,))
    assert sv._nearest_cursor == 1


@pytest.mark.requirement("REQ-PLOT-081")
def test_only_nearest_cursor_label_visible_in_two_mode(
    sv: CursorStripesView, stripe: PlotStripe
) -> None:
    _set_view_range(stripe, (0.0, 1.0), (-1.0, 1.0))
    active = _make_active()
    stripe.add_signal(active)
    sv.apply_mode(CursorMode.TWO, [0.2, 0.8])
    sv.update_labels([active], [0.2, 0.8], CursorMode.TWO)
    scene_pos = stripe.plot_item.vb.mapViewToScene(pg.Point(0.9, 0.0))
    sv._on_mouse_moved(stripe, (scene_pos,))
    lbl0, _ = sv._labels[(0, active)]
    lbl1, _ = sv._labels[(1, active)]
    assert not lbl0.isVisible()
    assert lbl1.isVisible()


@pytest.mark.requirement("REQ-PLOT-081")
def test_mouse_move_ignored_outside_two_mode(
    sv: CursorStripesView, stripe: PlotStripe
) -> None:
    _set_view_range(stripe, (0.0, 10.0), (-1.0, 1.0))
    sv.apply_mode(CursorMode.ONE, [2.0, 8.0])
    scene_pos = stripe.plot_item.vb.mapViewToScene(pg.Point(9.0, 0.0))
    sv._on_mouse_moved(stripe, (scene_pos,))
    assert sv._nearest_cursor == 0


@pytest.mark.requirement("REQ-PLOT-081")
def test_mouse_move_over_second_stripe_also_updates_nearest(
    sv: CursorStripesView, stripe2: PlotStripe
) -> None:
    sv.add_stripe(stripe2)
    _set_view_range(stripe2, (0.0, 10.0), (-1.0, 1.0))
    sv.apply_mode(CursorMode.TWO, [2.0, 8.0])
    scene_pos = stripe2.plot_item.vb.mapViewToScene(pg.Point(9.0, 0.0))
    sv._on_mouse_moved(stripe2, (scene_pos,))
    assert sv._nearest_cursor == 1


# ---------------------------------------------------------------------------
# remove_labels_for / clear_labels / recolor_labels
# ---------------------------------------------------------------------------

def test_remove_labels_for_removes_only_that_signal(
    sv: CursorStripesView, stripe: PlotStripe
) -> None:
    a, b = _make_active("a"), _make_active("b")
    stripe.add_signal(a)
    stripe.add_signal(b)
    sv.apply_mode(CursorMode.ONE, [0.5, 0.8])
    sv.update_labels([a, b], [0.5, 0.8], CursorMode.ONE)
    sv.remove_labels_for(a)
    remaining = [k[1] for k in sv._labels]
    assert not any(r is a for r in remaining)
    assert any(r is b for r in remaining)


def test_clear_labels_removes_all(sv: CursorStripesView, stripe: PlotStripe) -> None:
    sigs = [_make_active(f"s{i}") for i in range(3)]
    for s in sigs:
        stripe.add_signal(s)
    sv.apply_mode(CursorMode.ONE, [0.5, 0.8])
    sv.update_labels(sigs, [0.5, 0.8], CursorMode.ONE)
    sv.clear_labels()
    assert len(sv._labels) == 0


def test_recolor_labels_updates_color(sv: CursorStripesView, stripe: PlotStripe) -> None:
    active = _make_active()
    stripe.add_signal(active)
    sv.apply_mode(CursorMode.ONE, [0.25, 0.75])
    sv.update_labels([active], [0.25, 0.75], CursorMode.ONE)
    sv.recolor_labels(active, QColor(1, 2, 3))
    lbl, _ = sv._labels[(0, active)]
    assert lbl.color == QColor(1, 2, 3)


# ---------------------------------------------------------------------------
# Cross-stripe lockstep cursor dragging (REQ-PLOT-182)
# ---------------------------------------------------------------------------

def test_dragging_line_in_one_stripe_moves_sibling(
    sv: CursorStripesView, stripe: PlotStripe, stripe2: PlotStripe
) -> None:
    sv.add_stripe(stripe2)
    sv.apply_mode(CursorMode.ONE, [0.0, 0.0])
    view1 = sv._per_stripe[stripe]
    view2 = sv._per_stripe[stripe2]

    view1._lines[0].setValue(0.42)

    assert view2._lines[0].value() == pytest.approx(0.42)


def test_dragging_line_emits_cursor_moved_exactly_once(
    sv: CursorStripesView, stripe: PlotStripe, stripe2: PlotStripe, qtbot: QtBot
) -> None:
    sv.add_stripe(stripe2)
    sv.apply_mode(CursorMode.ONE, [0.0, 0.0])
    view1 = sv._per_stripe[stripe]

    received: list = []
    sv.cursor_moved.connect(lambda idx, x: received.append((idx, x)))
    view1._lines[0].setValue(0.42)

    assert received == [(0, pytest.approx(0.42))]


def test_dragging_line_updates_composite_positions(
    sv: CursorStripesView, stripe: PlotStripe, stripe2: PlotStripe
) -> None:
    sv.add_stripe(stripe2)
    sv.apply_mode(CursorMode.TWO, [0.1, 0.9])
    view1 = sv._per_stripe[stripe]
    view1._lines[1].setValue(0.55)
    assert sv._positions == [pytest.approx(0.1), pytest.approx(0.55)]


def test_three_stripes_all_stay_in_lockstep(qtbot: QtBot) -> None:
    sv = CursorStripesView()
    stripes = [PlotStripe() for _ in range(3)]
    for s in stripes:
        qtbot.addWidget(s)
        sv.add_stripe(s)
    sv.apply_mode(CursorMode.ONE, [0.0, 0.0])

    sv._per_stripe[stripes[1]]._lines[0].setValue(0.7)

    for s in stripes:
        assert sv._per_stripe[s]._lines[0].value() == pytest.approx(0.7)


# ---------------------------------------------------------------------------
# Delta-time line: active-stripe-only, independent per-stripe memory (REQ-PLOT-105/183)
# ---------------------------------------------------------------------------

def test_update_delta_time_shown_only_in_active_stripe(
    sv: CursorStripesView, stripe: PlotStripe, stripe2: PlotStripe
) -> None:
    sv.add_stripe(stripe2)
    sv.set_active_stripe(stripe)
    sv.update_delta_time(0.0, 1.0, "1.0 s", y_pos=0.5, show=True, color=(1, 2, 3))

    view1 = sv._per_stripe[stripe]
    view2 = sv._per_stripe[stripe2]
    assert view1._delta_line.isVisible()
    assert not view2._delta_line.isVisible()


def test_update_delta_time_switches_stripe_on_active_change(
    sv: CursorStripesView, stripe: PlotStripe, stripe2: PlotStripe
) -> None:
    sv.add_stripe(stripe2)
    sv.set_active_stripe(stripe)
    sv.update_delta_time(0.0, 1.0, "1.0 s", y_pos=0.5, show=True, color=(1, 2, 3))

    sv.set_active_stripe(stripe2)
    sv.update_delta_time(0.0, 1.0, "1.0 s", y_pos=0.3, show=True, color=(1, 2, 3))

    view1 = sv._per_stripe[stripe]
    view2 = sv._per_stripe[stripe2]
    assert not view1._delta_line.isVisible()
    assert view2._delta_line.isVisible()


def test_update_delta_time_show_false_hides_everywhere(
    sv: CursorStripesView, stripe: PlotStripe, stripe2: PlotStripe
) -> None:
    sv.add_stripe(stripe2)
    sv.set_active_stripe(stripe)
    sv.update_delta_time(0.0, 1.0, "1.0 s", y_pos=0.5, show=True, color=(1, 2, 3))
    sv.update_delta_time(0.0, 1.0, "", y_pos=None, show=False, color=(1, 2, 3))

    assert not sv._per_stripe[stripe]._delta_line.isVisible()
    assert not sv._per_stripe[stripe2]._delta_line.isVisible()
