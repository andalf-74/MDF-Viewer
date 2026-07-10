"""Tests for PlotStripe.

Verifies the contract (active.curve/view_box set/cleared, no crashes) rather
than PyQtGraph internals. All tests require a QApplication via qtbot.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pyqtgraph as pg
import pytest
from unittest.mock import patch

from PyQt6.QtCore import QByteArray, QEvent, QMimeData, QPoint, QRectF, Qt, QUrl
from PyQt6.QtGui import QColor, QMouseEvent
from pytestqt.qtbot import QtBot

from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.view._mime import (
    ROW_MIME_TYPE,
    SIGNAL_MIME_TYPE,
    encode_row_payload,
    encode_signal_payload,
)
from mdf_viewer.view.plot_stripe import PlotStripe, _SignalAxisItem, _ViewBox
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
def plot(qtbot: QtBot) -> PlotStripe:
    w = PlotStripe()
    qtbot.addWidget(w)
    return w


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

def test_plot_widget_present(plot: PlotStripe) -> None:
    import pyqtgraph as pg
    assert isinstance(plot._pw, pg.PlotWidget)


def test_initially_no_signals(plot: PlotStripe) -> None:
    assert len(plot._data) == 0


# ---------------------------------------------------------------------------
# _ViewBox mouse behaviour
# ---------------------------------------------------------------------------

def test_main_viewbox_is_custom_type(plot: PlotStripe) -> None:
    assert isinstance(plot._pi.vb, _ViewBox)


@pytest.mark.requirement("REQ-PLOT-051")
def test_main_viewbox_is_pan_mode(plot: PlotStripe) -> None:
    import pyqtgraph as pg
    assert plot._pi.vb.state['mouseMode'] == pg.ViewBox.PanMode


def test_signal_viewbox_is_custom_type(plot: PlotStripe) -> None:
    plot.add_signal(_make_active())
    vb = list(plot._data.values())[0].view_box
    assert isinstance(vb, _ViewBox)


@pytest.mark.requirement("REQ-PLOT-051")
def test_signal_viewbox_is_pan_mode(plot: PlotStripe) -> None:
    import pyqtgraph as pg
    plot.add_signal(_make_active())
    vb = list(plot._data.values())[0].view_box
    assert vb.state['mouseMode'] == pg.ViewBox.PanMode


def test_mouse_mode_menu_item_removed(plot: PlotStripe) -> None:
    from unittest.mock import MagicMock
    ev = MagicMock()
    menu = plot._pi.vb.getMenu(ev)
    titles = [a.text() for a in menu.actions()]
    assert not any('mouse' in t.lower() for t in titles)


@pytest.mark.requirement("REQ-PLOT-190")
def test_create_new_stripe_menu_item_present(plot: PlotStripe) -> None:
    from unittest.mock import MagicMock
    menu = plot._pi.vb.getMenu(MagicMock())
    titles = [a.text() for a in menu.actions()]
    assert "Create new Stripe" in titles


def test_create_new_stripe_menu_item_emits_signal(plot: PlotStripe, qtbot: QtBot) -> None:
    from unittest.mock import MagicMock
    menu = plot._pi.vb.getMenu(MagicMock())
    action = next(a for a in menu.actions() if a.text() == "Create new Stripe")
    with qtbot.waitSignal(plot.create_stripe_requested, timeout=1000) as blocker:
        action.trigger()
    assert blocker.args == [plot]


def test_delete_this_stripe_menu_item_emits_signal(plot: PlotStripe, qtbot: QtBot) -> None:
    from unittest.mock import MagicMock
    menu = plot._pi.vb.getMenu(MagicMock())
    action = next(a for a in menu.actions() if a.text() == "Delete this Stripe")
    with qtbot.waitSignal(plot.delete_stripe_requested, timeout=1000) as blocker:
        action.trigger()
    assert blocker.args == [plot]


def test_menu_items_not_duplicated_on_repeated_getMenu_calls(plot: PlotStripe) -> None:
    from unittest.mock import MagicMock
    plot._pi.vb.getMenu(MagicMock())
    menu = plot._pi.vb.getMenu(MagicMock())
    titles = [a.text() for a in menu.actions()]
    assert titles.count("Create new Stripe") == 1


# ---------------------------------------------------------------------------
# Active-stripe marker / X-axis tick visibility / activated signal
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-211")
def test_activated_emitted_on_mouse_press(plot: PlotStripe, qtbot: QtBot) -> None:
    event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        QPoint(5, 5).toPointF(),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    with qtbot.waitSignal(plot.activated, timeout=1000) as blocker:
        plot.eventFilter(plot._pw.viewport(), event)
    assert blocker.args == [plot]


@pytest.mark.requirement("REQ-PLOT-210")
def test_set_active_toggles_marker_style(plot: PlotStripe) -> None:
    plot.set_active(True)
    active_style = plot._active_marker.styleSheet()
    plot.set_active(False)
    inactive_style = plot._active_marker.styleSheet()
    assert active_style != inactive_style
    assert "transparent" in inactive_style


@pytest.mark.requirement("REQ-PLOT-181")
def test_set_show_x_axis_ticks(plot: PlotStripe) -> None:
    plot.set_show_x_axis_ticks(False)
    assert plot._pi.getAxis('bottom').style['showValues'] is False
    plot.set_show_x_axis_ticks(True)
    assert plot._pi.getAxis('bottom').style['showValues'] is True


@pytest.mark.requirement("REQ-PLOT-181")
def test_set_show_x_axis_ticks_also_hides_time_label(plot: PlotStripe) -> None:
    plot.set_show_x_axis_ticks(False)
    assert plot._pi.getAxis('bottom').label.isVisible() is False
    plot.set_show_x_axis_ticks(True)
    assert plot._pi.getAxis('bottom').label.isVisible() is True


# ---------------------------------------------------------------------------
# Drag-target highlight (REQ-PLOT-200)
# ---------------------------------------------------------------------------

def test_drag_enter_signal_mime_shows_highlight(plot: PlotStripe) -> None:
    mime = QMimeData()
    mime.setData(SIGNAL_MIME_TYPE, QByteArray(encode_signal_payload(0, [(0, 0)])))
    plot.eventFilter(plot._pw.viewport(), _drag_enter_event(mime))
    assert plot._drag_hover_active is True


def test_drag_leave_clears_highlight(plot: PlotStripe) -> None:
    mime = QMimeData()
    mime.setData(SIGNAL_MIME_TYPE, QByteArray(encode_signal_payload(0, [(0, 0)])))
    plot.eventFilter(plot._pw.viewport(), _drag_enter_event(mime))
    assert plot._drag_hover_active is True

    leave_event = MagicMock()
    leave_event.type.return_value = QEvent.Type.DragLeave
    plot.eventFilter(plot._pw.viewport(), leave_event)
    assert plot._drag_hover_active is False


def test_drop_clears_highlight(plot: PlotStripe) -> None:
    mime = QMimeData()
    mime.setData(SIGNAL_MIME_TYPE, QByteArray(encode_signal_payload(0, [(0, 0)])))
    plot.eventFilter(plot._pw.viewport(), _drag_enter_event(mime))
    assert plot._drag_hover_active is True

    plot.eventFilter(plot._pw.viewport(), _drop_event(mime))
    assert plot._drag_hover_active is False


# ---------------------------------------------------------------------------
# Cross-stripe X sharing primitives
# ---------------------------------------------------------------------------

def test_sync_x_range_sets_exact_range_no_padding(plot: PlotStripe) -> None:
    plot.sync_x_range(0.3, 0.7)
    assert plot.plot_item.vb.viewRange()[0] == pytest.approx([0.3, 0.7], abs=1e-9)


def test_autorange_y_does_not_change_x(plot: PlotStripe) -> None:
    active = _make_active()
    plot.add_signal(active)
    plot.zoom_to_x_range(0.25, 0.75)
    x_before = plot._pi.vb.viewRange()[0]
    plot.autorange_y()
    assert plot._pi.vb.viewRange()[0] == pytest.approx(x_before, abs=1e-9)


# ---------------------------------------------------------------------------
# Cross-stripe axis-width alignment (REQ-PLOT-180)
# ---------------------------------------------------------------------------

def test_content_axis_width_zero_with_no_signals(plot: PlotStripe) -> None:
    assert plot.content_axis_width() == 0


def test_content_axis_width_excludes_hidden_axis(plot: PlotStripe) -> None:
    other = _make_active("other")
    active = _make_active("target")
    plot.add_signal(other)
    plot.add_signal(active)
    plot.set_show_only_selected_y_axis(True)
    plot.set_selected_signals([other], all_signals=[other, active])  # hides active's axis
    assert plot._data[active].axis.isVisible() is False
    assert plot.content_axis_width() == pytest.approx(plot._data[other].axis.width())


def test_set_axis_padding_adds_and_removes_spacer(plot: PlotStripe) -> None:
    assert plot._axis_spacer is None
    plot.set_axis_padding(25)
    assert plot._axis_spacer is not None
    assert plot._axis_spacer.width() == 25
    plot.set_axis_padding(0)
    assert plot._axis_spacer is None


def test_set_axis_padding_does_not_count_toward_content_width(plot: PlotStripe) -> None:
    active = _make_active()
    plot.add_signal(active)
    before = plot.content_axis_width()
    plot.set_axis_padding(40)
    assert plot.content_axis_width() == before


def test_set_axis_padding_negative_clamped_to_zero(plot: PlotStripe) -> None:
    plot.set_axis_padding(-10)
    assert plot._axis_spacer is None


def _drag_event(button, last_pos, pos, axis_finish=False):
    ev = MagicMock()
    ev.button.return_value = button
    ev.lastPos.return_value = pg.Point(*last_pos)
    ev.pos.return_value = pg.Point(*pos)
    ev.isFinish.return_value = axis_finish
    ev.buttonDownPos.return_value = pg.Point(*last_pos)
    ev.screenPos.return_value = pg.Point(*pos)
    ev.lastScreenPos.return_value = pg.Point(*last_pos)
    return ev


@pytest.mark.requirement("REQ-PLOT-051")
def test_interior_left_drag_pans_x_only(plot: PlotStripe) -> None:
    """Left-drag in the plot interior must not change an individual signal's Y (#78 follow-up).

    Y-panning a signal is only meant to happen via dragging its own Y-axis
    column (axis=1) — an interior drag used to pan both X and Y of whichever
    ViewBox was topmost, which was reported as confusing/unwanted behaviour.
    """
    active = _make_active()
    plot.add_signal(active)
    vb = active.view_box
    vb.setRange(xRange=(0.0, 10.0), yRange=(0.0, 10.0), padding=0)
    y_before = vb.viewRange()[1]

    ev = _drag_event(Qt.MouseButton.LeftButton, (0, 0), (0, 50))
    vb.mouseDragEvent(ev, axis=None)

    assert vb.viewRange()[1] == pytest.approx(y_before)


@pytest.mark.requirement("REQ-PLOT-051")
def test_y_axis_drag_still_pans_y(plot: PlotStripe) -> None:
    """Dragging the Y-axis item itself (axis=1) must still pan that signal's Y."""
    active = _make_active()
    plot.add_signal(active)
    vb = active.view_box
    vb.setRange(xRange=(0.0, 10.0), yRange=(0.0, 10.0), padding=0)
    y_before = vb.viewRange()[1]

    ev = _drag_event(Qt.MouseButton.LeftButton, (0, 0), (0, 50))
    vb.mouseDragEvent(ev, axis=1)

    assert vb.viewRange()[1] != pytest.approx(y_before)


# ---------------------------------------------------------------------------
# add_signal
# ---------------------------------------------------------------------------

def test_add_signal_sets_curve(plot: PlotStripe) -> None:
    active = _make_active()
    plot.add_signal(active)
    assert active.curve is not None


def test_add_signal_sets_view_box(plot: PlotStripe) -> None:
    active = _make_active()
    plot.add_signal(active)
    assert active.view_box is not None


def test_add_signal_stored_in_data(plot: PlotStripe) -> None:
    active = _make_active()
    plot.add_signal(active)
    assert active in plot._data


@pytest.mark.requirement("REQ-PLOT-020")
def test_add_signal_duplicate_is_noop(plot: PlotStripe) -> None:
    active = _make_active()
    plot.add_signal(active)
    curve_first = active.curve
    plot.add_signal(active)
    assert active.curve is curve_first
    assert len(plot._data) == 1


def test_add_multiple_signals(plot: PlotStripe) -> None:
    sigs = [_make_active(f"s{i}", color=QColor(i * 30, 100, 200)) for i in range(3)]
    for s in sigs:
        plot.add_signal(s)
    assert len(plot._data) == 3
    for s in sigs:
        assert s.curve is not None
        assert s.view_box is not None


@pytest.mark.requirement("REQ-PLOT-011")
@pytest.mark.requirement("REQ-PLOT-030")
def test_add_signal_view_boxes_are_distinct(plot: PlotStripe) -> None:
    a = _make_active("a")
    b = _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    assert a.view_box is not b.view_box


def test_add_signal_curves_are_distinct(plot: PlotStripe) -> None:
    a = _make_active("a")
    b = _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    assert a.curve is not b.curve


# ---------------------------------------------------------------------------
# Shared X-axis (REQ-PLOT-010)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-010")
def test_add_signal_links_x_axis_to_main_plot(plot: PlotStripe) -> None:
    active = _make_active()
    plot.add_signal(active)
    assert active.view_box.linkedView(0) is plot._pi.vb


@pytest.mark.requirement("REQ-PLOT-010")
def test_zoom_to_x_range_moves_all_signal_viewboxes_in_lockstep(plot: PlotStripe) -> None:
    a = _make_active("a")
    b = _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)

    plot.zoom_to_x_range(2.0, 8.0)

    assert a.view_box.viewRange()[0] == pytest.approx(plot._pi.vb.viewRange()[0])
    assert b.view_box.viewRange()[0] == pytest.approx(plot._pi.vb.viewRange()[0])


# ---------------------------------------------------------------------------
# Rendering performance on large recordings (REQ-NFR-050/051)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-NFR-050")
def test_add_signal_enables_curve_downsampling(plot: PlotStripe) -> None:
    active = _make_active()
    plot.add_signal(active)
    assert active.curve.opts["autoDownsample"] is True
    assert active.curve.opts["downsampleMethod"] == "peak"


@pytest.mark.requirement("REQ-NFR-051")
def test_curve_data_is_full_resolution_despite_downsampling(plot: PlotStripe) -> None:
    """Downsampling (above) is a pyqtgraph rendering optimization only — the
    curve still receives every sample, and cursor/interpolation code reads
    from active.data directly, never from a simplified rendering."""
    active = _make_active(n=5000)
    plot.add_signal(active)
    x_data, y_data = active.curve.getData()
    assert len(x_data) == len(active.data.timestamps) == 5000
    assert np.array_equal(y_data, active.data.samples)


# ---------------------------------------------------------------------------
# remove_signal
# ---------------------------------------------------------------------------

def test_remove_signal_clears_curve(plot: PlotStripe) -> None:
    active = _make_active()
    plot.add_signal(active)
    plot.remove_signal(active)
    assert active.curve is None


def test_remove_signal_clears_view_box(plot: PlotStripe) -> None:
    active = _make_active()
    plot.add_signal(active)
    plot.remove_signal(active)
    assert active.view_box is None


def test_remove_signal_removed_from_data(plot: PlotStripe) -> None:
    active = _make_active()
    plot.add_signal(active)
    plot.remove_signal(active)
    assert active not in plot._data


@pytest.mark.requirement("REQ-PLOT-023")
def test_remove_signal_noop_for_unknown(plot: PlotStripe) -> None:
    stranger = _make_active("stranger")
    plot.remove_signal(stranger)  # must not raise


def test_remove_one_of_multiple(plot: PlotStripe) -> None:
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


def test_add_after_remove(plot: PlotStripe) -> None:
    active = _make_active()
    plot.add_signal(active)
    plot.remove_signal(active)
    plot.add_signal(active)
    assert active.curve is not None
    assert active in plot._data


# ---------------------------------------------------------------------------
# zoom_to_fit
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-053")
def test_zoom_to_fit_empty_is_noop(plot: PlotStripe) -> None:
    plot.zoom_to_fit()  # must not raise


@pytest.mark.requirement("REQ-PLOT-053")
def test_zoom_to_fit_with_signals_no_crash(plot: PlotStripe) -> None:
    for i in range(3):
        plot.add_signal(_make_active(f"s{i}"))
    plot.zoom_to_fit()  # must not raise


# ---------------------------------------------------------------------------
# recolor_signal
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-120")
def test_recolor_updates_active_color(plot: PlotStripe) -> None:
    active = _make_active(color=QColor(255, 0, 0))
    plot.add_signal(active)
    new_color = QColor(0, 0, 255)
    plot.recolor_signal(active, new_color)
    assert active.color == new_color


@pytest.mark.requirement("REQ-PLOT-120")
def test_recolor_updates_curve_pen(plot: PlotStripe) -> None:
    active = _make_active(color=QColor(255, 0, 0))
    plot.add_signal(active)
    new_color = QColor(0, 200, 50)
    plot.recolor_signal(active, new_color)
    assert active.curve.opts["pen"].color().name() == new_color.name()


@pytest.mark.requirement("REQ-PLOT-023")
def test_recolor_noop_for_unknown(plot: PlotStripe) -> None:
    stranger = _make_active()
    plot.recolor_signal(stranger, QColor(0, 255, 0))  # must not raise


@pytest.mark.requirement("REQ-PLOT-120")
def test_recolor_does_not_affect_other_signals(plot: PlotStripe) -> None:
    a = _make_active("a", color=QColor(255, 0, 0))
    b = _make_active("b", color=QColor(0, 0, 255))
    plot.add_signal(a)
    plot.add_signal(b)
    plot.recolor_signal(a, QColor(0, 255, 0))
    assert b.color == QColor(0, 0, 255)


# ---------------------------------------------------------------------------
# _SignalAxisItem tick formatting
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-012")
def test_float_signal_uses_float_axis(plot: PlotStripe) -> None:
    active = _make_active()  # float64 samples
    plot.add_signal(active)
    axis = plot._data[active].axis
    assert not axis._integer_ticks


@pytest.mark.requirement("REQ-PLOT-013")
def test_integer_signal_uses_integer_axis(plot: PlotStripe) -> None:
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


@pytest.mark.requirement("REQ-PLOT-012")
def test_float_tick_strings_use_g_format() -> None:
    axis = _SignalAxisItem("left")
    result = axis.tickStrings([256.000000007, 0.001234567, -3.14159], 1.0, 1.0)
    assert result == ["256", "0.00123457", "-3.14159"]


@pytest.mark.requirement("REQ-PLOT-013")
def test_integer_tick_strings_are_plain_ints() -> None:
    axis = _SignalAxisItem("left", integer_ticks=True)
    result = axis.tickStrings([1.0, 2.0, 7.0, -1.0], 1.0, 1.0)
    assert result == ["1", "2", "7", "-1"]


@pytest.mark.requirement("REQ-PLOT-013")
def test_integer_tick_values_no_fractions(plot: PlotStripe) -> None:
    axis = _SignalAxisItem("left", integer_ticks=True)
    # Ask for ticks across range 0–8 (gear signal)
    ticks = axis.tickValues(0.0, 8.0, 300)
    all_values = [v for _, vals in ticks for v in vals]
    # Every tick must be a whole number
    assert all(v == int(v) for v in all_values)


@pytest.mark.requirement("REQ-PLOT-013")
def test_integer_tick_values_no_duplicates(plot: PlotStripe) -> None:
    axis = _SignalAxisItem("left", integer_ticks=True)
    ticks = axis.tickValues(-1.0, 8.0, 300)
    all_values = [v for _, vals in ticks for v in vals]
    assert len(all_values) == len(set(all_values))


# ---------------------------------------------------------------------------
# _SignalAxisItem / set_enum_display_yaxis — enum Y-axis labels (REQ-PLOT-014)
# ---------------------------------------------------------------------------

def _make_active_enum(name: str = "ign") -> ActiveSignal:
    t = np.linspace(0.0, 1.0, 10)
    data = SignalData(timestamps=t, samples=np.round(np.linspace(0.0, 1.0, 10)))
    meta = SignalMetadata(
        name=name, unit="", group_index=0, channel_index=0,
        enum_map={0: "OFF", 1: "ON"},
    )
    return ActiveSignal(data=data, metadata=meta, color=QColor(100, 100, 200))


@pytest.mark.requirement("REQ-PLOT-014")
def test_axis_enum_display_off_shows_raw_integers() -> None:
    axis = _SignalAxisItem("left", integer_ticks=True, enum_map={0: "OFF", 1: "ON"})
    assert axis.tickStrings([0.0, 1.0], 1.0, 1.0) == ["0", "1"]


@pytest.mark.requirement("REQ-PLOT-014")
def test_axis_enum_display_on_shows_labels() -> None:
    axis = _SignalAxisItem("left", integer_ticks=True, enum_map={0: "OFF", 1: "ON"})
    axis.set_enum_display(True)
    assert axis.tickStrings([0.0, 1.0], 1.0, 1.0) == ["OFF", "ON"]


@pytest.mark.requirement("REQ-PLOT-014")
def test_axis_enum_display_falls_back_for_unmapped_value() -> None:
    axis = _SignalAxisItem("left", integer_ticks=True, enum_map={0: "OFF"})
    axis.set_enum_display(True)
    assert axis.tickStrings([0.0, 5.0], 1.0, 1.0) == ["OFF", "5"]


@pytest.mark.requirement("REQ-PLOT-014")
def test_set_enum_display_yaxis_enables_axis(plot: PlotStripe) -> None:
    active = _make_active_enum()
    plot.add_signal(active)
    plot.set_enum_display_yaxis(active, True)
    assert plot._data[active].axis._enum_display is True


@pytest.mark.requirement("REQ-PLOT-014")
def test_set_enum_display_yaxis_disables_axis(plot: PlotStripe) -> None:
    active = _make_active_enum()
    plot.add_signal(active)
    plot.set_enum_display_yaxis(active, True)
    plot.set_enum_display_yaxis(active, False)
    assert plot._data[active].axis._enum_display is False


@pytest.mark.requirement("REQ-PLOT-023")
def test_set_enum_display_yaxis_noop_for_unknown(plot: PlotStripe) -> None:
    stranger = _make_active_enum("x")
    plot.set_enum_display_yaxis(stranger, True)  # must not raise


@pytest.mark.requirement("REQ-PLOT-014")
def test_set_enum_display_yaxis_merged_any_on_rule(plot: PlotStripe) -> None:
    a = _make_active_enum("a")
    b = _make_active_enum("b")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.merge_signals([a, b])
    a.enum_display_yaxis = False
    b.enum_display_yaxis = True

    plot.set_enum_display_yaxis(a, False)

    # Shared axis: any member enabled -> labels shown, even though a's own
    # request was False.
    assert plot._data[a].axis._enum_display is True


# ---------------------------------------------------------------------------
# Drag and drop — signals
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-BROWSER-031")
def test_signals_dropped_emitted_on_signal_mime(plot: PlotStripe, qtbot: QtBot) -> None:
    locs = [(0, 1), (1, 2)]
    mime = QMimeData()
    mime.setData(SIGNAL_MIME_TYPE, QByteArray(encode_signal_payload(0, locs)))
    with qtbot.waitSignal(plot.signals_dropped) as blocker:
        plot.eventFilter(plot._pw.viewport(), _drop_event(mime))
    assert blocker.args[0] == [(0, 1), (1, 2)]
    assert blocker.args[1] == 0


@pytest.mark.requirement("REQ-FILE-031")
def test_signals_dropped_carries_measurement_index(plot: PlotStripe, qtbot: QtBot) -> None:
    mime = QMimeData()
    mime.setData(SIGNAL_MIME_TYPE, QByteArray(encode_signal_payload(2, [(0, 1)])))
    with qtbot.waitSignal(plot.signals_dropped) as blocker:
        plot.eventFilter(plot._pw.viewport(), _drop_event(mime))
    assert blocker.args[1] == 2


@pytest.mark.requirement("REQ-BROWSER-031")
def test_signals_dropped_not_emitted_for_wrong_mime(
    plot: PlotStripe, qtbot: QtBot
) -> None:
    mime = QMimeData()
    mime.setText("irrelevant")
    with qtbot.assertNotEmitted(plot.signals_dropped):
        plot.eventFilter(plot._pw.viewport(), _drop_event(mime))


# ---------------------------------------------------------------------------
# Drag and drop — active-signal row moved from the Active Signals Table (#116)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-281")
def test_drag_enter_accepted_for_row_mime(plot: PlotStripe) -> None:
    mime = QMimeData()
    mime.setData(ROW_MIME_TYPE, QByteArray(encode_row_payload([])))
    event = _drag_enter_event(mime)
    plot.eventFilter(plot._pw.viewport(), event)
    event.acceptProposedAction.assert_called_once()


@pytest.mark.requirement("REQ-PLOT-281")
def test_active_signals_dropped_emitted_on_row_mime(plot: PlotStripe, qtbot: QtBot) -> None:
    active = _make_active()
    mime = QMimeData()
    mime.setData(ROW_MIME_TYPE, QByteArray(encode_row_payload([active])))
    with qtbot.waitSignal(plot.active_signals_dropped) as blocker:
        plot.eventFilter(plot._pw.viewport(), _drop_event(mime))
    assert blocker.args[0] == {id(active)}


@pytest.mark.requirement("REQ-PLOT-281")
def test_active_signals_dropped_not_emitted_for_wrong_mime(
    plot: PlotStripe, qtbot: QtBot
) -> None:
    mime = QMimeData()
    mime.setText("irrelevant")
    with qtbot.assertNotEmitted(plot.active_signals_dropped):
        plot.eventFilter(plot._pw.viewport(), _drop_event(mime))


# ---------------------------------------------------------------------------
# Drag and drop — file
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-FILE-011")
def test_file_dropped_emitted_on_mdf_url(
    plot: PlotStripe, qtbot: QtBot, tmp_path: Path
) -> None:
    path = tmp_path / "data.mf4"
    path.touch()
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    with qtbot.waitSignal(plot.file_dropped) as blocker:
        plot.eventFilter(plot._pw.viewport(), _drop_event(mime))
    assert blocker.args[0] == path


@pytest.mark.requirement("REQ-FILE-011")
def test_file_dropped_not_emitted_for_non_mdf(
    plot: PlotStripe, qtbot: QtBot, tmp_path: Path
) -> None:
    path = tmp_path / "data.csv"
    path.touch()
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    with qtbot.assertNotEmitted(plot.file_dropped):
        plot.eventFilter(plot._pw.viewport(), _drop_event(mime))


@pytest.mark.requirement("REQ-BROWSER-031")
def test_drag_enter_accepted_for_signal_mime(plot: PlotStripe) -> None:
    mime = QMimeData()
    mime.setData(SIGNAL_MIME_TYPE, QByteArray(b"[]"))
    event = _drag_enter_event(mime)
    plot.eventFilter(plot._pw.viewport(), event)
    event.acceptProposedAction.assert_called_once()


@pytest.mark.requirement("REQ-FILE-011")
def test_drag_enter_accepted_for_mdf_url(plot: PlotStripe, tmp_path: Path) -> None:
    path = tmp_path / "data.mf4"
    path.touch()
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(path))])
    event = _drag_enter_event(mime)
    plot.eventFilter(plot._pw.viewport(), event)
    event.acceptProposedAction.assert_called_once()


def test_drag_enter_ignored_for_unknown_mime(plot: PlotStripe) -> None:
    mime = QMimeData()
    mime.setText("not a signal or file")
    event = _drag_enter_event(mime)
    plot.eventFilter(plot._pw.viewport(), event)
    event.ignore.assert_called_once()


# ---------------------------------------------------------------------------
# zoom_y_to_view
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-054")
def test_zoom_y_to_view_returns_false_when_empty(plot: PlotStripe) -> None:
    assert plot.zoom_y_to_view() is False


@pytest.mark.requirement("REQ-PLOT-054")
def test_zoom_y_to_view_returns_true_with_signals(plot: PlotStripe) -> None:
    plot.add_signal(_make_active())
    assert plot.zoom_y_to_view() is True


@pytest.mark.requirement("REQ-PLOT-056")
def test_zoom_y_to_view_constant_signal_expands_range(plot: PlotStripe) -> None:
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

@pytest.mark.requirement("REQ-PLOT-053")
def test_zoom_to_fit_sets_x_range(plot: PlotStripe) -> None:
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
# Multi-measurement offset (#101) — display_timestamps used for X-positioning
# ---------------------------------------------------------------------------

def _make_measurement(offset_s: float = 0.0):
    from mdf_viewer.model.loaded_measurement import LoadedMeasurement
    from mdf_viewer.model.mdf_loader import MdfLoader
    from mdf_viewer.model.measurement import MeasurementInfo

    return LoadedMeasurement(
        loader=MdfLoader(), info=MeasurementInfo(file_name="run.mf4"), label="run",
        offset_s=offset_s,
    )


@pytest.mark.requirement("REQ-PLOT-304")
def test_add_signal_renders_curve_at_offset_timestamps(plot: PlotStripe) -> None:
    measurement = _make_measurement(offset_s=5.0)
    t = np.array([0.0, 1.0, 2.0])
    data = SignalData(timestamps=t, samples=t)
    meta = SignalMetadata(name="x", group_index=0, channel_index=0)
    active = ActiveSignal(data=data, metadata=meta, color=QColor(200, 100, 50), measurement=measurement)
    plot.add_signal(active)
    # xData is the raw stored dataset; getData() would return the
    # view-clipped/downsampled display dataset instead (not what we want to
    # verify here — see test_curve_data_is_full_resolution_despite_downsampling
    # above for why that distinction matters).
    assert np.array_equal(active.curve.xData, np.array([5.0, 6.0, 7.0]))


@pytest.mark.requirement("REQ-PLOT-304")
def test_zoom_to_fit_uses_offset_shifted_range(plot: PlotStripe) -> None:
    measurement = _make_measurement(offset_s=10.0)
    t = np.linspace(0.5, 2.5, 50)
    data = SignalData(timestamps=t, samples=np.ones(50))
    meta = SignalMetadata(name="x", group_index=0, channel_index=0)
    active = ActiveSignal(data=data, metadata=meta, color=QColor(200, 100, 50), measurement=measurement)
    plot.add_signal(active)
    plot.zoom_to_fit()
    x_range = plot._pi.vb.viewRange()[0]
    assert x_range[0] <= 10.5
    assert x_range[1] >= 12.5


@pytest.mark.requirement("REQ-PLOT-304")
def test_swimlanes_visible_mask_uses_offset_shifted_range(plot: PlotStripe) -> None:
    measurement = _make_measurement(offset_s=100.0)
    t = np.linspace(0.0, 1.0, 50)
    data = SignalData(timestamps=t, samples=np.linspace(0.0, 10.0, 50))
    meta = SignalMetadata(name="x", group_index=0, channel_index=0)
    active = ActiveSignal(data=data, metadata=meta, color=QColor(200, 100, 50), measurement=measurement)
    plot.add_signal(active)
    plot._pi.vb.setXRange(100.0, 101.0, padding=0)
    assert plot.swimlanes([active])
    y_min, y_max = active.view_box.viewRange()[1]
    # With the view range matching the offset-shifted data, the visible mask
    # should include (nearly) the full sample range, not treat it as empty.
    assert y_max - y_min > 5.0


@pytest.mark.requirement("REQ-PLOT-304")
def test_zoom_y_to_view_visible_mask_uses_offset_shifted_range(plot: PlotStripe) -> None:
    measurement = _make_measurement(offset_s=100.0)
    t = np.linspace(0.0, 1.0, 50)
    data = SignalData(timestamps=t, samples=np.linspace(0.0, 10.0, 50))
    meta = SignalMetadata(name="x", group_index=0, channel_index=0)
    active = ActiveSignal(data=data, metadata=meta, color=QColor(200, 100, 50), measurement=measurement)
    plot.add_signal(active)
    plot._pi.vb.setXRange(100.0, 101.0, padding=0)
    assert plot.zoom_y_to_view()
    y_min, y_max = active.view_box.viewRange()[1]
    assert y_max - y_min > 5.0


@pytest.mark.requirement("REQ-PLOT-304")
def test_refresh_signal_data_reapplies_display_timestamps(plot: PlotStripe) -> None:
    measurement = _make_measurement(offset_s=0.0)
    t = np.array([0.0, 1.0, 2.0])
    data = SignalData(timestamps=t, samples=t)
    meta = SignalMetadata(name="x", group_index=0, channel_index=0)
    active = ActiveSignal(data=data, metadata=meta, color=QColor(200, 100, 50), measurement=measurement)
    plot.add_signal(active)
    assert np.array_equal(active.curve.xData, np.array([0.0, 1.0, 2.0]))

    measurement.offset_s = 5.0
    plot.refresh_signal_data(active)
    assert np.array_equal(active.curve.xData, np.array([5.0, 6.0, 7.0]))


def test_refresh_signal_data_noop_when_signal_not_present(plot: PlotStripe) -> None:
    active = _make_active()
    plot.refresh_signal_data(active)  # must not raise


# ---------------------------------------------------------------------------
# Per-measurement X-axis rows + drag-to-offset (#101)
# ---------------------------------------------------------------------------

def _make_measurement_axis(measurement, on_offset_changed=None, vb=None, draggable=True):
    from mdf_viewer.view.plot_stripe import _MeasurementAxisItem
    return _MeasurementAxisItem(
        measurement=measurement, on_offset_changed=on_offset_changed,
        draggable=draggable, linkView=vb or MagicMock(),
    )


@pytest.mark.requirement("REQ-PLOT-300")
def test_set_measurement_axes_creates_one_row_per_measurement(plot: PlotStripe) -> None:
    m1 = _make_measurement(offset_s=0.0)
    m2 = _make_measurement(offset_s=0.0)
    plot.set_measurement_axes([m1, m2])
    assert len(plot._measurement_axes) == 2


@pytest.mark.requirement("REQ-PLOT-301")
def test_set_measurement_axes_empty_clears_rows(plot: PlotStripe) -> None:
    m1 = _make_measurement()
    plot.set_measurement_axes([m1])
    assert len(plot._measurement_axes) == 1
    plot.set_measurement_axes([])
    assert plot._measurement_axes == []


@pytest.mark.requirement("REQ-PLOT-301")
def test_set_measurement_axes_rebuild_replaces_rows(plot: PlotStripe) -> None:
    m1 = _make_measurement()
    plot.set_measurement_axes([m1])
    first_axis = plot._measurement_axes[0]
    m2 = _make_measurement()
    plot.set_measurement_axes([m2])
    assert len(plot._measurement_axes) == 1
    assert plot._measurement_axes[0] is not first_axis


@pytest.mark.requirement("REQ-PLOT-300")
def test_measurement_axis_tick_strings_subtract_offset() -> None:
    m1 = _make_measurement(offset_s=10.0)
    axis = _make_measurement_axis(m1)
    assert axis.tickStrings([15.0], 1.0, 1.0) == ["5"]


def test_measurement_axis_tick_strings_zero_offset() -> None:
    m1 = _make_measurement(offset_s=0.0)
    axis = _make_measurement_axis(m1)
    assert axis.tickStrings([15.0], 1.0, 1.0) == ["15"]


@pytest.mark.requirement("REQ-PLOT-303")
def test_measurement_axis_drag_updates_offset(qtbot: QtBot) -> None:
    m1 = _make_measurement(offset_s=0.0)
    vb = MagicMock()
    vb.viewPixelSize.return_value = (0.1, 0.1)  # 0.1 data units per pixel
    received = []
    axis = _make_measurement_axis(m1, on_offset_changed=received.append, vb=vb)

    start = MagicMock()
    start.button.return_value = Qt.MouseButton.LeftButton
    start.isStart.return_value = True
    start.buttonDownScenePos.return_value = QPoint(0, 0)
    start.scenePos.return_value = QPoint(0, 0)
    axis.mouseDragEvent(start)

    move = MagicMock()
    move.button.return_value = Qt.MouseButton.LeftButton
    move.isStart.return_value = False
    move.buttonDownScenePos.return_value = QPoint(0, 0)
    move.scenePos.return_value = QPoint(50, 0)
    axis.mouseDragEvent(move)

    assert m1.offset_s == pytest.approx(5.0)  # 50 px * 0.1 data-units/px
    assert received == [m1, m1]
    move.accept.assert_called_once()


@pytest.mark.requirement("REQ-PLOT-303")
def test_measurement_axis_drag_never_touches_linked_view_pan() -> None:
    """Dragging the axis must never call the linked ViewBox's own
    mouseDragEvent — that would pan the shared X range, which REQ-PLOT-303
    reserves exclusively for interior drags/wheel zoom."""
    m1 = _make_measurement(offset_s=0.0)
    vb = MagicMock()
    vb.viewPixelSize.return_value = (0.1, 0.1)
    axis = _make_measurement_axis(m1, vb=vb)

    event = MagicMock()
    event.button.return_value = Qt.MouseButton.LeftButton
    event.isStart.return_value = True
    event.buttonDownScenePos.return_value = QPoint(0, 0)
    event.scenePos.return_value = QPoint(30, 0)
    axis.mouseDragEvent(event)

    vb.mouseDragEvent.assert_not_called()


def test_measurement_axis_drag_ignores_non_left_button() -> None:
    m1 = _make_measurement(offset_s=0.0)
    vb = MagicMock()
    axis = _make_measurement_axis(m1, vb=vb)
    event = MagicMock()
    event.button.return_value = Qt.MouseButton.RightButton
    axis.mouseDragEvent(event)
    event.ignore.assert_called_once()
    assert m1.offset_s == 0.0


@pytest.mark.requirement("REQ-PLOT-314")
def test_measurement_axis_drag_noop_when_not_draggable() -> None:
    m1 = _make_measurement(offset_s=0.0)
    vb = MagicMock()
    received = []
    axis = _make_measurement_axis(m1, on_offset_changed=received.append, vb=vb, draggable=False)
    event = MagicMock()
    event.button.return_value = Qt.MouseButton.LeftButton
    axis.mouseDragEvent(event)
    event.ignore.assert_called_once()
    event.accept.assert_not_called()
    assert m1.offset_s == 0.0
    assert received == []


@pytest.mark.requirement("REQ-PLOT-314")
def test_set_measurement_axes_default_draggable_true(plot: PlotStripe) -> None:
    m1 = _make_measurement(offset_s=0.0)
    plot.set_measurement_axes([m1])
    axis = plot._measurement_axes[0]
    event = MagicMock()
    event.button.return_value = Qt.MouseButton.LeftButton
    event.isStart.return_value = True
    event.buttonDownScenePos.return_value = QPoint(0, 0)
    event.scenePos.return_value = QPoint(30, 0)
    axis.mouseDragEvent(event)
    event.accept.assert_called_once()


@pytest.mark.requirement("REQ-PLOT-314")
def test_set_measurement_axes_draggable_false_propagates_to_rows(plot: PlotStripe) -> None:
    m1 = _make_measurement(offset_s=0.0)
    plot.set_measurement_axes([m1], draggable=False)
    axis = plot._measurement_axes[0]
    event = MagicMock()
    event.button.return_value = Qt.MouseButton.LeftButton
    axis.mouseDragEvent(event)
    event.ignore.assert_called_once()
    assert m1.offset_s == 0.0


# ---------------------------------------------------------------------------
# Synchronize/Un-sync button (#102)
# ---------------------------------------------------------------------------

def test_sync_button_hidden_by_default(plot: PlotStripe) -> None:
    # isHidden() (not isVisible()) — the widget's own explicit shown/hidden
    # state, independent of whether the top-level window itself is shown,
    # which this test fixture never does.
    assert plot._sync_button.isHidden() is True


@pytest.mark.requirement("REQ-PLOT-310")
def test_set_measurement_sync_control_visible_shows_button_with_label(plot: PlotStripe) -> None:
    plot.set_measurement_sync_control(visible=True, synchronized=False)
    assert plot._sync_button.isHidden() is False
    assert plot._sync_button.text() == "Sync"

    plot.set_measurement_sync_control(visible=True, synchronized=True)
    assert plot._sync_button.text() == "Un-Sync"


@pytest.mark.requirement("REQ-PLOT-316")
def test_set_measurement_sync_control_invisible_hides_button(plot: PlotStripe) -> None:
    plot.set_measurement_sync_control(visible=True, synchronized=False)
    assert plot._sync_button.isHidden() is False
    plot.set_measurement_sync_control(visible=False, synchronized=True)
    assert plot._sync_button.isHidden() is True


def test_sync_button_click_calls_on_toggle_callback(plot: PlotStripe) -> None:
    cb = MagicMock()
    plot.set_measurement_sync_control(visible=True, synchronized=False, on_toggle=cb)
    plot._sync_button.click()
    cb.assert_called_once()


def test_sync_button_click_noop_when_no_callback(plot: PlotStripe) -> None:
    plot.set_measurement_sync_control(visible=True, synchronized=False, on_toggle=None)
    plot._sync_button.click()  # must not raise


def test_sync_button_reraised_after_adding_a_signal(plot: PlotStripe) -> None:
    """Found live: adding a signal changes the axis layout without firing a
    Resize event on the viewport, and Qt's QGraphicsView appears to
    re-raise its own viewport on scene changes — burying the sync button
    (a sibling widget) behind it again unless it's explicitly re-raised
    too. _update_view_geometries (called at the end of add_signal) is the
    fix; this regression-tests that hook, not just the resize path."""
    plot.set_measurement_sync_control(visible=True, synchronized=False)
    with patch.object(plot, "_reposition_sync_button") as mock_reposition:
        plot.add_signal(_make_active())
    mock_reposition.assert_called()
# _ViewBox wheel event — axis routing (bug #34)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-050")
def test_wheel_axis_none_forces_x_zoom(plot: PlotStripe) -> None:
    """Wheel over plot interior (axis=None) must zoom X only."""
    import pyqtgraph as pg
    from unittest.mock import MagicMock, patch
    ev = MagicMock()
    with patch.object(pg.ViewBox, 'wheelEvent') as mock_wheel:
        plot._pi.vb.wheelEvent(ev, axis=None)
        mock_wheel.assert_called_once_with(ev, axis=0)


@pytest.mark.requirement("REQ-PLOT-050")
def test_wheel_axis_0_forces_x_zoom(plot: PlotStripe) -> None:
    """Wheel with explicit axis=0 must also zoom X only."""
    import pyqtgraph as pg
    from unittest.mock import MagicMock, patch
    ev = MagicMock()
    with patch.object(pg.ViewBox, 'wheelEvent') as mock_wheel:
        plot._pi.vb.wheelEvent(ev, axis=0)
        mock_wheel.assert_called_once_with(ev, axis=0)


@pytest.mark.requirement("REQ-PLOT-050")
def test_wheel_axis_1_allows_y_zoom(plot: PlotStripe) -> None:
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

@pytest.mark.requirement("REQ-PLOT-052")
def test_zoom_rect_updates_all_signal_viewboxes(plot: PlotStripe) -> None:
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


@pytest.mark.requirement("REQ-PLOT-052")
def test_zoom_rect_noop_when_no_signals(plot: PlotStripe) -> None:
    """_on_zoom_rect_finished with no signals must not raise."""
    plot._on_zoom_rect_finished(QRectF(0, 0, 100, 100))  # must not raise


def test_zoom_rect_signal_connected_on_add(plot: PlotStripe) -> None:
    """zoom_rect_finished on a signal ViewBox must trigger _on_zoom_rect_finished."""
    active = _make_active()
    plot.add_signal(active)
    vb = plot._data[active].view_box
    ptr_before = vb.axHistoryPointer

    # Emit from the ViewBox itself — should loop back and update its own history.
    vb.zoom_rect_finished.emit(QRectF(0, 0, 100, 100))

    assert vb.axHistoryPointer == ptr_before + 1


def test_zoom_rect_signal_disconnected_on_remove(plot: PlotStripe) -> None:
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

@pytest.mark.requirement("REQ-PLOT-055")
def test_swimlanes_returns_false_when_no_signals(plot: PlotStripe) -> None:
    assert plot.swimlanes([]) is False


@pytest.mark.requirement("REQ-PLOT-055")
def test_swimlanes_returns_false_when_data_empty(plot: PlotStripe) -> None:
    assert plot.swimlanes([_make_active()]) is False


@pytest.mark.requirement("REQ-PLOT-055")
def test_swimlanes_returns_true_with_signals(plot: PlotStripe) -> None:
    a = _make_active("a")
    plot.add_signal(a)
    plot.show()
    assert plot.swimlanes([a]) is True


@pytest.mark.requirement("REQ-PLOT-055")
def test_swimlanes_sets_y_range_per_signal(plot: PlotStripe) -> None:
    a = _make_active("a")
    b = _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.show()
    # Must not raise; each ViewBox gets an independent Y range
    result = plot.swimlanes([a, b])
    assert result is True


@pytest.mark.requirement("REQ-PLOT-023")
def test_swimlanes_skips_unknown_signals(plot: PlotStripe) -> None:
    a = _make_active("a")
    plot.add_signal(a)
    plot.show()
    stranger = _make_active("x")
    # Passing an unknown signal in the list must not raise
    assert plot.swimlanes([a, stranger]) is True



# ---------------------------------------------------------------------------
# set_display_mode
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-023")
def test_set_display_mode_noop_for_unknown(plot: PlotStripe) -> None:
    stranger = _make_active("x")
    plot.set_display_mode(stranger, "marker", "circle")  # must not raise


@pytest.mark.requirement("REQ-PLOT-120")
def test_set_display_mode_to_marker_removes_pen(plot: PlotStripe) -> None:
    from PyQt6.QtCore import Qt
    active = _make_active()
    plot.add_signal(active)
    plot.set_display_mode(active, "marker", "circle")
    # setPen(None) stores QPen(NoPen), not Python None
    assert active.curve.opts["pen"].style() == Qt.PenStyle.NoPen


@pytest.mark.requirement("REQ-PLOT-120")
def test_set_display_mode_to_line_restores_pen(plot: PlotStripe) -> None:
    from PyQt6.QtCore import Qt
    active = _make_active()
    plot.add_signal(active)
    plot.set_display_mode(active, "marker", "circle")
    plot.set_display_mode(active, "line", "circle")
    assert active.curve.opts["pen"].style() != Qt.PenStyle.NoPen


@pytest.mark.requirement("REQ-PLOT-120")
def test_set_display_mode_line_clears_symbol(plot: PlotStripe) -> None:
    active = _make_active()
    plot.add_signal(active)
    plot.set_display_mode(active, "line_marker", "circle")
    plot.set_display_mode(active, "line", "circle")
    assert active.curve.opts["symbol"] is None


@pytest.mark.requirement("REQ-PLOT-120")
def test_set_display_mode_line_marker_sets_symbol(plot: PlotStripe) -> None:
    active = _make_active()
    plot.add_signal(active)
    plot.set_display_mode(active, "line_marker", "square")
    assert active.curve.opts["symbol"] == "s"


@pytest.mark.requirement("REQ-PLOT-120")
def test_set_display_mode_marker_only_sets_symbol(plot: PlotStripe) -> None:
    active = _make_active()
    plot.add_signal(active)
    plot.set_display_mode(active, "marker", "diamond")
    assert active.curve.opts["symbol"] == "d"


@pytest.mark.requirement("REQ-PLOT-120")
def test_set_display_mode_cross_uses_correct_pg_symbol(plot: PlotStripe) -> None:
    active = _make_active()
    plot.add_signal(active)
    plot.set_display_mode(active, "marker", "cross")
    assert active.curve.opts["symbol"] == "+"


# ---------------------------------------------------------------------------
# set_line_width
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-023")
def test_set_line_width_noop_for_unknown(plot: PlotStripe) -> None:
    stranger = _make_active()
    plot.set_line_width(stranger, 3)  # must not raise


@pytest.mark.requirement("REQ-PLOT-120")
def test_set_line_width_updates_active_field(plot: PlotStripe) -> None:
    active = _make_active()
    plot.add_signal(active)
    plot.set_line_width(active, 4)
    assert active.line_width == 4


@pytest.mark.requirement("REQ-PLOT-120")
def test_set_line_width_updates_pen_width_in_line_mode(plot: PlotStripe) -> None:
    active = _make_active()
    plot.add_signal(active)
    plot.set_line_width(active, 5)
    assert active.curve.opts["pen"].width() == 5


@pytest.mark.requirement("REQ-PLOT-121")
def test_set_line_width_no_pen_in_marker_only_mode(plot: PlotStripe) -> None:
    from PyQt6.QtCore import Qt
    active = _make_active()
    active.display_mode = "marker"
    plot.add_signal(active)
    plot.set_line_width(active, 3)
    pen = active.curve.opts["pen"]
    assert pen is None or pen.style() == Qt.PenStyle.NoPen


@pytest.mark.requirement("REQ-PLOT-120")
def test_set_line_width_updates_symbol_size_in_line_marker_mode(plot: PlotStripe) -> None:
    from mdf_viewer.view.plot_stripe import _symbol_size
    active = _make_active()
    active.display_mode = "line_marker"
    plot.add_signal(active)
    plot.set_line_width(active, 3)
    assert active.curve.opts["symbolSize"] == _symbol_size(3)


@pytest.mark.requirement("REQ-PLOT-120")
def test_add_signal_uses_line_width_from_active(plot: PlotStripe) -> None:
    active = _make_active()
    active.line_width = 5
    plot.add_signal(active)
    assert active.curve.opts["pen"].width() == 5


# ---------------------------------------------------------------------------
# set_line_style
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-023")
def test_set_line_style_noop_for_unknown(plot: PlotStripe) -> None:
    stranger = _make_active()
    plot.set_line_style(stranger, "dashes")  # must not raise


@pytest.mark.requirement("REQ-PLOT-120")
def test_set_line_style_updates_active_field(plot: PlotStripe) -> None:
    active = _make_active()
    plot.add_signal(active)
    plot.set_line_style(active, "dots")
    assert active.line_style == "dots"


@pytest.mark.requirement("REQ-PLOT-120")
def test_set_line_style_updates_pen_style(plot: PlotStripe) -> None:
    from PyQt6.QtCore import Qt
    active = _make_active()
    plot.add_signal(active)
    plot.set_line_style(active, "dashes")
    assert active.curve.opts["pen"].style() == Qt.PenStyle.DashLine


@pytest.mark.requirement("REQ-PLOT-120")
def test_set_line_style_all_styles_map_correctly(plot: PlotStripe) -> None:
    from PyQt6.QtCore import Qt
    expected = {
        "solid":    Qt.PenStyle.SolidLine,
        "dashes":   Qt.PenStyle.DashLine,
        "dots":     Qt.PenStyle.DotLine,
        "dash-dot": Qt.PenStyle.DashDotLine,
    }
    for style, pen_style in expected.items():
        active = _make_active()
        plot.add_signal(active)
        plot.set_line_style(active, style)
        assert active.curve.opts["pen"].style() == pen_style
        plot.remove_signal(active)


@pytest.mark.requirement("REQ-PLOT-121")
def test_set_line_style_noop_in_marker_only_mode(plot: PlotStripe) -> None:
    from PyQt6.QtCore import Qt
    active = _make_active()
    active.display_mode = "marker"
    plot.add_signal(active)
    plot.set_line_style(active, "dashes")
    pen = active.curve.opts["pen"]
    assert pen is None or pen.style() == Qt.PenStyle.NoPen


@pytest.mark.requirement("REQ-PLOT-120")
def test_add_signal_uses_line_style_from_active(plot: PlotStripe) -> None:
    from PyQt6.QtCore import Qt
    active = _make_active()
    active.line_style = "dots"
    plot.add_signal(active)
    assert active.curve.opts["pen"].style() == Qt.PenStyle.DotLine


@pytest.mark.requirement("REQ-PLOT-120")
def test_set_line_width_preserves_line_style(plot: PlotStripe) -> None:
    from PyQt6.QtCore import Qt
    active = _make_active()
    plot.add_signal(active)
    plot.set_line_style(active, "dashes")
    plot.set_line_width(active, 3)
    assert active.curve.opts["pen"].style() == Qt.PenStyle.DashLine


# ---------------------------------------------------------------------------
# set_selected_signals
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-044")
def test_set_selected_signals_boosts_pen_width(plot: PlotStripe) -> None:
    active = _make_active()
    plot.add_signal(active)
    plot.set_selected_signals([active])
    assert active.curve.opts["pen"].width() == active.line_width + 1


@pytest.mark.requirement("REQ-PLOT-044")
def test_set_selected_signals_restores_pen_on_deselect(plot: PlotStripe) -> None:
    active = _make_active()
    plot.add_signal(active)
    plot.set_selected_signals([active])
    plot.set_selected_signals([])
    assert active.curve.opts["pen"].width() == active.line_width


@pytest.mark.requirement("REQ-PLOT-043")
def test_set_selected_signals_raises_z_value(plot: PlotStripe) -> None:
    active = _make_active()
    plot.add_signal(active)
    plot.set_selected_signals([active])
    assert active.view_box.zValue() >= 1


@pytest.mark.requirement("REQ-PLOT-043")
def test_set_selected_signals_restores_z_on_deselect(plot: PlotStripe) -> None:
    active = _make_active()
    plot.add_signal(active)
    plot.set_selected_signals([active])
    plot.set_selected_signals([])
    assert active.view_box.zValue() == 0


@pytest.mark.requirement("REQ-PLOT-043")
def test_set_selected_signals_latest_has_highest_z(plot: PlotStripe) -> None:
    a1 = _make_active("a")
    a2 = _make_active("b")
    plot.add_signal(a1)
    plot.add_signal(a2)
    plot.set_selected_signals([a1, a2])
    assert a2.view_box.zValue() > a1.view_box.zValue()


@pytest.mark.requirement("REQ-PLOT-043")
def test_set_selected_signals_unselected_stays_at_zero(plot: PlotStripe) -> None:
    a1 = _make_active("a")
    a2 = _make_active("b")
    plot.add_signal(a1)
    plot.add_signal(a2)
    plot.set_selected_signals([a1])
    assert a2.view_box.zValue() == 0


@pytest.mark.requirement("REQ-PLOT-121")
def test_set_selected_signals_no_boost_in_marker_mode(plot: PlotStripe) -> None:
    from PyQt6.QtCore import Qt
    active = _make_active()
    active.display_mode = "marker"
    plot.add_signal(active)
    plot.set_selected_signals([active])
    pen = active.curve.opts["pen"]
    assert pen is None or pen.style() == Qt.PenStyle.NoPen


@pytest.mark.requirement("REQ-PLOT-044")
def test_recolor_preserves_boost_when_selected(plot: PlotStripe) -> None:
    active = _make_active()
    plot.add_signal(active)
    plot.set_selected_signals([active])
    plot.recolor_signal(active, QColor(100, 200, 100))
    assert active.curve.opts["pen"].width() == active.line_width + 1


@pytest.mark.requirement("REQ-PLOT-044")
def test_set_line_width_preserves_boost_when_selected(plot: PlotStripe) -> None:
    active = _make_active()
    plot.add_signal(active)
    plot.set_selected_signals([active])
    plot.set_line_width(active, 3)
    assert active.curve.opts["pen"].width() == 4  # 3 + 1 boost


@pytest.mark.requirement("REQ-PLOT-044")
def test_set_line_style_preserves_boost_when_selected(plot: PlotStripe) -> None:
    from PyQt6.QtCore import Qt
    active = _make_active()
    plot.add_signal(active)
    plot.set_selected_signals([active])
    plot.set_line_style(active, "dots")
    assert active.curve.opts["pen"].width() == active.line_width + 1
    assert active.curve.opts["pen"].style() == Qt.PenStyle.DotLine


@pytest.mark.requirement("REQ-PLOT-042")
def test_set_selected_signals_top_first_top_row_has_highest_z(plot: PlotStripe) -> None:
    """With top_first=True, index-0 signal gets the highest base Z."""
    a1 = _make_active("a")  # top row
    a2 = _make_active("b")  # bottom row
    plot.add_signal(a1)
    plot.add_signal(a2)
    plot.set_selected_signals([], all_signals=[a1, a2], top_first=True)
    assert a1.view_box.zValue() > a2.view_box.zValue()


@pytest.mark.requirement("REQ-PLOT-042")
def test_set_selected_signals_bottom_first_bottom_row_has_highest_z(plot: PlotStripe) -> None:
    """With top_first=False, last signal in the list gets the highest base Z."""
    a1 = _make_active("a")  # top row
    a2 = _make_active("b")  # bottom row
    plot.add_signal(a1)
    plot.add_signal(a2)
    plot.set_selected_signals([], all_signals=[a1, a2], top_first=False)
    assert a2.view_box.zValue() > a1.view_box.zValue()


@pytest.mark.requirement("REQ-PLOT-043")
def test_set_selected_signals_selected_above_unselected(plot: PlotStripe) -> None:
    """Selected signals' Z must exceed any unselected signal's Z."""
    a1 = _make_active("a")
    a2 = _make_active("b")
    plot.add_signal(a1)
    plot.add_signal(a2)
    plot.set_selected_signals([a1], all_signals=[a1, a2], top_first=True)
    assert a1.view_box.zValue() > a2.view_box.zValue()


@pytest.mark.requirement("REQ-PLOT-042")
def test_set_selected_signals_unselected_z_equals_position(plot: PlotStripe) -> None:
    """With top_first=True, unselected Z for row-0 is n, row-1 is n-1, …"""
    a1 = _make_active("a")  # index 0 → Z = 2
    a2 = _make_active("b")  # index 1 → Z = 1
    plot.add_signal(a1)
    plot.add_signal(a2)
    plot.set_selected_signals([], all_signals=[a1, a2], top_first=True)
    assert a1.view_box.zValue() == 2
    assert a2.view_box.zValue() == 1


# ---------------------------------------------------------------------------
# set_selected_line_boost
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-044")
def test_set_selected_line_boost_changes_pen_width(plot: PlotStripe) -> None:
    active = _make_active()
    plot.add_signal(active)
    plot.set_selected_line_boost(3)
    plot.set_selected_signals([active])
    assert active.curve.opts["pen"].width() == active.line_width + 3


@pytest.mark.requirement("REQ-PLOT-044")
def test_set_selected_line_boost_zero_disables_boost(plot: PlotStripe) -> None:
    active = _make_active()
    plot.add_signal(active)
    plot.set_selected_line_boost(0)
    plot.set_selected_signals([active])
    assert active.curve.opts["pen"].width() == active.line_width


@pytest.mark.requirement("REQ-PLOT-044")
def test_set_selected_line_boost_applies_to_subsequent_selection(plot: PlotStripe) -> None:
    active = _make_active()
    plot.add_signal(active)
    plot.set_selected_signals([active])
    assert active.curve.opts["pen"].width() == active.line_width + 1  # default boost
    plot.set_selected_line_boost(4)
    plot.set_selected_signals([active])
    assert active.curve.opts["pen"].width() == active.line_width + 4


# ---------------------------------------------------------------------------
# signal_clicked / _hit_test
# ---------------------------------------------------------------------------

def _left_press_event(pos: QPoint = QPoint(100, 100)):
    ev = MagicMock()
    ev.type.return_value = QEvent.Type.MouseButtonPress
    ev.button.return_value = Qt.MouseButton.LeftButton
    ev.pos.return_value = pos
    return ev


def _right_press_event(pos: QPoint = QPoint(100, 100)):
    ev = MagicMock()
    ev.type.return_value = QEvent.Type.MouseButtonPress
    ev.button.return_value = Qt.MouseButton.RightButton
    ev.pos.return_value = pos
    return ev


@pytest.mark.requirement("REQ-PLOT-040")
def test_signal_clicked_emits_none_on_empty_plot(plot: PlotStripe) -> None:
    received = []
    plot.signal_clicked.connect(received.append)
    plot.eventFilter(plot._pw.viewport(), _left_press_event())
    assert received == [None]


@pytest.mark.requirement("REQ-PLOT-040")
def test_miss_does_not_consume_event(plot: PlotStripe) -> None:
    result = plot.eventFilter(plot._pw.viewport(), _left_press_event())
    assert result is False


def test_right_click_does_not_emit_signal_clicked(plot: PlotStripe) -> None:
    from PyQt6.QtWidgets import QWidget
    received = []
    plot.signal_clicked.connect(received.append)
    with patch.object(QWidget, "eventFilter", return_value=False):
        plot.eventFilter(plot._pw.viewport(), _right_press_event())
    assert received == []


@pytest.mark.requirement("REQ-PLOT-040")
def test_hit_emits_active_signal(plot: PlotStripe) -> None:
    active = _make_active()
    plot.add_signal(active)
    received = []
    plot.signal_clicked.connect(received.append)
    with patch.object(plot, "_hit_test", return_value=active):
        plot.eventFilter(plot._pw.viewport(), _left_press_event())
    assert received == [active]


@pytest.mark.requirement("REQ-PLOT-040")
def test_hit_consumes_event(plot: PlotStripe) -> None:
    active = _make_active()
    plot.add_signal(active)
    with patch.object(plot, "_hit_test", return_value=active):
        result = plot.eventFilter(plot._pw.viewport(), _left_press_event())
    assert result is True


@pytest.mark.requirement("REQ-PLOT-040")
def test_hit_test_returns_none_with_no_signals(plot: PlotStripe) -> None:
    from PyQt6.QtCore import QPointF
    assert plot._hit_test(QPointF(0, 0)) is None


@pytest.mark.requirement("REQ-PLOT-041")
def test_hit_test_merged_axis_prefers_selected_signal(plot: PlotStripe) -> None:
    """Two signals sharing a Y-axis must still hit-test in per-signal Z order (#80).

    Before the fix, _hit_test sorted by view_box.zValue(), which is identical
    for every member of a merged group since they use the same ViewBox object
    — so an overlapping click could resolve to the wrong signal regardless of
    selection. It must now use the per-signal Z tracked independently of the
    (possibly merged) ViewBox.
    """
    from PyQt6.QtCore import QPointF

    a, b = _make_active("a"), _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.merge_signals([a, b])
    plot.set_selected_signals([b], all_signals=[a, b])

    # Simulate both curves' shapes covering the same screen point (overlap).
    always_hit = MagicMock()
    always_hit.contains.return_value = True
    a.curve.curve.mouseShape = MagicMock(return_value=always_hit)
    b.curve.curve.mouseShape = MagicMock(return_value=always_hit)

    assert plot._hit_test(QPointF(100, 100)) is b


@pytest.mark.requirement("REQ-PLOT-040")
def test_hit_test_marker_scatter_miss_does_not_raise(plot: PlotStripe) -> None:
    """A marker-only signal's scatter miss must not crash _hit_test (#81).

    ScatterPlotItem.pointsAt() returns a numpy array; treating it as a bare
    bool raised "truth value of an empty array is ambiguous" whenever the
    click missed every marker.
    """
    from PyQt6.QtCore import QPointF

    active = _make_active()
    active.display_mode = "marker"
    plot.add_signal(active)
    # Far outside the data's screen position -> pointsAt() returns an empty array.
    assert plot._hit_test(QPointF(-99999, -99999)) is None


@pytest.mark.requirement("REQ-PLOT-041")
def test_hit_test_marker_scatter_miss_does_not_block_lower_z_signal(plot: PlotStripe) -> None:
    """A scatter-miss exception on a higher-Z marker signal must not abort
    the loop before it reaches lower-Z signals (#81).

    Before the fix, the crash above aborted _hit_test mid-iteration, so every
    signal ranked below a marker-only one in Z order became unselectable too
    — matching the reported symptom exactly.
    """
    from PyQt6.QtCore import QPointF

    marker_sig, line_sig = _make_active("marker_sig"), _make_active("line_sig")
    plot.add_signal(marker_sig)
    plot.add_signal(line_sig)
    marker_sig.display_mode = "marker"
    # marker_sig ranks above line_sig in Z (table order: marker_sig first).
    plot.set_selected_signals([], all_signals=[marker_sig, line_sig])

    always_hit = MagicMock()
    always_hit.contains.return_value = True
    line_sig.curve.curve.mouseShape = MagicMock(return_value=always_hit)

    assert plot._hit_test(QPointF(-99999, -99999)) is line_sig


@pytest.mark.requirement("REQ-PLOT-040")
def test_near_any_point_hits_within_tolerance(plot: PlotStripe) -> None:
    """Marker fallback hit-test (#81): a near-miss a few px away still counts."""
    from PyQt6.QtCore import QPointF

    scatter = pg.ScatterPlotItem(x=[5.0], y=[5.0], symbol="o", size=6)
    vb = MagicMock()
    vb.viewPixelSize.return_value = (0.1, 0.1)  # 0.1 data units per pixel
    near_pos = QPointF(5.0 + 3 * 0.1, 5.0 + 3 * 0.1)  # 3 px away in each axis
    assert plot._near_any_point(vb, scatter, near_pos) is True


@pytest.mark.requirement("REQ-PLOT-040")
def test_near_any_point_misses_beyond_tolerance(plot: PlotStripe) -> None:
    from PyQt6.QtCore import QPointF

    scatter = pg.ScatterPlotItem(x=[5.0], y=[5.0], symbol="o", size=6)
    vb = MagicMock()
    vb.viewPixelSize.return_value = (0.1, 0.1)
    far_pos = QPointF(5.0 + 20 * 0.1, 5.0 + 20 * 0.1)  # 20 px away
    assert plot._near_any_point(vb, scatter, far_pos) is False


def test_near_any_point_returns_false_on_viewpixelsize_error(plot: PlotStripe) -> None:
    """A ViewBox without real geometry raises inside viewPixelSize(); must not crash."""
    from PyQt6.QtCore import QPointF

    scatter = pg.ScatterPlotItem(x=[5.0], y=[5.0], symbol="o", size=6)
    vb = MagicMock()
    vb.viewPixelSize.side_effect = TypeError("no view")
    assert plot._near_any_point(vb, scatter, QPointF(5.0, 5.0)) is False


# ---------------------------------------------------------------------------
# register_drag_claimant / eventFilter routing
# ---------------------------------------------------------------------------

class _FakeClaimant:
    """Minimal DragClaimant stub for testing PlotStripe's press/move/release routing."""

    def __init__(self, claim: bool = True) -> None:
        self._claim = claim
        self.events: list[str] = []

    def hit_test(self, scene_pos):
        return "token" if self._claim else None

    def on_press(self, token, scene_pos):
        self.events.append("press")

    def on_move(self, token, scene_pos):
        self.events.append("move")

    def on_release(self, token, scene_pos):
        self.events.append("release")


def test_drag_claimant_claims_press_and_skips_hit_test(plot: PlotStripe) -> None:
    claimant = _FakeClaimant()
    plot.register_drag_claimant(claimant)
    received = []
    plot.signal_clicked.connect(received.append)

    result = plot.eventFilter(plot._pw.viewport(), _left_press_event())

    assert result is True
    assert claimant.events == ["press"]
    assert received == []  # curve hit-test never ran


def test_drag_claimant_miss_falls_through_to_hit_test(plot: PlotStripe) -> None:
    claimant = _FakeClaimant(claim=False)
    plot.register_drag_claimant(claimant)
    received = []
    plot.signal_clicked.connect(received.append)

    result = plot.eventFilter(plot._pw.viewport(), _left_press_event())

    assert result is False
    assert claimant.events == []
    assert received == [None]


def test_drag_claimant_receives_move_and_release(plot: PlotStripe) -> None:
    claimant = _FakeClaimant()
    plot.register_drag_claimant(claimant)
    plot.eventFilter(plot._pw.viewport(), _left_press_event())

    move_ev = MagicMock()
    move_ev.type.return_value = QEvent.Type.MouseMove
    move_ev.pos.return_value = QPoint(105, 105)
    plot.eventFilter(plot._pw.viewport(), move_ev)

    release_ev = MagicMock()
    release_ev.type.return_value = QEvent.Type.MouseButtonRelease
    release_ev.pos.return_value = QPoint(105, 105)
    plot.eventFilter(plot._pw.viewport(), release_ev)

    assert claimant.events == ["press", "move", "release"]
    assert plot._active_claimant is None


# ---------------------------------------------------------------------------
# show_only_selected_y_axis / _update_axis_visibility
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-045")
def test_axis_visible_by_default(plot: PlotStripe) -> None:
    active = _make_active()
    plot.add_signal(active)
    assert plot._data[active].axis.isVisible()


@pytest.mark.requirement("REQ-PLOT-045")
def test_show_only_selected_off_all_axes_visible(plot: PlotStripe) -> None:
    a, b = _make_active("a"), _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.set_show_only_selected_y_axis(False)
    assert plot._data[a].axis.isVisible()
    assert plot._data[b].axis.isVisible()


@pytest.mark.requirement("REQ-PLOT-045")
def test_show_only_selected_on_no_selection_all_axes_visible(plot: PlotStripe) -> None:
    a, b = _make_active("a"), _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.set_show_only_selected_y_axis(True)
    # No selected signals → all axes shown.
    assert plot._data[a].axis.isVisible()
    assert plot._data[b].axis.isVisible()


@pytest.mark.requirement("REQ-PLOT-045")
def test_show_only_selected_on_hides_unselected_axis(plot: PlotStripe) -> None:
    a, b = _make_active("a"), _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.set_show_only_selected_y_axis(True)
    plot.set_selected_signals([a], all_signals=[a, b])
    assert plot._data[a].axis.isVisible()
    assert not plot._data[b].axis.isVisible()


@pytest.mark.requirement("REQ-PLOT-045")
def test_show_only_selected_on_multi_selection_shows_all_selected(plot: PlotStripe) -> None:
    a, b, c = _make_active("a"), _make_active("b"), _make_active("c")
    for sig in (a, b, c):
        plot.add_signal(sig)
    plot.set_show_only_selected_y_axis(True)
    plot.set_selected_signals([a, b], all_signals=[a, b, c])
    assert plot._data[a].axis.isVisible()
    assert plot._data[b].axis.isVisible()
    assert not plot._data[c].axis.isVisible()


@pytest.mark.requirement("REQ-PLOT-045")
def test_show_only_selected_clearing_selection_restores_all_axes(plot: PlotStripe) -> None:
    a, b = _make_active("a"), _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.set_show_only_selected_y_axis(True)
    plot.set_selected_signals([a], all_signals=[a, b])
    assert not plot._data[b].axis.isVisible()
    plot.set_selected_signals([], all_signals=[a, b])
    assert plot._data[a].axis.isVisible()
    assert plot._data[b].axis.isVisible()


@pytest.mark.requirement("REQ-PLOT-045")
def test_show_only_selected_toggling_off_restores_all_axes(plot: PlotStripe) -> None:
    a, b = _make_active("a"), _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.set_show_only_selected_y_axis(True)
    plot.set_selected_signals([a], all_signals=[a, b])
    assert not plot._data[b].axis.isVisible()
    plot.set_show_only_selected_y_axis(False)
    assert plot._data[a].axis.isVisible()
    assert plot._data[b].axis.isVisible()


@pytest.mark.requirement("REQ-PLOT-045")
def test_new_signal_added_with_toggle_on_respects_visibility(plot: PlotStripe) -> None:
    a = _make_active("a")
    plot.add_signal(a)
    plot.set_show_only_selected_y_axis(True)
    plot.set_selected_signals([a], all_signals=[a])
    # Add a second signal while toggle is on and a is selected — b should be hidden.
    b = _make_active("b")
    plot.add_signal(b)
    assert plot._data[a].axis.isVisible()
    assert not plot._data[b].axis.isVisible()


# ---------------------------------------------------------------------------
# Axis grouping — merge_signals
# ---------------------------------------------------------------------------

def _make_active_unit(name: str, unit: str = "V", n: int = 50) -> ActiveSignal:
    t = np.linspace(0.0, 1.0, n)
    data = SignalData(timestamps=t, samples=np.sin(2 * np.pi * t))
    meta = SignalMetadata(name=name, unit=unit, group_index=0, channel_index=0)
    return ActiveSignal(data=data, metadata=meta, color=QColor(100, 100, 200))


@pytest.mark.requirement("REQ-PLOT-034")
def test_merge_signals_noop_when_less_than_two(plot: PlotStripe) -> None:
    a = _make_active("a")
    plot.add_signal(a)
    plot.merge_signals([a])
    assert plot._find_merged_group(a) is None


@pytest.mark.requirement("REQ-PLOT-031")
def test_merge_signals_creates_merged_group(plot: PlotStripe) -> None:
    a, b = _make_active("a"), _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.merge_signals([a, b])
    grp = plot._find_merged_group(a)
    assert grp is not None
    assert b in grp


@pytest.mark.requirement("REQ-PLOT-031")
def test_merge_signals_both_use_same_viewbox(plot: PlotStripe) -> None:
    a, b = _make_active("a"), _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.merge_signals([a, b])
    assert plot._data[a].view_box is plot._data[b].view_box


@pytest.mark.requirement("REQ-PLOT-031")
def test_merge_signals_both_use_same_axis(plot: PlotStripe) -> None:
    a, b = _make_active("a"), _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.merge_signals([a, b])
    assert plot._data[a].axis is plot._data[b].axis


@pytest.mark.requirement("REQ-PLOT-031")
def test_merge_signals_one_signal_owns_axis(plot: PlotStripe) -> None:
    a, b = _make_active("a"), _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.merge_signals([a, b])
    owners = [s for s in (a, b) if plot._data[s].owns_axis]
    non_owners = [s for s in (a, b) if not plot._data[s].owns_axis]
    assert len(owners) == 1
    assert len(non_owners) == 1


@pytest.mark.requirement("REQ-PLOT-031")
def test_merge_signals_axis_uses_neutral_color(plot: PlotStripe) -> None:
    from mdf_viewer.view.plot_stripe import _NEUTRAL_AXIS_COLOR
    a, b = _make_active("a"), _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.merge_signals([a, b])
    axis = plot._data[a].axis
    pen = axis.pen()
    expected_rgb = (pen.color().red(), pen.color().green(), pen.color().blue())
    assert expected_rgb == _NEUTRAL_AXIS_COLOR


@pytest.mark.requirement("REQ-PLOT-031")
def test_merge_signals_is_in_group(plot: PlotStripe) -> None:
    a, b = _make_active("a"), _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.merge_signals([a, b])
    assert plot.is_in_group(a)
    assert plot.is_in_group(b)


@pytest.mark.requirement("REQ-PLOT-031")
def test_merge_signals_group_type_merged(plot: PlotStripe) -> None:
    a, b = _make_active("a"), _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.merge_signals([a, b])
    assert plot.get_group_type(a) == "merged"


@pytest.mark.requirement("REQ-PLOT-031")
def test_get_grouped_signals_includes_merged(plot: PlotStripe) -> None:
    a, b = _make_active("a"), _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.merge_signals([a, b])
    grouped = plot.get_grouped_signals()
    assert a in grouped
    assert b in grouped


@pytest.mark.requirement("REQ-PLOT-031")
def test_unmerged_signal_not_in_get_grouped(plot: PlotStripe) -> None:
    a, b, c = _make_active("a"), _make_active("b"), _make_active("c")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.add_signal(c)
    plot.merge_signals([a, b])
    grouped = plot.get_grouped_signals()
    assert c not in grouped


@pytest.mark.requirement("REQ-PLOT-031")
def test_get_merged_signals_includes_only_merged(plot: PlotStripe) -> None:
    a, b, c, d = (_make_active(n) for n in "abcd")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.add_signal(c)
    plot.add_signal(d)
    plot.merge_signals([a, b])
    plot.sync_signals([c, d])
    merged = plot.get_merged_signals()
    assert merged == {a, b}


@pytest.mark.requirement("REQ-PLOT-032")
def test_get_synced_signals_includes_only_synced(plot: PlotStripe) -> None:
    a, b, c, d = (_make_active(n) for n in "abcd")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.add_signal(c)
    plot.add_signal(d)
    plot.merge_signals([a, b])
    plot.sync_signals([c, d])
    synced = plot.get_synced_signals()
    assert synced == {c, d}


@pytest.mark.requirement("REQ-PLOT-031")
def test_merge_signals_three_signals(plot: PlotStripe) -> None:
    a, b, c = _make_active("a"), _make_active("b"), _make_active("c")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.add_signal(c)
    plot.merge_signals([a, b, c])
    vbs = {id(plot._data[s].view_box) for s in (a, b, c)}
    assert len(vbs) == 1


@pytest.mark.requirement("REQ-PLOT-031")
def test_merge_signals_merges_two_existing_groups(plot: PlotStripe) -> None:
    a, b = _make_active("a"), _make_active("b")
    c, d = _make_active("c"), _make_active("d")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.add_signal(c)
    plot.add_signal(d)
    plot.merge_signals([a, b])
    plot.merge_signals([c, d])
    # Now merge the two groups together
    plot.merge_signals([a, c])
    vbs = {id(plot._data[s].view_box) for s in (a, b, c, d)}
    assert len(vbs) == 1
    assert len(plot._merged_groups) == 1
    assert set(plot._merged_groups[0]) == {a, b, c, d}


# ---------------------------------------------------------------------------
# Axis grouping — ungroup_signal (merged)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-024")
def test_ungroup_signal_two_members_dissolves_group(plot: PlotStripe) -> None:
    a, b = _make_active("a"), _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.merge_signals([a, b])
    plot.ungroup_signal(a)
    assert not plot.is_in_group(a)
    assert not plot.is_in_group(b)
    assert plot._merged_groups == []


@pytest.mark.requirement("REQ-PLOT-035")
def test_ungroup_signal_restores_own_viewbox(plot: PlotStripe) -> None:
    a, b = _make_active("a"), _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.merge_signals([a, b])
    merged_vb = plot._data[a].view_box
    plot.ungroup_signal(a)
    # Both a and b must now have their own (different) ViewBoxes.
    assert plot._data[a].view_box is not merged_vb
    assert plot._data[b].view_box is not merged_vb
    assert plot._data[a].view_box is not plot._data[b].view_box


@pytest.mark.requirement("REQ-PLOT-035")
def test_ungroup_signal_three_to_two_keeps_group(plot: PlotStripe) -> None:
    a, b, c = _make_active("a"), _make_active("b"), _make_active("c")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.add_signal(c)
    plot.merge_signals([a, b, c])
    plot.ungroup_signal(c)
    assert not plot.is_in_group(c)
    assert plot.is_in_group(a)
    assert plot.is_in_group(b)
    assert len(plot._merged_groups) == 1
    grp = plot._merged_groups[0]
    assert c not in grp
    # a and b still share one ViewBox
    assert plot._data[a].view_box is plot._data[b].view_box


@pytest.mark.requirement("REQ-PLOT-035")
def test_ungroup_signal_noop_when_not_in_group(plot: PlotStripe) -> None:
    a = _make_active("a")
    plot.add_signal(a)
    plot.ungroup_signal(a)  # should not raise
    assert not plot.is_in_group(a)


# ---------------------------------------------------------------------------
# Axis grouping — remove_signal cleans up merged groups
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-024")
def test_remove_signal_from_merged_group_two_members_dissolves(plot: PlotStripe) -> None:
    a, b = _make_active("a"), _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.merge_signals([a, b])
    plot.remove_signal(a)
    assert not plot.is_in_group(b)
    assert plot._merged_groups == []


@pytest.mark.requirement("REQ-PLOT-024")
def test_remove_signal_from_merged_group_three_members_shrinks(plot: PlotStripe) -> None:
    a, b, c = _make_active("a"), _make_active("b"), _make_active("c")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.add_signal(c)
    plot.merge_signals([a, b, c])
    plot.remove_signal(a)
    assert plot.is_in_group(b)
    assert plot.is_in_group(c)
    assert len(plot._merged_groups) == 1
    assert a not in plot._merged_groups[0]


@pytest.mark.requirement("REQ-PLOT-024")
def test_remove_owner_transfers_ownership(plot: PlotStripe) -> None:
    a, b, c = _make_active("a"), _make_active("b"), _make_active("c")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.add_signal(c)
    plot.merge_signals([a, b, c])
    # Find owner and remove it
    owner = next(s for s in (a, b, c) if plot._data[s].owns_axis)
    others = [s for s in (a, b, c) if s is not owner]
    plot.remove_signal(owner)
    # Exactly one remaining member should own the axis
    new_owners = [s for s in others if plot._data[s].owns_axis]
    assert len(new_owners) == 1


# ---------------------------------------------------------------------------
# Axis grouping — sync_signals
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-032")
def test_sync_signals_creates_synced_group(plot: PlotStripe) -> None:
    a, b = _make_active("a"), _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.sync_signals([a, b])
    grp = plot._find_synced_group(a)
    assert grp is not None
    assert b in grp


@pytest.mark.requirement("REQ-PLOT-032")
def test_sync_signals_keeps_separate_viewboxes(plot: PlotStripe) -> None:
    a, b = _make_active("a"), _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.sync_signals([a, b])
    assert plot._data[a].view_box is not plot._data[b].view_box


@pytest.mark.requirement("REQ-PLOT-032")
def test_sync_signals_group_type_synced(plot: PlotStripe) -> None:
    a, b = _make_active("a"), _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.sync_signals([a, b])
    assert plot.get_group_type(a) == "synced"
    assert plot.get_group_type(b) == "synced"


@pytest.mark.requirement("REQ-PLOT-032")
def test_sync_signals_is_in_group(plot: PlotStripe) -> None:
    a, b = _make_active("a"), _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.sync_signals([a, b])
    assert plot.is_in_group(a)
    assert plot.is_in_group(b)


@pytest.mark.requirement("REQ-PLOT-032")
def test_get_grouped_signals_includes_synced(plot: PlotStripe) -> None:
    a, b = _make_active("a"), _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.sync_signals([a, b])
    grouped = plot.get_grouped_signals()
    assert a in grouped
    assert b in grouped


@pytest.mark.requirement("REQ-PLOT-032")
def test_sync_signals_syncs_y_range_when_vb_changes(plot: PlotStripe) -> None:
    a, b = _make_active("a"), _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.sync_signals([a, b])
    # Simulate a Y range change on a's ViewBox via sigRangeChanged.
    vb_a = plot._data[a].view_box
    vb_b = plot._data[b].view_box
    # Directly set a's Y range via setYRange; this fires sigRangeChanged.
    vb_a.setYRange(-5.0, 5.0, padding=0)
    y_range_b = vb_b.viewRange()[1]
    assert abs(y_range_b[0] - (-5.0)) < 0.1
    assert abs(y_range_b[1] - 5.0) < 0.1


@pytest.mark.requirement("REQ-PLOT-032")
def test_sync_signals_noop_feedback_loop(plot: PlotStripe) -> None:
    """Changing b's Y range (triggered by a's change) must not re-trigger a handler."""
    a, b = _make_active("a"), _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.sync_signals([a, b])
    call_count = [0]
    original = plot._data[a].view_box.setYRange

    def counting_set(*args, **kwargs):
        call_count[0] += 1
        original(*args, **kwargs)

    plot._data[a].view_box.setYRange = counting_set
    plot._data[b].view_box.setYRange(-3.0, 3.0, padding=0)
    # a's setYRange should be called once (by the handler) not recursively
    assert call_count[0] <= 1


# ---------------------------------------------------------------------------
# Axis grouping — ungroup_signal (synced)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-035")
def test_ungroup_synced_signal_removes_from_group(plot: PlotStripe) -> None:
    a, b = _make_active("a"), _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.sync_signals([a, b])
    plot.ungroup_signal(a)
    assert not plot.is_in_group(a)
    assert not plot.is_in_group(b)


@pytest.mark.requirement("REQ-PLOT-035")
def test_ungroup_synced_three_to_two_keeps_group(plot: PlotStripe) -> None:
    a, b, c = _make_active("a"), _make_active("b"), _make_active("c")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.add_signal(c)
    plot.sync_signals([a, b, c])
    plot.ungroup_signal(c)
    assert not plot.is_in_group(c)
    assert plot.is_in_group(a)
    assert plot.is_in_group(b)


@pytest.mark.requirement("REQ-PLOT-024")
def test_remove_signal_from_synced_group_dissolves_when_one_left(plot: PlotStripe) -> None:
    a, b = _make_active("a"), _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.sync_signals([a, b])
    plot.remove_signal(a)
    assert not plot.is_in_group(b)
    assert plot._synced_groups == []


# ---------------------------------------------------------------------------
# Axis visibility with merged groups
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-046")
def test_show_only_selected_merged_axis_shown_when_any_member_selected(
    plot: PlotStripe,
) -> None:
    a, b = _make_active("a"), _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.merge_signals([a, b])
    plot.set_show_only_selected_y_axis(True)
    # Select only b — since a and b share the same axis, it must be visible.
    plot.set_selected_signals([b], all_signals=[a, b])
    assert plot._data[a].axis.isVisible()


@pytest.mark.requirement("REQ-PLOT-046")
def test_show_only_selected_merged_axis_hidden_when_no_member_selected(
    plot: PlotStripe,
) -> None:
    a, b = _make_active("a"), _make_active("b")
    c = _make_active("c")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.add_signal(c)
    plot.merge_signals([a, b])
    plot.set_show_only_selected_y_axis(True)
    # Select only c — a+b's merged axis must be hidden.
    plot.set_selected_signals([c], all_signals=[a, b, c])
    assert not plot._data[a].axis.isVisible()


# ---------------------------------------------------------------------------
# Swimlanes with merged groups
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-055")
def test_swimlanes_counts_merged_group_as_one_lane(plot: PlotStripe) -> None:
    a, b = _make_active("a"), _make_active("b")
    c = _make_active("c")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.add_signal(c)
    plot.merge_signals([a, b])
    result = plot.swimlanes([a, b, c])
    assert result is True
    # a+b share one VB → 2 unique lanes total (1 merged + 1 for c)
    unique_vbs = {id(plot._data[s].view_box) for s in (a, b, c)}
    assert len(unique_vbs) == 2


# ---------------------------------------------------------------------------
# _display_units / swimlanes / zoom with synced groups (#84)
# ---------------------------------------------------------------------------

def _make_active_range(name: str, y_min: float, y_max: float, n: int = 50) -> ActiveSignal:
    """Signal whose samples span exactly [y_min, y_max] — for distinguishing
    "combined extent of all group members" from "just one member's extent"."""
    t = np.linspace(0.0, 1.0, n)
    data = SignalData(timestamps=t, samples=np.linspace(y_min, y_max, n))
    meta = SignalMetadata(name=name, unit="V", group_index=0, channel_index=0)
    return ActiveSignal(data=data, metadata=meta, color=QColor(100, 100, 200))


@pytest.mark.requirement("REQ-PLOT-055")
def test_display_units_treats_synced_group_as_one_unit(plot: PlotStripe) -> None:
    a, b, c = _make_active("a"), _make_active("b"), _make_active("c")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.add_signal(c)
    plot.sync_signals([a, b])
    units = plot._display_units([a, b, c])
    assert len(units) == 2
    synced_unit = next(u for u in units if u[2])
    assert set(synced_unit[1]) == {a, b}


@pytest.mark.requirement("REQ-PLOT-055")
def test_display_units_merged_group_still_one_unit(plot: PlotStripe) -> None:
    a, b, c = _make_active("a"), _make_active("b"), _make_active("c")
    plot.add_signal(a)
    plot.add_signal(b)
    plot.add_signal(c)
    plot.merge_signals([a, b])
    units = plot._display_units([a, b, c])
    assert len(units) == 2
    assert all(not is_synced for _, _, is_synced in units)


@pytest.mark.requirement("REQ-PLOT-055")
def test_display_units_ungrouped_signals_each_own_unit(plot: PlotStripe) -> None:
    a, b = _make_active("a"), _make_active("b")
    plot.add_signal(a)
    plot.add_signal(b)
    units = plot._display_units([a, b])
    assert len(units) == 2


@pytest.mark.requirement("REQ-PLOT-055")
def test_swimlanes_synced_group_uses_combined_data_extent(plot: PlotStripe) -> None:
    """A synced group's lane must fit the union of all members' data (#84).

    Before the fix, swimlanes() treated each synced member as its own unit;
    the synced-sync handler then forced them to match whichever member's
    setYRange() call ran last, which reflected only that one member's data
    — not the combined extent — while wasting a second lane's worth of
    layout space that was computed for the other member and never used.
    """
    a = _make_active_range("a", 0.0, 10.0)
    b = _make_active_range("b", 100.0, 110.0)
    plot.add_signal(a)
    plot.add_signal(b)
    plot.sync_signals([a, b])

    assert plot.swimlanes([a, b]) is True

    y_a = a.view_box.viewRange()[1]
    y_b = b.view_box.viewRange()[1]
    assert y_a == pytest.approx(y_b)
    # Must include both members' ranges, not just one.
    assert y_a[0] < 10.0
    assert y_a[1] > 100.0


@pytest.mark.requirement("REQ-PLOT-054")
def test_zoom_y_to_view_synced_group_uses_combined_data_extent(plot: PlotStripe) -> None:
    a = _make_active_range("a", 0.0, 10.0)
    b = _make_active_range("b", 100.0, 110.0)
    plot.add_signal(a)
    plot.add_signal(b)
    plot.sync_signals([a, b])

    assert plot.zoom_y_to_view() is True

    y_a = a.view_box.viewRange()[1]
    y_b = b.view_box.viewRange()[1]
    assert y_a == pytest.approx(y_b)
    assert y_a[0] < 10.0
    assert y_a[1] > 100.0


@pytest.mark.requirement("REQ-PLOT-053")
def test_zoom_to_fit_synced_group_uses_combined_data_extent(plot: PlotStripe) -> None:
    a = _make_active_range("a", 0.0, 10.0)
    b = _make_active_range("b", 100.0, 110.0)
    plot.add_signal(a)
    plot.add_signal(b)
    plot.sync_signals([a, b])

    plot.zoom_to_fit()

    y_a = a.view_box.viewRange()[1]
    y_b = b.view_box.viewRange()[1]
    assert y_a == pytest.approx(y_b)
    assert y_a[0] < 10.0
    assert y_a[1] > 100.0
