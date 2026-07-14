"""Tests for VirtualSignal (#147)."""

from __future__ import annotations

import numpy as np

from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.model.virtual_signal import VirtualSignal


def test_resolver_is_not_called_at_construction() -> None:
    calls = []

    def resolver():
        calls.append(1)
        return SignalData(timestamps=np.array([0.0]), samples=np.array([1.0])), SignalMetadata(
            name="derived"
        )

    VirtualSignal(name="derived", resolver=resolver, template=SignalMetadata(name="derived"))
    assert calls == []


def test_resolver_runs_when_invoked() -> None:
    def resolver():
        return SignalData(timestamps=np.array([0.0]), samples=np.array([1.0])), SignalMetadata(
            name="derived"
        )

    signal = VirtualSignal(name="derived", resolver=resolver, template=SignalMetadata(name="derived"))
    data, meta = signal.resolver()
    assert data.samples.tolist() == [1.0]
    assert meta.name == "derived"
