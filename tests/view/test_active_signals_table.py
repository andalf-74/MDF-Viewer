"""Tests for ActiveSignalsTable."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PyQt6.QtCore import QByteArray, QEvent, QMimeData
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QMenu
from pytestqt.qtbot import QtBot

from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.view._mime import SIGNAL_MIME_TYPE, encode_signal_payload
from mdf_viewer.view.active_signals_table import (
    ActiveSignalsTable,
    _cell_inner_widget,
    _COL_C1,
    _COL_C2,
    _COL_COLOR,
    _COL_DELTA,
    _COL_NAME,
    _COL_VISIBLE,
)
from mdf_viewer.view.widgets import ColorSwatch as _ColorSwatch
from mdf_viewer.view_model.active_signal import ActiveSignal


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

class _FakeStripe:
    """Minimal stand-in for a PlotStripe in stripe-provider tests — just a
    named, identity-hashable object (SimpleNamespace defines __eq__, which
    makes it unhashable and unusable as a set element)."""

    def __init__(self, name: str) -> None:
        self.name = name


def _make_active(name: str = "sig", color: QColor | None = None) -> ActiveSignal:
    t = np.array([0.0, 1.0])
    data = SignalData(timestamps=t, samples=t)
    meta = SignalMetadata(name=name, unit="V", group_index=0, channel_index=0)
    return ActiveSignal(data=data, metadata=meta, color=color or QColor(255, 0, 0))


@pytest.fixture()
def table(qtbot: QtBot) -> ActiveSignalsTable:
    w = ActiveSignalsTable()
    qtbot.addWidget(w)
    return w


@pytest.fixture()
def populated(table: ActiveSignalsTable) -> tuple[ActiveSignalsTable, list[ActiveSignal]]:
    sigs = [
        _make_active("alpha", QColor(255, 0, 0)),
        _make_active("beta", QColor(0, 0, 255)),
        _make_active("gamma", QColor(0, 200, 0)),
    ]
    for s in sigs:
        table.add_row(s)
    return table, sigs


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

def test_initially_empty(table: ActiveSignalsTable) -> None:
    assert table._segments == []


@pytest.mark.requirement("REQ-PLOT-141")
def test_remove_button_disabled_initially(table: ActiveSignalsTable) -> None:
    assert not table._remove_btn.isEnabled()


@pytest.mark.requirement("REQ-PLOT-070")
def test_cursor_columns_hidden_initially(table: ActiveSignalsTable) -> None:
    assert table._header.isColumnHidden(_COL_C1)
    assert table._header.isColumnHidden(_COL_C2)
    assert table._header.isColumnHidden(_COL_DELTA)


# ---------------------------------------------------------------------------
# add_row
# ---------------------------------------------------------------------------

def test_add_row_increases_row_count(table: ActiveSignalsTable) -> None:
    table.add_row(_make_active("x"))
    assert table._segments[0].rowCount() == 1


def test_add_multiple_rows(table: ActiveSignalsTable) -> None:
    for i in range(3):
        table.add_row(_make_active(f"sig{i}"))
    assert table._segments[0].rowCount() == 3


def test_add_row_shows_signal_name(table: ActiveSignalsTable) -> None:
    table.add_row(_make_active("engine_speed"))
    assert table._segments[0].item(0, _COL_NAME).text() == "engine_speed"


@pytest.mark.requirement("REQ-PLOT-120")
def test_add_row_places_color_swatch(table: ActiveSignalsTable) -> None:
    table.add_row(_make_active("x", QColor(100, 200, 50)))
    swatch = _cell_inner_widget(table._segments[0], 0, _COL_COLOR)
    assert isinstance(swatch, _ColorSwatch)


@pytest.mark.requirement("REQ-PLOT-120")
def test_add_row_swatch_has_correct_color(table: ActiveSignalsTable) -> None:
    color = QColor(123, 45, 67)
    table.add_row(_make_active("x", color))
    swatch = _cell_inner_widget(table._segments[0], 0, _COL_COLOR)
    assert swatch.color == color


# ---------------------------------------------------------------------------
# remove_row
# ---------------------------------------------------------------------------

def test_remove_row_decreases_row_count(populated: tuple) -> None:
    t, sigs = populated
    t.remove_row(sigs[1])
    assert t._segments[0].rowCount() == 2


def test_remove_row_removes_correct_signal(populated: tuple) -> None:
    t, sigs = populated
    t.remove_row(sigs[1])
    assert t._segments[0].item(0, _COL_NAME).text() == "alpha"
    assert t._segments[0].item(1, _COL_NAME).text() == "gamma"


@pytest.mark.requirement("REQ-PLOT-023")
def test_remove_row_noop_for_unknown(table: ActiveSignalsTable) -> None:
    stranger = _make_active("x")
    table.remove_row(stranger)  # must not raise


def test_remove_selected_row_does_not_raise(populated: tuple) -> None:
    t, sigs = populated
    t._segments[0].selectRow(1)
    t.remove_row(sigs[1])  # must not raise IndexError from itemSelectionChanged


def test_remove_first_row(populated: tuple) -> None:
    t, sigs = populated
    t.remove_row(sigs[0])
    assert t._segments[0].item(0, _COL_NAME).text() == "beta"


def test_remove_last_row(populated: tuple) -> None:
    t, sigs = populated
    t.remove_row(sigs[2])
    assert t._segments[0].rowCount() == 2
    assert t._segments[0].item(1, _COL_NAME).text() == "beta"


# ---------------------------------------------------------------------------
# Multi-segment lifecycle (#100)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-270")
def test_no_segments_initially(table: ActiveSignalsTable) -> None:
    assert table._segments == []


@pytest.mark.requirement("REQ-PLOT-270")
def test_add_stripe_segment_creates_a_segment(table: ActiveSignalsTable) -> None:
    stripe = _FakeStripe("Stripe 1")
    seg = table.add_stripe_segment(stripe)
    assert table._segments == [seg]


@pytest.mark.requirement("REQ-PLOT-270")
def test_add_stripe_segment_is_idempotent(table: ActiveSignalsTable) -> None:
    stripe = _FakeStripe("Stripe 1")
    seg1 = table.add_stripe_segment(stripe)
    seg2 = table.add_stripe_segment(stripe)
    assert seg1 is seg2
    assert len(table._segments) == 1


@pytest.mark.requirement("REQ-PLOT-270")
def test_add_stripe_segment_for_two_stripes_creates_two_segments(
    table: ActiveSignalsTable,
) -> None:
    s1 = table.add_stripe_segment(_FakeStripe("Stripe 1"))
    s2 = table.add_stripe_segment(_FakeStripe("Stripe 2"))
    assert table._segments == [s1, s2]


def test_remove_stripe_segment_removes_it(table: ActiveSignalsTable) -> None:
    stripe = _FakeStripe("Stripe 1")
    table.add_stripe_segment(stripe)
    table.remove_stripe_segment(stripe)
    assert table._segments == []


def test_remove_stripe_segment_noop_for_unknown(table: ActiveSignalsTable) -> None:
    table.remove_stripe_segment(_FakeStripe("nope"))  # must not raise
    assert table._segments == []


@pytest.mark.requirement("REQ-PLOT-270")
def test_add_row_with_stripe_routes_to_correct_segment(table: ActiveSignalsTable) -> None:
    s1 = _FakeStripe("Stripe 1")
    s2 = _FakeStripe("Stripe 2")
    seg1 = table.add_stripe_segment(s1)
    seg2 = table.add_stripe_segment(s2)
    a = _make_active("alpha")
    b = _make_active("beta")
    table.add_row(a, s1)
    table.add_row(b, s2)
    assert table._segment_signals(seg1) == [a]
    assert table._segment_signals(seg2) == [b]


def test_add_row_creates_segment_lazily_for_unregistered_stripe(
    table: ActiveSignalsTable,
) -> None:
    stripe = _FakeStripe("Stripe 1")
    table.add_row(_make_active("x"), stripe)
    assert table._segment_for_stripe[stripe] in table._segments


@pytest.mark.requirement("REQ-PLOT-270")
def test_remove_row_finds_signal_across_segments(table: ActiveSignalsTable) -> None:
    s1 = _FakeStripe("Stripe 1")
    s2 = _FakeStripe("Stripe 2")
    seg1 = table.add_stripe_segment(s1)
    seg2 = table.add_stripe_segment(s2)
    a = _make_active("alpha")
    b = _make_active("beta")
    table.add_row(a, s1)
    table.add_row(b, s2)
    table.remove_row(b)
    assert table._segment_signals(seg1) == [a]
    assert table._segment_signals(seg2) == []


@pytest.mark.requirement("REQ-PLOT-270")
def test_set_row_color_finds_signal_across_segments(table: ActiveSignalsTable) -> None:
    s1 = _FakeStripe("Stripe 1")
    s2 = _FakeStripe("Stripe 2")
    table.add_stripe_segment(s1)
    seg2 = table.add_stripe_segment(s2)
    a = _make_active("alpha")
    b = _make_active("beta")
    table.add_row(a, s1)
    table.add_row(b, s2)
    new_color = QColor(9, 9, 9)
    table.set_row_color(b, new_color)
    swatch = _cell_inner_widget(seg2, 0, _COL_COLOR)
    assert swatch.color == new_color


@pytest.mark.requirement("REQ-PLOT-270")
def test_update_cursor_values_finds_signal_across_segments(table: ActiveSignalsTable) -> None:
    s1 = _FakeStripe("Stripe 1")
    s2 = _FakeStripe("Stripe 2")
    table.add_stripe_segment(s1)
    seg2 = table.add_stripe_segment(s2)
    a = _make_active("alpha")
    b = _make_active("beta")
    table.add_row(a, s1)
    table.add_row(b, s2)
    table.update_cursor_values(b, "1.1", "2.2", "3.3")
    assert seg2.item(0, _COL_C1).text() == "1.1"


# ---------------------------------------------------------------------------
# move_to_stripe (#100)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-202")
def test_move_to_stripe_reassigns_membership(table: ActiveSignalsTable) -> None:
    s1 = _FakeStripe("Stripe 1")
    s2 = _FakeStripe("Stripe 2")
    seg1 = table.add_stripe_segment(s1)
    seg2 = table.add_stripe_segment(s2)
    a = _make_active("alpha")
    table.add_row(a, s1)
    table.move_to_stripe([a], s2)
    assert table._segment_signals(seg1) == []
    assert table._segment_signals(seg2) == [a]


@pytest.mark.requirement("REQ-PLOT-203")
def test_move_to_stripe_does_not_duplicate(table: ActiveSignalsTable) -> None:
    s1 = _FakeStripe("Stripe 1")
    s2 = _FakeStripe("Stripe 2")
    table.add_stripe_segment(s1)
    table.add_stripe_segment(s2)
    a = _make_active("alpha")
    table.add_row(a, s1)
    table.move_to_stripe([a], s2)
    assert table._signals.count(a) == 1


def test_move_to_stripe_noop_when_already_in_target(table: ActiveSignalsTable) -> None:
    s1 = _FakeStripe("Stripe 1")
    seg1 = table.add_stripe_segment(s1)
    a = _make_active("alpha")
    table.add_row(a, s1)
    table.move_to_stripe([a], s1)  # already there
    assert table._segment_signals(seg1) == [a]


def test_move_to_stripe_creates_target_segment_if_missing(table: ActiveSignalsTable) -> None:
    s1 = _FakeStripe("Stripe 1")
    s2 = _FakeStripe("Stripe 2")  # never explicitly created
    table.add_stripe_segment(s1)
    a = _make_active("alpha")
    table.add_row(a, s1)
    table.move_to_stripe([a], s2)
    seg2 = table._segment_for_stripe[s2]
    assert table._segment_signals(seg2) == [a]


@pytest.mark.requirement("REQ-PLOT-202")
def test_signal_survives_deletion_of_its_former_stripe(table: ActiveSignalsTable) -> None:
    """Regression test for the #100 M3 postmortem: moving a signal to a
    different stripe, then deleting its OLD stripe, must not orphan the
    signal's AST row — reproduces the exact live-tested failure scenario."""
    s1 = _FakeStripe("Stripe 1")
    s2 = _FakeStripe("Stripe 2")
    table.add_stripe_segment(s1)
    seg2 = table.add_stripe_segment(s2)
    a = _make_active("alpha")
    table.add_row(a, s1)
    table.move_to_stripe([a], s2)
    table.remove_stripe_segment(s1)
    seg, row = table._find(a)
    assert seg is seg2
    assert row == 0


# ---------------------------------------------------------------------------
# Stripe rename (#100 M9)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-290")
def test_segment_label_shows_stripe_name(table: ActiveSignalsTable) -> None:
    stripe = _FakeStripe("Stripe 1")
    seg = table.add_stripe_segment(stripe)
    assert seg.name_label.text() == "Stripe 1"


@pytest.mark.requirement("REQ-PLOT-292")
def test_rename_segment_updates_stripe_name(table: ActiveSignalsTable) -> None:
    stripe = _FakeStripe("Stripe 1")
    seg = table.add_stripe_segment(stripe)
    with patch(
        "PyQt6.QtWidgets.QInputDialog.getText",
        return_value=("Engine Data", True),
    ):
        table._rename_segment(seg)
    assert stripe.name == "Engine Data"


@pytest.mark.requirement("REQ-PLOT-292")
def test_rename_segment_updates_label_text(table: ActiveSignalsTable) -> None:
    stripe = _FakeStripe("Stripe 1")
    seg = table.add_stripe_segment(stripe)
    with patch(
        "PyQt6.QtWidgets.QInputDialog.getText",
        return_value=("Engine Data", True),
    ):
        table._rename_segment(seg)
    assert seg.name_label.text() == "Engine Data"


def test_rename_segment_cancelled_leaves_name_unchanged(table: ActiveSignalsTable) -> None:
    stripe = _FakeStripe("Stripe 1")
    seg = table.add_stripe_segment(stripe)
    with patch(
        "PyQt6.QtWidgets.QInputDialog.getText",
        return_value=("Engine Data", False),  # user hit Cancel
    ):
        table._rename_segment(seg)
    assert stripe.name == "Stripe 1"


def test_rename_segment_blank_name_leaves_name_unchanged(table: ActiveSignalsTable) -> None:
    stripe = _FakeStripe("Stripe 1")
    seg = table.add_stripe_segment(stripe)
    with patch(
        "PyQt6.QtWidgets.QInputDialog.getText",
        return_value=("   ", True),
    ):
        table._rename_segment(seg)
    assert stripe.name == "Stripe 1"


@pytest.mark.requirement("REQ-FILE-090")
def test_rename_stripe_segment_sets_both_name_and_label(table: ActiveSignalsTable) -> None:
    """#106: stripe.name and the segment's name_label aren't live-bound —
    a programmatic caller (bulk session restore) must update both."""
    stripe = _FakeStripe("Stripe 1")
    seg = table.add_stripe_segment(stripe)

    table.rename_stripe_segment(stripe, "Vibration")

    assert stripe.name == "Vibration"
    assert seg.name_label.text() == "Vibration"


@pytest.mark.requirement("REQ-FILE-090")
def test_rename_stripe_segment_targets_correct_segment_among_several(
    table: ActiveSignalsTable,
) -> None:
    s1, s2 = _FakeStripe("Stripe 1"), _FakeStripe("Stripe 2")
    seg1 = table.add_stripe_segment(s1)
    seg2 = table.add_stripe_segment(s2)

    table.rename_stripe_segment(s2, "Temp")

    assert s1.name == "Stripe 1"
    assert seg1.name_label.text() != "Temp"
    assert s2.name == "Temp"
    assert seg2.name_label.text() == "Temp"


@pytest.mark.requirement("REQ-PLOT-293")
def test_move_to_stripe_submenu_reflects_rename(table: ActiveSignalsTable) -> None:
    s1 = _FakeStripe("Stripe 1")
    s2 = _FakeStripe("Stripe 2")
    table.add_stripe_segment(s1)  # segments[0] — gets the row _open_context_menu clicks
    seg2 = table.add_stripe_segment(s2)
    with patch(
        "PyQt6.QtWidgets.QInputDialog.getText",
        return_value=("Engine Data", True),
    ):
        table._rename_segment(seg2)
    table.add_row(_make_active("x"), s1)
    table.set_stripe_providers(lambda: [s1, s2], lambda a: s1)
    menu = _open_context_menu(table)
    submenu_action = next(a for a in menu.actions() if a.text() == "Move to Stripe")
    sub_titles = [a.text() for a in submenu_action.menu().actions()]
    assert sub_titles == ["Engine Data"]


def test_double_click_label_triggers_rename(table: ActiveSignalsTable) -> None:
    stripe = _FakeStripe("Stripe 1")
    seg = table.add_stripe_segment(stripe)
    with patch(
        "PyQt6.QtWidgets.QInputDialog.getText",
        return_value=("Engine Data", True),
    ):
        seg.name_label.mouseDoubleClickEvent(MagicMock())
    assert stripe.name == "Engine Data"


# ---------------------------------------------------------------------------
# Cross-segment selection / stripe activation (#100)
# ---------------------------------------------------------------------------

def _make_mouse_event(button, modifiers=None, point=None):
    from PyQt6.QtCore import QPoint, Qt
    event = MagicMock()
    event.button.return_value = button
    event.modifiers.return_value = modifiers if modifiers is not None else Qt.KeyboardModifier.NoModifier
    event.position.return_value.toPoint.return_value = point if point is not None else QPoint(5, 5)
    return event


@pytest.mark.requirement("REQ-PLOT-278")
def test_mouse_press_emits_segment_activated(table: ActiveSignalsTable, qtbot: QtBot) -> None:
    from PyQt6.QtCore import Qt
    s1 = _FakeStripe("Stripe 1")
    seg1 = table.add_stripe_segment(s1)
    with qtbot.waitSignal(table.segment_activated) as blocker:
        table._on_segment_mouse_press(seg1, _make_mouse_event(Qt.MouseButton.LeftButton))
    assert blocker.args[0] is s1


@pytest.mark.requirement("REQ-PLOT-278")
def test_right_click_also_emits_segment_activated(table: ActiveSignalsTable, qtbot: QtBot) -> None:
    from PyQt6.QtCore import Qt
    s1 = _FakeStripe("Stripe 1")
    seg1 = table.add_stripe_segment(s1)
    with qtbot.waitSignal(table.segment_activated) as blocker:
        table._on_segment_mouse_press(seg1, _make_mouse_event(Qt.MouseButton.RightButton))
    assert blocker.args[0] is s1


@pytest.mark.requirement("REQ-PLOT-276")
def test_plain_click_clears_other_segments_selection(table: ActiveSignalsTable) -> None:
    from PyQt6.QtCore import Qt
    s1 = _FakeStripe("Stripe 1")
    s2 = _FakeStripe("Stripe 2")
    seg1 = table.add_stripe_segment(s1)
    seg2 = table.add_stripe_segment(s2)
    table.add_row(_make_active("alpha"), s1)
    table.add_row(_make_active("beta"), s2)
    seg2.selectRow(0)
    table._on_segment_mouse_press(seg1, _make_mouse_event(Qt.MouseButton.LeftButton))
    assert not seg2.selectionModel().hasSelection()


@pytest.mark.requirement("REQ-PLOT-276")
def test_shift_click_clears_other_segments_selection(table: ActiveSignalsTable) -> None:
    from PyQt6.QtCore import Qt
    s1 = _FakeStripe("Stripe 1")
    s2 = _FakeStripe("Stripe 2")
    seg1 = table.add_stripe_segment(s1)
    seg2 = table.add_stripe_segment(s2)
    table.add_row(_make_active("alpha"), s1)
    table.add_row(_make_active("beta"), s2)
    seg2.selectRow(0)
    table._on_segment_mouse_press(
        seg1, _make_mouse_event(Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier)
    )
    assert not seg2.selectionModel().hasSelection()


@pytest.mark.requirement("REQ-PLOT-276")
def test_ctrl_click_preserves_other_segments_selection(table: ActiveSignalsTable) -> None:
    from PyQt6.QtCore import Qt
    s1 = _FakeStripe("Stripe 1")
    s2 = _FakeStripe("Stripe 2")
    seg1 = table.add_stripe_segment(s1)
    seg2 = table.add_stripe_segment(s2)
    table.add_row(_make_active("alpha"), s1)
    table.add_row(_make_active("beta"), s2)
    seg2.selectRow(0)
    table._on_segment_mouse_press(
        seg1, _make_mouse_event(Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier)
    )
    assert seg2.selectionModel().hasSelection()


@pytest.mark.requirement("REQ-PLOT-276")
def test_right_click_preserves_other_segments_selection(table: ActiveSignalsTable) -> None:
    from PyQt6.QtCore import Qt
    s1 = _FakeStripe("Stripe 1")
    s2 = _FakeStripe("Stripe 2")
    seg1 = table.add_stripe_segment(s1)
    seg2 = table.add_stripe_segment(s2)
    table.add_row(_make_active("alpha"), s1)
    table.add_row(_make_active("beta"), s2)
    seg2.selectRow(0)
    table._on_segment_mouse_press(seg1, _make_mouse_event(Qt.MouseButton.RightButton))
    assert seg2.selectionModel().hasSelection()


@pytest.mark.requirement("REQ-PLOT-279")
def test_press_on_already_selected_row_defers_clearing_other_segments(
    table: ActiveSignalsTable,
) -> None:
    """Regression test: pressing an already-selected row (to start dragging
    a cross-segment selection) must NOT immediately clear sibling segments
    — that pre-empts the drag before it can pick up the whole group. Found
    live: Ctrl-select rows in two segments, release, then press again
    (no Ctrl) on one of them intending to drag — the other segment's
    selection was being wiped on press, before the drag could start."""
    from PyQt6.QtCore import Qt
    s1 = _FakeStripe("Stripe 1")
    s2 = _FakeStripe("Stripe 2")
    seg1 = table.add_stripe_segment(s1)
    seg2 = table.add_stripe_segment(s2)
    table.add_row(_make_active("alpha"), s1)
    table.add_row(_make_active("beta"), s2)
    seg1.selectRow(0)
    seg2.selectRow(0)
    table._on_segment_mouse_press(seg1, _make_mouse_event(Qt.MouseButton.LeftButton))
    assert seg2.selectionModel().hasSelection()
    assert seg1.selectionModel().hasSelection()


@pytest.mark.requirement("REQ-PLOT-279")
def test_click_release_without_drag_collapses_deferred_selection(
    table: ActiveSignalsTable,
) -> None:
    """The other half of the deferred-clear: if the press on an
    already-selected row does NOT turn into a drag, releasing collapses the
    selection down to a plain single-segment click, same as an immediate
    clear would have."""
    from PyQt6.QtCore import Qt
    s1 = _FakeStripe("Stripe 1")
    s2 = _FakeStripe("Stripe 2")
    seg1 = table.add_stripe_segment(s1)
    seg2 = table.add_stripe_segment(s2)
    table.add_row(_make_active("alpha"), s1)
    table.add_row(_make_active("beta"), s2)
    seg1.selectRow(0)
    seg2.selectRow(0)
    table._on_segment_mouse_press(seg1, _make_mouse_event(Qt.MouseButton.LeftButton))
    assert seg2.selectionModel().hasSelection()  # still deferred
    table._on_segment_click_release(seg1, _make_mouse_event(Qt.MouseButton.LeftButton))
    assert not seg2.selectionModel().hasSelection()


@pytest.mark.requirement("REQ-PLOT-279")
def test_drag_after_press_on_selected_row_never_triggers_release_clear(
    table: ActiveSignalsTable,
) -> None:
    """_ActiveTable itself: once mouseMoveEvent has started a real drag,
    mouseReleaseEvent must not also fire on_click_release — the deferred
    clear only applies to a press that turns out to be a plain click."""
    from PyQt6.QtCore import QPointF, Qt
    from PyQt6.QtGui import QMouseEvent
    stripe = _FakeStripe("Stripe 1")
    seg = table.add_stripe_segment(stripe)
    table.add_row(_make_active("alpha"), stripe)
    seg._drag_happened = True
    calls = []
    seg.on_click_release = lambda event: calls.append(event)
    # A real QMouseEvent (not the MagicMock helper) since this call reaches
    # QTableWidget's own base mouseReleaseEvent, which needs a real one.
    release_event = QMouseEvent(
        QEvent.Type.MouseButtonRelease, QPointF(5, 5),
        Qt.MouseButton.LeftButton, Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
    )
    seg.mouseReleaseEvent(release_event)
    assert calls == []


@pytest.mark.requirement("REQ-PLOT-280")
def test_clear_clears_every_segment(table: ActiveSignalsTable) -> None:
    s1 = _FakeStripe("Stripe 1")
    s2 = _FakeStripe("Stripe 2")
    seg1 = table.add_stripe_segment(s1)
    seg2 = table.add_stripe_segment(s2)
    table.add_row(_make_active("alpha"), s1)
    table.add_row(_make_active("beta"), s2)
    table.clear()
    assert seg1.rowCount() == 0
    assert seg2.rowCount() == 0
    assert table._segment_signals(seg1) == []
    assert table._segment_signals(seg2) == []


@pytest.mark.requirement("REQ-PLOT-271")
def test_show_cursor_columns_applies_to_header_and_every_segment(
    table: ActiveSignalsTable,
) -> None:
    seg1 = table.add_stripe_segment(_FakeStripe("Stripe 1"))
    seg2 = table.add_stripe_segment(_FakeStripe("Stripe 2"))
    table.show_cursor_columns(True)
    assert not table._header.isColumnHidden(_COL_C1)
    assert not seg1.isColumnHidden(_COL_C1)
    assert not seg2.isColumnHidden(_COL_C1)


@pytest.mark.requirement("REQ-PLOT-271")
def test_header_column_resize_propagates_to_every_segment(
    table: ActiveSignalsTable,
) -> None:
    seg1 = table.add_stripe_segment(_FakeStripe("Stripe 1"))
    seg2 = table.add_stripe_segment(_FakeStripe("Stripe 2"))
    table._header.setColumnWidth(_COL_NAME, 250)
    assert seg1.columnWidth(_COL_NAME) == 250
    assert seg2.columnWidth(_COL_NAME) == 250


@pytest.mark.requirement("REQ-FILE-090")
def test_column_widths_reflects_header(table: ActiveSignalsTable) -> None:
    table._header.setColumnWidth(1, 250)
    widths = table.column_widths()
    assert widths[1] == 250
    assert len(widths) == table._header.columnCount()


@pytest.mark.requirement("REQ-FILE-090")
def test_set_column_widths_applies_to_header_and_segments(table: ActiveSignalsTable) -> None:
    seg1 = table.add_stripe_segment(_FakeStripe("Stripe 1"))

    table.set_column_widths([24, 28, 200, 90, 90, 90])

    assert table._header.columnWidth(_COL_NAME) == 200
    assert seg1.columnWidth(_COL_NAME) == 200


@pytest.mark.requirement("REQ-FILE-090")
def test_set_column_widths_ignores_extra_and_invalid_entries(table: ActiveSignalsTable) -> None:
    original = table.column_widths()
    table.set_column_widths([0, -5] + [999] * 10)  # first two invalid, rest out of range
    assert table.column_widths()[0] == original[0]
    assert table.column_widths()[1] == original[1]


@pytest.mark.requirement("REQ-PLOT-274")
def test_set_segment_sizes_applies_to_splitter(table: ActiveSignalsTable) -> None:
    # Only the first/last entries are adjusted (by the widget's own known
    # header/button chrome) — see _build_ui's _top_size_offset/
    # _bottom_size_offset comment for why a plain 1:1 copy is wrong.
    table.add_stripe_segment(_FakeStripe("Stripe 1"))
    table.add_stripe_segment(_FakeStripe("Stripe 2"))
    with patch.object(table._segments_splitter, "setSizes") as mock_set_sizes:
        table.set_segment_sizes([100, 900])
    mock_set_sizes.assert_called_once_with(
        [100 - table._top_size_offset, 900 - table._bottom_size_offset]
    )


@pytest.mark.requirement("REQ-PLOT-274")
def test_set_segment_sizes_does_not_emit_segment_sizes_changed(
    table: ActiveSignalsTable, qtbot: QtBot
) -> None:
    table.add_stripe_segment(_FakeStripe("Stripe 1"))
    table.add_stripe_segment(_FakeStripe("Stripe 2"))
    with qtbot.assertNotEmitted(table.segment_sizes_changed):
        table.set_segment_sizes([10, 90])


@pytest.mark.requirement("REQ-PLOT-274")
def test_segment_splitter_moved_emits_segment_sizes_changed(
    table: ActiveSignalsTable, qtbot: QtBot
) -> None:
    table.add_stripe_segment(_FakeStripe("Stripe 1"))
    table.add_stripe_segment(_FakeStripe("Stripe 2"))
    raw = table._segments_splitter.sizes()
    with qtbot.waitSignal(table.segment_sizes_changed) as blocker:
        table._on_segment_splitter_moved(0, 0)
    assert blocker.args[0] == [
        raw[0] + table._top_size_offset, raw[1] + table._bottom_size_offset
    ]


# ---------------------------------------------------------------------------
# clear
# ---------------------------------------------------------------------------

def test_clear_removes_all_rows(populated: tuple) -> None:
    t, _ = populated
    t.clear()
    assert t._segments[0].rowCount() == 0


def test_clear_resets_internal_list(populated: tuple) -> None:
    t, _ = populated
    t.clear()
    assert t._signals == []


def test_clear_with_selection_does_not_raise(populated: tuple) -> None:
    t, _ = populated
    t._segments[0].selectRow(0)
    t.clear()  # must not raise IndexError from itemSelectionChanged


# ---------------------------------------------------------------------------
# show_cursor_columns
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-080")
def test_show_cursor_columns_makes_them_visible(table: ActiveSignalsTable) -> None:
    table.show_cursor_columns(True)
    assert not table._header.isColumnHidden(_COL_C1)
    assert not table._header.isColumnHidden(_COL_C2)
    assert not table._header.isColumnHidden(_COL_DELTA)


@pytest.mark.requirement("REQ-PLOT-080")
def test_hide_cursor_columns(table: ActiveSignalsTable) -> None:
    table.show_cursor_columns(True)
    table.show_cursor_columns(False)
    assert table._header.isColumnHidden(_COL_C1)


# ---------------------------------------------------------------------------
# update_cursor_values
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-080")
def test_update_cursor_values_sets_text(populated: tuple) -> None:
    t, sigs = populated
    t.update_cursor_values(sigs[0], "1.23", "4.56", "3.33")
    assert t._segments[0].item(0, _COL_C1).text() == "1.23"
    assert t._segments[0].item(0, _COL_C2).text() == "4.56"
    assert t._segments[0].item(0, _COL_DELTA).text() == "3.33"


@pytest.mark.requirement("REQ-PLOT-023")
def test_update_cursor_values_noop_for_unknown(table: ActiveSignalsTable) -> None:
    stranger = _make_active("x")
    table.update_cursor_values(stranger, "1", "2", "3")  # must not raise


# ---------------------------------------------------------------------------
# Remove button state
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-141")
def test_remove_button_enabled_after_selection(populated: tuple) -> None:
    t, sigs = populated
    idx = t._segments[0].model().index(0, 1)
    t._segments[0].setCurrentIndex(idx)
    assert t._remove_btn.isEnabled()


@pytest.mark.requirement("REQ-PLOT-141")
def test_remove_button_disabled_after_clear(populated: tuple) -> None:
    t, sigs = populated
    t._segments[0].setCurrentIndex(t._segments[0].model().index(0, 1))
    t.clear()
    assert not t._remove_btn.isEnabled()


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-141")
def test_remove_button_emits_remove_requested(
    populated: tuple, qtbot: QtBot
) -> None:
    t, sigs = populated
    t._segments[0].setCurrentIndex(t._segments[0].model().index(1, 1))
    with qtbot.waitSignal(t.remove_requested, timeout=500) as blocker:
        t._remove_btn.click()
    assert blocker.args[0] == [sigs[1]]


def test_remove_all_button_emits_remove_all_requested(
    populated: tuple, qtbot: QtBot
) -> None:
    t, _ = populated
    with qtbot.waitSignal(t.remove_all_requested, timeout=500):
        t._remove_all_btn.click()


def test_selection_change_emits_active_signal(
    populated: tuple, qtbot: QtBot
) -> None:
    t, sigs = populated
    with qtbot.waitSignal(t.selection_changed, timeout=500) as blocker:
        t._segments[0].setCurrentIndex(t._segments[0].model().index(2, 1))
    assert blocker.args[0] is sigs[2]


def test_clearing_selection_emits_none(populated: tuple, qtbot: QtBot) -> None:
    t, _ = populated
    t._segments[0].setCurrentIndex(t._segments[0].model().index(0, 1))
    with qtbot.waitSignal(t.selection_changed, timeout=500) as blocker:
        t._segments[0].clearSelection()
    assert blocker.args[0] is None


@pytest.mark.requirement("REQ-PLOT-120")
def test_color_change_emits_signal(populated: tuple, qtbot: QtBot) -> None:
    t, sigs = populated
    new_color = QColor(10, 20, 30)
    with patch(
        "mdf_viewer.view.active_signals_table.QColorDialog.getColor",
        return_value=new_color,
    ):
        with qtbot.waitSignal(t.color_change_requested, timeout=500) as blocker:
            t._on_color_swatch_clicked(sigs[0])
    assert blocker.args[0] == [sigs[0]]
    assert blocker.args[1] == new_color


@pytest.mark.requirement("REQ-PLOT-120")
def test_color_change_updates_swatch(populated: tuple, qtbot: QtBot) -> None:
    t, sigs = populated
    new_color = QColor(10, 20, 30)
    with patch(
        "mdf_viewer.view.active_signals_table.QColorDialog.getColor",
        return_value=new_color,
    ):
        t._on_color_swatch_clicked(sigs[0])
    swatch = _cell_inner_widget(t._segments[0], 0, _COL_COLOR)
    assert swatch.color == new_color


@pytest.mark.requirement("REQ-PLOT-120")
def test_color_change_cancelled_does_not_emit(
    populated: tuple, qtbot: QtBot
) -> None:
    t, sigs = populated
    invalid = QColor()  # invalid color = dialog cancelled
    with patch(
        "mdf_viewer.view.active_signals_table.QColorDialog.getColor",
        return_value=invalid,
    ):
        with qtbot.assertNotEmitted(t.color_change_requested):
            t._on_color_swatch_clicked(sigs[0])


# ---------------------------------------------------------------------------
# Signal Visibility (#133)
# ---------------------------------------------------------------------------

def test_add_row_places_visibility_button(table: ActiveSignalsTable) -> None:
    from mdf_viewer.view.widgets import VisibilityToggleButton
    table.add_row(_make_active("x"))
    btn = _cell_inner_widget(table._segments[0], 0, _COL_VISIBLE)
    assert isinstance(btn, VisibilityToggleButton)


def test_add_row_visibility_button_reflects_initial_state(table: ActiveSignalsTable) -> None:
    hidden = _make_active("x")
    hidden.visible = False
    table.add_row(hidden)
    btn = _cell_inner_widget(table._segments[0], 0, _COL_VISIBLE)
    assert btn.visible_state is False


@pytest.mark.requirement("REQ-PLOT-332")
def test_visibility_button_click_emits_just_that_row(populated: tuple, qtbot: QtBot) -> None:
    t, sigs = populated
    btn = _cell_inner_widget(t._segments[0], 0, _COL_VISIBLE)
    with qtbot.waitSignal(t.visibility_toggle_requested, timeout=500) as blocker:
        btn.click()
    assert blocker.args[0] == [sigs[0]]


@pytest.mark.requirement("REQ-PLOT-334")
def test_visibility_button_click_on_multi_selection_emits_whole_selection(
    populated: tuple, qtbot: QtBot
) -> None:
    t, sigs = populated
    sm = t._segments[0].selectionModel()
    sm.clearSelection()
    for row in (0, 1):
        sm.select(
            t._segments[0].model().index(row, 0),
            sm.SelectionFlag.Select | sm.SelectionFlag.Rows,
        )
    btn = _cell_inner_widget(t._segments[0], 0, _COL_VISIBLE)
    with qtbot.waitSignal(t.visibility_toggle_requested, timeout=500) as blocker:
        btn.click()
    assert set(blocker.args[0]) == {sigs[0], sigs[1]}


@pytest.mark.requirement("REQ-PLOT-334")
def test_visibility_button_click_on_row_outside_selection_emits_just_that_row(
    populated: tuple, qtbot: QtBot
) -> None:
    t, sigs = populated
    t._segments[0].selectRow(1)
    btn = _cell_inner_widget(t._segments[0], 0, _COL_VISIBLE)
    with qtbot.waitSignal(t.visibility_toggle_requested, timeout=500) as blocker:
        btn.click()
    assert blocker.args[0] == [sigs[0]]


@pytest.mark.requirement("REQ-PLOT-332")
def test_ctrl_w_toggles_selected_signals(populated: tuple, qtbot: QtBot) -> None:
    from PyQt6.QtCore import Qt
    t, sigs = populated
    t._segments[0].selectRow(0)
    with qtbot.waitSignal(t.visibility_toggle_requested, timeout=500) as blocker:
        qtbot.keyClick(t, Qt.Key.Key_W, Qt.KeyboardModifier.ControlModifier)
    assert blocker.args[0] == [sigs[0]]


@pytest.mark.requirement("REQ-PLOT-332")
def test_ctrl_w_no_selection_does_not_emit(table: ActiveSignalsTable, qtbot: QtBot) -> None:
    from PyQt6.QtCore import Qt
    with qtbot.assertNotEmitted(table.visibility_toggle_requested):
        qtbot.keyClick(table, Qt.Key.Key_W, Qt.KeyboardModifier.ControlModifier)


def test_set_row_visible_icon_updates_button(populated: tuple) -> None:
    t, sigs = populated
    t.set_row_visible_icon(sigs[0], False)
    btn = _cell_inner_widget(t._segments[0], 0, _COL_VISIBLE)
    assert btn.visible_state is False


def test_set_row_visible_icon_unknown_signal_is_noop(table: ActiveSignalsTable) -> None:
    stranger = _make_active("x")
    table.set_row_visible_icon(stranger, False)  # must not raise


# ---------------------------------------------------------------------------
# Issue #8 — Delete key removes selected signal
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-141")
def test_delete_key_emits_remove_requested(populated: tuple, qtbot: QtBot) -> None:
    from PyQt6.QtCore import Qt
    t, sigs = populated
    t._segments[0].selectRow(0)
    with qtbot.waitSignal(t.remove_requested) as blocker:
        qtbot.keyClick(t, Qt.Key.Key_Delete)
    assert blocker.args[0] == [sigs[0]]


@pytest.mark.requirement("REQ-PLOT-141")
def test_delete_key_no_selection_does_not_emit(table: ActiveSignalsTable, qtbot: QtBot) -> None:
    from PyQt6.QtCore import Qt
    with qtbot.assertNotEmitted(table.remove_requested):
        qtbot.keyClick(table, Qt.Key.Key_Delete)


# ---------------------------------------------------------------------------
# Multi-select
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-152")
def test_multi_select_selection_changed_emits_none(
    populated: tuple, qtbot: QtBot
) -> None:
    t, sigs = populated
    t._segments[0].selectRow(0)
    t._segments[0].selectionModel().select(
        t._segments[0].model().index(2, 0),
        t._segments[0].selectionModel().SelectionFlag.Select | t._segments[0].selectionModel().SelectionFlag.Rows,
    )
    with qtbot.waitSignal(t.selection_changed, timeout=500) as blocker:
        t._on_selection_changed(t._segments[0])
    assert blocker.args[0] is None


@pytest.mark.requirement("REQ-PLOT-152")
def test_multi_select_emits_multi_selection_active_true(
    populated: tuple, qtbot: QtBot
) -> None:
    t, sigs = populated
    t._segments[0].selectRow(0)
    t._segments[0].selectionModel().select(
        t._segments[0].model().index(2, 0),
        t._segments[0].selectionModel().SelectionFlag.Select | t._segments[0].selectionModel().SelectionFlag.Rows,
    )
    with qtbot.waitSignal(t.multi_selection_active, timeout=500) as blocker:
        t._on_selection_changed(t._segments[0])
    assert blocker.args[0] is True


@pytest.mark.requirement("REQ-PLOT-152")
def test_single_select_emits_multi_selection_active_false(
    populated: tuple, qtbot: QtBot
) -> None:
    t, sigs = populated
    with qtbot.waitSignal(t.multi_selection_active, timeout=500) as blocker:
        t._segments[0].selectRow(1)
    assert blocker.args[0] is False


@pytest.mark.requirement("REQ-PLOT-141")
def test_remove_button_multi_select_emits_all(
    populated: tuple, qtbot: QtBot
) -> None:
    t, sigs = populated
    t._segments[0].selectRow(0)
    t._segments[0].selectionModel().select(
        t._segments[0].model().index(2, 0),
        t._segments[0].selectionModel().SelectionFlag.Select | t._segments[0].selectionModel().SelectionFlag.Rows,
    )
    with qtbot.waitSignal(t.remove_requested, timeout=500) as blocker:
        t._remove_btn.click()
    assert blocker.args[0] == [sigs[0], sigs[2]]


@pytest.mark.requirement("REQ-PLOT-141")
def test_delete_key_multi_select_emits_all(
    populated: tuple, qtbot: QtBot
) -> None:
    from PyQt6.QtCore import Qt
    t, sigs = populated
    t._segments[0].selectRow(0)
    t._segments[0].selectionModel().select(
        t._segments[0].model().index(1, 0),
        t._segments[0].selectionModel().SelectionFlag.Select | t._segments[0].selectionModel().SelectionFlag.Rows,
    )
    with qtbot.waitSignal(t.remove_requested) as blocker:
        qtbot.keyClick(t, Qt.Key.Key_Delete)
    assert blocker.args[0] == [sigs[0], sigs[1]]


@pytest.mark.requirement("REQ-PLOT-122")
def test_color_swatch_multi_select_emits_all_selected(
    populated: tuple, qtbot: QtBot
) -> None:
    t, sigs = populated
    t._segments[0].selectRow(0)
    t._segments[0].selectionModel().select(
        t._segments[0].model().index(2, 0),
        t._segments[0].selectionModel().SelectionFlag.Select | t._segments[0].selectionModel().SelectionFlag.Rows,
    )
    new_color = QColor(10, 20, 30)
    with patch(
        "mdf_viewer.view.active_signals_table.QColorDialog.getColor",
        return_value=new_color,
    ):
        with qtbot.waitSignal(t.color_change_requested, timeout=500) as blocker:
            t._on_color_swatch_clicked(sigs[0])
    assert blocker.args[0] == [sigs[0], sigs[2]]
    assert blocker.args[1] == new_color


@pytest.mark.requirement("REQ-PLOT-122")
def test_color_swatch_unselected_signal_ignores_selection(
    populated: tuple, qtbot: QtBot
) -> None:
    t, sigs = populated
    t._segments[0].selectRow(0)
    t._segments[0].selectionModel().select(
        t._segments[0].model().index(2, 0),
        t._segments[0].selectionModel().SelectionFlag.Select | t._segments[0].selectionModel().SelectionFlag.Rows,
    )
    new_color = QColor(10, 20, 30)
    with patch(
        "mdf_viewer.view.active_signals_table.QColorDialog.getColor",
        return_value=new_color,
    ):
        with qtbot.waitSignal(t.color_change_requested, timeout=500) as blocker:
            t._on_color_swatch_clicked(sigs[1])  # sigs[1] not in selection
    assert blocker.args[0] == [sigs[1]]


# ---------------------------------------------------------------------------
# Issue #7 — Name and cursor columns are interactively resizable
# ---------------------------------------------------------------------------

def test_name_column_is_interactive(table: ActiveSignalsTable) -> None:
    from PyQt6.QtWidgets import QHeaderView
    mode = table._header.horizontalHeader().sectionResizeMode(_COL_NAME)
    assert mode == QHeaderView.ResizeMode.Interactive


def test_cursor_columns_are_interactive(table: ActiveSignalsTable) -> None:
    from PyQt6.QtWidgets import QHeaderView
    hdr = table._header.horizontalHeader()
    for col in (2, 3, 4):  # _CURSOR_COLS
        assert hdr.sectionResizeMode(col) == QHeaderView.ResizeMode.Interactive


# ---------------------------------------------------------------------------
# Drag and drop — signals
# ---------------------------------------------------------------------------

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


@pytest.mark.requirement("REQ-PLOT-143")
@pytest.mark.requirement("REQ-PLOT-277")
def test_signals_dropped_emitted_on_valid_mime(
    table: ActiveSignalsTable, qtbot: QtBot
) -> None:
    stripe = _FakeStripe("Stripe 1")
    table.add_stripe_segment(stripe)
    locs = [(0, 0, 1), (1, 1, 2)]
    mime = QMimeData()
    mime.setData(SIGNAL_MIME_TYPE, QByteArray(encode_signal_payload(locs)))
    with qtbot.waitSignal(table.signals_dropped_on_stripe) as blocker:
        table.eventFilter(table._segments[0].viewport(), _drop_event(mime))
    assert blocker.args[0] == [(0, 0, 1), (1, 1, 2)]
    assert blocker.args[1] is stripe


@pytest.mark.requirement("REQ-PLOT-143")
def test_signals_dropped_not_emitted_for_wrong_mime(
    table: ActiveSignalsTable, qtbot: QtBot
) -> None:
    table.add_stripe_segment(object())
    mime = QMimeData()
    mime.setText("not a signal")
    with qtbot.assertNotEmitted(table.signals_dropped_on_stripe):
        table.eventFilter(table._segments[0].viewport(), _drop_event(mime))


@pytest.mark.requirement("REQ-PLOT-143")
def test_drag_enter_accepted_for_signal_mime(table: ActiveSignalsTable) -> None:
    table.add_stripe_segment(object())
    mime = QMimeData()
    mime.setData(SIGNAL_MIME_TYPE, QByteArray(b"[]"))
    event = _drag_enter_event(mime)
    table.eventFilter(table._segments[0].viewport(), event)
    event.acceptProposedAction.assert_called_once()


@pytest.mark.requirement("REQ-PLOT-143")
def test_drag_enter_ignored_for_unknown_mime(table: ActiveSignalsTable) -> None:
    table.add_stripe_segment(object())
    mime = QMimeData()
    mime.setText("irrelevant")
    event = _drag_enter_event(mime)
    table.eventFilter(table._segments[0].viewport(), event)
    event.ignore.assert_called_once()


# ---------------------------------------------------------------------------
# Row reorder / _render_segment
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-142")
def test_rebuild_rows_preserves_signal_count(
    populated: tuple[ActiveSignalsTable, list[ActiveSignal]]
) -> None:
    table, sigs = populated
    table._render_segment(table._segments[0])
    assert table._segments[0].rowCount() == len(sigs)


def test_rebuild_rows_preserves_names(
    populated: tuple[ActiveSignalsTable, list[ActiveSignal]]
) -> None:
    table, sigs = populated
    table._render_segment(table._segments[0])
    seg = table._segments[0]
    names = [seg.item(r, _COL_NAME).text() for r in range(seg.rowCount())]
    assert names == [s.metadata.name for s in sigs]


def test_rebuild_rows_selects_given_row(
    populated: tuple[ActiveSignalsTable, list[ActiveSignal]]
) -> None:
    table, _ = populated
    table._render_segment(table._segments[0], select_rows=[1])
    rows = table._segments[0].selectionModel().selectedRows()
    assert len(rows) == 1
    assert rows[0].row() == 1


@pytest.mark.requirement("REQ-PLOT-142")
def test_order_changed_emitted_on_row_reorder(
    populated: tuple[ActiveSignalsTable, list[ActiveSignal]],
    qtbot,
) -> None:
    table, sigs = populated
    # Simulate a reorder by manipulating the shared signal list directly.
    table._signals = [sigs[1], sigs[0], sigs[2]]
    with qtbot.waitSignal(table.order_changed) as blocker:
        table.order_changed.emit(list(table._signals))
    assert blocker.args[0] == [sigs[1], sigs[0], sigs[2]]


# ---------------------------------------------------------------------------
# Drag-to-move data logic (#100 M7) — NOT the drag gesture itself: QDrag.exec()
# blocks waiting for real mouse events in a headless test, so _start_segment_drag
# is only exercised here for its early-return (nothing selected) path. The
# actual gesture needs a live-app check (#78 postmortem policy).
# ---------------------------------------------------------------------------

def test_start_segment_drag_noop_when_nothing_selected(table: ActiveSignalsTable) -> None:
    stripe = _FakeStripe("Stripe 1")
    seg = table.add_stripe_segment(stripe)
    table.add_row(_make_active("alpha"), stripe)
    table._start_segment_drag(seg)  # no selection — must return before drag.exec()


@pytest.mark.requirement("REQ-PLOT-142")
def test_apply_row_move_reorders_within_segment(table: ActiveSignalsTable) -> None:
    stripe = _FakeStripe("Stripe 1")
    seg = table.add_stripe_segment(stripe)
    a, b, c = (_make_active("alpha"), _make_active("beta"), _make_active("gamma"))
    for s in (a, b, c):
        table.add_row(s, stripe)
    table._apply_row_move([c], seg, 0)  # drag gamma to the top
    assert table._segment_signals(seg) == [c, a, b]


@pytest.mark.requirement("REQ-PLOT-142")
def test_apply_row_move_selects_moved_rows(table: ActiveSignalsTable) -> None:
    stripe = _FakeStripe("Stripe 1")
    seg = table.add_stripe_segment(stripe)
    a, b = _make_active("alpha"), _make_active("beta")
    table.add_row(a, stripe)
    table.add_row(b, stripe)
    table._apply_row_move([b], seg, 0)
    rows = seg.selectionModel().selectedRows()
    assert len(rows) == 1
    assert rows[0].row() == 0


@pytest.mark.requirement("REQ-PLOT-142")
def test_apply_row_move_emits_order_changed(
    table: ActiveSignalsTable, qtbot: QtBot
) -> None:
    stripe = _FakeStripe("Stripe 1")
    seg = table.add_stripe_segment(stripe)
    a, b = _make_active("alpha"), _make_active("beta")
    table.add_row(a, stripe)
    table.add_row(b, stripe)
    with qtbot.waitSignal(table.order_changed) as blocker:
        table._apply_row_move([b], seg, 0)
    assert blocker.args[0] == [b, a]


def test_on_row_move_drop_applies_move(table: ActiveSignalsTable) -> None:
    stripe = _FakeStripe("Stripe 1")
    seg = table.add_stripe_segment(stripe)
    a, b = _make_active("alpha"), _make_active("beta")
    table.add_row(a, stripe)
    table.add_row(b, stripe)

    payload = json.dumps([id(b)]).encode()
    event = MagicMock()
    event.mimeData.return_value.data.return_value = payload
    event.position.return_value.toPoint.return_value = None
    seg_index = MagicMock()
    seg_index.isValid.return_value = True
    seg_index.row.return_value = 0
    with patch.object(seg, "indexAt", return_value=seg_index):
        table._on_row_move_drop(seg, event)

    assert table._segment_signals(seg) == [b, a]
    event.acceptProposedAction.assert_called_once()


def test_on_row_move_drop_ignores_unknown_ids(table: ActiveSignalsTable) -> None:
    stripe = _FakeStripe("Stripe 1")
    seg = table.add_stripe_segment(stripe)
    a = _make_active("alpha")
    table.add_row(a, stripe)

    payload = json.dumps([999999]).encode()  # not a real id() in this table
    event = MagicMock()
    event.mimeData.return_value.data.return_value = payload
    table._on_row_move_drop(seg, event)

    assert table._segment_signals(seg) == [a]
    event.ignore.assert_called_once()


# ---------------------------------------------------------------------------
# Cross-segment drag-to-move (#100 M8)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-279")
def test_apply_row_move_across_segments_reassigns_stripe(table: ActiveSignalsTable) -> None:
    s1 = _FakeStripe("Stripe 1")
    s2 = _FakeStripe("Stripe 2")
    seg1 = table.add_stripe_segment(s1)
    seg2 = table.add_stripe_segment(s2)
    a = _make_active("alpha")
    table.add_row(a, s1)
    table.add_row(_make_active("beta"), s2)
    table._apply_row_move([a], seg2, 0)
    assert table._segment_signals(seg1) == []
    assert a in table._segment_signals(seg2)


@pytest.mark.requirement("REQ-PLOT-279")
def test_apply_row_move_across_segments_emits_move_to_stripe_requested(
    table: ActiveSignalsTable, qtbot: QtBot
) -> None:
    """A cross-segment drag must also relocate the signal in the plot (#116),
    not just the table row — reuses the same signal the "Move to Stripe"
    context-menu action already emits, so AppController.move_signals_to_stripe
    handles both the same way."""
    s1 = _FakeStripe("Stripe 1")
    s2 = _FakeStripe("Stripe 2")
    seg1 = table.add_stripe_segment(s1)
    seg2 = table.add_stripe_segment(s2)
    a = _make_active("alpha")
    table.add_row(a, s1)
    with qtbot.waitSignal(table.move_to_stripe_requested) as blocker:
        table._apply_row_move([a], seg2, 0)
    assert blocker.args == [[a], s2]


def test_apply_row_move_within_segment_does_not_emit_move_to_stripe_requested(
    table: ActiveSignalsTable, qtbot: QtBot
) -> None:
    """A same-segment reorder is not a stripe change — no plot-side move needed."""
    s1 = _FakeStripe("Stripe 1")
    seg1 = table.add_stripe_segment(s1)
    a = _make_active("alpha")
    b = _make_active("beta")
    table.add_row(a, s1)
    table.add_row(b, s1)
    with qtbot.assertNotEmitted(table.move_to_stripe_requested):
        table._apply_row_move([b], seg1, 0)


@pytest.mark.requirement("REQ-PLOT-279")
def test_apply_row_move_across_segments_lands_at_requested_position(
    table: ActiveSignalsTable,
) -> None:
    s1 = _FakeStripe("Stripe 1")
    s2 = _FakeStripe("Stripe 2")
    seg1 = table.add_stripe_segment(s1)
    seg2 = table.add_stripe_segment(s2)
    a = _make_active("alpha")
    x, y = _make_active("x"), _make_active("y")
    table.add_row(a, s1)
    table.add_row(x, s2)
    table.add_row(y, s2)
    table._apply_row_move([a], seg2, 1)  # drop between x and y
    assert table._segment_signals(seg2) == [x, a, y]


@pytest.mark.requirement("REQ-PLOT-279")
def test_apply_row_move_across_segments_rerenders_source_segment(
    table: ActiveSignalsTable,
) -> None:
    s1 = _FakeStripe("Stripe 1")
    s2 = _FakeStripe("Stripe 2")
    seg1 = table.add_stripe_segment(s1)
    seg2 = table.add_stripe_segment(s2)
    a = _make_active("alpha")
    table.add_row(a, s1)
    table.add_row(_make_active("beta"), s2)
    table._apply_row_move([a], seg2, 0)
    assert seg1.rowCount() == 0


@pytest.mark.requirement("REQ-PLOT-279")
def test_apply_row_move_multi_segment_sourced_drag(table: ActiveSignalsTable) -> None:
    """The scenario this milestone exists for: a selection spanning two
    source segments, dragged together onto a third."""
    s1 = _FakeStripe("Stripe 1")
    s2 = _FakeStripe("Stripe 2")
    s3 = _FakeStripe("Stripe 3")
    seg1 = table.add_stripe_segment(s1)
    seg2 = table.add_stripe_segment(s2)
    seg3 = table.add_stripe_segment(s3)
    a = _make_active("alpha")
    b = _make_active("beta")
    z = _make_active("zeta")
    table.add_row(a, s1)
    table.add_row(b, s2)
    table.add_row(z, s3)
    table._apply_row_move([a, b], seg3, 0)
    assert table._segment_signals(seg1) == []
    assert table._segment_signals(seg2) == []
    assert table._segment_signals(seg3) == [a, b, z]


@pytest.mark.requirement("REQ-PLOT-279")
def test_apply_row_move_multi_segment_sourced_drag_preserves_shared_list_order(
    table: ActiveSignalsTable,
) -> None:
    # a and b start on opposite sides of z in the shared list; after moving
    # both to s3 together they must keep their relative order (a before b),
    # matching the order they were dragged in, not their old global
    # positions relative to each other.
    s1 = _FakeStripe("Stripe 1")
    s2 = _FakeStripe("Stripe 2")
    s3 = _FakeStripe("Stripe 3")
    seg1 = table.add_stripe_segment(s1)
    seg2 = table.add_stripe_segment(s2)
    seg3 = table.add_stripe_segment(s3)
    b = _make_active("beta")
    a = _make_active("alpha")
    table.add_row(b, s2)
    table.add_row(a, s1)
    table.add_row(_make_active("zeta"), s3)
    table._apply_row_move([b, a], seg3, 0)
    assert table._segment_signals(seg3)[:2] == [b, a]


def test_on_row_move_drop_across_segments(table: ActiveSignalsTable) -> None:
    s1 = _FakeStripe("Stripe 1")
    s2 = _FakeStripe("Stripe 2")
    seg1 = table.add_stripe_segment(s1)
    seg2 = table.add_stripe_segment(s2)
    a = _make_active("alpha")
    table.add_row(a, s1)
    table.add_row(_make_active("beta"), s2)

    payload = json.dumps([id(a)]).encode()
    event = MagicMock()
    event.mimeData.return_value.data.return_value = payload
    seg_index = MagicMock()
    seg_index.isValid.return_value = True
    seg_index.row.return_value = 0
    with patch.object(seg2, "indexAt", return_value=seg_index):
        table._on_row_move_drop(seg2, event)

    assert table._segment_signals(seg1) == []
    assert a in table._segment_signals(seg2)
    event.acceptProposedAction.assert_called_once()


@pytest.mark.requirement("REQ-PLOT-120")
def test_rebuild_rows_restores_color_swatches(
    populated: tuple[ActiveSignalsTable, list[ActiveSignal]]
) -> None:
    table, sigs = populated
    table._render_segment(table._segments[0])
    seg = table._segments[0]
    for r in range(seg.rowCount()):
        widget = _cell_inner_widget(seg, r, _COL_COLOR)
        assert isinstance(widget, _ColorSwatch)


@pytest.mark.requirement("REQ-PLOT-101")
def test_set_delta_column_header(table: ActiveSignalsTable) -> None:
    table.set_delta_column_header("Δt = 1.234 s")
    item = table._header.horizontalHeaderItem(_COL_DELTA)
    assert item is not None
    assert item.text() == "Δt = 1.234 s"


@pytest.mark.requirement("REQ-PLOT-101")
def test_set_delta_column_header_resets_to_default(table: ActiveSignalsTable) -> None:
    table.set_delta_column_header("Δt = 1.234 s")
    table.set_delta_column_header("Δ")
    item = table._header.horizontalHeaderItem(_COL_DELTA)
    assert item is not None
    assert item.text() == "Δ"


# ---------------------------------------------------------------------------
# multi_selection_changed
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-140")
def test_multi_selection_changed_emitted_on_multi_select(
    populated: tuple[ActiveSignalsTable, list[ActiveSignal]], qtbot: QtBot
) -> None:
    table, sigs = populated
    with qtbot.waitSignal(table.multi_selection_changed, timeout=1000) as blocker:
        sm = table._segments[0].selectionModel()
        sm.clearSelection()
        for row in (0, 1):
            sm.select(
                table._segments[0].model().index(row, 0),
                sm.SelectionFlag.Select | sm.SelectionFlag.Rows,
            )
    assert set(blocker.args[0]) == {sigs[0], sigs[1]}


@pytest.mark.requirement("REQ-PLOT-140")
def test_multi_selection_changed_not_emitted_on_single_select(
    populated: tuple[ActiveSignalsTable, list[ActiveSignal]], qtbot: QtBot
) -> None:
    table, sigs = populated
    emitted: list = []
    table.multi_selection_changed.connect(emitted.append)
    sm = table._segments[0].selectionModel()
    sm.clearSelection()
    sm.select(
        table._segments[0].model().index(0, 0),
        sm.SelectionFlag.Select | sm.SelectionFlag.Rows,
    )
    assert emitted == []


# ---------------------------------------------------------------------------
# select_signal
# ---------------------------------------------------------------------------

def test_select_signal_selects_correct_row(
    populated: tuple[ActiveSignalsTable, list[ActiveSignal]], qtbot: QtBot
) -> None:
    table, sigs = populated
    table.select_signal(sigs[1])
    selected_rows = {item.row() for item in table._segments[0].selectedItems()}
    assert selected_rows == {1}


def test_select_signal_none_clears_selection(
    populated: tuple[ActiveSignalsTable, list[ActiveSignal]], qtbot: QtBot
) -> None:
    table, sigs = populated
    table._segments[0].selectRow(0)
    table.select_signal(None)
    assert table._segments[0].selectedItems() == []


def test_select_signal_emits_selection_changed(
    populated: tuple[ActiveSignalsTable, list[ActiveSignal]], qtbot: QtBot
) -> None:
    table, sigs = populated
    received = []
    table.selection_changed.connect(received.append)
    table.select_signal(sigs[0])
    assert received == [sigs[0]]


def test_select_signal_none_emits_selection_changed_none(
    populated: tuple[ActiveSignalsTable, list[ActiveSignal]], qtbot: QtBot
) -> None:
    table, sigs = populated
    table._segments[0].selectRow(0)
    received = []
    table.selection_changed.connect(received.append)
    table.select_signal(None)
    assert received == [None]


@pytest.mark.requirement("REQ-PLOT-023")
def test_select_signal_noop_for_unknown(table: ActiveSignalsTable, qtbot: QtBot) -> None:
    stranger = _make_active("stranger")
    table.select_signal(stranger)  # must not raise


# ---------------------------------------------------------------------------
# set_name_formatter
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-160")
def test_set_name_formatter_updates_existing_rows(
    populated: tuple[ActiveSignalsTable, list[ActiveSignal]], qtbot: QtBot
) -> None:
    table, sigs = populated
    table.set_name_formatter(lambda a: a.metadata.name.upper())
    for row, sig in enumerate(sigs):
        assert table._segments[0].item(row, _COL_NAME).text() == sig.metadata.name.upper()


@pytest.mark.requirement("REQ-PLOT-160")
def test_set_name_formatter_applied_to_new_rows(
    table: ActiveSignalsTable, qtbot: QtBot
) -> None:
    table.set_name_formatter(lambda a: f"[{a.metadata.name}]")
    active = _make_active("mysig")
    table.add_row(active)
    assert table._segments[0].item(0, _COL_NAME).text() == "[mysig]"


@pytest.mark.requirement("REQ-PLOT-161")
def test_default_formatter_shows_full_name(
    table: ActiveSignalsTable, qtbot: QtBot
) -> None:
    active = _make_active("full.name.here")
    table.add_row(active)
    assert table._segments[0].item(0, _COL_NAME).text() == "full.name.here"


@pytest.mark.requirement("REQ-PLOT-160")
def test_configure_display_names_signal_carries_name(
    populated: tuple[ActiveSignalsTable, list[ActiveSignal]], qtbot: QtBot
) -> None:
    table, sigs = populated
    received: list[str] = []
    table.configure_display_names_requested.connect(received.append)
    table.configure_display_names_requested.emit(sigs[0].metadata.name)
    assert received == [sigs[0].metadata.name]


@pytest.mark.requirement("REQ-PLOT-160")
def test_shorten_names_toggled_signal_exists(table: ActiveSignalsTable) -> None:
    received: list = []
    table.shorten_names_toggled.connect(received.append)
    table.shorten_names_toggled.emit(True)
    assert received == [True]


@pytest.mark.requirement("REQ-PLOT-160")
def test_set_shorten_names_enabled_updates_field(table: ActiveSignalsTable) -> None:
    assert table._shorten_names_enabled is False
    table.set_shorten_names_enabled(True)
    assert table._shorten_names_enabled is True


# ---------------------------------------------------------------------------
# Context menu — Share/Link Y-axis mutual exclusivity (#84)
# ---------------------------------------------------------------------------

def _select_rows(t: ActiveSignalsTable, *rows: int) -> None:
    t._segments[0].selectRow(rows[0])
    for row in rows[1:]:
        t._segments[0].selectionModel().select(
            t._segments[0].model().index(row, 0),
            t._segments[0].selectionModel().SelectionFlag.Select
            | t._segments[0].selectionModel().SelectionFlag.Rows,
        )


def _open_context_menu(t: ActiveSignalsTable) -> QMenu:
    pos = t._segments[0].visualRect(t._segments[0].model().index(0, 0)).center()
    captured: dict = {}

    def fake_exec(self, *args, **kwargs):
        captured["menu"] = self

    with patch.object(QMenu, "exec", fake_exec):
        t._on_context_menu(t._segments[0], pos)
    return captured["menu"]


@pytest.mark.requirement("REQ-PLOT-037")
@pytest.mark.requirement("REQ-PLOT-033")
def test_both_group_actions_shown_when_selection_ungrouped(
    populated: tuple[ActiveSignalsTable, list[ActiveSignal]],
) -> None:
    t, sigs = populated
    _select_rows(t, 0, 1)
    titles = [a.text() for a in _open_context_menu(t).actions()]
    assert "Merge Y-Axis" in titles
    assert "Sync Y-Axis" in titles


@pytest.mark.requirement("REQ-PLOT-033")
def test_merge_action_hidden_when_selection_includes_synced_signal(
    populated: tuple[ActiveSignalsTable, list[ActiveSignal]],
) -> None:
    t, sigs = populated
    t.set_group_membership(merged=set(), synced={sigs[1]})
    _select_rows(t, 0, 1)
    titles = [a.text() for a in _open_context_menu(t).actions()]
    assert "Merge Y-Axis" not in titles
    assert "Sync Y-Axis" in titles


@pytest.mark.requirement("REQ-PLOT-033")
def test_sync_action_hidden_when_selection_includes_merged_signal(
    populated: tuple[ActiveSignalsTable, list[ActiveSignal]],
) -> None:
    t, sigs = populated
    t.set_group_membership(merged={sigs[1]}, synced=set())
    _select_rows(t, 0, 1)
    titles = [a.text() for a in _open_context_menu(t).actions()]
    assert "Sync Y-Axis" not in titles
    assert "Merge Y-Axis" in titles


@pytest.mark.requirement("REQ-PLOT-035")
def test_ungroup_action_covers_both_merged_and_synced_selection(
    populated: tuple[ActiveSignalsTable, list[ActiveSignal]],
) -> None:
    t, sigs = populated
    t.set_group_membership(merged={sigs[0]}, synced={sigs[1]})
    _select_rows(t, 0, 1)
    titles = [a.text() for a in _open_context_menu(t).actions()]
    assert "Remove from merged/synced axis" in titles


# ---------------------------------------------------------------------------
# Context menu — Move to Stripe
# ---------------------------------------------------------------------------

def test_move_to_stripe_actions_absent_without_providers(
    populated: tuple[ActiveSignalsTable, list[ActiveSignal]],
) -> None:
    t, sigs = populated
    _select_rows(t, 0)
    titles = [a.text() for a in _open_context_menu(t).actions()]
    assert "Move to new Stripe" not in titles
    assert "Move to Stripe" not in titles


@pytest.mark.requirement("REQ-PLOT-191")
def test_move_to_new_stripe_action_present_with_providers(
    populated: tuple[ActiveSignalsTable, list[ActiveSignal]],
) -> None:
    t, sigs = populated
    t.set_stripe_providers(lambda: ["stripe0"], lambda a: "stripe0")
    _select_rows(t, 0)
    titles = [a.text() for a in _open_context_menu(t).actions()]
    assert "Move to new Stripe" in titles


def test_move_to_stripe_submenu_absent_with_only_one_stripe(
    populated: tuple[ActiveSignalsTable, list[ActiveSignal]],
) -> None:
    t, sigs = populated
    t.set_stripe_providers(lambda: ["stripe0"], lambda a: "stripe0")
    _select_rows(t, 0)
    titles = [a.text() for a in _open_context_menu(t).actions()]
    assert "Move to Stripe" not in titles


@pytest.mark.requirement("REQ-PLOT-202")
@pytest.mark.requirement("REQ-PLOT-293")
def test_move_to_stripe_submenu_lists_only_other_stripes(
    populated: tuple[ActiveSignalsTable, list[ActiveSignal]],
) -> None:
    t, sigs = populated
    s0 = _FakeStripe("Stripe 1")
    s1 = _FakeStripe("Stripe 2")
    t.set_stripe_providers(lambda: [s0, s1], lambda a: s0)
    _select_rows(t, 0)
    menu = _open_context_menu(t)
    submenu_action = next(a for a in menu.actions() if a.text() == "Move to Stripe")
    sub_titles = [a.text() for a in submenu_action.menu().actions()]
    assert sub_titles == ["Stripe 2"]


def test_move_to_stripe_action_emits_signal(
    populated: tuple[ActiveSignalsTable, list[ActiveSignal]],
) -> None:
    t, sigs = populated
    s0 = _FakeStripe("Stripe 1")
    s1 = _FakeStripe("Stripe 2")
    t.set_stripe_providers(lambda: [s0, s1], lambda a: s0)
    _select_rows(t, 0)
    menu = _open_context_menu(t)
    submenu_action = next(a for a in menu.actions() if a.text() == "Move to Stripe")
    target_action = next(a for a in submenu_action.menu().actions() if a.text() == "Stripe 2")

    received: list = []
    t.move_to_stripe_requested.connect(lambda signals, stripe: received.append((signals, stripe)))
    target_action.trigger()
    assert received == [([sigs[0]], s1)]


def test_move_to_new_stripe_action_emits_signal(
    populated: tuple[ActiveSignalsTable, list[ActiveSignal]],
) -> None:
    t, sigs = populated
    t.set_stripe_providers(lambda: ["s0"], lambda a: "s0")
    _select_rows(t, 0)
    menu = _open_context_menu(t)
    action = next(a for a in menu.actions() if a.text() == "Move to new Stripe")

    received: list = []
    t.move_to_new_stripe_requested.connect(received.append)
    action.trigger()
    assert received == [[sigs[0]]]
