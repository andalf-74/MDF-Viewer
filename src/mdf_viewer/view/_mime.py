"""MIME types and payload encoding shared by drag/drop sites across the view
layer:

- SIGNAL_MIME_TYPE — the Signal Browser (source) dragging onto PlotStripe or
  ActiveSignalsTable (targets). The payload identifies which loaded
  measurement (#101) a drag's (group_index, channel_index) pairs belong to —
  a drag always originates from a single Signal Browser tree, so one
  measurement_index covers the whole payload.
- ROW_MIME_TYPE — ActiveSignalsTable's own already-active signals (source)
  dragging onto another AST segment or a PlotStripe's plot area (targets,
  #116). The payload is just each dragged ActiveSignal's id(), resolved back
  to the actual object by whichever widget receives the drop (same process,
  so the ids stay valid for the drag's lifetime).
"""

from __future__ import annotations

import json

SIGNAL_MIME_TYPE = "application/x-mdf-viewer-signals"
ROW_MIME_TYPE = "application/x-mdf-viewer-active-signal-move"


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


def encode_row_payload(actives: list) -> bytes:
    """Encode a row-move drag payload: id() of each dragged ActiveSignal."""
    return json.dumps([id(a) for a in actives]).encode()


def decode_row_payload(data: bytes) -> set[int]:
    """Decode bytes produced by encode_row_payload() back to a set of ids."""
    return set(json.loads(data))
