"""LoadedMeasurement — one loaded measurement within the multi-measurement pool.

Bundles the model-layer pieces needed to track a loaded measurement across
its lifetime: the MeasurementLoader that owns its channel data, the
file-level MeasurementInfo snapshot, a user-facing short name (`label`,
editable via AppController.rename_measurement — REQ-FILE-027), and the
mutable X-axis time offset the user pans independently of every other
loaded measurement (#101). Which measurement is currently "Primary" (#103,
REQ-PLOT-317) is tracked on AppController, not here, to keep "exactly one
Primary" a structural invariant rather than a per-instance flag that could
desync.
"""

from __future__ import annotations

from dataclasses import dataclass

from mdf_viewer.model.measurement import MeasurementInfo
from mdf_viewer.model.measurement_loader import MeasurementLoader


@dataclass
class LoadedMeasurement:
    """One measurement in the app's global multi-measurement pool."""

    loader: MeasurementLoader
    info: MeasurementInfo
    label: str
    offset_s: float = 0.0
    # Contributing plugin's name for a virtual measurement (#147); None for
    # any real, file-backed measurement. Single source of truth for "is
    # this measurement virtual" — doubles as the UI-badge signal
    # (REQ-VMEAS-210) and the teardown/notification attribution
    # (REQ-PLUGIN-300), rather than two flags that could drift apart.
    owner_plugin: str | None = None


def make_label(index: int, existing_labels: list[str]) -> str:
    """Derive a default short name for the *index*-th loaded measurement.

    0-based, in load order: "M1", "M2", .... On collision with
    *existing_labels* (e.g. a later measurement was manually renamed to a
    name a not-yet-loaded default would also produce), appends " (2)",
    " (3)", etc. until unique (REQ-FILE-027).
    """
    candidate = f"M{index + 1}"
    if candidate not in existing_labels:
        return candidate
    n = 2
    while f"{candidate} ({n})" in existing_labels:
        n += 1
    return f"{candidate} ({n})"
