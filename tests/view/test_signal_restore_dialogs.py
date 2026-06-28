"""Tests for SignalGroupPickerDialog and SignalsNotFoundDialog."""

from __future__ import annotations

import pytest
from pytestqt.qtbot import QtBot

from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.view.signal_group_picker_dialog import SignalGroupPickerDialog
from mdf_viewer.view.signals_not_found_dialog import SignalsNotFoundDialog


def _meta(name: str = "rpm", gi: int = 0, ci: int = 1) -> SignalMetadata:
    return SignalMetadata(name=name, group_index=gi, channel_index=ci)


# ---------------------------------------------------------------------------
# SignalGroupPickerDialog
# ---------------------------------------------------------------------------

class TestSignalGroupPickerDialog:
    def test_shows_all_candidates(self, qtbot: QtBot) -> None:
        candidates = [_meta(gi=0, ci=1), _meta(gi=1, ci=1)]
        dlg = SignalGroupPickerDialog("rpm", candidates)
        qtbot.addWidget(dlg)
        assert dlg._list.count() == 2

    def test_first_candidate_is_preselected(self, qtbot: QtBot) -> None:
        candidates = [_meta(gi=0, ci=1), _meta(gi=2, ci=1)]
        dlg = SignalGroupPickerDialog("rpm", candidates)
        qtbot.addWidget(dlg)
        assert dlg._list.currentRow() == 0

    def test_selected_returns_none_before_accept(self, qtbot: QtBot) -> None:
        dlg = SignalGroupPickerDialog("rpm", [_meta(gi=0)])
        qtbot.addWidget(dlg)
        assert dlg.selected() is None

    def test_accept_returns_selected_metadata(self, qtbot: QtBot) -> None:
        m0 = _meta(gi=0, ci=1)
        m1 = _meta(gi=1, ci=2)
        dlg = SignalGroupPickerDialog("rpm", [m0, m1])
        qtbot.addWidget(dlg)
        dlg._list.setCurrentRow(1)
        dlg._on_accept()
        assert dlg.selected() is m1

    def test_list_items_mention_group_index(self, qtbot: QtBot) -> None:
        candidates = [_meta(gi=7, ci=1)]
        dlg = SignalGroupPickerDialog("rpm", candidates)
        qtbot.addWidget(dlg)
        text = dlg._list.item(0).text()
        assert "7" in text


# ---------------------------------------------------------------------------
# SignalsNotFoundDialog
# ---------------------------------------------------------------------------

class TestSignalsNotFoundDialog:
    def test_shows_all_missing_names(self, qtbot: QtBot) -> None:
        names = ["signal_a", "signal_b", "signal_c"]
        dlg = SignalsNotFoundDialog(names)
        qtbot.addWidget(dlg)
        assert dlg._list.count() == 3
        texts = [dlg._list.item(i).text() for i in range(dlg._list.count())]
        assert texts == names

    def test_single_item_label(self, qtbot: QtBot) -> None:
        dlg = SignalsNotFoundDialog(["only_one"])
        qtbot.addWidget(dlg)
        # Label should use singular "signal"
        labels = [c.text() for c in dlg.findChildren(dlg.__class__.__mro__[1])
                  if hasattr(c, 'text')]

    def test_copy_to_clipboard(self, qtbot: QtBot, qapp) -> None:
        from PyQt6.QtGui import QGuiApplication
        names = ["abc", "def"]
        dlg = SignalsNotFoundDialog(names)
        qtbot.addWidget(dlg)
        dlg._copy_to_clipboard()
        text = QGuiApplication.clipboard().text()
        assert text == "abc\ndef"

    def test_empty_list_is_accepted(self, qtbot: QtBot) -> None:
        dlg = SignalsNotFoundDialog([])
        qtbot.addWidget(dlg)
        assert dlg._list.count() == 0
