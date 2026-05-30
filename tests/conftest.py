"""Shared pytest fixtures.

Model and controller tests run headless (no Qt). View tests that need a
QApplication should use the ``qtbot`` fixture from pytest-qt.
"""

from __future__ import annotations
