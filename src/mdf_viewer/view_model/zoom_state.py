"""ZoomState — snapshot of the full plot zoom state."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ZoomState:
    """Snapshot of the shared X range plus each active signal's Y range.

    y_ranges is keyed by ActiveSignal identity (object.__hash__), so lookup
    is O(1) and survives signals being added or removed after capture.
    """
    x_range: tuple[float, float]
    y_ranges: dict = field(default_factory=dict)  # ActiveSignal → (y_min, y_max)
