"""Shared pytest fixtures.

Model and controller tests run headless (no Qt). View tests that need a
QApplication should use the ``qtbot`` fixture from pytest-qt.
"""

from __future__ import annotations

import os

# Real dialogs/windows (e.g. an un-mocked QMessageBox.question()) would
# otherwise flash visibly on screen during a test run — setdefault() so an
# explicit override (e.g. debugging with a real platform plugin) still
# wins. Per CLAUDE.md's #78 postmortem, offscreen does NOT make synthetic
# mouse-interaction tests trustworthy on its own — it's unrelated to that;
# this is purely about not rendering visible windows during automated runs.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
