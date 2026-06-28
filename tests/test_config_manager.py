"""Tests for ConfigManager — save, load, and path resolution."""

from __future__ import annotations

from pathlib import Path

import pytest

from mdf_viewer.config_manager import CONFIG_FORMAT_VERSION, ConfigManager
from mdf_viewer.errors import ConfigLoadError
from mdf_viewer.model.viewer_config import SignalConfig, ViewerConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(measurement_path: str = "/data/test.mf4") -> ViewerConfig:
    sig = SignalConfig(
        name="Speed",
        group_name="Engine",
        color=(255, 85, 85),
        line_width=1,
        line_style="solid",
        display_mode="line",
        marker_shape="circle",
        step_mode=False,
        enum_display_table=True,
        enum_display_cursor=False,
        enum_display_yaxis=False,
    )
    return ViewerConfig(
        format_version=CONFIG_FORMAT_VERSION,
        measurement_path=measurement_path,
        signals=(sig,),
        x_range=(0.0, 10.0),
        y_ranges={"Speed": (0.0, 200.0)},
        shared_groups=(("Speed", "Torque"),),
        linked_groups=(),
        cursor_mode="ONE",
        cursor_positions=(3.5, 0.0),
        selected_signal="Speed",
    )


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------

def test_save_creates_file(tmp_path: Path) -> None:
    config = _make_config()
    path = tmp_path / "session.mvc"
    ConfigManager.save(config, path)
    assert path.exists()


def test_round_trip_signal_fields(tmp_path: Path) -> None:
    config = _make_config()
    path = tmp_path / "session.mvc"
    ConfigManager.save(config, path)
    loaded = ConfigManager.load(path)

    assert len(loaded.signals) == 1
    s = loaded.signals[0]
    assert s.name == "Speed"
    assert s.group_name == "Engine"
    assert s.color == (255, 85, 85)
    assert s.line_width == 1
    assert s.line_style == "solid"
    assert s.display_mode == "line"
    assert s.marker_shape == "circle"
    assert s.step_mode is False
    assert s.enum_display_table is True
    assert s.enum_display_cursor is False
    assert s.enum_display_yaxis is False


def test_round_trip_zoom(tmp_path: Path) -> None:
    config = _make_config()
    path = tmp_path / "session.mvc"
    ConfigManager.save(config, path)
    loaded = ConfigManager.load(path)

    assert loaded.x_range == (0.0, 10.0)
    assert loaded.y_ranges == {"Speed": (0.0, 200.0)}


def test_round_trip_axes(tmp_path: Path) -> None:
    config = _make_config()
    path = tmp_path / "session.mvc"
    ConfigManager.save(config, path)
    loaded = ConfigManager.load(path)

    assert loaded.shared_groups == (("Speed", "Torque"),)
    assert loaded.linked_groups == ()


def test_round_trip_cursors(tmp_path: Path) -> None:
    config = _make_config()
    path = tmp_path / "session.mvc"
    ConfigManager.save(config, path)
    loaded = ConfigManager.load(path)

    assert loaded.cursor_mode == "ONE"
    assert loaded.cursor_positions == (3.5, 0.0)


def test_round_trip_selection(tmp_path: Path) -> None:
    config = _make_config()
    path = tmp_path / "session.mvc"
    ConfigManager.save(config, path)
    loaded = ConfigManager.load(path)

    assert loaded.selected_signal == "Speed"


def test_round_trip_no_selection(tmp_path: Path) -> None:
    config = ViewerConfig(
        format_version=CONFIG_FORMAT_VERSION,
        measurement_path="/data/test.mf4",
        signals=(),
        x_range=(0.0, 1.0),
        y_ranges={},
        shared_groups=(),
        linked_groups=(),
        cursor_mode="HIDDEN",
        cursor_positions=(0.0, 0.0),
        selected_signal=None,
    )
    path = tmp_path / "session.mvc"
    ConfigManager.save(config, path)
    loaded = ConfigManager.load(path)
    assert loaded.selected_signal is None


# ---------------------------------------------------------------------------
# Path mode
# ---------------------------------------------------------------------------

def test_save_absolute_stores_full_path(tmp_path: Path) -> None:
    meas = tmp_path / "measurement.mf4"
    meas.touch()
    config = _make_config(measurement_path=str(meas))
    mvc = tmp_path / "sub" / "session.mvc"
    ConfigManager.save(config, mvc, path_mode="absolute")
    loaded = ConfigManager.load(mvc)
    assert Path(loaded.measurement_path).is_absolute()


def test_save_relative_stores_relative_path(tmp_path: Path) -> None:
    meas = tmp_path / "data" / "measurement.mf4"
    meas.parent.mkdir()
    meas.touch()
    config = _make_config(measurement_path=str(meas))
    mvc = tmp_path / "configs" / "session.mvc"
    ConfigManager.save(config, mvc, path_mode="relative")
    loaded = ConfigManager.load(mvc)
    assert not Path(loaded.measurement_path).is_absolute()


# ---------------------------------------------------------------------------
# resolve_measurement_path
# ---------------------------------------------------------------------------

def test_resolve_absolute_existing_path(tmp_path: Path) -> None:
    meas = tmp_path / "test.mf4"
    meas.touch()
    result = ConfigManager.resolve_measurement_path(str(meas), tmp_path / "any.mvc")
    assert result == meas


def test_resolve_absolute_missing_path_returns_none(tmp_path: Path) -> None:
    result = ConfigManager.resolve_measurement_path(
        str(tmp_path / "missing.mf4"), tmp_path / "any.mvc"
    )
    assert result is None


def test_resolve_relative_existing_path(tmp_path: Path) -> None:
    meas = tmp_path / "data" / "test.mf4"
    meas.parent.mkdir()
    meas.touch()
    mvc = tmp_path / "configs" / "session.mvc"
    relative = "../data/test.mf4"
    result = ConfigManager.resolve_measurement_path(relative, mvc)
    assert result is not None
    assert result.resolve() == meas.resolve()


def test_resolve_relative_missing_returns_none(tmp_path: Path) -> None:
    mvc = tmp_path / "session.mvc"
    result = ConfigManager.resolve_measurement_path("../nope.mf4", mvc)
    assert result is None


def test_resolve_empty_string_returns_none(tmp_path: Path) -> None:
    result = ConfigManager.resolve_measurement_path("", tmp_path / "any.mvc")
    assert result is None


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

def test_load_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigLoadError):
        ConfigManager.load(tmp_path / "nonexistent.mvc")


def test_load_invalid_json_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.mvc"
    bad.write_text("this is not json", encoding="utf-8")
    with pytest.raises(ConfigLoadError):
        ConfigManager.load(bad)


def test_load_missing_signals_key_returns_empty_list(tmp_path: Path) -> None:
    mvc = tmp_path / "session.mvc"
    mvc.write_text('{"measurement_path": "/x.mf4"}', encoding="utf-8")
    loaded = ConfigManager.load(mvc)
    assert loaded.signals == ()


def test_load_tolerates_missing_optional_signal_fields(tmp_path: Path) -> None:
    mvc = tmp_path / "session.mvc"
    mvc.write_text(
        '{"signals": [{"name": "RPM"}]}',
        encoding="utf-8",
    )
    loaded = ConfigManager.load(mvc)
    assert len(loaded.signals) == 1
    s = loaded.signals[0]
    assert s.name == "RPM"
    assert s.group_name == ""
    assert s.line_width == 1
