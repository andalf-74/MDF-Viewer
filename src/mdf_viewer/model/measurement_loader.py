"""MeasurementLoader — structural contract for LoadedMeasurement.loader (#147).

Captures the surface MdfLoader already exposes and the rest of the app
already depends on structurally (Signal Browser population, plotting,
workspace capture). Lets LoadedMeasurement hold something other than an
MdfLoader — e.g. VirtualMeasurementLoader — without any call site needing
to know or care which one it has.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from mdf_viewer.model.mdf_loader import ChannelGroupInfo
from mdf_viewer.model.measurement import MeasurementInfo
from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata


@runtime_checkable
class MeasurementLoader(Protocol):
    """Structural contract satisfied by both MdfLoader and VirtualMeasurementLoader."""

    @property
    def is_open(self) -> bool: ...

    @property
    def path(self) -> Path | None: ...

    def measurement_info(self) -> MeasurementInfo: ...

    def channel_tree(self) -> list[ChannelGroupInfo]: ...

    def find_signal_by_name(self, name: str) -> list[SignalMetadata]: ...

    def find_similar_signal_by_name(self, name: str) -> list[SignalMetadata]: ...

    def load_signal(
        self, group_index: int, channel_index: int
    ) -> tuple[SignalData, SignalMetadata]: ...

    def close(self) -> None: ...
