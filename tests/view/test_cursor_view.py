"""Tests for CursorView — requires QApplication via qtbot."""

from __future__ import annotations

import numpy as np
import pytest
import pyqtgraph as pg
from PyQt6.QtGui import QColor
from pytestqt.qtbot import QtBot

from mdf_viewer.controller.cursor_controller import CursorMode
from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.view.cursors import CursorView
from mdf_viewer.view_model.active_signal import ActiveSignal


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

def _make_active(name: str = "sig", color: QColor | None = None) -> ActiveSignal:
    t = np.linspace(0.0, 1.0, 101)
    data = SignalData(timestamps=t, samples=np.sin(2 * np.pi * t))
    meta = SignalMetadata(name=name, unit="V", group_index=0, channel_index=0)
    return ActiveSignal(data=data, metadata=meta, color=color or QColor(255, 85, 85))


def _make_active_with_vb(
    pw: pg.PlotWidget,
    name: str = "sig",
    color: QColor | None = None,
) -> ActiveSignal:
    """Create an ActiveSignal with a real ViewBox attached (needed for label tests)."""
    active = _make_active(name, color)
    vb = pg.ViewBox()
    pw.getPlotItem().scene().addItem(vb)
    active.view_box = vb
    return active


@pytest.fixture()
def pw(qtbot: QtBot) -> pg.PlotWidget:
    w = pg.PlotWidget()
    qtbot.addWidget(w)
    return w


@pytest.fixture()
def cv(pw: pg.PlotWidget) -> CursorView:
    # Keep pw alive via the fixture parameter so the C++ PlotItem/ViewBox
    # are not destroyed before the test finishes.
    return CursorView(pw.getPlotItem())


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

def test_two_lines_added_to_plot(cv: CursorView) -> None:
    assert len(cv._lines) == 2


def test_lines_hidden_initially(cv: CursorView) -> None:
    assert not cv._lines[0].isVisible()
    assert not cv._lines[1].isVisible()


def test_no_labels_initially(cv: CursorView) -> None:
    assert len(cv._labels) == 0


# ---------------------------------------------------------------------------
# apply_mode
# ---------------------------------------------------------------------------

def test_apply_mode_one_shows_line_0(cv: CursorView) -> None:
    cv.apply_mode(CursorMode.ONE, [0.3, 0.6])
    assert cv._lines[0].isVisible()
    assert not cv._lines[1].isVisible()


def test_apply_mode_two_shows_both_lines(cv: CursorView) -> None:
    cv.apply_mode(CursorMode.TWO, [0.3, 0.6])
    assert cv._lines[0].isVisible()
    assert cv._lines[1].isVisible()


def test_apply_mode_hidden_hides_both(cv: CursorView) -> None:
    cv.apply_mode(CursorMode.TWO, [0.3, 0.6])
    cv.apply_mode(CursorMode.HIDDEN, [0.3, 0.6])
    assert not cv._lines[0].isVisible()
    assert not cv._lines[1].isVisible()


def test_apply_mode_sets_line_positions(cv: CursorView) -> None:
    cv.apply_mode(CursorMode.TWO, [0.25, 0.75])
    assert cv._lines[0].value() == pytest.approx(0.25)
    assert cv._lines[1].value() == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# update_labels
# ---------------------------------------------------------------------------

def test_update_labels_creates_label_for_signal(
    cv: CursorView, pw: pg.PlotWidget
) -> None:
    active = _make_active_with_vb(pw)
    cv.apply_mode(CursorMode.ONE, [0.25, 0.75])
    cv.update_labels([active], [0.25, 0.75], CursorMode.ONE)
    assert len(cv._labels) == 1


def test_update_labels_two_mode_creates_two_per_signal(
    cv: CursorView, pw: pg.PlotWidget
) -> None:
    active = _make_active_with_vb(pw)
    cv.apply_mode(CursorMode.TWO, [0.25, 0.75])
    cv.update_labels([active], [0.25, 0.75], CursorMode.TWO)
    assert len(cv._labels) == 2


def test_update_labels_multiple_signals(
    cv: CursorView, pw: pg.PlotWidget
) -> None:
    sigs = [_make_active_with_vb(pw, f"s{i}") for i in range(3)]
    cv.apply_mode(CursorMode.ONE, [0.5, 0.8])
    cv.update_labels(sigs, [0.5, 0.8], CursorMode.ONE)
    assert len(cv._labels) == 3


def test_update_labels_removes_stale_labels(
    cv: CursorView, pw: pg.PlotWidget
) -> None:
    sigs = [_make_active_with_vb(pw, "a"), _make_active_with_vb(pw, "b")]
    cv.apply_mode(CursorMode.ONE, [0.5, 0.8])
    cv.update_labels(sigs, [0.5, 0.8], CursorMode.ONE)
    assert len(cv._labels) == 2
    cv.update_labels(sigs[:1], [0.5, 0.8], CursorMode.ONE)
    assert len(cv._labels) == 1


def test_update_labels_out_of_range_hides_label(
    cv: CursorView, pw: pg.PlotWidget
) -> None:
    active = _make_active_with_vb(pw)
    cv.apply_mode(CursorMode.ONE, [5.0, 6.0])
    cv.update_labels([active], [5.0, 6.0], CursorMode.ONE)
    # Cursor at x=5.0, signal only covers [0,1] → no label created
    assert all(not lbl.isVisible() for lbl, _ in cv._labels.values())


def test_update_labels_skips_signal_without_view_box(cv: CursorView) -> None:
    # Signal with view_box=None (not yet added to plot) should be skipped.
    active = _make_active()  # view_box is None
    cv.apply_mode(CursorMode.ONE, [0.25, 0.75])
    cv.update_labels([active], [0.25, 0.75], CursorMode.ONE)
    assert len(cv._labels) == 0


# ---------------------------------------------------------------------------
# Label visibility rules
# ---------------------------------------------------------------------------

def test_one_mode_label_always_visible(
    cv: CursorView, pw: pg.PlotWidget
) -> None:
    active = _make_active_with_vb(pw)
    cv.apply_mode(CursorMode.ONE, [0.25, 0.75])
    cv.update_labels([active], [0.25, 0.75], CursorMode.ONE)
    lbl, _ = cv._labels[(0, active)]
    assert lbl.isVisible()


def test_hidden_mode_labels_not_visible(
    cv: CursorView, pw: pg.PlotWidget
) -> None:
    active = _make_active_with_vb(pw)
    cv.apply_mode(CursorMode.ONE, [0.25, 0.75])
    cv.update_labels([active], [0.25, 0.75], CursorMode.ONE)
    cv.apply_mode(CursorMode.HIDDEN, [0.25, 0.75])
    for lbl, _ in cv._labels.values():
        assert not lbl.isVisible()


# ---------------------------------------------------------------------------
# remove_labels_for / clear_labels
# ---------------------------------------------------------------------------

def test_remove_labels_for_removes_only_that_signal(
    cv: CursorView, pw: pg.PlotWidget
) -> None:
    a = _make_active_with_vb(pw, "a")
    b = _make_active_with_vb(pw, "b")
    cv.apply_mode(CursorMode.ONE, [0.5, 0.8])
    cv.update_labels([a, b], [0.5, 0.8], CursorMode.ONE)
    cv.remove_labels_for(a)
    remaining = [k[1] for k in cv._labels]
    assert not any(r is a for r in remaining)
    assert any(r is b for r in remaining)


def test_clear_labels_removes_all(
    cv: CursorView, pw: pg.PlotWidget
) -> None:
    sigs = [_make_active_with_vb(pw, f"s{i}") for i in range(3)]
    cv.apply_mode(CursorMode.ONE, [0.5, 0.8])
    cv.update_labels(sigs, [0.5, 0.8], CursorMode.ONE)
    cv.clear_labels()
    assert len(cv._labels) == 0


# ---------------------------------------------------------------------------
# cursor_moved signal
# ---------------------------------------------------------------------------

def test_cursor_moved_emitted_on_line_move(
    cv: CursorView, qtbot: QtBot
) -> None:
    with qtbot.waitSignal(cv.cursor_moved, timeout=500) as blocker:
        cv._lines[0].setValue(0.42)
    assert blocker.args[0] == 0
    assert blocker.args[1] == pytest.approx(0.42)


# ---------------------------------------------------------------------------
# Chevron indicators — off-screen cursor / delta-time line
# ---------------------------------------------------------------------------

def _set_view_range(pw: pg.PlotWidget, x: tuple, y: tuple) -> None:
    """Set the ViewBox range with no padding so viewRange() matches exactly."""
    pw.getViewBox().setRange(xRange=x, yRange=y, padding=0)


def test_chevrons_created(cv: CursorView) -> None:
    assert len(cv._c_chevrons) == 2
    assert cv._dt_chevron is not None


def test_chevrons_hidden_initially(cv: CursorView) -> None:
    assert not cv._c_chevrons[0].isVisible()
    assert not cv._c_chevrons[1].isVisible()
    assert not cv._dt_chevron.isVisible()


def test_cursor_chevron_hidden_when_mode_is_hidden(
    cv: CursorView, pw: pg.PlotWidget
) -> None:
    _set_view_range(pw, (0.0, 10.0), (-1.0, 1.0))
    cv._lines[0].setValue(-5.0)  # off-screen left
    cv._update_chevrons()
    assert not cv._c_chevrons[0].isVisible()


def test_cursor_chevron_left_shown_when_off_screen(
    cv: CursorView, pw: pg.PlotWidget
) -> None:
    _set_view_range(pw, (0.0, 10.0), (-1.0, 1.0))
    cv.apply_mode(CursorMode.ONE, [-5.0, 7.5])
    assert cv._c_chevrons[0].isVisible()
    assert cv._c_chevrons[0].toPlainText() == "<"


def test_cursor_chevron_right_shown_when_off_screen(
    cv: CursorView, pw: pg.PlotWidget
) -> None:
    _set_view_range(pw, (0.0, 10.0), (-1.0, 1.0))
    cv.apply_mode(CursorMode.ONE, [99.0, 7.5])
    assert cv._c_chevrons[0].isVisible()
    assert cv._c_chevrons[0].toPlainText() == ">"


def test_cursor_chevron_hidden_when_on_screen(
    cv: CursorView, pw: pg.PlotWidget
) -> None:
    _set_view_range(pw, (0.0, 10.0), (-1.0, 1.0))
    cv.apply_mode(CursorMode.ONE, [5.0, 7.5])
    assert not cv._c_chevrons[0].isVisible()


def test_cursor_1_chevron_hidden_in_one_mode(
    cv: CursorView, pw: pg.PlotWidget
) -> None:
    _set_view_range(pw, (0.0, 10.0), (-1.0, 1.0))
    cv.apply_mode(CursorMode.ONE, [5.0, 99.0])  # cursor 1 off-screen
    assert not cv._c_chevrons[1].isVisible()


def test_both_cursors_off_screen_same_side(
    cv: CursorView, pw: pg.PlotWidget
) -> None:
    _set_view_range(pw, (0.0, 10.0), (-1.0, 1.0))
    cv.apply_mode(CursorMode.TWO, [-3.0, -1.0])
    assert cv._c_chevrons[0].isVisible()
    assert cv._c_chevrons[1].isVisible()
    # Stacked: different Y positions
    assert cv._c_chevrons[0].pos().y() != cv._c_chevrons[1].pos().y()


def test_delta_chevron_shown_above(cv: CursorView, pw: pg.PlotWidget) -> None:
    _set_view_range(pw, (0.0, 10.0), (-1.0, 1.0))
    cv.apply_mode(CursorMode.TWO, [2.5, 7.5])
    cv._cached_delta_y = 5.0   # above y_max = 1.0
    cv._cached_delta_show = True
    cv._cached_delta_color = (200, 200, 200)
    cv._update_chevrons()
    assert cv._dt_chevron.isVisible()
    assert cv._dt_chevron.toPlainText() == "^"


def test_delta_chevron_shown_below(cv: CursorView, pw: pg.PlotWidget) -> None:
    _set_view_range(pw, (0.0, 10.0), (-1.0, 1.0))
    cv.apply_mode(CursorMode.TWO, [2.5, 7.5])
    cv._cached_delta_y = -5.0  # below y_min = -1.0
    cv._cached_delta_show = True
    cv._cached_delta_color = (200, 200, 200)
    cv._update_chevrons()
    assert cv._dt_chevron.isVisible()
    assert cv._dt_chevron.toPlainText() == "v"


def test_delta_chevron_hidden_when_on_screen(
    cv: CursorView, pw: pg.PlotWidget
) -> None:
    _set_view_range(pw, (0.0, 10.0), (-1.0, 1.0))
    cv.apply_mode(CursorMode.TWO, [2.5, 7.5])
    cv._cached_delta_y = 0.0   # within range
    cv._cached_delta_show = True
    cv._cached_delta_color = (200, 200, 200)
    cv._update_chevrons()
    assert not cv._dt_chevron.isVisible()


def test_delta_chevron_hidden_when_show_false(
    cv: CursorView, pw: pg.PlotWidget
) -> None:
    _set_view_range(pw, (0.0, 10.0), (-1.0, 1.0))
    cv.apply_mode(CursorMode.TWO, [2.5, 7.5])
    cv._cached_delta_y = 5.0
    cv._cached_delta_show = False
    cv._update_chevrons()
    assert not cv._dt_chevron.isVisible()


def test_cursor_fetch_signal_emitted(cv: CursorView, qtbot: QtBot) -> None:
    # Simulate a click by calling the callback with a dummy scene position.
    # The real conversion (scenePos → data-X) needs a live scene, so we test
    # that the signal fires and carries the cursor index as its first arg.
    from PyQt6.QtCore import QPointF
    with qtbot.waitSignal(cv.cursor_fetch_requested, timeout=500) as blocker:
        cv._c_chevrons[0]._clicked_cb(QPointF(0.0, 0.0))
    assert blocker.args[0] == 0  # cursor index


def test_delta_fetch_signal_emitted(cv: CursorView, qtbot: QtBot) -> None:
    from PyQt6.QtCore import QPointF
    with qtbot.waitSignal(cv.delta_fetch_requested, timeout=500):
        cv._dt_chevron._clicked_cb(QPointF(0.0, 0.0))


# ---------------------------------------------------------------------------
# DragClaimant protocol (registered with PlotArea.register_drag_claimant)
# ---------------------------------------------------------------------------

def test_hit_test_misses_when_no_line_visible(cv: CursorView, pw: pg.PlotWidget) -> None:
    from PyQt6.QtCore import QPointF
    assert cv.hit_test(QPointF(0.0, 0.0)) is None


def test_hit_test_hits_visible_cursor_line(cv: CursorView, pw: pg.PlotWidget) -> None:
    _set_view_range(pw, (0.0, 10.0), (-1.0, 1.0))
    cv.apply_mode(CursorMode.ONE, [5.0, 7.5])
    scene_pos = cv._lines[0].mapToScene(cv._lines[0].boundingRect().center())
    assert cv.hit_test(scene_pos) is cv._lines[0]


def test_hit_test_hits_visible_delta_line(cv: CursorView, pw: pg.PlotWidget) -> None:
    _set_view_range(pw, (0.0, 10.0), (-1.0, 1.0))
    cv.apply_mode(CursorMode.TWO, [2.5, 7.5])
    cv.update_delta_time(2.5, 7.5, "1.0 s", y_pos=0.0, show=True, color=(200, 200, 200))
    scene_pos = cv._delta_line.mapToScene(cv._delta_line.boundingRect().center())
    assert cv.hit_test(scene_pos) is cv._delta_line


def test_on_move_drives_line_value_directly(cv: CursorView, pw: pg.PlotWidget) -> None:
    _set_view_range(pw, (0.0, 10.0), (-1.0, 1.0))
    cv.apply_mode(CursorMode.ONE, [5.0, 7.5])
    line = cv._lines[0]
    cv.on_press(line, line.mapToScene(line.boundingRect().center()))
    scene_pos = cv._pi.vb.mapViewToScene(pg.Point(3.0, 0.0))
    cv.on_move(line, scene_pos)
    assert line.value() == pytest.approx(3.0)


def test_on_release_without_move_emits_cursor_clicked(
    cv: CursorView, pw: pg.PlotWidget, qtbot: QtBot
) -> None:
    _set_view_range(pw, (0.0, 10.0), (-1.0, 1.0))
    cv.apply_mode(CursorMode.ONE, [5.0, 7.5])
    line = cv._lines[0]
    scene_pos = line.mapToScene(line.boundingRect().center())
    cv.on_press(line, scene_pos)
    with qtbot.waitSignal(cv.cursor_clicked, timeout=500) as blocker:
        cv.on_release(line, scene_pos)
    assert blocker.args[0] == 0


def test_on_release_after_move_does_not_emit_cursor_clicked(
    cv: CursorView, pw: pg.PlotWidget, qtbot: QtBot
) -> None:
    _set_view_range(pw, (0.0, 10.0), (-1.0, 1.0))
    cv.apply_mode(CursorMode.ONE, [5.0, 7.5])
    line = cv._lines[0]
    scene_pos = line.mapToScene(line.boundingRect().center())
    cv.on_press(line, scene_pos)
    cv.on_move(line, cv._pi.vb.mapViewToScene(pg.Point(3.0, 0.0)))
    received = []
    cv.cursor_clicked.connect(received.append)
    cv.on_release(line, scene_pos)
    assert received == []


def test_set_cursor_names_updates_tooltip(
    cv: CursorView, pw: pg.PlotWidget
) -> None:
    _set_view_range(pw, (0.0, 10.0), (-1.0, 1.0))
    cv.set_cursor_names("Cursor L", "Cursor R")
    cv.apply_mode(CursorMode.ONE, [-5.0, 7.5])
    assert cv._c_chevrons[0].toolTip() == "Fetch Cursor L"
