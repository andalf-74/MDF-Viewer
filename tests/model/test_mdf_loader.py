"""Tests for MdfLoader."""

from __future__ import annotations

from pathlib import Path

import asammdf
import numpy as np
import pytest

from mdf_viewer.model.mdf_loader import ChannelGroupInfo, MdfLoadError, MdfLoader
from mdf_viewer.model.measurement import MeasurementInfo
from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_mdf4(path: Path) -> None:
    """Create a minimal MDF4 file with two numeric signals in one group."""
    t = np.linspace(0.0, 1.0, 101)
    mdf = asammdf.MDF(version="4.10")
    mdf.append(
        [
            asammdf.Signal(
                samples=np.sin(2 * np.pi * t),
                timestamps=t,
                name="sin",
                unit="V",
                comment="sine wave",
            ),
            asammdf.Signal(
                samples=np.cos(2 * np.pi * t),
                timestamps=t,
                name="cos",
                unit="A",
                comment="cosine wave",
            ),
            asammdf.Signal(
                samples=np.arange(101, dtype=np.uint8) % 9,
                timestamps=t,
                name="gear",
                unit="",
            ),
        ]
    )
    mdf.save(str(path), overwrite=True)
    mdf.close()


@pytest.fixture()
def mdf4_path(tmp_path: Path) -> Path:
    p = tmp_path / "test.mf4"
    _make_mdf4(p)
    return p


@pytest.fixture()
def loader(mdf4_path: Path) -> MdfLoader:
    ldr = MdfLoader()
    ldr.open(mdf4_path)
    yield ldr
    ldr.close()


# ---------------------------------------------------------------------------
# open / close / is_open
# ---------------------------------------------------------------------------

def test_open_valid_file(mdf4_path: Path) -> None:
    ldr = MdfLoader()
    ldr.open(mdf4_path)
    assert ldr.is_open
    ldr.close()


def test_close_sets_not_open(mdf4_path: Path) -> None:
    ldr = MdfLoader()
    ldr.open(mdf4_path)
    ldr.close()
    assert not ldr.is_open


def test_open_nonexistent_raises(tmp_path: Path) -> None:
    ldr = MdfLoader()
    with pytest.raises(MdfLoadError):
        ldr.open(tmp_path / "no_such_file.mf4")


def test_open_invalid_file_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.mf4"
    bad.write_bytes(b"this is not an MDF file at all")
    ldr = MdfLoader()
    with pytest.raises(MdfLoadError):
        ldr.open(bad)


def test_open_replaces_previous_file(mdf4_path: Path, tmp_path: Path) -> None:
    second = tmp_path / "second.mf4"
    _make_mdf4(second)
    ldr = MdfLoader()
    ldr.open(mdf4_path)
    ldr.open(second)  # should not raise; closes old file first
    assert ldr.is_open
    ldr.close()


def test_close_when_not_open_is_noop() -> None:
    MdfLoader().close()  # must not raise


# ---------------------------------------------------------------------------
# Guard: methods require an open file
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "method",
    ["measurement_info", "channel_tree"],
)
def test_requires_open(method: str) -> None:
    ldr = MdfLoader()
    with pytest.raises(MdfLoadError, match="No file is open"):
        getattr(ldr, method)()


def test_load_signal_requires_open() -> None:
    ldr = MdfLoader()
    with pytest.raises(MdfLoadError, match="No file is open"):
        ldr.load_signal(0, 1)


# ---------------------------------------------------------------------------
# measurement_info
# ---------------------------------------------------------------------------

def test_measurement_info_returns_measurement_info(loader: MdfLoader) -> None:
    info = loader.measurement_info()
    assert isinstance(info, MeasurementInfo)


def test_measurement_info_file_name(loader: MdfLoader, mdf4_path: Path) -> None:
    assert loader.measurement_info().file_name == mdf4_path.name


def test_measurement_info_version(loader: MdfLoader) -> None:
    assert "4" in loader.measurement_info().mdf_version


def test_measurement_info_duration(loader: MdfLoader) -> None:
    info = loader.measurement_info()
    assert info.duration_s is not None
    assert abs(info.duration_s - 1.0) < 0.05


def test_measurement_info_recorded_at_nonempty(loader: MdfLoader) -> None:
    info = loader.measurement_info()
    assert info.recorded_at != ""


# ---------------------------------------------------------------------------
# channel_tree
# ---------------------------------------------------------------------------

def test_channel_tree_returns_list(loader: MdfLoader) -> None:
    tree = loader.channel_tree()
    assert isinstance(tree, list)
    assert len(tree) > 0


def test_channel_tree_group_type(loader: MdfLoader) -> None:
    for group in loader.channel_tree():
        assert isinstance(group, ChannelGroupInfo)


def test_channel_tree_has_sin_and_cos(loader: MdfLoader) -> None:
    all_names = {
        ch.name
        for group in loader.channel_tree()
        for ch in group.channels
    }
    assert "sin" in all_names
    assert "cos" in all_names


def test_channel_tree_metadata_populated(loader: MdfLoader) -> None:
    sin_meta = next(
        ch
        for group in loader.channel_tree()
        for ch in group.channels
        if ch.name == "sin"
    )
    assert sin_meta.unit == "V"
    assert sin_meta.comment == "sine wave"
    assert sin_meta.group_index is not None
    assert sin_meta.channel_index is not None


def test_channel_tree_indices_are_consistent(loader: MdfLoader) -> None:
    for group in loader.channel_tree():
        assert group.index >= 0
        for ch in group.channels:
            assert ch.group_index == group.index
            assert ch.channel_index is not None


# ---------------------------------------------------------------------------
# load_signal
# ---------------------------------------------------------------------------

def _find_channel_location(loader: MdfLoader, name: str) -> tuple[int, int]:
    for group in loader.channel_tree():
        for ch in group.channels:
            if ch.name == name:
                return ch.group_index, ch.channel_index
    raise KeyError(name)


def test_load_signal_returns_tuple(loader: MdfLoader) -> None:
    gi, ci = _find_channel_location(loader, "sin")
    result = loader.load_signal(gi, ci)
    assert len(result) == 2
    data, meta = result
    assert isinstance(data, SignalData)
    assert isinstance(meta, SignalMetadata)


def test_load_signal_correct_sample_count(loader: MdfLoader) -> None:
    gi, ci = _find_channel_location(loader, "sin")
    data, meta = loader.load_signal(gi, ci)
    assert data.sample_count == 101
    assert meta.sample_count == 101


def test_load_signal_timestamps_monotonic(loader: MdfLoader) -> None:
    gi, ci = _find_channel_location(loader, "sin")
    data, _ = loader.load_signal(gi, ci)
    assert np.all(np.diff(data.timestamps) > 0)


def test_load_signal_samples_match_sin(loader: MdfLoader) -> None:
    gi, ci = _find_channel_location(loader, "sin")
    data, _ = loader.load_signal(gi, ci)
    expected = np.sin(2 * np.pi * data.timestamps)
    np.testing.assert_allclose(data.samples, expected, atol=1e-6)


def test_load_signal_metadata_name_and_unit(loader: MdfLoader) -> None:
    gi, ci = _find_channel_location(loader, "cos")
    _, meta = loader.load_signal(gi, ci)
    assert meta.name == "cos"
    assert meta.unit == "A"


def test_load_signal_data_type_populated(loader: MdfLoader) -> None:
    gi, ci = _find_channel_location(loader, "sin")
    _, meta = loader.load_signal(gi, ci)
    assert meta.data_type != ""


def test_load_signal_float_is_not_integer(loader: MdfLoader) -> None:
    gi, ci = _find_channel_location(loader, "sin")
    _, meta = loader.load_signal(gi, ci)
    # sin samples are float64 in the test fixture
    assert not meta.is_integer


def test_load_signal_min_max(loader: MdfLoader) -> None:
    gi, ci = _find_channel_location(loader, "sin")
    _, meta = loader.load_signal(gi, ci)
    assert meta.min_value is not None
    assert meta.max_value is not None
    assert meta.min_value < 0
    assert meta.max_value > 0
    assert meta.max_value <= 1.0 + 1e-9
    assert meta.min_value >= -1.0 - 1e-9


def test_load_signal_integer_dtype_sets_is_integer(loader: MdfLoader) -> None:
    gi, ci = _find_channel_location(loader, "gear")
    _, meta = loader.load_signal(gi, ci)
    assert meta.is_integer
    assert meta.data_type == "uint8"


def test_load_signal_invalid_index_raises(loader: MdfLoader) -> None:
    with pytest.raises(MdfLoadError):
        loader.load_signal(999, 0)
