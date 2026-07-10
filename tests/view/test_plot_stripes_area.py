"""Tests for PlotStripesArea.

Covers stripe lifecycle (create/delete/anchor reassignment), signal-to-stripe
routing, active-stripe tracking, and the cross-stripe scoping rules (swimlanes,
merge/sync same-stripe validation, click-selection). PlotStripe's own rendering
behavior is covered by test_plot_stripe.py.
"""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pytest
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QSplitter
from pytestqt.qtbot import QtBot

from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.view.plot_stripe import PlotStripe
from mdf_viewer.view.plot_stripes_area import PlotStripesArea
from mdf_viewer.view_model.active_signal import ActiveSignal


def _make_active(name: str = "sig", n: int = 100, unit: str = "V") -> ActiveSignal:
    t = np.linspace(0.0, 1.0, n)
    data = SignalData(timestamps=t, samples=np.sin(2 * np.pi * t))
    meta = SignalMetadata(name=name, unit=unit, group_index=0, channel_index=0)
    return ActiveSignal(data=data, metadata=meta, color=QColor(255, 85, 85))


@pytest.fixture()
def area(qtbot: QtBot) -> PlotStripesArea:
    w = PlotStripesArea()
    qtbot.addWidget(w)
    return w


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------

def test_starts_with_one_stripe(area: PlotStripesArea) -> None:
    assert isinstance(area._stripes[0], PlotStripe)
    assert isinstance(area._splitter, QSplitter)
    assert area._splitter.count() == 1
    assert area.get_stripes() == [area._stripes[0]]


def test_initial_stripe_is_active(area: PlotStripesArea) -> None:
    assert area.get_active_stripe() is area._stripes[0]


def test_plot_item_passthrough(area: PlotStripesArea) -> None:
    assert area.plot_item is area._stripes[0].plot_item


# ---------------------------------------------------------------------------
# Stripe naming
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-291")
def test_initial_stripe_named_stripe_1(area: PlotStripesArea) -> None:
    assert area._stripes[0].name == "Stripe 1"


@pytest.mark.requirement("REQ-PLOT-291")
def test_created_stripes_named_by_creation_order(area: PlotStripesArea) -> None:
    s2 = area.create_stripe()
    s3 = area.create_stripe()
    assert s2.name == "Stripe 2"
    assert s3.name == "Stripe 3"


# ---------------------------------------------------------------------------
# Stripe size sync (#100)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-274")
def test_set_stripe_sizes_applies_to_splitter(area: PlotStripesArea) -> None:
    area.create_stripe()
    with patch.object(area._splitter, "setSizes") as mock_set_sizes:
        area.set_stripe_sizes([10, 90])
    mock_set_sizes.assert_called_once_with([10, 90])


@pytest.mark.requirement("REQ-PLOT-274")
def test_set_stripe_sizes_does_not_emit_stripe_sizes_changed(
    area: PlotStripesArea, qtbot: QtBot
) -> None:
    area.create_stripe()
    with qtbot.assertNotEmitted(area.stripe_sizes_changed):
        area.set_stripe_sizes([10, 90])


@pytest.mark.requirement("REQ-PLOT-274")
def test_splitter_moved_emits_stripe_sizes_changed(
    area: PlotStripesArea, qtbot: QtBot
) -> None:
    area.create_stripe()
    with qtbot.waitSignal(area.stripe_sizes_changed) as blocker:
        area._on_splitter_moved(0, 0)
    assert blocker.args[0] == area._splitter.sizes()


@pytest.mark.requirement("REQ-PLOT-274")
def test_create_stripe_emits_stripe_sizes_changed(
    area: PlotStripesArea, qtbot: QtBot
) -> None:
    # A freshly created stripe's segment must be sized immediately, not left
    # at whatever arbitrary size Qt gave it until a drag happens to touch
    # that divider (#100 postmortem).
    with qtbot.waitSignal(area.stripe_sizes_changed) as blocker:
        area.create_stripe()
    assert blocker.args[0] == area._splitter.sizes()


@pytest.mark.requirement("REQ-PLOT-274")
def test_delete_stripe_emits_stripe_sizes_changed(
    area: PlotStripesArea, qtbot: QtBot
) -> None:
    s2 = area.create_stripe()
    with qtbot.waitSignal(area.stripe_sizes_changed) as blocker:
        area.delete_stripe(s2)
    assert blocker.args[0] == area._splitter.sizes()


def test_get_stripe_sizes_returns_splitter_sizes(area: PlotStripesArea) -> None:
    assert area.get_stripe_sizes() == area._splitter.sizes()


@pytest.mark.requirement("REQ-PLOT-291")
def test_stripe_names_not_reused_or_renumbered_after_deletion(area: PlotStripesArea) -> None:
    s2 = area.create_stripe()
    area.create_stripe()
    area.delete_stripe(s2)
    s4 = area.create_stripe()
    assert s4.name == "Stripe 4"


# ---------------------------------------------------------------------------
# Stripe lifecycle
# ---------------------------------------------------------------------------

def test_create_stripe_appends_and_shares_x(area: PlotStripesArea) -> None:
    s2 = area.create_stripe()
    assert area.get_stripes() == [area._stripes[0], s2]
    assert area._splitter.count() == 2
    area.zoom_to_x_range(0.1, 0.9)
    expected = area._stripes[0].plot_item.vb.viewRange()[0]
    assert s2.plot_item.vb.viewRange()[0] == pytest.approx(expected, abs=1e-6)


def test_new_stripe_picks_up_existing_x_range_immediately(area: PlotStripesArea) -> None:
    area.zoom_to_x_range(0.25, 0.75)
    expected = area._stripes[0].plot_item.vb.viewRange()[0]
    s2 = area.create_stripe()
    assert s2.plot_item.vb.viewRange()[0] == pytest.approx(expected, abs=1e-6)


def test_panning_one_stripe_propagates_to_others(area: PlotStripesArea) -> None:
    s2 = area.create_stripe()
    area._stripes[0].sync_x_range(0.15, 0.85)  # simulate an interior-drag pan on stripe 0
    assert s2.plot_item.vb.viewRange()[0] == pytest.approx([0.15, 0.85], abs=1e-6)


def test_create_stripe_does_not_change_active_stripe(area: PlotStripesArea) -> None:
    first = area.get_active_stripe()
    area.create_stripe()
    assert area.get_active_stripe() is first


def test_delete_stripe_refuses_last_one(area: PlotStripesArea) -> None:
    assert area.delete_stripe(area._stripes[0]) is False
    assert len(area.get_stripes()) == 1


def test_delete_empty_stripe_succeeds(area: PlotStripesArea) -> None:
    s2 = area.create_stripe()
    assert area.delete_stripe(s2) is True
    assert area.get_stripes() == [area._stripes[0]]


def test_delete_nonempty_stripe_always_refuses(area: PlotStripesArea) -> None:
    """PlotStripesArea has no "force" concept — removing a non-empty stripe's
    signals via the full AppController.remove_signal pipeline (table row,
    cursor cleanup) is a controller-level concern, not this view's."""
    s2 = area.create_stripe()
    active = _make_active()
    area.add_signal(active, stripe=s2)
    assert area.delete_stripe(s2) is False
    assert s2 in area.get_stripes()


def test_delete_stripe_succeeds_once_emptied(area: PlotStripesArea) -> None:
    s2 = area.create_stripe()
    active = _make_active()
    area.add_signal(active, stripe=s2)
    area.remove_signal(active)
    assert area.delete_stripe(s2) is True
    assert s2 not in area.get_stripes()


def test_delete_active_stripe_reassigns_active(area: PlotStripesArea) -> None:
    first = area._stripes[0]
    s2 = area.create_stripe()
    area.set_active_stripe(s2)
    area.delete_stripe(s2)
    assert area.get_active_stripe() is first


def test_delete_first_stripe_x_sharing_still_works(area: PlotStripesArea, qtbot: QtBot) -> None:
    """Deleting stripe 0 must not break X sharing among the survivors."""
    first = area._stripes[0]
    s2 = area.create_stripe()
    s3 = area.create_stripe()
    area.delete_stripe(first)
    assert area.get_stripes() == [s2, s3]
    s2.sync_x_range(0.3, 0.6)
    assert s3.plot_item.vb.viewRange()[0] == pytest.approx([0.3, 0.6], abs=1e-6)


def test_create_stripe_redistributes_sizes_equally(area: PlotStripesArea) -> None:
    area.create_stripe()
    area.create_stripe()
    sizes = area._splitter.sizes()
    assert len(sizes) == 3


# ---------------------------------------------------------------------------
# Active stripe / X-axis tick visibility
# ---------------------------------------------------------------------------

def test_stripe_activated_signal_updates_active_stripe(area: PlotStripesArea) -> None:
    s2 = area.create_stripe()
    s2.activated.emit(s2)
    assert area.get_active_stripe() is s2


def test_only_bottom_stripe_shows_x_axis_ticks(area: PlotStripesArea) -> None:
    first = area._stripes[0]
    s2 = area.create_stripe()
    assert first._pi.getAxis('bottom').style['showValues'] is False
    assert s2._pi.getAxis('bottom').style['showValues'] is True


def test_deleting_bottom_stripe_reveals_ticks_on_new_bottom(area: PlotStripesArea) -> None:
    first = area._stripes[0]
    s2 = area.create_stripe()
    area.delete_stripe(s2)
    assert first._pi.getAxis('bottom').style['showValues'] is True


# ---------------------------------------------------------------------------
# Per-measurement X-axis rows (#101)
# ---------------------------------------------------------------------------

def _make_measurement(offset_s: float = 0.0):
    from mdf_viewer.model.loaded_measurement import LoadedMeasurement
    from mdf_viewer.model.mdf_loader import MdfLoader
    from mdf_viewer.model.measurement import MeasurementInfo

    return LoadedMeasurement(
        loader=MdfLoader(), info=MeasurementInfo(file_name="run.mf4"), label="run",
        offset_s=offset_s,
    )


@pytest.mark.requirement("REQ-PLOT-301")
def test_refresh_measurement_axes_targets_only_bottom_stripe(area: PlotStripesArea) -> None:
    first = area._stripes[0]
    s2 = area.create_stripe()
    m1 = _make_measurement()
    area.refresh_measurement_axes([m1])
    assert first._measurement_axes == []
    assert len(s2._measurement_axes) == 1


@pytest.mark.requirement("REQ-PLOT-301")
def test_plain_time_axis_hidden_once_measurements_loaded(area: PlotStripesArea) -> None:
    """Per-measurement rows replace the plain 'Time' axis rather than
    stacking alongside it — loading 2 measurements should show 2 axis
    rows total, not 3 (bug found during the M6 live-test checkpoint)."""
    bottom = area._stripes[-1]
    assert bottom._pi.getAxis('bottom').style['showValues'] is True

    m1, m2 = _make_measurement(), _make_measurement()
    area.refresh_measurement_axes([m1, m2])

    assert bottom._pi.getAxis('bottom').style['showValues'] is False
    assert len(bottom._measurement_axes) == 2


@pytest.mark.requirement("REQ-PLOT-301")
def test_plain_time_axis_shown_again_when_pool_empties(area: PlotStripesArea) -> None:
    m1 = _make_measurement()
    area.refresh_measurement_axes([m1])
    bottom = area._stripes[-1]
    assert bottom._pi.getAxis('bottom').style['showValues'] is False

    area.refresh_measurement_axes([])

    assert bottom._pi.getAxis('bottom').style['showValues'] is True
    assert bottom._measurement_axes == []


@pytest.mark.requirement("REQ-PLOT-301")
def test_new_bottom_stripe_gets_measurement_axes_on_create(area: PlotStripesArea) -> None:
    m1 = _make_measurement()
    area.refresh_measurement_axes([m1])
    first = area._stripes[0]
    assert len(first._measurement_axes) == 1

    s2 = area.create_stripe()
    assert first._measurement_axes == []
    assert len(s2._measurement_axes) == 1


@pytest.mark.requirement("REQ-PLOT-301")
def test_deleting_bottom_stripe_moves_measurement_axes_to_new_bottom(
    area: PlotStripesArea,
) -> None:
    m1 = _make_measurement()
    area.refresh_measurement_axes([m1])
    first = area._stripes[0]
    s2 = area.create_stripe()
    area.delete_stripe(s2)
    assert len(first._measurement_axes) == 1


@pytest.mark.requirement("REQ-FILE-031")
def test_measurement_offset_changed_reemitted(area: PlotStripesArea, qtbot: QtBot) -> None:
    m1 = _make_measurement()
    area.refresh_measurement_axes([m1])
    bottom = area._stripes[-1]
    with qtbot.waitSignal(area.measurement_offset_changed) as blocker:
        bottom._measurement_axes[0]._on_offset_changed(m1)
    assert blocker.args == [m1]


@pytest.mark.requirement("REQ-PLOT-304")
def test_refresh_signal_data_reaches_owning_stripe(area: PlotStripesArea) -> None:
    active = _make_active()
    area.add_signal(active)
    original = active.curve.xData.copy()
    active.measurement = _make_measurement(offset_s=5.0)
    area.refresh_signal_data(active)
    assert not np.array_equal(active.curve.xData, original)
    assert np.array_equal(active.curve.xData, original + 5.0)


def test_refresh_signal_data_noop_for_unknown_signal(area: PlotStripesArea) -> None:
    active = _make_active()
    area.refresh_signal_data(active)  # must not raise


# ---------------------------------------------------------------------------
# Signal routing
# ---------------------------------------------------------------------------

def test_add_signal_defaults_to_active_stripe(area: PlotStripesArea) -> None:
    active = _make_active()
    area.add_signal(active)
    assert area.get_stripe_for_signal(active) is area.get_active_stripe()
    assert active in area._stripes[0]._data


def test_add_signal_to_explicit_stripe(area: PlotStripesArea) -> None:
    s2 = area.create_stripe()
    active = _make_active()
    area.add_signal(active, stripe=s2)
    assert area.get_stripe_for_signal(active) is s2
    assert active in s2._data
    assert active not in area._stripes[0]._data


def test_remove_signal_reaches_owning_stripe(area: PlotStripesArea) -> None:
    active = _make_active()
    area.add_signal(active)
    area.remove_signal(active)
    assert active not in area._stripes[0]._data
    assert area.get_stripe_for_signal(active) is None


def test_move_signal_to_stripe(area: PlotStripesArea) -> None:
    s2 = area.create_stripe()
    active = _make_active()
    area.add_signal(active)
    area.move_signal_to_stripe(active, s2)
    assert area.get_stripe_for_signal(active) is s2
    assert active not in area._stripes[0]._data
    assert active in s2._data


def test_move_signal_to_same_stripe_is_noop(area: PlotStripesArea) -> None:
    active = _make_active()
    area.add_signal(active)
    stripe = area.get_stripe_for_signal(active)
    area.move_signal_to_stripe(active, stripe)
    assert area.get_stripe_for_signal(active) is stripe


def test_get_signals_in_stripe(area: PlotStripesArea) -> None:
    s2 = area.create_stripe()
    a1, a2 = _make_active("a"), _make_active("b")
    area.add_signal(a1)
    area.add_signal(a2, stripe=s2)
    assert area.get_signals_in_stripe(area._stripes[0]) == [a1]
    assert area.get_signals_in_stripe(s2) == [a2]


# ---------------------------------------------------------------------------
# Cross-stripe scoping: swimlanes, merge/sync, zoom
# ---------------------------------------------------------------------------

def test_swimlanes_scoped_to_active_stripe(area: PlotStripesArea) -> None:
    s2 = area.create_stripe()
    a1 = _make_active("a")
    a2 = _make_active("b")
    area.add_signal(a1)  # active stripe
    area.add_signal(a2, stripe=s2)
    assert area.swimlanes([a1, a2]) is True  # only a1 (active stripe) actually arranged


def test_swimlanes_false_when_active_stripe_empty(area: PlotStripesArea) -> None:
    s2 = area.create_stripe()
    active = _make_active()
    area.add_signal(active, stripe=s2)  # not in the active stripe
    assert area.swimlanes([active]) is False


def test_merge_signals_same_stripe_succeeds(area: PlotStripesArea) -> None:
    a1, a2 = _make_active("a"), _make_active("b")
    area.add_signal(a1)
    area.add_signal(a2)
    area.merge_signals([a1, a2])
    assert area.get_group_type(a1) == "merged"


def test_merge_signals_cross_stripe_is_noop(area: PlotStripesArea) -> None:
    s2 = area.create_stripe()
    a1, a2 = _make_active("a"), _make_active("b")
    area.add_signal(a1)
    area.add_signal(a2, stripe=s2)
    area.merge_signals([a1, a2])
    assert area.get_group_type(a1) is None
    assert area.get_group_type(a2) is None


def test_sync_signals_cross_stripe_is_noop(area: PlotStripesArea) -> None:
    s2 = area.create_stripe()
    a1, a2 = _make_active("a"), _make_active("b")
    area.add_signal(a1)
    area.add_signal(a2, stripe=s2)
    area.sync_signals([a1, a2])
    assert area.get_group_type(a1) is None


def test_zoom_to_fit_x_spans_all_stripes(area: PlotStripesArea) -> None:
    s2 = area.create_stripe()
    short = ActiveSignal(
        data=SignalData(timestamps=np.linspace(0.0, 1.0, 10), samples=np.zeros(10)),
        metadata=SignalMetadata(name="short", unit="V", group_index=0, channel_index=0),
        color=QColor(1, 2, 3),
    )
    long = ActiveSignal(
        data=SignalData(timestamps=np.linspace(0.0, 100.0, 10), samples=np.zeros(10)),
        metadata=SignalMetadata(name="long", unit="V", group_index=0, channel_index=1),
        color=QColor(4, 5, 6),
    )
    area.add_signal(short)
    area.add_signal(long, stripe=s2)
    area.zoom_to_fit()
    x_min, x_max = area.plot_item.vb.viewRange()[0]
    assert x_min < 1.0
    assert x_max > 99.0


@pytest.mark.requirement("REQ-PLOT-304")
def test_zoom_to_fit_uses_offset_shifted_range(area: PlotStripesArea) -> None:
    from mdf_viewer.model.loaded_measurement import LoadedMeasurement
    from mdf_viewer.model.mdf_loader import MdfLoader
    from mdf_viewer.model.measurement import MeasurementInfo

    measurement = LoadedMeasurement(
        loader=MdfLoader(), info=MeasurementInfo(file_name="run.mf4"), label="run",
        offset_s=50.0,
    )
    active = ActiveSignal(
        data=SignalData(timestamps=np.linspace(0.0, 1.0, 10), samples=np.zeros(10)),
        metadata=SignalMetadata(name="sig", unit="V", group_index=0, channel_index=0),
        color=QColor(1, 2, 3),
        measurement=measurement,
    )
    area.add_signal(active)
    area.zoom_to_fit()
    x_min, x_max = area.plot_item.vb.viewRange()[0]
    assert x_min <= 50.0
    assert x_max >= 51.0


def _make_flat(name: str, y: float) -> ActiveSignal:
    return ActiveSignal(
        data=SignalData(timestamps=np.linspace(0.0, 1.0, 10), samples=np.full(10, y)),
        metadata=SignalMetadata(name=name, unit="V", group_index=0, channel_index=0),
        color=QColor(1, 2, 3),
    )


@pytest.mark.requirement("REQ-PLOT-057")
def test_zoom_to_fit_x_always_spans_all_stripes_regardless_of_scope(
    area: PlotStripesArea,
) -> None:
    s2 = area.create_stripe()
    area.add_signal(_make_flat("a", 0.0))
    long = ActiveSignal(
        data=SignalData(timestamps=np.linspace(0.0, 100.0, 10), samples=np.zeros(10)),
        metadata=SignalMetadata(name="long", unit="V", group_index=0, channel_index=1),
        color=QColor(4, 5, 6),
    )
    area.add_signal(long, stripe=s2)
    area.zoom_to_fit(all_stripes=False)  # active stripe is stripe 0
    x_min, x_max = area.plot_item.vb.viewRange()[0]
    assert x_max > 99.0  # X still spans "long" in the other, inactive stripe


@pytest.mark.requirement("REQ-PLOT-057")
def test_zoom_to_fit_active_stripe_only_leaves_other_stripes_y_untouched(
    area: PlotStripesArea,
) -> None:
    s2 = area.create_stripe()
    a = _make_flat("a", 0.0)
    b = _make_flat("b", 500.0)
    area.add_signal(a)          # active stripe (stripe 0)
    area.add_signal(b, stripe=s2)
    s2._data[b].view_box.setYRange(-1.0, 1.0, padding=0)  # known, deliberately-wrong baseline
    before = s2._data[b].view_box.viewRange()[1]

    area.zoom_to_fit(all_stripes=False)

    after = s2._data[b].view_box.viewRange()[1]
    assert after == pytest.approx(before)


@pytest.mark.requirement("REQ-PLOT-057")
def test_zoom_to_fit_all_stripes_autoranges_every_stripe(area: PlotStripesArea) -> None:
    s2 = area.create_stripe()
    a = _make_flat("a", 0.0)
    b = _make_flat("b", 500.0)
    area.add_signal(a)
    area.add_signal(b, stripe=s2)
    s2._data[b].view_box.setYRange(-1.0, 1.0, padding=0)

    area.zoom_to_fit(all_stripes=True)

    y_min, y_max = s2._data[b].view_box.viewRange()[1]
    assert y_min < 500.0 < y_max


@pytest.mark.requirement("REQ-PLOT-057")
def test_zoom_y_to_view_active_stripe_only_leaves_others_untouched(
    area: PlotStripesArea,
) -> None:
    s2 = area.create_stripe()
    a = _make_flat("a", 0.0)
    b = _make_flat("b", 500.0)
    area.add_signal(a)
    area.add_signal(b, stripe=s2)
    s2._data[b].view_box.setYRange(-1.0, 1.0, padding=0)
    before = s2._data[b].view_box.viewRange()[1]

    area.zoom_y_to_view(all_stripes=False)

    after = s2._data[b].view_box.viewRange()[1]
    assert after == pytest.approx(before)


@pytest.mark.requirement("REQ-PLOT-057")
def test_zoom_y_to_view_all_stripes_affects_every_stripe(area: PlotStripesArea) -> None:
    s2 = area.create_stripe()
    a = _make_flat("a", 0.0)
    b = _make_flat("b", 500.0)
    area.add_signal(a)
    area.add_signal(b, stripe=s2)
    s2._data[b].view_box.setYRange(-1.0, 1.0, padding=0)

    area.zoom_y_to_view(all_stripes=True)

    y_min, y_max = s2._data[b].view_box.viewRange()[1]
    assert y_min < 500.0 < y_max


def test_get_zoom_state_and_set_zoom_state_roundtrip(area: PlotStripesArea) -> None:
    active = _make_active()
    area.add_signal(active)
    area.zoom_to_x_range(0.2, 0.8)
    expected_x_range = area.plot_item.vb.viewRange()[0]
    state = area.get_zoom_state([active])
    area.zoom_to_x_range(0.0, 1.0)
    area.set_zoom_state(state, [active])
    assert area.plot_item.vb.viewRange()[0] == pytest.approx(expected_x_range, abs=1e-6)


def test_get_axis_grouping_empty_by_default(area: PlotStripesArea) -> None:
    assert area.get_axis_grouping() == ([], [])


# ---------------------------------------------------------------------------
# Click-selection cross-stripe rule (REQ-PLOT-047)
# ---------------------------------------------------------------------------

def test_hit_click_always_reemitted(area: PlotStripesArea, qtbot: QtBot) -> None:
    active = _make_active()
    with qtbot.waitSignal(area.signal_clicked, timeout=1000) as blocker:
        area._stripes[0].signal_clicked.emit(active)
    assert blocker.args == [active]


def test_miss_click_in_owning_stripe_clears_selection(area: PlotStripesArea, qtbot: QtBot) -> None:
    active = _make_active()
    area._stripes[0].signal_clicked.emit(active)  # selection now "owned" by stripe 0
    with qtbot.waitSignal(area.signal_clicked, timeout=1000) as blocker:
        area._stripes[0].signal_clicked.emit(None)
    assert blocker.args == [None]


def test_miss_click_in_other_stripe_does_not_clear_selection(area: PlotStripesArea, qtbot: QtBot) -> None:
    s2 = area.create_stripe()
    active = _make_active()
    area._stripes[0].signal_clicked.emit(active)  # selection owned by stripe 0

    received: list = []
    area.signal_clicked.connect(received.append)
    s2.signal_clicked.emit(None)  # miss-click in a *different* stripe
    qtbot.wait(50)
    assert received == []  # not forwarded — must not clear stripe 0's selection


def test_first_ever_miss_click_is_forwarded(area: PlotStripesArea, qtbot: QtBot) -> None:
    with qtbot.waitSignal(area.signal_clicked, timeout=1000) as blocker:
        area._stripes[0].signal_clicked.emit(None)
    assert blocker.args == [None]


# ---------------------------------------------------------------------------
# Drag-and-drop onto a specific stripe
# ---------------------------------------------------------------------------

def test_signals_dropped_on_stripe_carries_target_stripe(area: PlotStripesArea, qtbot: QtBot) -> None:
    s2 = area.create_stripe()
    with qtbot.waitSignal(area.signals_dropped_on_stripe, timeout=1000) as blocker:
        s2.signals_dropped.emit([(0, 1)], 2)
    assert blocker.args == [[(0, 1)], s2, 2]


@pytest.mark.requirement("REQ-PLOT-281")
def test_active_signals_dropped_on_stripe_carries_target_stripe(
    area: PlotStripesArea, qtbot: QtBot
) -> None:
    s2 = area.create_stripe()
    ids = {123, 456}
    with qtbot.waitSignal(area.active_signals_dropped_on_stripe, timeout=1000) as blocker:
        s2.active_signals_dropped.emit(ids)
    assert blocker.args == [ids, s2]


# ---------------------------------------------------------------------------
# Signal re-emission
# ---------------------------------------------------------------------------

def test_range_changed_reemitted(area: PlotStripesArea, qtbot: QtBot) -> None:
    with qtbot.waitSignal(area.range_changed, timeout=1000):
        area._stripes[0].range_changed.emit()


def test_y_grid_toggled_reemitted(area: PlotStripesArea, qtbot: QtBot) -> None:
    with qtbot.waitSignal(area.y_grid_toggled, timeout=1000) as blocker:
        area._stripes[0].y_grid_toggled.emit(True)
    assert blocker.args == [True]


def test_delete_stripe_requested_bubbles_up(area: PlotStripesArea, qtbot: QtBot) -> None:
    s2 = area.create_stripe()
    with qtbot.waitSignal(area.delete_stripe_requested, timeout=1000) as blocker:
        s2.delete_stripe_requested.emit(s2)
    assert blocker.args == [s2]


def test_stripe_created_and_deleted_signals(area: PlotStripesArea, qtbot: QtBot) -> None:
    with qtbot.waitSignal(area.stripe_created, timeout=1000) as blocker:
        s2 = area.create_stripe()
    assert blocker.args == [s2]
    with qtbot.waitSignal(area.stripe_deleted, timeout=1000) as blocker:
        area.delete_stripe(s2)
    assert blocker.args == [s2]


# ---------------------------------------------------------------------------
# Cross-stripe axis-width alignment (REQ-PLOT-180)
# ---------------------------------------------------------------------------

def _total_axis_width(stripe) -> float:
    return stripe.content_axis_width() + (
        stripe._axis_spacer.width() if stripe._axis_spacer is not None else 0
    )


def test_stripes_with_different_signal_counts_end_up_same_total_width(
    area: PlotStripesArea, qtbot: QtBot
) -> None:
    s2 = area.create_stripe()
    area.add_signal(_make_active("a"))          # stripe 0: 1 signal
    area.add_signal(_make_active("b"), stripe=s2)  # stripe 1
    area.add_signal(_make_active("c"), stripe=s2)  # stripe 1: 2 signals, wider axis area
    qtbot.wait(20)  # let the deferred realign fire

    assert _total_axis_width(area._stripes[0]) == pytest.approx(_total_axis_width(s2), abs=1.0)


def test_narrower_stripe_gets_padding_not_wider_one(area: PlotStripesArea, qtbot: QtBot) -> None:
    s2 = area.create_stripe()
    area.add_signal(_make_active("a"))
    area.add_signal(_make_active("b"), stripe=s2)
    area.add_signal(_make_active("c"), stripe=s2)
    qtbot.wait(20)

    assert area._stripes[0]._axis_spacer is not None
    assert s2._axis_spacer is None


def test_realign_is_noop_with_equal_width_stripes(area: PlotStripesArea, qtbot: QtBot) -> None:
    s2 = area.create_stripe()
    area.add_signal(_make_active("a"))
    area.add_signal(_make_active("b"), stripe=s2)
    qtbot.wait(20)

    assert area._stripes[0]._axis_spacer is None
    assert s2._axis_spacer is None


def test_removing_signal_reduces_padding_on_other_stripes(
    area: PlotStripesArea, qtbot: QtBot
) -> None:
    s2 = area.create_stripe()
    a = _make_active("a")
    area.add_signal(a)
    area.add_signal(_make_active("b"), stripe=s2)
    area.add_signal(_make_active("c"), stripe=s2)
    qtbot.wait(20)
    assert area._stripes[0]._axis_spacer is not None

    area.remove_signal(list(area.get_signals_in_stripe(s2))[0])
    qtbot.wait(20)

    assert _total_axis_width(area._stripes[0]) == pytest.approx(_total_axis_width(s2), abs=1.0)


def test_range_changed_triggers_realign_after_debounce(
    area: PlotStripesArea, qtbot: QtBot
) -> None:
    """A stripe's axis width can change mid-pan/zoom (e.g. an integer signal's
    tick labels gaining a digit) with no add/remove/move to trigger the
    immediate structural-change path — range_changed must eventually catch
    this too, debounced rather than recomputed every frame."""
    s2 = area.create_stripe()
    a = _make_active("a")
    b = _make_active("b")
    area.add_signal(a)
    area.add_signal(b, stripe=s2)
    qtbot.wait(20)
    assert area._stripes[0]._axis_spacer is None  # equal widths initially

    area._stripes[0]._data[a].axis.setWidth(200)  # simulate a's axis growing wider
    area.zoom_to_x_range(0.1, 0.9)  # fires range_changed, starts the debounce timer

    assert s2._axis_spacer is None  # not recomputed instantly
    qtbot.wait(area._range_realign_timer.interval() + 50)
    assert s2._axis_spacer is not None


def test_single_stripe_has_no_padding(area: PlotStripesArea, qtbot: QtBot) -> None:
    area.add_signal(_make_active())
    qtbot.wait(20)
    assert area._stripes[0]._axis_spacer is None
