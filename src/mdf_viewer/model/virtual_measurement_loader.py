"""VirtualMeasurementLoader — MeasurementLoader backed by VirtualSignals (#147).

Implements the same structural contract MdfLoader does, so the rest of the
app (Signal Browser, plotting, offset/Primary/Sync) doesn't need to know a
measurement isn't backed by a real file. Always exposes its attached
signals as one synthetic channel group (REQ-VMEAS-130 — a virtual
measurement's channel tree holds only virtual signals).
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from mdf_viewer.errors import MdfLoadError
from mdf_viewer.model.mdf_loader import ChannelGroupInfo
from mdf_viewer.model.measurement import MeasurementInfo
from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.model.virtual_signal import VirtualSignal


class VirtualMeasurementLoader:
    """A MeasurementLoader with no file behind it — its data is plugin-supplied."""

    def __init__(self, owner_plugin: str) -> None:
        self._owner_plugin = owner_plugin
        self._signals: list[VirtualSignal] = []

    def attach(self, signal: VirtualSignal) -> None:
        self._signals.append(signal)

    @property
    def is_open(self) -> bool:
        return True

    @property
    def path(self) -> Path | None:
        return None

    def measurement_info(self) -> MeasurementInfo:
        return MeasurementInfo(file_name="")

    def channel_tree(self) -> list[ChannelGroupInfo]:
        channels = tuple(
            replace(
                signal.template,
                group_index=0,
                channel_index=ci,
                group_name=self._owner_plugin,
            )
            for ci, signal in enumerate(self._signals)
        )
        return [ChannelGroupInfo(name=self._owner_plugin, index=0, channels=channels)]

    def find_signal_by_name(self, name: str) -> list[SignalMetadata]:
        return [ch for group in self.channel_tree() for ch in group.channels if ch.name == name]

    def find_similar_signal_by_name(self, name: str) -> list[SignalMetadata]:
        # Same semantics as MdfLoader.find_similar_signal_by_name (REQ-FILE-032/033):
        # names sharing everything up to the last "\", excluding exact matches.
        if "\\" not in name:
            return []
        prefix = name.rsplit("\\", 1)[0]
        result: list[SignalMetadata] = []
        for group in self.channel_tree():
            for ch in group.channels:
                if ch.name == name or "\\" not in ch.name:
                    continue
                if ch.name.rsplit("\\", 1)[0] == prefix:
                    result.append(ch)
        return result

    def load_signal(
        self, group_index: int, channel_index: int
    ) -> tuple[SignalData, SignalMetadata]:
        # Wraps a raising resolver() in MdfLoadError, exactly like
        # MdfLoader.load_signal() wraps a raising asammdf read — so a
        # virtual signal's failure flows through the same established
        # path (MainWindow's existing `except MdfLoadError` dialog) a
        # real signal's failure already does, rather than needing a
        # second, differently-shaped error-handling mechanism.
        signal = self._signals[channel_index]
        try:
            data, metadata = signal.resolver()
        except Exception as exc:
            raise MdfLoadError(f"Cannot resolve virtual signal '{signal.name}': {exc}") from exc
        return data, replace(metadata, group_index=group_index, channel_index=channel_index)

    def close(self) -> None:
        pass
