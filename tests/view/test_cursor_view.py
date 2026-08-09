"""Tests for CursorView — requires QApplication via qtbot.

Label bookkeeping and nearest-cursor tracking moved to CursorStripesView
(tests/view/test_cursor_stripes_view.py) — CursorView itself no longer owns
either, only the InfiniteLines/chevrons for its own stripe.
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

@pytest.mark.requirement("REQ-PLOT-070")
def test_two_lines_added_to_plot(cv: CursorView) -> None:
    assert len(cv._lines) == 2


@pytest.mark.requirement("REQ-PLOT-070")
def test_lines_hidden_initially(cv: CursorView) -> None:
    assert not cv._lines[0].isVisible()


def test_delta_label_uses_monospace_font(cv: CursorView) -> None:
    from mdf_viewer.view import theme

    assert cv._delta_label.textItem.font().family() == theme.monospace_font().family()
    assert not cv._lines[1].isVisible()


# ---------------------------------------------------------------------------
# apply_mode
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-070")
def test_apply_mode_one_shows_line_0(cv: CursorView) -> None:
    cv.apply_mode(CursorMode.ONE, [0.3, 0.6])
    assert cv._lines[0].isVisible()
    assert not cv._lines[1].isVisible()


@pytest.mark.requirement("REQ-PLOT-070")
def test_apply_mode_two_shows_both_lines(cv: CursorView) -> None:
    cv.apply_mode(CursorMode.TWO, [0.3, 0.6])
    assert cv._lines[0].isVisible()
    assert cv._lines[1].isVisible()


@pytest.mark.requirement("REQ-PLOT-070")
def test_apply_mode_hidden_hides_both(cv: CursorView) -> None:
    cv.apply_mode(CursorMode.TWO, [0.3, 0.6])
    cv.apply_mode(CursorMode.HIDDEN, [0.3, 0.6])
    assert not cv._lines[0].isVisible()
    assert not cv._lines[1].isVisible()


@pytest.mark.requirement("REQ-PLOT-073")
def test_apply_mode_sets_line_positions(cv: CursorView) -> None:
    cv.apply_mode(CursorMode.TWO, [0.25, 0.75])
    assert cv._lines[0].value() == pytest.approx(0.25)
    assert cv._lines[1].value() == pytest.approx(0.75)


# ---------------------------------------------------------------------------
# cursor_moved signal
# ---------------------------------------------------------------------------

def test_cursor_moved_emitted_on_line_move(
    cv: CursorView, qtbot: QtBot
) -> None:
    # _set_cursor_time() is what on_move() calls during a real drag (#86 —
    # cursor_moved must report the authoritative time, not the InfiniteLine's
    # raw render-space value, so a bare setValue() no longer suffices here).
    with qtbot.waitSignal(cv.cursor_moved, timeout=500) as blocker:
        cv._set_cursor_time(0, 0.42)
    assert blocker.args[0] == 0
    assert blocker.args[1] == pytest.approx(0.42)


def test_cursor_moved_reports_current_position_when_line_moved_natively(
    cv: CursorView, qtbot: QtBot
) -> None:
    # A cursor line stays movable=True, so pyqtgraph's own native
    # mouseDragEvent can still move it directly via setPos() whenever
    # PlotStripe's DragClaimant hit-test misses the press (observed right
    # after a tab switch) — bypassing _set_cursor_time() entirely. Without
    # resyncing from the line's own rendered position, cursor_moved would
    # keep reporting the stale _current_times cache (0.0 here) forever,
    # freezing the Active Signals Table for that cursor.
    with qtbot.waitSignal(cv.cursor_moved, timeout=500) as blocker:
        cv._lines[0].setValue(0.77)  # bypasses on_move()/_set_cursor_time()
    assert blocker.args[0] == 0
    assert blocker.args[1] == pytest.approx(0.77)
    assert cv._current_times[0] == pytest.approx(0.77)


def test_cursor_moved_resolves_through_translation_seam_when_moved_natively(
    pw: pg.PlotWidget, qtbot: QtBot
) -> None:
    # Same scenario, but for an X-Axis Signal tab (#86) where render-space
    # positions aren't times — the resync must go through
    # resolve_time_at_render_x(), not treat the raw render-space value as
    # the time directly.
    calls = []

    def resolve(render_x: float, current_time: float | None) -> float:
        calls.append((render_x, current_time))
        return render_x * 10.0

    cv = CursorView(pw.getPlotItem(), resolve_time_at_render_x=resolve)
    cv._set_cursor_time(0, 1.0)
    calls.clear()
    with qtbot.waitSignal(cv.cursor_moved, timeout=500) as blocker:
        cv._lines[0].setValue(0.5)
    assert calls == [(0.5, 1.0)]
    assert blocker.args[1] == pytest.approx(5.0)
    assert cv._current_times[0] == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# Chevron indicators — off-screen cursor / delta-time line
# ---------------------------------------------------------------------------

def _set_view_range(pw: pg.PlotWidget, x: tuple, y: tuple) -> None:
    """Set the ViewBox range with no padding so viewRange() matches exactly."""
    pw.getViewBox().setRange(xRange=x, yRange=y, padding=0)


@pytest.mark.requirement("REQ-PLOT-110")
def test_chevrons_created(cv: CursorView) -> None:
    assert len(cv._c_chevrons) == 2
    assert cv._dt_chevron is not None


@pytest.mark.requirement("REQ-PLOT-113")
def test_chevrons_hidden_initially(cv: CursorView) -> None:
    assert not cv._c_chevrons[0].isVisible()
    assert not cv._c_chevrons[1].isVisible()
    assert not cv._dt_chevron.isVisible()


@pytest.mark.requirement("REQ-PLOT-113")
def test_cursor_chevron_hidden_when_mode_is_hidden(
    cv: CursorView, pw: pg.PlotWidget
) -> None:
    _set_view_range(pw, (0.0, 10.0), (-1.0, 1.0))
    cv._lines[0].setValue(-5.0)  # off-screen left
    cv._update_chevrons()
    assert not cv._c_chevrons[0].isVisible()


@pytest.mark.requirement("REQ-PLOT-110")
def test_cursor_chevron_left_shown_when_off_screen(
    cv: CursorView, pw: pg.PlotWidget
) -> None:
    _set_view_range(pw, (0.0, 10.0), (-1.0, 1.0))
    cv.apply_mode(CursorMode.ONE, [-5.0, 7.5])
    assert cv._c_chevrons[0].isVisible()
    assert cv._c_chevrons[0].toPlainText() == "<"


@pytest.mark.requirement("REQ-PLOT-110")
def test_cursor_chevron_right_shown_when_off_screen(
    cv: CursorView, pw: pg.PlotWidget
) -> None:
    _set_view_range(pw, (0.0, 10.0), (-1.0, 1.0))
    cv.apply_mode(CursorMode.ONE, [99.0, 7.5])
    assert cv._c_chevrons[0].isVisible()
    assert cv._c_chevrons[0].toPlainText() == ">"


@pytest.mark.requirement("REQ-PLOT-110")
def test_cursor_chevron_hidden_when_on_screen(
    cv: CursorView, pw: pg.PlotWidget
) -> None:
    _set_view_range(pw, (0.0, 10.0), (-1.0, 1.0))
    cv.apply_mode(CursorMode.ONE, [5.0, 7.5])
    assert not cv._c_chevrons[0].isVisible()


@pytest.mark.requirement("REQ-PLOT-070")
def test_cursor_1_chevron_hidden_in_one_mode(
    cv: CursorView, pw: pg.PlotWidget
) -> None:
    _set_view_range(pw, (0.0, 10.0), (-1.0, 1.0))
    cv.apply_mode(CursorMode.ONE, [5.0, 99.0])  # cursor 1 off-screen
    assert not cv._c_chevrons[1].isVisible()


@pytest.mark.requirement("REQ-PLOT-110")
def test_both_cursors_off_screen_same_side(
    cv: CursorView, pw: pg.PlotWidget
) -> None:
    _set_view_range(pw, (0.0, 10.0), (-1.0, 1.0))
    cv.apply_mode(CursorMode.TWO, [-3.0, -1.0])
    assert cv._c_chevrons[0].isVisible()
    assert cv._c_chevrons[1].isVisible()
    # Stacked: different Y positions
    assert cv._c_chevrons[0].pos().y() != cv._c_chevrons[1].pos().y()


@pytest.mark.requirement("REQ-PLOT-112")
def test_delta_chevron_shown_above(cv: CursorView, pw: pg.PlotWidget) -> None:
    _set_view_range(pw, (0.0, 10.0), (-1.0, 1.0))
    cv.apply_mode(CursorMode.TWO, [2.5, 7.5])
    cv._cached_delta_y = 5.0   # above y_max = 1.0
    cv._cached_delta_show = True
    cv._cached_delta_color = (200, 200, 200)
    cv._update_chevrons()
    assert cv._dt_chevron.isVisible()
    assert cv._dt_chevron.toPlainText() == "^"


@pytest.mark.requirement("REQ-PLOT-112")
def test_delta_chevron_shown_below(cv: CursorView, pw: pg.PlotWidget) -> None:
    _set_view_range(pw, (0.0, 10.0), (-1.0, 1.0))
    cv.apply_mode(CursorMode.TWO, [2.5, 7.5])
    cv._cached_delta_y = -5.0  # below y_min = -1.0
    cv._cached_delta_show = True
    cv._cached_delta_color = (200, 200, 200)
    cv._update_chevrons()
    assert cv._dt_chevron.isVisible()
    assert cv._dt_chevron.toPlainText() == "v"


@pytest.mark.requirement("REQ-PLOT-112")
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


@pytest.mark.requirement("REQ-PLOT-112")
def test_delta_chevron_hidden_when_show_false(
    cv: CursorView, pw: pg.PlotWidget
) -> None:
    _set_view_range(pw, (0.0, 10.0), (-1.0, 1.0))
    cv.apply_mode(CursorMode.TWO, [2.5, 7.5])
    cv._cached_delta_y = 5.0
    cv._cached_delta_show = False
    cv._update_chevrons()
    assert not cv._dt_chevron.isVisible()


@pytest.mark.requirement("REQ-PLOT-111")
def test_cursor_fetch_signal_emitted(cv: CursorView, qtbot: QtBot) -> None:
    # Simulate a click by calling the callback with a dummy scene position.
    # The real conversion (scenePos → data-X) needs a live scene, so we test
    # that the signal fires and carries the cursor index as its first arg.
    from PyQt6.QtCore import QPointF
    with qtbot.waitSignal(cv.cursor_fetch_requested, timeout=500) as blocker:
        cv._c_chevrons[0]._clicked_cb(QPointF(0.0, 0.0))
    assert blocker.args[0] == 0  # cursor index


@pytest.mark.requirement("REQ-PLOT-112")
def test_delta_fetch_signal_emitted(cv: CursorView, qtbot: QtBot) -> None:
    from PyQt6.QtCore import QPointF
    with qtbot.waitSignal(cv.delta_fetch_requested, timeout=500):
        cv._dt_chevron._clicked_cb(QPointF(0.0, 0.0))


# ---------------------------------------------------------------------------
# update_delta_time — label tracks the midpoint (REQ-PLOT-103)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-103")
def test_update_delta_time_positions_label_at_midpoint(cv: CursorView) -> None:
    cv.update_delta_time(2.0, 8.0, "6.0 s", y_pos=0.5, show=True, color=(200, 200, 200))
    assert cv._delta_label.pos().x() == pytest.approx(5.0)


@pytest.mark.requirement("REQ-PLOT-103")
def test_update_delta_time_label_tracks_midpoint_as_cursors_move(cv: CursorView) -> None:
    cv.update_delta_time(2.0, 8.0, "6.0 s", y_pos=0.5, show=True, color=(200, 200, 200))
    cv.update_delta_time(0.0, 4.0, "4.0 s", y_pos=0.5, show=True, color=(200, 200, 200))
    assert cv._delta_label.pos().x() == pytest.approx(2.0)


@pytest.mark.requirement("REQ-PLOT-103")
def test_update_delta_time_label_text_updates_live(cv: CursorView) -> None:
    cv.update_delta_time(2.0, 8.0, "6.0 s", y_pos=0.5, show=True, color=(200, 200, 200))
    assert cv._delta_label.toPlainText() == "6.0 s"
    cv.update_delta_time(0.0, 4.0, "4.0 s", y_pos=0.5, show=True, color=(200, 200, 200))
    assert cv._delta_label.toPlainText() == "4.0 s"


# ---------------------------------------------------------------------------
# DragClaimant protocol (registered with PlotStripe.register_drag_claimant)
# ---------------------------------------------------------------------------

def test_hit_test_misses_when_no_line_visible(cv: CursorView, pw: pg.PlotWidget) -> None:
    from PyQt6.QtCore import QPointF
    assert cv.hit_test(QPointF(0.0, 0.0)) is None


def test_hit_test_hits_visible_cursor_line(cv: CursorView, pw: pg.PlotWidget) -> None:
    _set_view_range(pw, (0.0, 10.0), (-1.0, 1.0))
    cv.apply_mode(CursorMode.ONE, [5.0, 7.5])
    scene_pos = cv._lines[0].mapToScene(cv._lines[0].boundingRect().center())
    assert cv.hit_test(scene_pos) is cv._lines[0]


@pytest.mark.requirement("REQ-PLOT-102")
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


@pytest.mark.requirement("REQ-PLOT-090")
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


@pytest.mark.requirement("REQ-PLOT-090")
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


@pytest.mark.requirement("REQ-PLOT-072")
def test_set_cursor_names_updates_tooltip(
    cv: CursorView, pw: pg.PlotWidget
) -> None:
    _set_view_range(pw, (0.0, 10.0), (-1.0, 1.0))
    cv.set_cursor_names("Cursor L", "Cursor R")
    cv.apply_mode(CursorMode.ONE, [-5.0, 7.5])
    assert cv._c_chevrons[0].toolTip() == "Fetch Cursor L"


# ---------------------------------------------------------------------------
# Render-space translation seam (#86 — X-Axis Signal tabs)
# ---------------------------------------------------------------------------

def _doubling_view(pw: pg.PlotWidget) -> CursorView:
    """A CursorView whose render position is always 2x the stored time,
    and whose reverse resolution halves it back — a synthetic stand-in for
    a real axis-signal translation, distinct enough from identity that any
    site still using a raw value directly (not routed through the seam)
    would fail these tests.
    """
    return CursorView(
        pw.getPlotItem(),
        to_render_x=lambda t: t * 2.0,
        resolve_time_at_render_x=lambda render_x, current_time: render_x / 2.0,
    )


def test_apply_mode_renders_at_translated_position(pw: pg.PlotWidget) -> None:
    cv = _doubling_view(pw)
    cv.apply_mode(CursorMode.ONE, [5.0])
    assert cv._lines[0].value() == pytest.approx(10.0)


def test_cursor_moved_reports_time_not_render_position(
    pw: pg.PlotWidget, qtbot: QtBot
) -> None:
    cv = _doubling_view(pw)
    with qtbot.waitSignal(cv.cursor_moved, timeout=500) as blocker:
        cv._set_cursor_time(0, 5.0)
    assert cv._lines[0].value() == pytest.approx(10.0)  # rendered, doubled
    assert blocker.args[1] == pytest.approx(5.0)         # reported, as time


def test_on_move_routes_through_resolve_time_at_render_x(
    pw: pg.PlotWidget, qtbot: QtBot
) -> None:
    cv = _doubling_view(pw)
    _set_view_range(pw, (0.0, 20.0), (-1.0, 1.0))
    cv.apply_mode(CursorMode.ONE, [5.0])
    line = cv._lines[0]
    cv.on_press(line, line.mapToScene(line.boundingRect().center()))
    scene_pos = cv._pi.vb.mapViewToScene(pg.Point(16.0, 0.0))  # render x=16
    with qtbot.waitSignal(cv.cursor_moved, timeout=500) as blocker:
        cv.on_move(line, scene_pos)
    assert line.value() == pytest.approx(16.0)   # render position unchanged
    assert blocker.args[1] == pytest.approx(8.0)  # resolved time (16 / 2)


def test_delta_label_positioned_at_translated_midpoint(pw: pg.PlotWidget) -> None:
    cv = _doubling_view(pw)
    _set_view_range(pw, (0.0, 20.0), (-1.0, 1.0))
    cv.apply_mode(CursorMode.TWO, [2.0, 4.0])
    cv.update_delta_time(2.0, 4.0, "Δt = 2 s", y_pos=0.0, show=True, color=(200, 200, 200))
    # Midpoint in time is 3.0; rendered position must be translated (6.0),
    # not the raw time midpoint.
    assert cv._delta_label.pos().x() == pytest.approx(6.0)


def test_identity_default_matches_pre_seam_behavior(pw: pg.PlotWidget) -> None:
    """A CursorView built with no translation args behaves exactly as
    before this seam existed — the explicit non-regression check."""
    cv = CursorView(pw.getPlotItem())
    cv.apply_mode(CursorMode.ONE, [5.0])
    assert cv._lines[0].value() == pytest.approx(5.0)
