"""Shared pytest fixtures.

Model and controller tests run headless (no Qt). View tests that need a
QApplication should use the ``qtbot`` fixture from pytest-qt.
"""

from __future__ import annotations

import logging
import os
import sys

import pytest

# Real dialogs/windows (e.g. an un-mocked QMessageBox.question()) would
# otherwise flash visibly on screen during a test run — setdefault() so an
# explicit override (e.g. debugging with a real platform plugin) still
# wins. Per CLAUDE.md's #78 postmortem, offscreen does NOT make synthetic
# mouse-interaction tests trustworthy on its own — it's unrelated to that;
# this is purely about not rendering visible windows during automated runs.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(autouse=True)
def _isolate_root_logger():
    """Undo any process-wide logging state a test leaves behind (#126).

    Unlike the per-instance Qt objects most other fixtures in this repo
    guard against, the root logger and `sys.excepthook` are genuine
    process-wide singletons — a test that calls `configure_logging()`
    without this would leak a `RotatingFileHandler` pointed at its own
    `tmp_path`, which on Windows keeps the directory's file handle open and
    makes pytest's automatic tmp-dir cleanup fail with `PermissionError`.
    """
    root = logging.getLogger()
    handlers_before = list(root.handlers)
    level_before = root.level
    excepthook_before = sys.excepthook
    yield
    for handler in list(root.handlers):
        if handler not in handlers_before:
            root.removeHandler(handler)
            handler.close()
    root.setLevel(level_before)
    sys.excepthook = excepthook_before

    from mdf_viewer import logging_config
    logging_config._handler = None
    logging_config._excepthook_installed = False
