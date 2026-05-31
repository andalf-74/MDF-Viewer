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
# Fixtures
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

def test_update_labels_creates_label_for_signal(cv: CursorView) -> None:
    active = _make_active()
    cv.apply_mode(CursorMode.ONE, [0.25, 0.75])
    cv.update_labels([active], [0.25, 0.75], CursorMode.ONE)
    assert len(cv._labels) == 1


def test_update_labels_two_mode_creates_two_per_signal(cv: CursorView) -> None:
    active = _make_active()
    cv.apply_mode(CursorMode.TWO, [0.25, 0.75])
    cv.update_labels([active], [0.25, 0.75], CursorMode.TWO)
    assert len(cv._labels) == 2


def test_update_labels_multiple_signals(cv: CursorView) -> None:
    sigs = [_make_active(f"s{i}") for i in range(3)]
    cv.apply_mode(CursorMode.ONE, [0.5, 0.8])
    cv.update_labels(sigs, [0.5, 0.8], CursorMode.ONE)
    assert len(cv._labels) == 3


def test_update_labels_removes_stale_labels(cv: CursorView) -> None:
    sigs = [_make_active("a"), _make_active("b")]
    cv.apply_mode(CursorMode.ONE, [0.5, 0.8])
    cv.update_labels(sigs, [0.5, 0.8], CursorMode.ONE)
    assert len(cv._labels) == 2
    # Remove one signal
    cv.update_labels(sigs[:1], [0.5, 0.8], CursorMode.ONE)
    assert len(cv._labels) == 1


def test_update_labels_out_of_range_hides_label(cv: CursorView) -> None:
    active = _make_active()
    cv.apply_mode(CursorMode.ONE, [5.0, 6.0])
    cv.update_labels([active], [5.0, 6.0], CursorMode.ONE)
    # Cursor at x=5.0, signal only covers [0,1] → no label created
    assert all(not lbl.isVisible() for lbl in cv._labels.values())


# ---------------------------------------------------------------------------
# Label visibility rules
# ---------------------------------------------------------------------------

def test_one_mode_label_always_visible(cv: CursorView) -> None:
    active = _make_active()
    cv.apply_mode(CursorMode.ONE, [0.25, 0.75])
    cv.update_labels([active], [0.25, 0.75], CursorMode.ONE)
    label = cv._labels[(0, active)]
    assert label.isVisible()


def test_hidden_mode_labels_not_visible(cv: CursorView) -> None:
    active = _make_active()
    cv.apply_mode(CursorMode.ONE, [0.25, 0.75])
    cv.update_labels([active], [0.25, 0.75], CursorMode.ONE)
    cv.apply_mode(CursorMode.HIDDEN, [0.25, 0.75])
    for lbl in cv._labels.values():
        assert not lbl.isVisible()


# ---------------------------------------------------------------------------
# remove_labels_for / clear_labels
# ---------------------------------------------------------------------------

def test_remove_labels_for_removes_only_that_signal(cv: CursorView) -> None:
    a, b = _make_active("a"), _make_active("b")
    cv.apply_mode(CursorMode.ONE, [0.5, 0.8])
    cv.update_labels([a, b], [0.5, 0.8], CursorMode.ONE)
    cv.remove_labels_for(a)
    remaining = [k[1] for k in cv._labels]
    assert not any(r is a for r in remaining)
    assert any(r is b for r in remaining)


def test_clear_labels_removes_all(cv: CursorView) -> None:
    sigs = [_make_active(f"s{i}") for i in range(3)]
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
