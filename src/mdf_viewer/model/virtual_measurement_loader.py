"""VirtualMeasurementLoader — MeasurementLoader backed by VirtualSignals (#147).

Implements the same structural contract MdfLoader does, so the rest of the
app (Signal Browser, plotting, offset/Primary/Sync) doesn't need to know a
measurement isn't backed by a real file. Always exposes its attached
signals as one synthetic channel group (REQ-VMEAS-130 — a virtual
measurement's channel tree holds only virtual signals).
"""

from __future__ import annotations

import logging
from dataclasses import replace
from pathlib import Path

from mdf_viewer.errors import MdfLoadError
from mdf_viewer.model.mdf_loader import ChannelGroupInfo
from mdf_viewer.model.measurement import MeasurementInfo
from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.model.virtual_signal import VirtualSignal

logger = logging.getLogger("mdf_viewer.model.virtual_measurement_loader")


class VirtualMeasurementLoader:
    """A MeasurementLoader with no file behind it — its data is plugin-supplied."""

    def __init__(self, owner_plugin: str) -> None:
        self._owner_plugin = owner_plugin
        # Keyed by a monotonically-increasing channel_index assigned once at
        # attach() time, never reused — NOT a list, so detach() never has
        # to renumber every later signal's channel_index (#162, REQ-VMEAS-124).
        # A positional scheme was tried and rejected: an already-plotted
        # signal's channel_index is baked into its ActiveSignal.metadata at
        # load_signal() time and never refreshed, so shifting a later
        # signal's index after a detach would silently duplicate or drop it
        # the next time add_signal() touches this measurement.
        self._signals: dict[int, VirtualSignal] = {}
        self._next_channel_index = 0

    def attach(self, signal: VirtualSignal) -> None:
        # Identity (`is`), not equality: two attached signals may share
        # identical name/template (REQ-VMEAS-123), so `in`/`==` can't be
        # used to detect "already attached" without also rejecting
        # legitimate distinct signals that happen to look alike.
        if any(existing is signal for existing in self._signals.values()):
            logger.error(
                "Plugin '%s' tried to attach the same virtual signal '%s' twice — ignored",
                self._owner_plugin, signal.name,
            )
            return
        self._signals[self._next_channel_index] = signal
        self._next_channel_index += 1

    def detach(self, signal: VirtualSignal) -> int | None:
        """Detach *signal*, found by identity, returning its freed
        channel_index — or None if it wasn't attached. The caller (#162)
        needs the freed index to tear down any plotted instance of this
        exact signal, since name alone can't safely distinguish it from
        another attached signal sharing the same name."""
        for channel_index, existing in self._signals.items():
            if existing is signal:
                del self._signals[channel_index]
                return channel_index
        return None

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
            for ci, signal in sorted(self._signals.items())
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
