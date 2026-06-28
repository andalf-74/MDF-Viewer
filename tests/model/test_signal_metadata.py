"""Tests for SignalMetadata."""

from __future__ import annotations

from mdf_viewer.model.signal_metadata import SignalMetadata


def test_group_name_defaults_to_empty() -> None:
    meta = SignalMetadata(name="Speed")
    assert meta.group_name == ""


def test_group_name_stored() -> None:
    meta = SignalMetadata(name="Speed", group_name="Engine")
    assert meta.group_name == "Engine"


def test_all_other_defaults_unaffected_by_group_name() -> None:
    meta = SignalMetadata(name="RPM", group_name="Drivetrain")
    assert meta.unit == ""
    assert meta.group_index is None
    assert meta.channel_index is None
    assert meta.is_integer is False
