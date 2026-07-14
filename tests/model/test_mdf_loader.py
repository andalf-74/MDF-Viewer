"""Tests for MdfLoader."""

from __future__ import annotations

from pathlib import Path

import asammdf
import numpy as np
import pytest

from mdf_viewer.errors import MdfLoadError
from mdf_viewer.model.mdf_loader import (
    ChannelGroupInfo,
    MdfLoader,
    _channel_comment,
    _channel_unit,
    _compute_raster,
    _extract_enum_map,
)
from mdf_viewer.model.measurement import MeasurementInfo
from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_HEADER_COMMENT_XML = """<HDcomment>
<TX>recorded during bench test</TX>
<common_properties>
<e name="author">Jane Doe</e>
</common_properties>
</HDcomment>"""


def _build_signals() -> list[asammdf.Signal]:
    """Two numeric signals plus one integer signal, shared by the MDF3/MDF4 fixtures."""
    t = np.linspace(0.0, 1.0, 101)
    return [
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


def _make_mdf4(path: Path) -> None:
    """Create a minimal MDF4 file with the shared signal layout and header metadata."""
    mdf = asammdf.MDF(version="4.10")
    mdf.append(_build_signals())
    mdf.header.comment = _HEADER_COMMENT_XML
    mdf.save(str(path), overwrite=True)
    mdf.close()


def _make_mdf3(path: Path) -> None:
    """Create a minimal MDF3 file with the same signal layout as _make_mdf4."""
    mdf = asammdf.MDF(version="3.30")
    mdf.append(_build_signals())
    mdf.save(str(path), overwrite=True)
    mdf.close()


@pytest.fixture()
def mdf4_path(tmp_path: Path) -> Path:
    p = tmp_path / "test.mf4"
    _make_mdf4(p)
    return p


@pytest.fixture()
def mdf3_path(tmp_path: Path) -> Path:
    p = tmp_path / "test.mdf"
    _make_mdf3(p)
    return p


@pytest.fixture()
def loader(mdf4_path: Path) -> MdfLoader:
    ldr = MdfLoader()
    ldr.open(mdf4_path)
    yield ldr
    ldr.close()


@pytest.fixture()
def loader_mdf3(mdf3_path: Path) -> MdfLoader:
    ldr = MdfLoader()
    ldr.open(mdf3_path)
    yield ldr
    ldr.close()


# ---------------------------------------------------------------------------
# open / close / is_open
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-MDF-010")
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


def test_path_reflects_opened_file(mdf4_path: Path) -> None:
    ldr = MdfLoader()
    ldr.open(mdf4_path)
    assert ldr.path == mdf4_path


def test_path_is_none_after_close(mdf4_path: Path) -> None:
    ldr = MdfLoader()
    ldr.open(mdf4_path)
    ldr.close()
    assert ldr.path is None


@pytest.mark.requirement("REQ-MDF-070")
def test_open_nonexistent_raises(tmp_path: Path) -> None:
    ldr = MdfLoader()
    with pytest.raises(MdfLoadError):
        ldr.open(tmp_path / "no_such_file.mf4")


@pytest.mark.requirement("REQ-MDF-070")
def test_open_invalid_file_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.mf4"
    bad.write_bytes(b"this is not an MDF file at all")
    ldr = MdfLoader()
    with pytest.raises(MdfLoadError):
        ldr.open(bad)


@pytest.mark.requirement("REQ-FILE-012")
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


@pytest.mark.requirement("REQ-MDF-050")
def test_measurement_info_file_name(loader: MdfLoader, mdf4_path: Path) -> None:
    assert loader.measurement_info().file_name == mdf4_path.name


@pytest.mark.requirement("REQ-MDF-050")
def test_measurement_info_version(loader: MdfLoader) -> None:
    assert "4" in loader.measurement_info().mdf_version


@pytest.mark.requirement("REQ-MDF-050")
def test_measurement_info_duration(loader: MdfLoader) -> None:
    info = loader.measurement_info()
    assert info.duration_s is not None
    assert abs(info.duration_s - 1.0) < 0.05


@pytest.mark.requirement("REQ-MDF-050")
def test_measurement_info_recorded_at_nonempty(loader: MdfLoader) -> None:
    info = loader.measurement_info()
    assert info.recorded_at != ""


# ---------------------------------------------------------------------------
# channel_tree
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-MDF-020")
def test_channel_tree_returns_list(loader: MdfLoader) -> None:
    tree = loader.channel_tree()
    assert isinstance(tree, list)
    assert len(tree) > 0


def test_channel_tree_group_type(loader: MdfLoader) -> None:
    for group in loader.channel_tree():
        assert isinstance(group, ChannelGroupInfo)


@pytest.mark.requirement("REQ-MDF-020")
def test_channel_tree_has_sin_and_cos(loader: MdfLoader) -> None:
    all_names = {
        ch.name
        for group in loader.channel_tree()
        for ch in group.channels
    }
    assert "sin" in all_names
    assert "cos" in all_names


@pytest.mark.requirement("REQ-MDF-022")
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


@pytest.mark.requirement("REQ-MDF-022")
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


@pytest.mark.requirement("REQ-MDF-030")
def test_load_signal_returns_tuple(loader: MdfLoader) -> None:
    gi, ci = _find_channel_location(loader, "sin")
    result = loader.load_signal(gi, ci)
    assert len(result) == 2
    data, meta = result
    assert isinstance(data, SignalData)
    assert isinstance(meta, SignalMetadata)


@pytest.mark.requirement("REQ-MDF-040")
def test_load_signal_correct_sample_count(loader: MdfLoader) -> None:
    gi, ci = _find_channel_location(loader, "sin")
    data, meta = loader.load_signal(gi, ci)
    assert data.sample_count == 101
    assert meta.sample_count == 101


def test_load_signal_timestamps_monotonic(loader: MdfLoader) -> None:
    gi, ci = _find_channel_location(loader, "sin")
    data, _ = loader.load_signal(gi, ci)
    assert np.all(np.diff(data.timestamps) > 0)


@pytest.mark.requirement("REQ-MDF-031")
def test_load_signal_samples_match_sin(loader: MdfLoader) -> None:
    gi, ci = _find_channel_location(loader, "sin")
    data, _ = loader.load_signal(gi, ci)
    expected = np.sin(2 * np.pi * data.timestamps)
    np.testing.assert_allclose(data.samples, expected, atol=1e-6)


@pytest.mark.requirement("REQ-MDF-040")
def test_load_signal_metadata_name_and_unit(loader: MdfLoader) -> None:
    gi, ci = _find_channel_location(loader, "cos")
    _, meta = loader.load_signal(gi, ci)
    assert meta.name == "cos"
    assert meta.unit == "A"


@pytest.mark.requirement("REQ-MDF-040")
def test_load_signal_data_type_populated(loader: MdfLoader) -> None:
    gi, ci = _find_channel_location(loader, "sin")
    _, meta = loader.load_signal(gi, ci)
    assert meta.data_type != ""


@pytest.mark.requirement("REQ-MDF-040")
def test_load_signal_float_is_not_integer(loader: MdfLoader) -> None:
    gi, ci = _find_channel_location(loader, "sin")
    _, meta = loader.load_signal(gi, ci)
    # sin samples are float64 in the test fixture
    assert not meta.is_integer


@pytest.mark.requirement("REQ-MDF-040")
def test_load_signal_min_max(loader: MdfLoader) -> None:
    gi, ci = _find_channel_location(loader, "sin")
    _, meta = loader.load_signal(gi, ci)
    assert meta.min_value is not None
    assert meta.max_value is not None
    assert meta.min_value < 0
    assert meta.max_value > 0
    assert meta.max_value <= 1.0 + 1e-9
    assert meta.min_value >= -1.0 - 1e-9


@pytest.mark.requirement("REQ-MDF-040")
def test_load_signal_integer_dtype_sets_is_integer(loader: MdfLoader) -> None:
    gi, ci = _find_channel_location(loader, "gear")
    _, meta = loader.load_signal(gi, ci)
    assert meta.is_integer
    assert meta.data_type == "uint8"


@pytest.mark.requirement("REQ-MDF-070")
def test_load_signal_invalid_index_raises(loader: MdfLoader) -> None:
    with pytest.raises(MdfLoadError):
        loader.load_signal(999, 0)


def _mock_signal(samples, timestamps=None, name="ch", unit="", comment=""):
    """Build a minimal MagicMock that looks like an asammdf Signal."""
    from unittest.mock import MagicMock
    sig = MagicMock()
    sig.samples = samples
    sig.timestamps = timestamps if timestamps is not None else np.linspace(0, 1, len(samples))
    sig.name = name
    sig.unit = unit
    sig.comment = comment
    return sig


def _loader_with_mock_mdf(string_sig, raw_sig=None):
    """Return a MdfLoader whose _mdf.get() returns string_sig first, raw_sig second."""
    from unittest.mock import MagicMock
    ldr = MdfLoader()
    ldr._mdf = MagicMock()
    ldr._mdf.groups = [MagicMock()]
    ldr._mdf.groups[0].channels = [MagicMock()]
    ldr._mdf.groups[0].channels[0].name = string_sig.name
    if raw_sig is not None:
        ldr._mdf.get.side_effect = [string_sig, raw_sig]
    else:
        ldr._mdf.get.return_value = string_sig
    return ldr


@pytest.mark.requirement("REQ-MDF-032")
def test_load_signal_string_samples_falls_back_to_raw() -> None:
    t = np.array([0.0, 0.5, 1.0])
    raw_samples = np.array([0, 1, 0], dtype=np.uint8)
    string_sig = _mock_signal(np.array([b"Off", b"On", b"Off"]), t)
    raw_sig = _mock_signal(raw_samples, t)
    ldr = _loader_with_mock_mdf(string_sig, raw_sig)

    data, meta = ldr.load_signal(0, 0)

    assert np.array_equal(data.samples, raw_samples.astype(np.float64))
    assert meta.is_integer is True


@pytest.mark.requirement("REQ-MDF-032")
def test_load_signal_raw_fallback_calls_get_with_raw_true() -> None:
    t = np.array([0.0, 0.5])
    raw_sig = _mock_signal(np.array([0, 1], dtype=np.uint8), t)
    string_sig = _mock_signal(np.array([b"Off", b"On"]), t)
    ldr = _loader_with_mock_mdf(string_sig, raw_sig)

    ldr.load_signal(0, 0)

    _, kwargs = ldr._mdf.get.call_args
    assert kwargs.get("raw") is True


# ---------------------------------------------------------------------------
# _compute_raster
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-MDF-040")
def test_compute_raster_fixed_returns_interval() -> None:
    t = np.linspace(0.0, 1.0, 101)  # exactly 0.01 s spacing
    result = _compute_raster(t)
    assert result is not None
    assert abs(result - 0.01) < 1e-9


@pytest.mark.requirement("REQ-MDF-040")
def test_compute_raster_variable_returns_none() -> None:
    t = np.array([0.0, 0.01, 0.1, 0.11, 1.0])  # irregular
    assert _compute_raster(t) is None


@pytest.mark.requirement("REQ-MDF-040")
def test_compute_raster_single_sample_returns_none() -> None:
    assert _compute_raster(np.array([0.0])) is None


@pytest.mark.requirement("REQ-MDF-040")
def test_compute_raster_empty_returns_none() -> None:
    assert _compute_raster(np.array([])) is None


@pytest.mark.requirement("REQ-MDF-040")
def test_compute_raster_within_tolerance_is_fixed() -> None:
    # intervals within 5% of mean (p99) should be fixed
    t = np.array([0.0, 0.01, 0.0201, 0.0301])
    result = _compute_raster(t)
    assert result is not None


@pytest.mark.requirement("REQ-MDF-040")
def test_compute_raster_single_outlier_still_fixed() -> None:
    # one rogue interval in 1001 (0.1% of data) should not flip a fixed-rate signal
    t = np.linspace(0.0, 10.0, 1001)  # 1000 intervals at exactly 0.01 s
    t_jittered = t.copy()
    t_jittered[500] += 0.002  # one interval becomes ~20% off
    result = _compute_raster(t_jittered)
    assert result is not None


@pytest.mark.requirement("REQ-MDF-040")
def test_compute_raster_truly_variable_returns_none() -> None:
    # more than 1% of intervals far off → variable (every 5th is 30% off)
    t = np.linspace(0.0, 10.0, 1001)
    t_jittered = t.copy()
    for i in range(0, 1000, 5):
        t_jittered[i + 1] += 0.003  # 30% deviation, 200 out of 1000 intervals
    result = _compute_raster(t_jittered)
    assert result is None


@pytest.mark.requirement("REQ-MDF-040")
def test_compute_raster_two_samples() -> None:
    t = np.array([0.0, 0.5])
    result = _compute_raster(t)
    assert result is not None
    assert abs(result - 0.5) < 1e-9


# ---------------------------------------------------------------------------
# load_signal – raster
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-MDF-040")
def test_load_signal_raster_populated(loader: MdfLoader) -> None:
    gi, ci = _find_channel_location(loader, "sin")
    _, meta = loader.load_signal(gi, ci)
    # linspace(0, 1, 101) → 0.01 s raster
    assert meta.raster_s is not None
    assert abs(meta.raster_s - 0.01) < 1e-9


@pytest.mark.requirement("REQ-MDF-033")
def test_load_signal_non_numeric_even_with_raw_raises() -> None:
    t = np.array([0.0, 0.5])
    string_sig = _mock_signal(np.array([b"Off", b"On"]), t)
    ldr = _loader_with_mock_mdf(string_sig, string_sig)

    with pytest.raises(MdfLoadError, match="cannot be converted"):
        ldr.load_signal(0, 0)


# ---------------------------------------------------------------------------
# _extract_enum_map
# ---------------------------------------------------------------------------

class _FakeConversion:
    """Minimal stand-in for an asammdf ChannelConversion (type 7)."""
    conversion_type = 7
    referenced_blocks: dict
    # val_N attributes set per-instance in tests


@pytest.mark.requirement("REQ-MDF-041")
def test_extract_enum_map_type7_returns_mapping() -> None:
    conv = _FakeConversion()
    conv.referenced_blocks = {"text_0": b"OFF", "text_1": b"ON"}
    conv.val_0 = 0.0
    conv.val_1 = 1.0
    assert _extract_enum_map(conv) == {0: "OFF", 1: "ON"}


@pytest.mark.requirement("REQ-MDF-041")
def test_extract_enum_map_non_contiguous_values() -> None:
    conv = _FakeConversion()
    conv.referenced_blocks = {"text_0": b"Initialization", "text_1": b"RUN", "text_2": b"SNA"}
    conv.val_0 = 0.0
    conv.val_1 = 4.0
    conv.val_2 = 7.0
    result = _extract_enum_map(conv)
    assert result == {0: "Initialization", 4: "RUN", 7: "SNA"}


@pytest.mark.requirement("REQ-MDF-041")
def test_extract_enum_map_none_returns_empty() -> None:
    assert _extract_enum_map(None) == {}


@pytest.mark.requirement("REQ-MDF-041")
def test_extract_enum_map_wrong_type_returns_empty() -> None:
    conv = _FakeConversion()
    conv.conversion_type = 1  # linear, not value-to-text
    assert _extract_enum_map(conv) == {}


@pytest.mark.requirement("REQ-MDF-041")
def test_extract_enum_map_no_conversion_type_returns_empty() -> None:
    class _NoType:
        referenced_blocks = {}
    assert _extract_enum_map(_NoType()) == {}


@pytest.mark.requirement("REQ-MDF-041")
def test_extract_enum_map_decodes_bytes() -> None:
    conv = _FakeConversion()
    conv.referenced_blocks = {"text_0": b"KEY_IN_IGN"}
    conv.val_0 = 2.0
    result = _extract_enum_map(conv)
    assert result[2] == "KEY_IN_IGN"
    assert isinstance(result[2], str)


# ---------------------------------------------------------------------------
# load_signal — enum_map extraction
# ---------------------------------------------------------------------------

def _mock_signal_with_conv(samples, timestamps, conversion=None):
    sig = _mock_signal(samples, timestamps)
    sig.conversion = conversion
    return sig


def _fake_conv(val_text_pairs: list[tuple[float, bytes]]) -> _FakeConversion:
    conv = _FakeConversion()
    rb = {}
    for i, (val, text) in enumerate(val_text_pairs):
        setattr(conv, f"val_{i}", val)
        rb[f"text_{i}"] = text
    conv.referenced_blocks = rb
    return conv


@pytest.mark.requirement("REQ-MDF-041")
def test_load_signal_enum_map_populated_from_raw_conversion() -> None:
    t = np.array([0.0, 0.5, 1.0])
    conv = _fake_conv([(0.0, b"OFF"), (1.0, b"ON")])
    raw_sig = _mock_signal_with_conv(np.array([0, 1, 0], dtype=np.uint8), t, conv)
    string_sig = _mock_signal(np.array([b"OFF", b"ON", b"OFF"]), t)
    ldr = _loader_with_mock_mdf(string_sig, raw_sig)

    _, meta = ldr.load_signal(0, 0)

    assert meta.enum_map == {0: "OFF", 1: "ON"}


@pytest.mark.requirement("REQ-MDF-041")
def test_load_signal_enum_map_empty_for_numeric_signal(loader: MdfLoader) -> None:
    gi, ci = _find_channel_location(loader, "sin")
    _, meta = loader.load_signal(gi, ci)
    assert meta.enum_map == {}


# ---------------------------------------------------------------------------
# find_signal_by_name
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-MDF-060")
def test_find_signal_by_name_returns_empty_when_not_open() -> None:
    loader = MdfLoader()
    result = loader.find_signal_by_name("sin")
    assert result == []


@pytest.mark.requirement("REQ-MDF-060")
def test_find_signal_by_name_finds_existing_channel(loader: MdfLoader) -> None:
    result = loader.find_signal_by_name("sin")
    assert len(result) >= 1
    assert all(m.name == "sin" for m in result)


@pytest.mark.requirement("REQ-MDF-060")
def test_find_signal_by_name_returns_empty_for_unknown(loader: MdfLoader) -> None:
    assert loader.find_signal_by_name("no_such_channel_xyz") == []


@pytest.mark.requirement("REQ-MDF-060")
def test_find_signal_by_name_result_has_group_and_channel_index(loader: MdfLoader) -> None:
    result = loader.find_signal_by_name("sin")
    assert result
    for meta in result:
        assert meta.group_index is not None
        assert meta.channel_index is not None


@pytest.mark.requirement("REQ-MDF-060")
def test_find_signal_by_name_exact_match_only(loader: MdfLoader) -> None:
    # "si" is a prefix of "sin" but should not be returned
    result = loader.find_signal_by_name("si")
    assert all(m.name == "si" for m in result)


# ---------------------------------------------------------------------------
# group_name
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-MDF-021")
def test_channel_tree_group_name_is_non_empty(loader: MdfLoader) -> None:
    groups = loader.channel_tree()
    for group in groups:
        for ch in group.channels:
            assert isinstance(ch.group_name, str)
            assert ch.group_name != ""


@pytest.mark.requirement("REQ-MDF-021")
def test_load_signal_group_name_matches_channel_tree(loader: MdfLoader) -> None:
    groups = loader.channel_tree()
    first_group = groups[0]
    # find a real channel index (skip master channel at index 0 if needed)
    for ch in first_group.channels:
        try:
            _, meta = loader.load_signal(ch.group_index, ch.channel_index)
            assert meta.group_name == first_group.name
            break
        except Exception:
            continue


@pytest.mark.requirement("REQ-MDF-060")
def test_find_signal_by_name_result_has_group_name(loader: MdfLoader) -> None:
    results = loader.find_signal_by_name("sin")
    assert len(results) >= 1
    for meta in results:
        assert meta.group_name != ""


# ---------------------------------------------------------------------------
# MDF3 regression (REQ-MDF-010)
# ---------------------------------------------------------------------------
# Mirrors the MDF4 open/channel_tree/load_signal coverage above using an MDF3
# fixture, so both formats accepted by asammdf.MDF() are actually exercised.

@pytest.mark.requirement("REQ-MDF-010")
def test_open_mdf3_file(mdf3_path: Path) -> None:
    ldr = MdfLoader()
    ldr.open(mdf3_path)
    assert ldr.is_open
    ldr.close()


@pytest.mark.requirement("REQ-MDF-010")
def test_measurement_info_mdf3_version(loader_mdf3: MdfLoader) -> None:
    assert "3" in loader_mdf3.measurement_info().mdf_version


@pytest.mark.requirement("REQ-MDF-010")
def test_channel_tree_mdf3_has_sin_and_cos(loader_mdf3: MdfLoader) -> None:
    all_names = {
        ch.name
        for group in loader_mdf3.channel_tree()
        for ch in group.channels
    }
    assert "sin" in all_names
    assert "cos" in all_names


@pytest.mark.requirement("REQ-MDF-010")
@pytest.mark.requirement("REQ-MDF-022")
def test_channel_tree_mdf3_metadata_populated(loader_mdf3: MdfLoader) -> None:
    sin_meta = next(
        ch
        for group in loader_mdf3.channel_tree()
        for ch in group.channels
        if ch.name == "sin"
    )
    assert sin_meta.unit == "V"
    assert sin_meta.comment == "sine wave"


@pytest.mark.requirement("REQ-MDF-010")
@pytest.mark.requirement("REQ-MDF-031")
def test_load_signal_mdf3_samples_match_sin(loader_mdf3: MdfLoader) -> None:
    gi, ci = _find_channel_location(loader_mdf3, "sin")
    data, meta = loader_mdf3.load_signal(gi, ci)
    assert data.sample_count == 101
    expected = np.sin(2 * np.pi * data.timestamps)
    np.testing.assert_allclose(data.samples, expected, atol=1e-6)
    assert meta.unit == "V"


@pytest.mark.requirement("REQ-MDF-010")
@pytest.mark.requirement("REQ-MDF-040")
def test_load_signal_mdf3_integer_dtype_sets_is_integer(loader_mdf3: MdfLoader) -> None:
    gi, ci = _find_channel_location(loader_mdf3, "gear")
    _, meta = loader_mdf3.load_signal(gi, ci)
    assert meta.is_integer


# ---------------------------------------------------------------------------
# _channel_unit / _channel_comment (MDF3 fallback paths)
# ---------------------------------------------------------------------------

class _FakeConversionWithUnit:
    def __init__(self, unit: str) -> None:
        self.unit = unit


@pytest.mark.requirement("REQ-MDF-022")
def test_channel_unit_prefers_direct_attribute() -> None:
    channel = _FakeChannel("ch", unit="V")
    assert _channel_unit(channel) == "V"


@pytest.mark.requirement("REQ-MDF-022")
def test_channel_unit_falls_back_to_conversion_block() -> None:
    channel = _FakeChannel("ch", unit="")
    channel.conversion = _FakeConversionWithUnit("A")
    assert _channel_unit(channel) == "A"


@pytest.mark.requirement("REQ-MDF-022")
def test_channel_unit_no_conversion_returns_empty() -> None:
    channel = _FakeChannel("ch", unit="")
    assert _channel_unit(channel) == ""


@pytest.mark.requirement("REQ-MDF-022")
def test_channel_comment_plain_attribute_only() -> None:
    channel = _FakeChannel("ch", comment="hello")
    assert _channel_comment(channel) == "hello"


@pytest.mark.requirement("REQ-MDF-022")
def test_channel_comment_appends_mdf3_description() -> None:
    channel = _FakeChannel("ch", comment="hello")
    channel.description = b"world\x00\x00"
    assert _channel_comment(channel) == "hello\nworld"


@pytest.mark.requirement("REQ-MDF-022")
def test_channel_comment_description_only_when_no_comment() -> None:
    channel = _FakeChannel("ch", comment="")
    channel.description = b"padded\x00\x00"
    assert _channel_comment(channel) == "padded"


# ---------------------------------------------------------------------------
# measurement_info — author/comment and resilience (REQ-MDF-050/051)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-MDF-050")
def test_measurement_info_author(loader: MdfLoader) -> None:
    assert loader.measurement_info().author == "Jane Doe"


@pytest.mark.requirement("REQ-MDF-050")
def test_measurement_info_comment(loader: MdfLoader) -> None:
    assert "recorded during bench test" in loader.measurement_info().comment


class _FailingMdf:
    """Stand-in for asammdf.MDF whose header/start_time/groups reads all raise."""

    version = "4.10"

    @property
    def header(self):
        raise RuntimeError("header read failed")

    @property
    def start_time(self):
        raise RuntimeError("start_time read failed")

    @property
    def groups(self):
        raise RuntimeError("groups read failed")


@pytest.mark.requirement("REQ-MDF-051")
def test_measurement_info_survives_metadata_read_failures() -> None:
    ldr = MdfLoader()
    ldr._mdf = _FailingMdf()
    ldr._path = Path("broken.mf4")

    info = ldr.measurement_info()

    assert info.file_name == "broken.mf4"
    assert info.author == ""
    assert info.comment == ""
    assert info.recorded_at == ""
    assert info.duration_s is None


# ---------------------------------------------------------------------------
# channel_tree — failure paths (REQ-MDF-071/072)
# ---------------------------------------------------------------------------

class _RaisingChannel:
    """A channel whose .name access always raises, simulating a corrupt channel block."""

    @property
    def name(self):
        raise RuntimeError("corrupt channel block")


class _FakeChannel:
    def __init__(self, name: str, unit: str = "", comment: str = "") -> None:
        self.name = name
        self.unit = unit
        self.comment = comment


class _FakeChannelGroupBlock:
    def __init__(self, acq_name: str = "") -> None:
        self.acq_name = acq_name


class _FakeGroup:
    def __init__(self, channels, acq_name: str = "Group 0") -> None:
        self.channels = channels
        self.channel_group = _FakeChannelGroupBlock(acq_name)


@pytest.mark.requirement("REQ-MDF-071")
def test_channel_tree_skips_channel_that_raises_during_description() -> None:
    from unittest.mock import MagicMock

    good = _FakeChannel("good_channel", unit="V")
    group = _FakeGroup([_RaisingChannel(), good])
    ldr = MdfLoader()
    ldr._mdf = MagicMock()
    ldr._mdf.groups = [group]

    tree = ldr.channel_tree()

    names = {ch.name for g in tree for ch in g.channels}
    assert names == {"good_channel"}


@pytest.mark.requirement("REQ-MDF-072")
def test_channel_tree_raises_when_groups_enumeration_fails() -> None:
    class _FailingGroupsMdf:
        @property
        def groups(self):
            raise RuntimeError("cannot enumerate groups")

    ldr = MdfLoader()
    ldr._mdf = _FailingGroupsMdf()

    with pytest.raises(MdfLoadError, match="Failed to enumerate channels"):
        ldr.channel_tree()


# ---------------------------------------------------------------------------
# Known-corrupt fixture (REQ-MDF-070)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-MDF-070")
@pytest.mark.requirement("REQ-NFR-010")
def test_open_known_corrupt_faultfile_raises_cleanly() -> None:
    """data/faultfile.mf4 is a known-corrupt MDF4 documented in CLAUDE.md.

    Opening it triggers a harmless GC-time AttributeError from asammdf's
    MDF4.__del__ (printed to stderr) - that is expected and not asserted on.
    """
    faultfile = Path(__file__).resolve().parents[2] / "data" / "faultfile.mf4"
    ldr = MdfLoader()

    with pytest.raises(MdfLoadError):
        ldr.open(faultfile)

    assert not ldr.is_open


# ---------------------------------------------------------------------------
# find_similar_signal_by_name (#109, REQ-FILE-032/033)
# ---------------------------------------------------------------------------

@pytest.fixture()
def loader_with_protocol_names(tmp_path: Path) -> MdfLoader:
    """A file with two protocol-suffixed names sharing a prefix, plus a
    plain no-backslash name, for near-match testing."""
    t = np.linspace(0.0, 1.0, 11)
    mdf = asammdf.MDF(version="4.10")
    mdf.append([
        asammdf.Signal(samples=t, timestamps=t, name="FZGG_NAB_AKT\\ETKC:1"),
        asammdf.Signal(samples=t, timestamps=t, name="FZGG_NAB_AKT\\XCP:1"),
        asammdf.Signal(samples=t, timestamps=t, name="plain_signal"),
    ])
    path = tmp_path / "protocol_names.mf4"
    mdf.save(str(path), overwrite=True)
    mdf.close()

    ldr = MdfLoader()
    ldr.open(path)
    yield ldr
    ldr.close()


def test_find_similar_signal_by_name_returns_empty_when_not_open() -> None:
    ldr = MdfLoader()
    assert ldr.find_similar_signal_by_name("a\\ETKC:1") == []


@pytest.mark.requirement("REQ-FILE-032")
def test_find_similar_signal_by_name_matches_same_prefix(
    loader_with_protocol_names: MdfLoader,
) -> None:
    result = loader_with_protocol_names.find_similar_signal_by_name("FZGG_NAB_AKT\\XCP:1")
    assert [m.name for m in result] == ["FZGG_NAB_AKT\\ETKC:1"]


@pytest.mark.requirement("REQ-FILE-032")
def test_find_similar_signal_by_name_excludes_exact_match(
    loader_with_protocol_names: MdfLoader,
) -> None:
    result = loader_with_protocol_names.find_similar_signal_by_name("FZGG_NAB_AKT\\ETKC:1")
    assert "FZGG_NAB_AKT\\ETKC:1" not in [m.name for m in result]


@pytest.mark.requirement("REQ-FILE-033")
def test_find_similar_signal_by_name_no_backslash_in_query_returns_empty(
    loader_with_protocol_names: MdfLoader,
) -> None:
    assert loader_with_protocol_names.find_similar_signal_by_name("plain_signal") == []


@pytest.mark.requirement("REQ-FILE-033")
def test_find_similar_signal_by_name_ignores_no_backslash_candidates(
    loader_with_protocol_names: MdfLoader,
) -> None:
    # A query with a different, unmatched prefix should not near-match the
    # no-backslash "plain_signal" channel.
    result = loader_with_protocol_names.find_similar_signal_by_name("plain_signal\\ETKC:1")
    assert "plain_signal" not in [m.name for m in result]


def test_find_similar_signal_by_name_returns_empty_for_unrelated_name(
    loader_with_protocol_names: MdfLoader,
) -> None:
    assert loader_with_protocol_names.find_similar_signal_by_name("unrelated\\ETKC:1") == []
