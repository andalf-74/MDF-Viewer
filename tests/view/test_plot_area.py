"""Tests for PlotArea.

Verifies the contract (active.curve/view_box set/cleared, no crashes) rather
than PyQtGraph internals. All tests require a QApplication via qtbot.
"""

from __future__ import annotations

import numpy as np
import pytest
from PyQt6.QtGui import QColor
from pytestqt.qtbot import QtBot

from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.view.plot_area import PlotArea
from mdf_viewer.view_model.active_signal import ActiveSignal


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_active(
    name: str = "sig",
    n: int = 100,
    color: QColor | None = None,
) -> ActiveSignal:
    t = np.linspace(0.0, 1.0, n)
    data = SignalData(timestamps=t, samples=np.sin(2 * np.pi * t))
    meta = SignalMetadata(name=name, unit="V", group_index=0, channel_index=0)
    return ActiveSignal(data=data, metadata=meta, color=color or QColor(255, 85, 85))


@pytest.fixture()
def plot(qtbot: QtBot) -> PlotArea:
    w = PlotArea()
    qtbot.addWidget(w)
    return w


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

def test_plot_widget_present(plot: PlotArea) -> None:
    import pyqtgraph as pg
    assert isinstance(plot._pw, pg.PlotWidget)


def test_initially_no_signals(plot: PlotArea) -> None:
    assert len(plot._data) == 0


# ---------------------------------------------------------------------------
# add_signal
# ---------------------------------------------------------------------------

def test_add_signal_sets_curve(plot: PlotArea) -> None:
    active = _make_active()
    plot.add_signal(active)
    assert active.curve is not None


def test_add_signal_sets_view_box(plot: PlotArea) -> None:
    active = _make_active()
    plot.add_signal(active)
    assert active.view_box is not None


def test_add_signal_stored_in_data(plot: PlotArea) -> None:
    active = _make_active()
    plot.add_signal(active)
    assert active in plot._data


def test_add_signal_duplicate_is_noop(plot: PlotArea) -> None:
    active = _make_active()
    plot.add_signal(active)
    curve_first = active.curve
    plot.add_signal(active)
    assert active.curve is curve_first
    assert len(plot._data) == 1


def test_add_multiple_signals(plot: PlotArea) -> None:
    sigs = [_make_active(f"s{i}", color=QColor(i * 30, 100, 200)) for i in range(3)]
    for s in sigs:
        plot.add_signal(s)
    assert len(plot._data) == 3
    for s in sigs:
        assert s.curve is not None
        assert s.view_box is not None


def test_add_signal_view_boxes_are_distinct(plot: PlotArea) -> None:
    a = _make_active("a")
    b = _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    assert a.view_box is not b.view_box


def test_add_signal_curves_are_distinct(plot: PlotArea) -> None:
    a = _make_active("a")
    b = _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    assert a.curve is not b.curve


# ---------------------------------------------------------------------------
# remove_signal
# ---------------------------------------------------------------------------

def test_remove_signal_clears_curve(plot: PlotArea) -> None:
    active = _make_active()
    plot.add_signal(active)
    plot.remove_signal(active)
    assert active.curve is None


def test_remove_signal_clears_view_box(plot: PlotArea) -> None:
    active = _make_active()
    plot.add_signal(active)
    plot.remove_signal(active)
    assert active.view_box is None


def test_remove_signal_removed_from_data(plot: PlotArea) -> None:
    active = _make_active()
    plot.add_signal(active)
    plot.remove_signal(active)
    assert active not in plot._data


def test_remove_signal_noop_for_unknown(plot: PlotArea) -> None:
    stranger = _make_active("stranger")
    plot.remove_signal(stranger)  # must not raise


def test_remove_one_of_multiple(plot: PlotArea) -> None:
    a, b, c = _make_active("a"), _make_active("b"), _make_active("c")
    for s in (a, b, c):
        plot.add_signal(s)
    plot.remove_signal(b)
    assert len(plot._data) == 2
    assert a in plot._data
    assert c in plot._data
    assert b not in plot._data
    assert b.curve is None
    assert b.view_box is None


def test_add_after_remove(plot: PlotArea) -> None:
    active = _make_active()
    plot.add_signal(active)
    plot.remove_signal(active)
    plot.add_signal(active)
    assert active.curve is not None
    assert active in plot._data


# ---------------------------------------------------------------------------
# zoom_to_fit
# ---------------------------------------------------------------------------

def test_zoom_to_fit_empty_is_noop(plot: PlotArea) -> None:
    plot.zoom_to_fit()  # must not raise


def test_zoom_to_fit_with_signals_no_crash(plot: PlotArea) -> None:
    for i in range(3):
        plot.add_signal(_make_active(f"s{i}"))
    plot.zoom_to_fit()  # must not raise


# ---------------------------------------------------------------------------
# recolor_signal
# ---------------------------------------------------------------------------

def test_recolor_updates_active_color(plot: PlotArea) -> None:
    active = _make_active(color=QColor(255, 0, 0))
    plot.add_signal(active)
    new_color = QColor(0, 0, 255)
    plot.recolor_signal(active, new_color)
    assert active.color == new_color


def test_recolor_updates_curve_pen(plot: PlotArea) -> None:
    active = _make_active(color=QColor(255, 0, 0))
    plot.add_signal(active)
    new_color = QColor(0, 200, 50)
    plot.recolor_signal(active, new_color)
    assert active.curve.opts["pen"].color().name() == new_color.name()


def test_recolor_noop_for_unknown(plot: PlotArea) -> None:
    stranger = _make_active()
    plot.recolor_signal(stranger, QColor(0, 255, 0))  # must not raise


def test_recolor_does_not_affect_other_signals(plot: PlotArea) -> None:
    a = _make_active("a", color=QColor(255, 0, 0))
    b = _make_active("b", color=QColor(0, 0, 255))
    plot.add_signal(a)
    plot.add_signal(b)
    plot.recolor_signal(a, QColor(0, 255, 0))
    assert b.color == QColor(0, 0, 255)


def test_zoom_to_fit_sets_x_range(plot: PlotArea) -> None:
    t = np.linspace(0.5, 2.5, 50)
    data = SignalData(timestamps=t, samples=np.ones(50))
    meta = SignalMetadata(name="x", group_index=0, channel_index=0)
    active = ActiveSignal(data=data, metadata=meta, color=QColor(200, 100, 50))
    plot.add_signal(active)
    plot.zoom_to_fit()
    x_range = plot._pi.vb.viewRange()[0]
    # Range should encompass [0.5, 2.5] with some padding
    assert x_range[0] <= 0.5
    assert x_range[1] >= 2.5
