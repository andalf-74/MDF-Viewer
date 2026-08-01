"""Tests for StatusMessageHistory (#125)."""

from __future__ import annotations

from datetime import datetime

from mdf_viewer.view.status_message_history import StatusMessageEntry, StatusMessageHistory


def test_record_appends_entry() -> None:
    history = StatusMessageHistory()
    history.record("hello")
    assert len(history.entries) == 1
    assert history.entries[0].text == "hello"


def test_record_preserves_order() -> None:
    history = StatusMessageHistory()
    history.record("first")
    history.record("second")
    assert [e.text for e in history.entries] == ["first", "second"]


def test_unbounded_retains_every_message() -> None:
    history = StatusMessageHistory()
    for i in range(500):
        history.record(f"message {i}")
    assert len(history.entries) == 500


def test_formatted_uses_hh_mm_ss_local_time() -> None:
    entry = StatusMessageEntry(timestamp=datetime(2026, 8, 1, 9, 5, 3), text="saved")
    assert entry.formatted() == "09:05:03  saved"


def test_as_text_joins_formatted_entries() -> None:
    history = StatusMessageHistory()
    history.record("first", timestamp=datetime(2026, 8, 1, 9, 0, 0))
    history.record("second", timestamp=datetime(2026, 8, 1, 9, 0, 1))
    assert history.as_text() == "09:00:00  first\n09:00:01  second"


def test_as_text_empty_history() -> None:
    assert StatusMessageHistory().as_text() == ""
