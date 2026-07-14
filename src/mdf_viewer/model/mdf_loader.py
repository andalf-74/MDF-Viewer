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

from mdf_viewer.errors import MdfLoadError
from mdf_viewer.model.measurement import MeasurementInfo
from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata


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

    @property
    def path(self) -> Path | None:
        return self._path

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
                            unit = _channel_unit(channel)
                        except Exception:
                            pass
                        try:
                            comment = _channel_comment(channel)
                        except Exception:
                            pass
                        channels.append(
                            SignalMetadata(
                                name=name,
                                unit=unit,
                                comment=comment,
                                group_index=gi,
                                channel_index=ci,
                                group_name=group_name,
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

    def find_signal_by_name(self, name: str) -> list[SignalMetadata]:
        """Return all channels whose name exactly matches *name*, across all groups.

        Returns an empty list when the file has no such channel or no file is open.
        """
        if not self.is_open:
            return []
        result: list[SignalMetadata] = []
        try:
            for group in self.channel_tree():
                for ch in group.channels:
                    if ch.name == name:
                        result.append(ch)
        except Exception:
            pass
        return result

    def find_similar_signal_by_name(self, name: str) -> list[SignalMetadata]:
        """Return channels whose name matches *name* up to its own last "\\",
        differing only in what follows it (REQ-FILE-032) — covers a signal
        recorded under a different protocol/source, e.g. "...\\ETKC:1" vs
        "...\\XCP:1". A name with no "\\" has no such prefix and never
        matches, on either side of the comparison (REQ-FILE-033). Excludes
        exact matches, which find_signal_by_name already covers. Returns an
        empty list when the file has no such channel or no file is open.
        """
        if not self.is_open or "\\" not in name:
            return []
        prefix = name.rsplit("\\", 1)[0]
        result: list[SignalMetadata] = []
        try:
            for group in self.channel_tree():
                for ch in group.channels:
                    if ch.name == name or "\\" not in ch.name:
                        continue
                    if ch.name.rsplit("\\", 1)[0] == prefix:
                        result.append(ch)
        except Exception:
            pass
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
        except (ValueError, TypeError):
            # Samples are strings/enums — retry with raw (unconverted) values.
            try:
                sig = mdf.get(
                    channel_name, group=group_index, index=channel_index, raw=True
                )
                raw_dtype = np.asarray(sig.samples).dtype
                timestamps = np.asarray(sig.timestamps, dtype=np.float64)
                samples = np.asarray(sig.samples, dtype=np.float64)
            except (ValueError, TypeError) as exc:
                raise MdfLoadError(
                    f"Channel '{channel_name}' samples cannot be converted to "
                    f"numeric values: {exc}"
                ) from exc

        data = SignalData(timestamps=timestamps, samples=samples)
        enum_map = _extract_enum_map(getattr(sig, "conversion", None))

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
            group_name=_channel_group_name(mdf.groups[group_index], group_index),
            data_type=str(raw_dtype),
            is_integer=bool(np.issubdtype(raw_dtype, np.integer)),
            raster_s=_compute_raster(timestamps),
            enum_map=enum_map,
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

def _compute_raster(timestamps: np.ndarray) -> float | None:
    """Return the fixed raster in seconds, or None when variable or indeterminate."""
    if len(timestamps) < 2:
        return None
    intervals = np.diff(timestamps)
    mean = float(np.mean(intervals))
    if mean <= 0:
        return None
    if float(np.percentile(np.abs(intervals - mean) / mean, 99)) <= 0.05:
        return mean
    return None


def _channel_unit(channel) -> str:
    """Return the channel's unit.

    MDF4 channel blocks carry the unit directly. MDF3 channel blocks leave it
    empty and store it on the conversion block instead.
    """
    unit = str(getattr(channel, "unit", "") or "")
    if unit:
        return unit
    conversion = getattr(channel, "conversion", None)
    if conversion is not None:
        unit = str(getattr(conversion, "unit", "") or "")
    return unit


def _channel_comment(channel) -> str:
    """Return the channel's comment.

    MDF3 channel blocks additionally carry a fixed-size ``description`` field
    that asammdf appends to the free-text comment when reading a signal via
    ``mdf.get()``; replicate that here so channel_tree() output matches.
    """
    comment = str(getattr(channel, "comment", "") or "")
    description = getattr(channel, "description", None)
    if isinstance(description, bytes):
        description = description.decode("latin-1").strip(" \t\n\0")
    else:
        description = str(description) if description else ""
    if description:
        comment = f"{comment}\n{description}" if comment else description
    return comment


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


def _extract_enum_map(conversion) -> dict[int, str]:
    """Extract a value→label mapping from an asammdf ChannelConversion (type 7 only).

    Type 7 is MDF4 "value to text": val_0 maps to text_0, val_1 to text_1, etc.
    Returns an empty dict for any other conversion type or when conversion is None.
    """
    if conversion is None or getattr(conversion, "conversion_type", None) != 7:
        return {}
    result: dict[int, str] = {}
    rb = getattr(conversion, "referenced_blocks", {})
    i = 0
    while True:
        val = getattr(conversion, f"val_{i}", None)
        if val is None:
            break
        text = rb.get(f"text_{i}")
        if text is not None:
            label = text.decode("utf-8", errors="replace") if isinstance(text, bytes) else str(text)
            result[int(val)] = label
        i += 1
    return result


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
