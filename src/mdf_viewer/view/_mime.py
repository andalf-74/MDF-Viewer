"""MIME types and payload encoding shared by drag/drop sites across the view
layer:

- SIGNAL_MIME_TYPE — the Signal Browser (source) dragging onto PlotStripe or
  ActiveSignalsTable (targets). The payload is a flat list of
  (measurement_index, group_index, channel_index) triples — the Signal
  Browser's unified cross-measurement list (#103) means one drag/multi-
  selection can legally span rows from different measurements, so each
  item carries its own measurement_index rather than one shared index for
  the whole payload.
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


def encode_signal_payload(items: list[tuple[int, int, int]]) -> bytes:
    """Encode a drag payload: (measurement_index, group_index, channel_index) triples."""
    return json.dumps({
        "items": [[mi, gi, ci] for mi, gi, ci in items],
    }).encode()


def decode_signal_payload(data: bytes) -> list[tuple[int, int, int]]:
    """Decode bytes produced by encode_signal_payload() back to a list of triples."""
    obj = json.loads(data)
    return [tuple(item) for item in obj["items"]]


def encode_row_payload(actives: list) -> bytes:
    """Encode a row-move drag payload: id() of each dragged ActiveSignal."""
    return json.dumps([id(a) for a in actives]).encode()


def decode_row_payload(data: bytes) -> set[int]:
    """Decode bytes produced by encode_row_payload() back to a set of ids."""
    return set(json.loads(data))
