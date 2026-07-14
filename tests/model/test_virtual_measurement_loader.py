"""Tests for VirtualMeasurementLoader (#147)."""

from __future__ import annotations

import numpy as np
import pytest

from mdf_viewer.errors import MdfLoadError
from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.model.virtual_measurement_loader import VirtualMeasurementLoader
from mdf_viewer.model.virtual_signal import VirtualSignal


def _signal(name: str, value: float = 1.0) -> VirtualSignal:
    def resolver():
        return (
            SignalData(timestamps=np.array([0.0, 1.0]), samples=np.array([value, value])),
            SignalMetadata(name=name),
        )

    return VirtualSignal(name=name, resolver=resolver, template=SignalMetadata(name=name, unit="V"))


def test_path_is_always_none() -> None:
    assert VirtualMeasurementLoader(owner_plugin="p").path is None


def test_is_open_is_always_true() -> None:
    assert VirtualMeasurementLoader(owner_plugin="p").is_open


def test_close_is_a_no_op() -> None:
    loader = VirtualMeasurementLoader(owner_plugin="p")
    loader.close()  # should not raise
    assert loader.is_open


@pytest.mark.requirement("REQ-VMEAS-130")
def test_channel_tree_holds_only_attached_virtual_signals() -> None:
    loader = VirtualMeasurementLoader(owner_plugin="my_plugin")
    loader.attach(_signal("a"))
    loader.attach(_signal("b"))

    groups = loader.channel_tree()

    assert len(groups) == 1
    assert groups[0].name == "my_plugin"
    assert [ch.name for ch in groups[0].channels] == ["a", "b"]


def test_channel_tree_patches_group_and_channel_index() -> None:
    loader = VirtualMeasurementLoader(owner_plugin="p")
    loader.attach(_signal("a"))
    loader.attach(_signal("b"))

    channels = loader.channel_tree()[0].channels

    assert (channels[0].group_index, channels[0].channel_index) == (0, 0)
    assert (channels[1].group_index, channels[1].channel_index) == (0, 1)


def test_channel_tree_preserves_template_fields() -> None:
    loader = VirtualMeasurementLoader(owner_plugin="p")
    loader.attach(_signal("a"))

    assert loader.channel_tree()[0].channels[0].unit == "V"


@pytest.mark.requirement("REQ-VMEAS-140")
def test_load_signal_calls_resolver_and_patches_metadata_indices() -> None:
    loader = VirtualMeasurementLoader(owner_plugin="p")
    loader.attach(_signal("a", value=3.0))
    loader.attach(_signal("b", value=5.0))

    data, meta = loader.load_signal(0, 1)

    assert data.samples.tolist() == [5.0, 5.0]
    assert (meta.group_index, meta.channel_index) == (0, 1)


@pytest.mark.requirement("REQ-VMEAS-150")
def test_load_signal_wraps_resolver_exception_in_mdf_load_error() -> None:
    def raising_resolver():
        raise ValueError("boom")

    loader = VirtualMeasurementLoader(owner_plugin="p")
    loader.attach(VirtualSignal(name="a", resolver=raising_resolver, template=SignalMetadata(name="a")))

    with pytest.raises(MdfLoadError, match="boom"):
        loader.load_signal(0, 0)


def test_find_signal_by_name_exact_match() -> None:
    loader = VirtualMeasurementLoader(owner_plugin="p")
    loader.attach(_signal("a"))
    loader.attach(_signal("b"))

    result = loader.find_signal_by_name("b")

    assert [ch.name for ch in result] == ["b"]


def test_find_signal_by_name_no_match_returns_empty() -> None:
    loader = VirtualMeasurementLoader(owner_plugin="p")
    loader.attach(_signal("a"))

    assert loader.find_signal_by_name("nonexistent") == []


def test_find_similar_signal_by_name_matches_shared_prefix() -> None:
    loader = VirtualMeasurementLoader(owner_plugin="p")
    loader.attach(_signal(r"Group\ETKC:1"))
    loader.attach(_signal(r"Group\XCP:1"))

    result = loader.find_similar_signal_by_name(r"Group\ETKC:1")

    assert [ch.name for ch in result] == [r"Group\XCP:1"]


def test_find_similar_signal_by_name_no_backslash_returns_empty() -> None:
    loader = VirtualMeasurementLoader(owner_plugin="p")
    loader.attach(_signal("plain"))

    assert loader.find_similar_signal_by_name("plain") == []


def test_measurement_info_has_empty_file_name() -> None:
    info = VirtualMeasurementLoader(owner_plugin="p").measurement_info()
    assert info.file_name == ""
