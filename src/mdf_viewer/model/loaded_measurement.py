"""LoadedMeasurement — one loaded MDF file within the multi-measurement pool.

Bundles the model-layer pieces needed to track a loaded measurement across
its lifetime: the MdfLoader that owns its channel data, the file-level
MeasurementInfo snapshot, a user-facing label, and the mutable X-axis time
offset the user pans independently of every other loaded measurement (#101).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from mdf_viewer.model.mdf_loader import MdfLoader
from mdf_viewer.model.measurement import MeasurementInfo


@dataclass
class LoadedMeasurement:
    """One measurement in the app's global multi-measurement pool."""

    loader: MdfLoader
    info: MeasurementInfo
    label: str
    offset_s: float = 0.0


def make_label(path: str | os.PathLike, existing_labels: list[str]) -> str:
    """Derive a display label for *path* that doesn't collide with *existing_labels*.

    Uses the file stem (REQ-FILE-027); on collision, appends " (2)", " (3)",
    etc. until unique.
    """
    stem = Path(path).stem
    if stem not in existing_labels:
        return stem
    n = 2
    while f"{stem} ({n})" in existing_labels:
        n += 1
    return f"{stem} ({n})"
