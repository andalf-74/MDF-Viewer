"""MeasurementInfo — file-level MDF metadata for the Measurement Info Box.

Pure data: describes the loaded file, not its signal samples.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class MeasurementInfo:
    """File-level metadata about a loaded MDF measurement."""

    file_name: str
    mdf_version: str = ""
    author: str = ""
    recorded_at: str = ""
    duration_s: float | None = None
    comment: str = ""
    # Any additional file-level metadata fields exposed by the MDF.
    extra: dict[str, Any] = field(default_factory=dict)
