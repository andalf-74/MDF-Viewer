"""SearchController — find-next-vs-restart session state for #110.

Owns the one piece of state that makes "find next" work (REQ-SEARCH-041/042):
whether the current click's criteria match the previous click's, and if so,
where to resume scanning from. The actual scan itself is delegated to the
pure model.signal_search.find_match.
"""

from __future__ import annotations

from typing import Any

from mdf_viewer.model.signal_search import SearchRow, find_match


class SearchController:
    """Session state for one Search dialog's worth of repeated searches."""

    def __init__(self) -> None:
        self._last_snapshot: list[tuple[Any, Any, float]] | None = None
        self._last_match: float | None = None

    def reset(self) -> None:
        """Discard continuation state — the next run() starts from the beginning."""
        self._last_snapshot = None
        self._last_match = None

    def run(self, rows: list[SearchRow]) -> float | None:
        """Run a search, continuing from the last match if *rows* is
        unchanged from the previous call, or restarting from the beginning
        otherwise (REQ-SEARCH-040/041/042).

        The snapshot compares each row's signal, operator, and value —
        signal identity via ActiveSignal's identity __eq__, not id(), since
        id() values can be recycled once an ActiveSignal is freed and this
        state persists across separate calls, not just within one.
        """
        snapshot = [(row.signal, row.operator, row.value) for row in rows]
        after = self._last_match if snapshot == self._last_snapshot else None
        match = find_match(rows, after=after)
        self._last_snapshot = snapshot
        self._last_match = match if match is not None else after
        return match
