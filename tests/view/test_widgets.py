"""Tests for small reusable view widgets (view/widgets/)."""

from __future__ import annotations

import pytest
from pytestqt.qtbot import QtBot

from mdf_viewer.view.widgets.visibility_toggle_button import VisibilityToggleButton


@pytest.fixture()
def button(qtbot: QtBot) -> VisibilityToggleButton:
    b = VisibilityToggleButton(True)
    qtbot.addWidget(b)
    return b


def test_defaults_to_given_state(button: VisibilityToggleButton) -> None:
    assert button.visible_state is True


def test_set_visible_state_updates_state(button: VisibilityToggleButton) -> None:
    button.set_visible_state(False)
    assert button.visible_state is False
    button.set_visible_state(True)
    assert button.visible_state is True


def test_icon_changes_between_states(button: VisibilityToggleButton) -> None:
    open_icon = button.icon()
    button.set_visible_state(False)
    hidden_icon = button.icon()
    # QIcon has no simple equality by content, but cacheKey() differs for
    # distinct icon sources loaded from different files.
    assert open_icon.cacheKey() != hidden_icon.cacheKey()


def test_constructs_hidden_by_default_when_asked(qtbot: QtBot) -> None:
    b = VisibilityToggleButton(False)
    qtbot.addWidget(b)
    assert b.visible_state is False
