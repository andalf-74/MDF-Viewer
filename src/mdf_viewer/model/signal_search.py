"""Signal Value Search evaluation engine (#110).

Pure, Qt-free: given a set of per-signal conditions, finds the next
timestamp where all of them hold simultaneously. See
docs/requirements/signal-search.md (REQ-SEARCH-030 through 032) for the
evaluation semantics this implements.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Callable

import numpy as np

from mdf_viewer.model.signal_rate import highest_rate_signal

if TYPE_CHECKING:
    from mdf_viewer.view_model.active_signal import ActiveSignal


class SearchOperator(Enum):
    EQ = "="
    NE = "≠"
    GT = ">"
    LT = "<"
    GE = "≥"
    LE = "≤"


_OPS: dict[SearchOperator, Callable[[np.ndarray, float], np.ndarray]] = {
    SearchOperator.EQ: np.equal,
    SearchOperator.NE: np.not_equal,
    SearchOperator.GT: np.greater,
    SearchOperator.LT: np.less,
    SearchOperator.GE: np.greater_equal,
    SearchOperator.LE: np.less_equal,
}


@dataclass(frozen=True, slots=True)
class SearchRow:
    """One signal's condition within a search (REQ-SEARCH-020/021/022)."""

    signal: "ActiveSignal"
    operator: SearchOperator
    value: float


def find_match(rows: list[SearchRow], after: float | None) -> float | None:
    """Return the first display-time timestamp where every row's condition
    holds simultaneously, or None if no such timestamp exists.

    Evaluation scans along the fastest-raster signal among *rows* only
    (REQ-SEARCH-031). Every row's value is read as the most recent sample at
    or before each scan timestamp — zero-order-hold, held forever past a
    signal's last sample — never interpolated (REQ-SEARCH-030). This
    deliberately diverges from model.interpolate.interpolate(), which is a
    single-point API for cursor-value display and returns None past a
    signal's last sample; that bounds check must not be copied here.

    If *after* is given, only timestamps strictly greater than it are
    considered (REQ-SEARCH-041) — so a repeated call with an unchanged
    *after* never re-reports the same match.
    """
    if not rows:
        return None
    reference = highest_rate_signal([row.signal for row in rows])
    if reference is None:
        return None
    grid = reference.display_timestamps
    if after is not None:
        grid = grid[grid > after]
    if grid.size == 0:
        return None

    mask = np.ones(grid.shape, dtype=bool)
    for row in rows:
        samples = row.signal.data.samples
        if len(samples) == 0:
            # No data at all for this row's signal — its condition can
            # never hold, so the whole conjunction is permanently False.
            return None
        ts = row.signal.display_timestamps
        idx = np.searchsorted(ts, grid, side="right") - 1
        valid = idx >= 0
        vals = np.where(valid, samples[np.clip(idx, 0, len(samples) - 1)], np.nan)
        mask &= _OPS[row.operator](vals, row.value) & valid

    hits = np.nonzero(mask)[0]
    if hits.size == 0:
        return None
    return float(grid[hits[0]])
