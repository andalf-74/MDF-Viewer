"""Shared fixtures for tests/plugin_api/."""

from __future__ import annotations

import urllib.error

import pytest


def _raise_urlerror(*_args, **_kwargs):
    raise urllib.error.URLError("network disabled in tests")


@pytest.fixture(autouse=True)
def _no_real_network_for_update_checker(monkeypatch):
    """The update_checker plugin (#76) is discovered from REPO_PLUGINS_DIR
    by every test in this package that loads the real plugins directory,
    not just its own — its `activate()` starts a real background network
    check by default. Patch `urlopen` to fail fast here so unrelated
    plugin tests (signal_statistics, tab_type_fixture, ...) never make a
    real HTTP request or block waiting on one; tests that specifically
    exercise update-checker's network behavior patch this themselves
    (via `unittest.mock.patch`) for the duration of that one call, which
    composes fine on top of this default.
    """
    monkeypatch.setattr("urllib.request.urlopen", _raise_urlerror)
