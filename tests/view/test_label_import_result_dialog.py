"""Tests for LabelImportResultDialog (#143)."""

from __future__ import annotations

import pytest
from pytestqt.qtbot import QtBot
from PyQt6.QtGui import QGuiApplication

from mdf_viewer.view.label_import_result_dialog import LabelImportResultDialog


@pytest.mark.requirement("REQ-LABEL-050")
def test_shows_not_found_names(qtbot: QtBot) -> None:
    dlg = LabelImportResultDialog(["Ghost", "Missing"], [], parent=None)
    qtbot.addWidget(dlg)
    texts = [dlg._not_found_list.item(i).text() for i in range(dlg._not_found_list.count())]
    assert texts == ["Ghost", "Missing"]


@pytest.mark.requirement("REQ-LABEL-050")
def test_shows_already_active_names(qtbot: QtBot) -> None:
    dlg = LabelImportResultDialog([], ["Speed"], parent=None)
    qtbot.addWidget(dlg)
    texts = [
        dlg._already_active_list.item(i).text() for i in range(dlg._already_active_list.count())
    ]
    assert texts == ["Speed"]


@pytest.mark.requirement("REQ-LABEL-050")
def test_lists_are_kept_separate(qtbot: QtBot) -> None:
    dlg = LabelImportResultDialog(["Ghost"], ["Speed"], parent=None)
    qtbot.addWidget(dlg)
    assert dlg._not_found_list.count() == 1
    assert dlg._already_active_list.count() == 1


def test_copy_to_clipboard_copies_only_the_requested_list(qtbot: QtBot, qapp) -> None:
    dlg = LabelImportResultDialog(["Ghost"], ["Speed"], parent=None)
    qtbot.addWidget(dlg)

    dlg._copy_to_clipboard(dlg._not_found)
    assert QGuiApplication.clipboard().text() == "Ghost"

    dlg._copy_to_clipboard(dlg._already_active)
    assert QGuiApplication.clipboard().text() == "Speed"


def test_empty_lists_are_accepted(qtbot: QtBot) -> None:
    dlg = LabelImportResultDialog([], [], parent=None)
    qtbot.addWidget(dlg)
    assert dlg._not_found_list.count() == 0
    assert dlg._already_active_list.count() == 0
