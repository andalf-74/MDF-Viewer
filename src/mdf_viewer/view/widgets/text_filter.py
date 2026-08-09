"""Shared text-filter helpers for QSortFilterProxyModel-backed lists.

Used by SignalBrowser and the X-Axis Signal picker dialog (#86) so every
filterable channel list in the app interprets the same filter syntax (plain
substring, or `*`/`?` wildcards) and debounce timing identically, without
one importing the other's unrelated machinery (Tree mode, drag-and-drop,
measurement filter).
"""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QObject, QSortFilterProxyModel, QTimer
from PyQt6.QtWidgets import QLineEdit

# Delay before applying the filter after the user stops typing — re-filtering
# on every keystroke makes typing feel sluggish over a large channel list.
FILTER_DELAY_MS = 250


def apply_text_filter(proxy: QSortFilterProxyModel, text: str) -> None:
    """Filter *proxy* by *text* — wildcard matching (`*`/`?`) when either
    character is present, else a plain substring match.

    Qt's own `setFilterWildcard()` requires the *whole* string to match a
    pattern containing no wildcard characters (it behaves as "equals", not
    "contains"), so a plain search term needs `setFilterFixedString()`
    instead to behave the way a filter box user expects.
    """
    if "*" in text or "?" in text:
        proxy.setFilterWildcard(text)
    else:
        proxy.setFilterFixedString(text)


def wire_debounced_filter(
    line_edit: QLineEdit,
    apply: "Callable[[], None]",
    *,
    delay_ms: int = FILTER_DELAY_MS,
    parent: QObject | None = None,
) -> QTimer:
    """Debounce *line_edit*'s `textChanged` into a call to *apply*.

    Returns the QTimer, parented to *line_edit* by default so its lifetime
    is tied to the widget without the caller needing to keep its own
    reference.
    """
    timer = QTimer(parent or line_edit)
    timer.setSingleShot(True)
    timer.setInterval(delay_ms)
    timer.timeout.connect(apply)
    line_edit.textChanged.connect(lambda: timer.start())
    return timer
