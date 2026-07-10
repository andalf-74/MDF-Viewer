"""Tests for the shared SIGNAL_MIME_TYPE (#101) and ROW_MIME_TYPE (#116)
payload encoding."""

from __future__ import annotations

from mdf_viewer.view._mime import (
    decode_row_payload,
    decode_signal_payload,
    encode_row_payload,
    encode_signal_payload,
)


def test_round_trip_single_item() -> None:
    data = encode_signal_payload(0, [(0, 1)])
    measurement_index, items = decode_signal_payload(data)
    assert measurement_index == 0
    assert items == [(0, 1)]


def test_round_trip_multiple_items() -> None:
    data = encode_signal_payload(2, [(0, 1), (1, 5), (3, 0)])
    measurement_index, items = decode_signal_payload(data)
    assert measurement_index == 2
    assert items == [(0, 1), (1, 5), (3, 0)]


def test_round_trip_empty_items() -> None:
    data = encode_signal_payload(1, [])
    measurement_index, items = decode_signal_payload(data)
    assert measurement_index == 1
    assert items == []


def test_row_payload_round_trip() -> None:
    a, b = object(), object()
    data = encode_row_payload([a, b])
    ids = decode_row_payload(data)
    assert ids == {id(a), id(b)}


def test_row_payload_round_trip_empty() -> None:
    data = encode_row_payload([])
    ids = decode_row_payload(data)
    assert ids == set()
