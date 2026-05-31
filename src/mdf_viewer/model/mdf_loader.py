"""MdfLoader — the only module that imports ``asammdf``.

Isolating all file I/O here means the rest of the application depends on plain
data classes (SignalData, SignalMetadata, MeasurementInfo) rather than on the
asammdf API. It is also the single place responsible for catching malformed or
unexpected MDF content and surfacing it as a clean error.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from mdf_viewer.model.measurement import MeasurementInfo
from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata


class MdfLoadError(Exception):
    """Raised when an MDF file cannot be opened or read.

    The controller/view should catch this and present the message to the user;
    the application must never crash on malformed or incomplete MDF content.
    """


@dataclass(frozen=True, slots=True)
class ChannelGroupInfo:
    """Describes one channel group from the MDF file hierarchy."""

    name: str
    index: int
    channels: tuple[SignalMetadata, ...]


class MdfLoader:
    """Loads an MDF file and exposes its hierarchy, signals, and metadata.

    Wraps ``asammdf.MDF``. Call ``open()`` before any other method.
    """

    def __init__(self) -> None:
        self._mdf = None  # asammdf.MDF instance, set by open()
        self._path: Path | None = None

    # ------------------------------------------------------------------
    # File lifecycle
    # ------------------------------------------------------------------

    def open(self, path: str | os.PathLike) -> None:
        """Open an MDF file (MDF3 or MDF4). Raises MdfLoadError on failure."""
        import asammdf  # imported here to keep asammdf out of the module namespace

        self.close()
        path = Path(path)
        try:
            self._mdf = asammdf.MDF(path)
            self._path = path
        except Exception as exc:
            self._mdf = None
            self._path = None
            raise MdfLoadError(f"Cannot open '{path.name}': {exc}") from exc

    def close(self) -> None:
        """Close the underlying MDF file if one is open."""
        if self._mdf is not None:
            try:
                self._mdf.close()
            except Exception:
                pass
            self._mdf = None
            self._path = None

    @property
    def is_open(self) -> bool:
        return self._mdf is not None

    # ------------------------------------------------------------------
    # Data access
    # ------------------------------------------------------------------

    def measurement_info(self) -> MeasurementInfo:
        """Return file-level metadata for the Measurement Info Box."""
        self._require_open()
        mdf = self._mdf

        author = ""
        comment = ""
        recorded_at = ""
        duration_s: float | None = None
        extra: dict = {}

        try:
            header = mdf.header
            try:
                author = str(header.author or "")
            except Exception:
                pass
            try:
                raw_comment = header.comment or ""
                comment = str(raw_comment)
            except Exception:
                pass
        except Exception:
            pass

        try:
            start = mdf.start_time
            if start is not None:
                recorded_at = start.isoformat(sep=" ", timespec="seconds")
        except Exception:
            pass

        try:
            duration_s = _compute_duration(mdf)
        except Exception:
            pass

        return MeasurementInfo(
            file_name=self._path.name,
            mdf_version=str(mdf.version),
            author=author,
            recorded_at=recorded_at,
            duration_s=duration_s,
            comment=comment,
            extra=extra,
        )

    def channel_tree(self) -> list[ChannelGroupInfo]:
        """Return the full channel group / channel hierarchy.

        Used by the Signal Browser to build its TreeView.
        """
        self._require_open()
        mdf = self._mdf

        result: list[ChannelGroupInfo] = []
        try:
            for gi, group in enumerate(mdf.groups):
                group_name = _channel_group_name(group, gi)
                channels: list[SignalMetadata] = []

                for ci, channel in enumerate(group.channels):
                    try:
                        name = channel.name or f"channel_{ci}"
                        unit = ""
                        comment = ""
                        try:
                            unit = str(channel.unit or "")
                        except Exception:
                            pass
                        try:
                            comment = str(channel.comment or "")
                        except Exception:
                            pass
                        channels.append(
                            SignalMetadata(
                                name=name,
                                unit=unit,
                                comment=comment,
                                group_index=gi,
                                channel_index=ci,
                            )
                        )
                    except Exception:
                        continue

                result.append(
                    ChannelGroupInfo(
                        name=group_name,
                        index=gi,
                        channels=tuple(channels),
                    )
                )
        except Exception as exc:
            raise MdfLoadError(f"Failed to enumerate channels: {exc}") from exc

        return result

    def load_signal(
        self, group_index: int, channel_index: int
    ) -> tuple[SignalData, SignalMetadata]:
        """Load samples for one channel. Returns ``(SignalData, SignalMetadata)``.

        Raises MdfLoadError if the channel cannot be read or its samples cannot
        be represented as float64 (e.g. string or struct channels).
        """
        self._require_open()
        mdf = self._mdf

        try:
            channel_block = mdf.groups[group_index].channels[channel_index]
            channel_name = channel_block.name
        except (IndexError, AttributeError) as exc:
            raise MdfLoadError(
                f"Channel [{group_index}][{channel_index}] not found: {exc}"
            ) from exc

        try:
            sig = mdf.get(channel_name, group=group_index, index=channel_index)
        except Exception as exc:
            raise MdfLoadError(
                f"Cannot read channel '{channel_name}' "
                f"[{group_index}][{channel_index}]: {exc}"
            ) from exc

        try:
            raw_dtype = np.asarray(sig.samples).dtype
            timestamps = np.asarray(sig.timestamps, dtype=np.float64)
            samples = np.asarray(sig.samples, dtype=np.float64)
        except (ValueError, TypeError) as exc:
            raise MdfLoadError(
                f"Channel '{channel_name}' samples cannot be converted to "
                f"numeric values: {exc}"
            ) from exc

        data = SignalData(timestamps=timestamps, samples=samples)

        min_val: float | None = None
        max_val: float | None = None
        if data.sample_count > 0:
            try:
                min_val = float(np.nanmin(samples))
                max_val = float(np.nanmax(samples))
            except Exception:
                pass

        meta = SignalMetadata(
            name=sig.name,
            unit=str(sig.unit or ""),
            comment=str(sig.comment or ""),
            sample_count=data.sample_count,
            min_value=min_val,
            max_value=max_val,
            group_index=group_index,
            channel_index=channel_index,
            data_type=str(raw_dtype),
            is_integer=bool(np.issubdtype(raw_dtype, np.integer)),
        )

        return data, meta

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _require_open(self) -> None:
        if self._mdf is None:
            raise MdfLoadError("No file is open. Call open() first.")


# ---------------------------------------------------------------------------
# Module-level helpers (no MdfLoader state needed)
# ---------------------------------------------------------------------------

def _channel_group_name(group, gi: int) -> str:
    """Derive a display name for a channel group block."""
    cg = group.channel_group
    # MDF4 groups have acq_name; MDF3 groups only have comment.
    for attr in ("acq_name", "comment"):
        try:
            value = getattr(cg, attr, None)
            if value:
                return str(value)
        except Exception:
            pass
    return f"Group {gi}"


def _compute_duration(mdf) -> float | None:
    """Return recording duration in seconds, or None if not determinable."""
    t_min: float | None = None
    t_max: float | None = None

    for gi in range(len(mdf.groups)):
        try:
            master = mdf.get_master(gi)
            if master is None or len(master) == 0:
                continue
            lo = float(master[0])
            hi = float(master[-1])
            t_min = lo if t_min is None else min(t_min, lo)
            t_max = hi if t_max is None else max(t_max, hi)
        except Exception:
            continue

    if t_min is not None and t_max is not None:
        return t_max - t_min
    return None
