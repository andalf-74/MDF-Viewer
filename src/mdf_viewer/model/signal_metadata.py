"""SignalMetadata — descriptive information about a signal.

Pure data: no samples, no UI. Holds everything needed to describe a channel
without loading its data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class SignalMetadata:
    """Descriptive metadata for a single MDF channel."""

    name: str
    unit: str = ""
    comment: str = ""
    sample_count: int | None = None
    min_value: float | None = None
    max_value: float | None = None
    # Identifies where the channel lives inside the MDF file.
    group_index: int | None = None
    channel_index: int | None = None
    # Any additional MDF metadata fields that don't map to the above.
    extra: dict[str, Any] = field(default_factory=dict)
