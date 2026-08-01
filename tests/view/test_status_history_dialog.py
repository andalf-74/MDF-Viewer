"""Tests for StatusHistoryDialog (#125)."""

from __future__ import annotations

from datetime import datetime

import pytest
from pytestqt.qtbot import QtBot
from PyQt6.QtGui import QGuiApplication

from mdf_viewer.view.status_history_dialog import StatusHistoryDialog
from mdf_viewer.view.status_message_history import StatusMessageEntry, StatusMessageHistory


def _history(*texts: str) -> StatusMessageHistory:
    history = StatusMessageHistory()
    for i, text in enumerate(texts):
        history.record(text, timestamp=datetime(2026, 8, 1, 9, 0, i))
    return history


@pytest.mark.requirement("REQ-STATUS-030")
def test_populates_from_history_on_construction(qtbot: QtBot) -> None:
    dlg = StatusHistoryDialog(_history("first", "second"), parent=None)
    qtbot.addWidget(dlg)
    assert dlg._text.toPlainText() == "09:00:00  first\n09:00:01  second"


@pytest.mark.requirement("REQ-STATUS-030")
def test_empty_history_shows_empty_text(qtbot: QtBot) -> None:
    dlg = StatusHistoryDialog(StatusMessageHistory(), parent=None)
    qtbot.addWidget(dlg)
    assert dlg._text.toPlainText() == ""


@pytest.mark.requirement("REQ-STATUS-023")
def test_append_entry_adds_a_new_line(qtbot: QtBot) -> None:
    dlg = StatusHistoryDialog(_history("first"), parent=None)
    qtbot.addWidget(dlg)
    dlg.append_entry(StatusMessageEntry(timestamp=datetime(2026, 8, 1, 9, 0, 5), text="second"))
    assert dlg._text.toPlainText() == "09:00:00  first\n09:00:05  second"


@pytest.mark.requirement("REQ-STATUS-031")
def test_text_is_read_only(qtbot: QtBot) -> None:
    dlg = StatusHistoryDialog(_history("first"), parent=None)
    qtbot.addWidget(dlg)
    assert dlg._text.isReadOnly()


@pytest.mark.requirement("REQ-STATUS-032")
def test_copy_to_clipboard_copies_full_history(qtbot: QtBot, qapp) -> None:
    dlg = StatusHistoryDialog(_history("first", "second"), parent=None)
    qtbot.addWidget(dlg)
    dlg._copy_to_clipboard()
    assert QGuiApplication.clipboard().text() == "09:00:00  first\n09:00:01  second"


@pytest.mark.requirement("REQ-STATUS-032")
def test_copy_to_clipboard_ignores_selection(qtbot: QtBot, qapp) -> None:
    dlg = StatusHistoryDialog(_history("first", "second"), parent=None)
    qtbot.addWidget(dlg)
    cursor = dlg._text.textCursor()
    cursor.select(cursor.SelectionType.WordUnderCursor)
    dlg._text.setTextCursor(cursor)
    dlg._copy_to_clipboard()
    assert QGuiApplication.clipboard().text() == "09:00:00  first\n09:00:01  second"


def test_is_non_modal(qtbot: QtBot) -> None:
    dlg = StatusHistoryDialog(StatusMessageHistory(), parent=None)
    qtbot.addWidget(dlg)
    assert not dlg.isModal()
