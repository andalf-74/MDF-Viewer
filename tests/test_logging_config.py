"""Tests for logging_config.py — root-logger setup driven by Settings (#126)."""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

import pytest

from mdf_viewer.logging_config import (
    configure_logging,
    install_excepthook,
    log_file_path,
    open_log_folder,
)
from mdf_viewer.settings import Settings


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(path=tmp_path / "settings.json")


def _read_log(settings: Settings) -> str:
    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.handlers.RotatingFileHandler):
            handler.flush()
    return log_file_path(settings).read_text(encoding="utf-8")


@pytest.mark.requirement("REQ-LOG-010")
def test_log_file_path_is_under_settings_config_dir(settings: Settings) -> None:
    path = log_file_path(settings)
    assert path == settings.config_dir / "logs" / "mdf_viewer.log"


@pytest.mark.requirement("REQ-LOG-020")
def test_configure_logging_enabled_creates_file_and_captures_entries(settings: Settings) -> None:
    assert settings.logging_enabled is True
    configure_logging(settings)
    logging.getLogger("mdf_viewer.testmod").info("hello")
    assert "hello" in _read_log(settings)


@pytest.mark.requirement("REQ-LOG-021")
def test_configure_logging_disabled_attaches_no_handler(settings: Settings) -> None:
    settings.logging_enabled = False
    configure_logging(settings)
    assert not log_file_path(settings).exists()
    root = logging.getLogger()
    assert not any(
        isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers
    )


@pytest.mark.requirement("REQ-LOG-012")
def test_log_entry_includes_timestamp_level_logger_name_and_message(settings: Settings) -> None:
    configure_logging(settings)
    logging.getLogger("mdf_viewer.testmod").warning("something happened")
    content = _read_log(settings)
    assert "WARNING" in content
    assert "mdf_viewer.testmod" in content
    assert "something happened" in content


@pytest.mark.requirement("REQ-LOG-022")
def test_configure_logging_filters_below_selected_level(settings: Settings) -> None:
    settings.logging_level = "WARNING"
    configure_logging(settings)
    logging.getLogger("mdf_viewer.testmod").info("should be filtered out")
    logging.getLogger("mdf_viewer.testmod").warning("should pass through")
    content = _read_log(settings)
    assert "should be filtered out" not in content
    assert "should pass through" in content


@pytest.mark.requirement("REQ-LOG-011")
def test_configure_logging_sets_rotation_parameters(settings: Settings) -> None:
    configure_logging(settings)
    root = logging.getLogger()
    (handler,) = [h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
    assert handler.maxBytes == 5 * 1024 * 1024
    assert handler.backupCount == 3


def test_configure_logging_captures_non_mdf_viewer_namespaced_logger(settings: Settings) -> None:
    """A plugin's dynamically-imported module has a synthesized __name__ that
    never falls under "mdf_viewer" — root-logger attachment must still catch it
    (REQ-LOG-034)."""
    configure_logging(settings)
    logging.getLogger("_mdf_viewer_plugin_abc123_some_plugin").info("plugin says hi")
    assert "plugin says hi" in _read_log(settings)


def test_configure_logging_is_idempotent_no_duplicate_handlers(settings: Settings) -> None:
    configure_logging(settings)
    configure_logging(settings)
    configure_logging(settings)
    root = logging.getLogger()
    file_handlers = [h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
    assert len(file_handlers) == 1


def test_enable_disable_reenable_cycle_ends_correct(settings: Settings) -> None:
    configure_logging(settings)
    logging.getLogger("mdf_viewer.testmod").info("first")

    settings.logging_enabled = False
    configure_logging(settings)
    root = logging.getLogger()
    assert not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers)
    assert root.level == logging.WARNING

    settings.logging_enabled = True
    configure_logging(settings)
    logging.getLogger("mdf_viewer.testmod").info("second")
    file_handlers = [h for h in root.handlers if isinstance(h, logging.handlers.RotatingFileHandler)]
    assert len(file_handlers) == 1
    content = _read_log(settings)
    assert "first" in content
    assert "second" in content


def test_configure_logging_handler_creation_failure_does_not_raise(settings: Settings) -> None:
    # Create a *file* where the "logs" directory needs to go, so mkdir()
    # raises — must fall back to "logging disabled", never propagate.
    log_file_path(settings).parent.parent.mkdir(parents=True, exist_ok=True)
    (log_file_path(settings).parent.parent / "logs").write_text("not a directory")
    configure_logging(settings)  # must not raise


@pytest.mark.requirement("REQ-LOG-035")
def test_install_excepthook_logs_and_chains_to_previous(settings: Settings) -> None:
    configure_logging(settings)
    called_with = []
    previous = sys.excepthook
    sys.excepthook = lambda *args: called_with.append(args)
    try:
        install_excepthook()
        try:
            raise ValueError("boom")
        except ValueError:
            sys.excepthook(*sys.exc_info())
        content = _read_log(settings)
        assert "Uncaught exception" in content
        assert "ValueError" in content
        assert len(called_with) == 1
    finally:
        sys.excepthook = previous


def test_install_excepthook_is_idempotent(settings: Settings) -> None:
    install_excepthook()
    hook_after_first = sys.excepthook
    install_excepthook()
    assert sys.excepthook is hook_after_first


@pytest.mark.requirement("REQ-LOG-043")
def test_open_log_folder_creates_folder_if_missing(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    opened = []

    class _FakeQDesktopServices:
        @staticmethod
        def openUrl(url):
            opened.append(url)

    monkeypatch.setattr("mdf_viewer.logging_config.QDesktopServices", _FakeQDesktopServices)
    assert not log_file_path(settings).parent.exists()
    open_log_folder(settings)
    assert log_file_path(settings).parent.exists()
    assert len(opened) == 1
