"""busy_cursor — wait-cursor + optional status-bar message for a blocking call."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Callable

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication


@contextmanager
def busy_cursor(
    message: str | None = None,
    *,
    show_status: Callable[[str, int], None] | None = None,
    clear_status: Callable[[], None] | None = None,
):
    """Show a wait cursor for the duration of the `with` block (#137).

    If *message* is given, shows it via *show_status* before the cursor
    goes up and clears it via *clear_status* afterward. The cursor is
    always restored — and the message always cleared, if one was shown —
    even if the wrapped code raises, matching every pre-existing call
    site's own `try/finally` exactly.
    """
    if message is not None and show_status is not None:
        show_status(message, 0)
    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    QApplication.processEvents()
    try:
        yield
    finally:
        QApplication.restoreOverrideCursor()
        if message is not None and clear_status is not None:
            clear_status()
