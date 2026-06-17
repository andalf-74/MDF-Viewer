"""Tests for PlotArea.

Verifies the contract (active.curve/view_box set/cleared, no crashes) rather
than PyQtGraph internals. All tests require a QApplication via qtbot.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest
from PyQt6.QtCore import QByteArray, QEvent, QMimeData, QRectF, QUrl
from PyQt6.QtGui import QColor
from pytestqt.qtbot import QtBot

from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.view._mime import SIGNAL_MIME_TYPE
from mdf_viewer.view.plot_area import PlotArea, _SignalAxisItem, _ViewBox
from mdf_viewer.view_model.active_signal import ActiveSignal


def _drop_event(mime_data):
    event = MagicMock()
    event.type.return_value = QEvent.Type.Drop
    event.mimeData.return_value = mime_data
    return event


def _drag_enter_event(mime_data):
    event = MagicMock()
    event.type.return_value = QEvent.Type.DragEnter
    event.mimeData.return_value = mime_data
    return event


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
# _ViewBox mouse behaviour
# ---------------------------------------------------------------------------

def test_main_viewbox_is_custom_type(plot: PlotArea) -> None:
    assert isinstance(plot._pi.vb, _ViewBox)


def test_main_viewbox_is_pan_mode(plot: PlotArea) -> None:
    import pyqtgraph as pg
    assert plot._pi.vb.state['mouseMode'] == pg.ViewBox.PanMode


def test_signal_viewbox_is_custom_type(plot: PlotArea) -> None:
    plot.add_signal(_make_active())
    vb = list(plot._data.values())[0].view_box
    assert isinstance(vb, _ViewBox)


def test_signal_viewbox_is_pan_mode(plot: PlotArea) -> None:
    import pyqtgraph as pg
    plot.add_signal(_make_active())
    vb = list(plot._data.values())[0].view_box
    assert vb.state['mouseMode'] == pg.ViewBox.PanMode


def test_mouse_mode_menu_item_removed(plot: PlotArea) -> None:
    from unittest.mock import MagicMock
    ev = MagicMock()
    menu = plot._pi.vb.getMenu(ev)
    titles = [a.text() for a in menu.actions()]
    assert not any('mouse' in t.lower() for t in titles)


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


# ---------------------------------------------------------------------------
# _SignalAxisItem tick formatting
# ---------------------------------------------------------------------------

def test_float_signal_uses_float_axis(plot: PlotArea) -> None:
    active = _make_active()  # float64 samples
    plot.add_signal(active)
    axis = plot._data[active].axis
    assert not axis._integer_ticks


def test_integer_signal_uses_integer_axis(plot: PlotArea) -> None:
    t = np.linspace(0.0, 1.0, 10)
    # Samples are float64 (as MdfLoader always produces), but metadata carries
    # is_integer=True set from the raw dtype before conversion.
    data = SignalData(
        timestamps=t,
        samples=np.linspace(6.0, 8.0, 10),  # float64, as MdfLoader outputs
    )
    meta = SignalMetadata(
        name="gear", group_index=0, channel_index=0,
        data_type="uint8", is_integer=True,
    )
    active = ActiveSignal(data=data, metadata=meta, color=QColor(200, 100, 50))
    plot.add_signal(active)
    assert plot._data[active].axis._integer_ticks


def test_float_tick_strings_use_g_format() -> None:
    axis = _SignalAxisItem("left")
    result = axis.tickStrings([256.000000007, 0.001234567, -3.14159], 1.0, 1.0)
    assert result == ["256", "0.00123457", "-3.14159"]


def test_integer_tick_strings_are_plain_ints() -> None:
    axis = _SignalAxisItem("left", integer_ticks=True)
    result = axis.tickStrings([1.0, 2.0, 7.0, -1.0], 1.0, 1.0)
    assert result == ["1", "2", "7", "-1"]


def test_integer_tick_values_no_fractions(plot: PlotArea) -> None:
    axis = _SignalAxisItem("left", integer_ticks=True)
    # Ask for ticks across range 0–8 (gear signal)
    ticks = axis.tickValues(0.0, 8.0, 300)
    all_values = [v for _, vals in ticks for v in vals]
    # Every tick must be a whole number
    assert all(v == int(v) for v in all_values)


def test_integer_tick_values_no_duplicates(plot: PlotArea) -> None:
    axis = _SignalAxisItem("left", integer_ticks=True)
    ticks = axis.tickValues(-1.0, 8.0, 300)
    all_values = [v for _, vals in ticks for v in vals]
    assert len(all_values) == len(set(all_values))


# ---------------------------------------------------------------------------
# Drag and drop — signals
# ---------------------------------------------------------------------------

def test_signals_dropped_emitted_on_signal_mime(plot: PlotArea, qtbot: QtBot) -> None:
    locs = [[0, 1], [1, 2]]
    mime = QMimeData()
    mime.setData(SIGNAL_MIME_TYPE, QByteArray(json.dumps(locs).encode()))
    with qtbot.waitSignal(plot.signals_dropped) as blocker:
        plot.eventFilter(plot._pw.viewport(), _drop_event(mime))
    assert blocker.args[0] == [(0, 1), (1, 2)]


def test_signals_dropped_not_emitted_for_wrong_mime(
    plot: PlotArea, qtbot: QtBot
) -> None:
    mime = QMimeData()
    mime.setText("irrelevant")
    with qtbot.assertNotEmitted(plot.signals_dropped):
        plot.eventFilter(plot._pw.viewport(), _drop_event(mime))


# ---------------------------------------------------------------------------
# Drag and drop — file
# ---------------------------------------------------------------------------

def test_file_dropped_emitted_on_mdf_url(
    plot: PlotArea, qtbot: QtBot, tmp_path: Path
) -> None:
    path = tmp_path / "data.mf4"
    path.touch()
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    with qtbot.waitSignal(plot.file_dropped) as blocker:
        plot.eventFilter(plot._pw.viewport(), _drop_event(mime))
    assert blocker.args[0] == path


def test_file_dropped_not_emitted_for_non_mdf(
    plot: PlotArea, qtbot: QtBot, tmp_path: Path
) -> None:
    path = tmp_path / "data.csv"
    path.touch()
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    with qtbot.assertNotEmitted(plot.file_dropped):
        plot.eventFilter(plot._pw.viewport(), _drop_event(mime))


def test_drag_enter_accepted_for_signal_mime(plot: PlotArea) -> None:
    mime = QMimeData()
    mime.setData(SIGNAL_MIME_TYPE, QByteArray(b"[]"))
    event = _drag_enter_event(mime)
    plot.eventFilter(plot._pw.viewport(), event)
    event.acceptProposedAction.assert_called_once()


def test_drag_enter_accepted_for_mdf_url(plot: PlotArea, tmp_path: Path) -> None:
    path = tmp_path / "data.mf4"
    path.touch()
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    event = _drag_enter_event(mime)
    plot.eventFilter(plot._pw.viewport(), event)
    event.acceptProposedAction.assert_called_once()


def test_drag_enter_ignored_for_unknown_mime(plot: PlotArea) -> None:
    mime = QMimeData()
    mime.setText("not a signal or file")
    event = _drag_enter_event(mime)
    plot.eventFilter(plot._pw.viewport(), event)
    event.ignore.assert_called_once()


# ---------------------------------------------------------------------------
# zoom_y_to_view
# ---------------------------------------------------------------------------

def test_zoom_y_to_view_returns_false_when_empty(plot: PlotArea) -> None:
    assert plot.zoom_y_to_view() is False


def test_zoom_y_to_view_returns_true_with_signals(plot: PlotArea) -> None:
    plot.add_signal(_make_active())
    assert plot.zoom_y_to_view() is True


def test_zoom_y_to_view_constant_signal_expands_range(plot: PlotArea) -> None:
    t = np.linspace(0.0, 1.0, 50)
    data = SignalData(timestamps=t, samples=np.zeros(50))
    meta = SignalMetadata(name="z", group_index=0, channel_index=0)
    active = ActiveSignal(data=data, metadata=meta, color=QColor(100, 100, 200))
    plot.add_signal(active)
    plot.zoom_y_to_view()
    y_range = plot._data[active].view_box.viewRange()[1]
    assert y_range[0] < 0.0
    assert y_range[1] > 0.0


# ---------------------------------------------------------------------------
# zoom_to_fit
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# _ViewBox wheel event — axis routing (bug #34)
# ---------------------------------------------------------------------------

def test_wheel_axis_none_forces_x_zoom(plot: PlotArea) -> None:
    """Wheel over plot interior (axis=None) must zoom X only."""
    import pyqtgraph as pg
    from unittest.mock import MagicMock, patch
    ev = MagicMock()
    with patch.object(pg.ViewBox, 'wheelEvent') as mock_wheel:
        plot._pi.vb.wheelEvent(ev, axis=None)
        mock_wheel.assert_called_once_with(ev, axis=0)


def test_wheel_axis_0_forces_x_zoom(plot: PlotArea) -> None:
    """Wheel with explicit axis=0 must also zoom X only."""
    import pyqtgraph as pg
    from unittest.mock import MagicMock, patch
    ev = MagicMock()
    with patch.object(pg.ViewBox, 'wheelEvent') as mock_wheel:
        plot._pi.vb.wheelEvent(ev, axis=0)
        mock_wheel.assert_called_once_with(ev, axis=0)


def test_wheel_axis_1_allows_y_zoom(plot: PlotArea) -> None:
    """Wheel over a Y-axis (axis=1) must zoom Y, not X."""
    import pyqtgraph as pg
    from unittest.mock import MagicMock, patch
    ev = MagicMock()
    with patch.object(pg.ViewBox, 'wheelEvent') as mock_wheel:
        plot._pi.vb.wheelEvent(ev, axis=1)
        mock_wheel.assert_called_once_with(ev, axis=1)


# ---------------------------------------------------------------------------
# Zoom rect Y propagation (bug #35)
# ---------------------------------------------------------------------------

def test_zoom_rect_updates_all_signal_viewboxes(plot: PlotArea) -> None:
    """_on_zoom_rect_finished increments axHistoryPointer on every signal ViewBox."""
    a = _make_active("a")
    b = _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    ptr_a = plot._data[a].view_box.axHistoryPointer
    ptr_b = plot._data[b].view_box.axHistoryPointer

    plot._on_zoom_rect_finished(QRectF(0, 0, 100, 100))

    assert plot._data[a].view_box.axHistoryPointer == ptr_a + 1
    assert plot._data[b].view_box.axHistoryPointer == ptr_b + 1


def test_zoom_rect_noop_when_no_signals(plot: PlotArea) -> None:
    """_on_zoom_rect_finished with no signals must not raise."""
    plot._on_zoom_rect_finished(QRectF(0, 0, 100, 100))  # must not raise


def test_zoom_rect_signal_connected_on_add(plot: PlotArea) -> None:
    """zoom_rect_finished on a signal ViewBox must trigger _on_zoom_rect_finished."""
    active = _make_active()
    plot.add_signal(active)
    vb = plot._data[active].view_box
    ptr_before = vb.axHistoryPointer

    # Emit from the ViewBox itself — should loop back and update its own history.
    vb.zoom_rect_finished.emit(QRectF(0, 0, 100, 100))

    assert vb.axHistoryPointer == ptr_before + 1


def test_zoom_rect_signal_disconnected_on_remove(plot: PlotArea) -> None:
    """After remove_signal, the removed ViewBox's zoom_rect_finished must not fire the handler."""
    a = _make_active("a")
    b = _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    vb_a = plot._data[a].view_box
    plot.remove_signal(a)

    ptr_b_before = plot._data[b].view_box.axHistoryPointer

    # Emit from the removed ViewBox — b's history must stay unchanged.
    vb_a.zoom_rect_finished.emit(QRectF(0, 0, 100, 100))

    assert plot._data[b].view_box.axHistoryPointer == ptr_b_before


# ---------------------------------------------------------------------------
# swimlanes
# ---------------------------------------------------------------------------

def test_swimlanes_returns_false_when_no_signals(plot: PlotArea) -> None:
    assert plot.swimlanes([]) is False


def test_swimlanes_returns_false_when_data_empty(plot: PlotArea) -> None:
    assert plot.swimlanes([_make_active()]) is False


def test_swimlanes_returns_true_with_signals(plot: PlotArea) -> None:
    a = _make_active("a")
    plot.add_signal(a)
    plot.show()
    assert plot.swimlanes([a]) is True


def test_swimlanes_sets_y_range_per_signal(plot: PlotArea) -> None:
    a = _make_active("a")
    b = _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.show()
    # Must not raise; each ViewBox gets an independent Y range
    result = plot.swimlanes([a, b])
    assert result is True


def test_swimlanes_skips_unknown_signals(plot: PlotArea) -> None:
    a = _make_active("a")
    plot.add_signal(a)
    plot.show()
    stranger = _make_active("x")
    # Passing an unknown signal in the list must not raise
    assert plot.swimlanes([a, stranger]) is True
