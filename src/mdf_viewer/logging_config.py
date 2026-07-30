"""Application logging setup (#126).

Configures Python's standard `logging` module against a single rotating
file, driven by `Settings.logging_enabled`/`logging_level`. Deliberately
attaches to the *root* logger, not a "mdf_viewer"-namespaced one, so a
plugin's own `logging.getLogger(__name__)` call is captured automatically —
a dynamically-imported plugin module's `__name__` is a synthesized name
(see `PluginLoader._module_name_for`) that never falls under a "mdf_viewer"
logger hierarchy, so a namespaced handler would silently miss it.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from PyQt6.QtCore import QUrl
from PyQt6.QtGui import QDesktopServices

if TYPE_CHECKING:
    from mdf_viewer.settings import Settings

_MAX_BYTES = 5 * 1024 * 1024
_BACKUP_COUNT = 3
_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"

_handler: logging.Handler | None = None
_excepthook_installed = False


def log_file_path(settings: "Settings") -> Path:
    return settings.config_dir / "logs" / "mdf_viewer.log"


def configure_logging(settings: "Settings") -> None:
    """(Re-)configure the root logger from *settings*. Idempotent — safe to
    call repeatedly (once at startup, and again after every Preferences
    change) without accumulating duplicate handlers.
    """
    global _handler
    root = logging.getLogger()

    if _handler is not None:
        root.removeHandler(_handler)
        _handler.close()
        _handler = None

    if not settings.logging_enabled:
        # Restore the interpreter's own default so a user who explicitly
        # disabled logging doesn't still get third-party DEBUG/INFO chatter
        # printed to stderr by logging's "handler of last resort".
        root.setLevel(logging.WARNING)
        return

    path = log_file_path(settings)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=_MAX_BYTES, backupCount=_BACKUP_COUNT, encoding="utf-8"
        )
    except OSError:
        # A locked-down config directory must never prevent the app from
        # starting — logging is a diagnostic convenience, not a dependency.
        logging.getLogger("mdf_viewer.logging_config").exception(
            "Failed to set up log file at '%s' — logging disabled for this session", path
        )
        return

    handler.setFormatter(logging.Formatter(_FORMAT))
    root.addHandler(handler)
    root.setLevel(getattr(logging, settings.logging_level, logging.INFO))
    _handler = handler


def install_excepthook() -> None:
    """Log any uncaught exception before falling through to the previous
    excepthook (so console/debugger behavior is unchanged). Idempotent.
    """
    global _excepthook_installed
    if _excepthook_installed:
        return
    _excepthook_installed = True

    previous = sys.excepthook

    def _hook(exc_type, exc_value, exc_tb):
        logging.getLogger("mdf_viewer.app").critical(
            "Uncaught exception", exc_info=(exc_type, exc_value, exc_tb)
        )
        previous(exc_type, exc_value, exc_tb)

    sys.excepthook = _hook


def open_log_folder(settings: "Settings") -> None:
    """Open the log folder in the OS file browser, creating it first if
    it doesn't exist yet (e.g. logging has never been enabled)."""
    folder = log_file_path(settings).parent
    folder.mkdir(parents=True, exist_ok=True)
    QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))
