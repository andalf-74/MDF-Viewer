"""Tests for SignalGroupPickerDialog, SignalsNotFoundDialog, and NearMatchDialog."""

from __future__ import annotations

import pytest
from pytestqt.qtbot import QtBot
from PyQt6.QtCore import Qt

from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.view.near_match_dialog import NearMatchDialog
from mdf_viewer.view.signal_group_picker_dialog import SignalGroupPickerDialog
from mdf_viewer.view.signals_not_found_dialog import SignalsNotFoundDialog


def _meta(name: str = "rpm", gi: int = 0, ci: int = 1) -> SignalMetadata:
    return SignalMetadata(name=name, group_index=gi, channel_index=ci)


# ---------------------------------------------------------------------------
# SignalGroupPickerDialog
# ---------------------------------------------------------------------------

class TestSignalGroupPickerDialog:
    @pytest.mark.requirement("REQ-FILE-031")
    def test_shows_all_candidates(self, qtbot: QtBot) -> None:
        candidates = [_meta(gi=0, ci=1), _meta(gi=1, ci=1)]
        dlg = SignalGroupPickerDialog("rpm", candidates)
        qtbot.addWidget(dlg)
        assert dlg._list.count() == 2

    @pytest.mark.requirement("REQ-FILE-031")
    def test_first_candidate_is_preselected(self, qtbot: QtBot) -> None:
        candidates = [_meta(gi=0, ci=1), _meta(gi=2, ci=1)]
        dlg = SignalGroupPickerDialog("rpm", candidates)
        qtbot.addWidget(dlg)
        assert dlg._list.currentRow() == 0

    @pytest.mark.requirement("REQ-FILE-031")
    def test_selected_returns_none_before_accept(self, qtbot: QtBot) -> None:
        dlg = SignalGroupPickerDialog("rpm", [_meta(gi=0)])
        qtbot.addWidget(dlg)
        assert dlg.selected() is None

    @pytest.mark.requirement("REQ-FILE-031")
    def test_accept_returns_selected_metadata(self, qtbot: QtBot) -> None:
        m0 = _meta(gi=0, ci=1)
        m1 = _meta(gi=1, ci=2)
        dlg = SignalGroupPickerDialog("rpm", [m0, m1])
        qtbot.addWidget(dlg)
        dlg._list.setCurrentRow(1)
        dlg._on_accept()
        assert dlg.selected() is m1

    @pytest.mark.requirement("REQ-FILE-031")
    def test_list_items_mention_group_index(self, qtbot: QtBot) -> None:
        candidates = [_meta(gi=7, ci=1)]
        dlg = SignalGroupPickerDialog("rpm", candidates)
        qtbot.addWidget(dlg)
        text = dlg._list.item(0).text()
        assert "7" in text

    @pytest.mark.requirement("REQ-PLOT-306")
    def test_tagged_candidates_show_measurement_label(self, qtbot: QtBot) -> None:
        from unittest.mock import MagicMock
        measurement = MagicMock(label="run1")
        candidates = [(measurement, _meta(gi=3, ci=1))]
        dlg = SignalGroupPickerDialog("rpm", candidates)
        qtbot.addWidget(dlg)
        text = dlg._list.item(0).text()
        assert "run1" in text
        assert "3" in text

    @pytest.mark.requirement("REQ-PLOT-306")
    def test_accept_returns_selected_tagged_tuple(self, qtbot: QtBot) -> None:
        from unittest.mock import MagicMock
        measurement = MagicMock(label="run1")
        c0 = (measurement, _meta(gi=0, ci=1))
        c1 = (measurement, _meta(gi=1, ci=2))
        dlg = SignalGroupPickerDialog("rpm", [c0, c1])
        qtbot.addWidget(dlg)
        dlg._list.setCurrentRow(1)
        dlg._on_accept()
        assert dlg.selected() is c1


# ---------------------------------------------------------------------------
# SignalsNotFoundDialog
# ---------------------------------------------------------------------------

class TestSignalsNotFoundDialog:
    @pytest.mark.requirement("REQ-FILE-031")
    def test_shows_all_missing_names(self, qtbot: QtBot) -> None:
        names = ["signal_a", "signal_b", "signal_c"]
        dlg = SignalsNotFoundDialog(names)
        qtbot.addWidget(dlg)
        assert dlg._list.count() == 3
        texts = [dlg._list.item(i).text() for i in range(dlg._list.count())]
        assert texts == names

    def test_single_item_label(self, qtbot: QtBot) -> None:
        from PyQt6.QtWidgets import QLabel
        dlg = SignalsNotFoundDialog(["only_one"])
        qtbot.addWidget(dlg)
        labels = [c.text() for c in dlg.findChildren(QLabel)]
        assert any("1 signal " in text for text in labels)

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


# ---------------------------------------------------------------------------
# NearMatchDialog (#109)
# ---------------------------------------------------------------------------

class TestNearMatchDialog:
    @pytest.mark.requirement("REQ-FILE-036")
    def test_shows_all_pending_matches(self, qtbot: QtBot) -> None:
        pending = [
            ("a\\ETKC:1", _meta("a\\XCP:1")),
            ("b\\ETKC:1", _meta("b\\XCP:1")),
        ]
        dlg = NearMatchDialog(pending)
        qtbot.addWidget(dlg)
        assert dlg._list.count() == 2

    @pytest.mark.requirement("REQ-FILE-036")
    def test_list_item_shows_original_and_candidate_name(self, qtbot: QtBot) -> None:
        dlg = NearMatchDialog([("old\\ETKC:1", _meta("old\\XCP:1"))])
        qtbot.addWidget(dlg)
        text = dlg._list.item(0).text()
        assert "old\\ETKC:1" in text
        assert "old\\XCP:1" in text

    @pytest.mark.requirement("REQ-FILE-036")
    def test_rows_start_checked(self, qtbot: QtBot) -> None:
        dlg = NearMatchDialog([("old\\ETKC:1", _meta("old\\XCP:1"))])
        qtbot.addWidget(dlg)
        assert dlg._list.item(0).checkState() == Qt.CheckState.Checked

    @pytest.mark.requirement("REQ-FILE-036")
    def test_accepted_matches_returns_all_when_none_unchecked(self, qtbot: QtBot) -> None:
        pending = [("a\\ETKC:1", _meta("a\\XCP:1")), ("b\\ETKC:1", _meta("b\\XCP:1"))]
        dlg = NearMatchDialog(pending)
        qtbot.addWidget(dlg)
        assert dlg.accepted_matches() == pending
        assert dlg.declined_matches() == []

    @pytest.mark.requirement("REQ-FILE-036")
    def test_unchecking_a_row_moves_it_to_declined(self, qtbot: QtBot) -> None:
        pending = [("a\\ETKC:1", _meta("a\\XCP:1")), ("b\\ETKC:1", _meta("b\\XCP:1"))]
        dlg = NearMatchDialog(pending)
        qtbot.addWidget(dlg)
        dlg._list.item(0).setCheckState(Qt.CheckState.Unchecked)
        assert dlg.accepted_matches() == [pending[1]]
        assert dlg.declined_matches() == [pending[0]]

    def test_empty_pending_list_is_accepted(self, qtbot: QtBot) -> None:
        dlg = NearMatchDialog([])
        qtbot.addWidget(dlg)
        assert dlg._list.count() == 0

    @pytest.mark.requirement("REQ-FILE-036")
    def test_checked_mask_matches_row_order(self, qtbot: QtBot) -> None:
        pending = [("a\\ETKC:1", _meta("a\\XCP:1")), ("a\\ETKC:1", _meta("a\\XCP:2"))]
        dlg = NearMatchDialog(pending)
        qtbot.addWidget(dlg)
        dlg._list.item(1).setCheckState(Qt.CheckState.Unchecked)
        assert dlg.checked_mask() == [True, False]

    @pytest.mark.requirement("REQ-PLOT-306")
    def test_tagged_candidate_shows_measurement_label(self, qtbot: QtBot) -> None:
        from unittest.mock import MagicMock
        measurement = MagicMock(label="run1")
        pending = [("old\\ETKC:1", (measurement, _meta("old\\XCP:1")))]
        dlg = NearMatchDialog(pending)
        qtbot.addWidget(dlg)
        text = dlg._list.item(0).text()
        assert "old\\ETKC:1" in text
        assert "run1" in text
        assert "old\\XCP:1" in text

    @pytest.mark.requirement("REQ-PLOT-306")
    def test_accepted_matches_returns_tagged_tuple(self, qtbot: QtBot) -> None:
        from unittest.mock import MagicMock
        measurement = MagicMock(label="run1")
        pending = [("old\\ETKC:1", (measurement, _meta("old\\XCP:1")))]
        dlg = NearMatchDialog(pending)
        qtbot.addWidget(dlg)
        assert dlg.accepted_matches() == pending
