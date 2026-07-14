"""VirtualSignal — a plugin-contributed signal resolved lazily (#147).

Pure data: no UI knowledge. `resolver` is invoked only when the signal is
actually needed for display (REQ-VMEAS-140), never eagerly at creation —
so a future windowed/downsampled resolver can vary its return by requested
range without changing this contract's shape.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata


@dataclass(frozen=True, slots=True)
class VirtualSignal:
    """One plugin-contributed signal, not yet attached to any measurement."""

    name: str
    resolver: Callable[[], tuple[SignalData, SignalMetadata]]
    template: SignalMetadata
