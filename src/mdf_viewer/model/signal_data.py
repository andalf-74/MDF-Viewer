"""SignalData — raw timestamps and sample values for a single signal.

Pure data: holds only numeric arrays. No UI, no metadata, no plotting concepts.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True, slots=True)
class SignalData:
    """Raw measurement data: timestamps paired with sample values.

    ``timestamps`` and ``samples`` must have the same length.
    """

    timestamps: np.ndarray
    samples: np.ndarray

    def __post_init__(self) -> None:
        if self.timestamps.shape[0] != self.samples.shape[0]:
            raise ValueError(
                "timestamps and samples must have equal length "
                f"({self.timestamps.shape[0]} != {self.samples.shape[0]})"
            )

    @property
    def sample_count(self) -> int:
        return int(self.samples.shape[0])
