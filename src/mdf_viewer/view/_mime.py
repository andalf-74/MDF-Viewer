"""MIME type and payload encoding shared by every SIGNAL_MIME_TYPE drag/drop
site: the Signal Browser (source), PlotStripe, and ActiveSignalsTable
(targets).

The payload identifies which loaded measurement (#101) a drag's
(group_index, channel_index) pairs belong to — a drag always originates
from a single Signal Browser tree, so one measurement_index covers the
whole payload.
"""

from __future__ import annotations

import json

SIGNAL_MIME_TYPE = "application/x-mdf-viewer-signals"


def encode_signal_payload(measurement_index: int, items: list[tuple[int, int]]) -> bytes:
    """Encode a drag payload: which measurement, and its (group_index, channel_index) pairs."""
    return json.dumps({
        "measurement_index": measurement_index,
        "items": [[gi, ci] for gi, ci in items],
    }).encode()


def decode_signal_payload(data: bytes) -> tuple[int, list[tuple[int, int]]]:
    """Decode bytes produced by encode_signal_payload() back to (measurement_index, items)."""
    obj = json.loads(data)
    items = [tuple(item) for item in obj["items"]]
    return obj["measurement_index"], items
