"""Tests for ConfigManager — save, load, and path resolution."""

from __future__ import annotations

import dataclasses
import json
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
        merged_groups=(("Speed", "Torque"),),
        synced_groups=(),
        cursor_mode="ONE",
        cursor_positions=(3.5, 0.0),
        selected_signal="Speed",
        display_name_separator=".",
        display_name_direction="right",
        display_name_segments=1,
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

    assert loaded.merged_groups == (("Speed", "Torque"),)
    assert loaded.synced_groups == ()


def test_round_trip_cursors(tmp_path: Path) -> None:
    config = _make_config()
    path = tmp_path / "session.mvc"
    ConfigManager.save(config, path)
    loaded = ConfigManager.load(path)

    assert loaded.cursor_mode == "ONE"
    assert loaded.cursor_positions == (3.5, 0.0)


def test_round_trip_display_name_rule_custom_values(tmp_path: Path) -> None:
    """The display-name-shortening rule *parameters* used for this session
    round-trip through a saved .mvc — not whether the rule is enabled,
    which stays governed solely by Preferences (#89)."""
    sig = SignalConfig(
        name="Speed", group_name="Engine", color=(255, 85, 85), line_width=1,
        line_style="solid", display_mode="line", marker_shape="circle",
        step_mode=False, enum_display_table=True, enum_display_cursor=False,
        enum_display_yaxis=False,
    )
    config = ViewerConfig(
        format_version=CONFIG_FORMAT_VERSION,
        measurement_path="/data/test.mf4",
        signals=(sig,),
        x_range=(0.0, 10.0),
        y_ranges={},
        merged_groups=(),
        synced_groups=(),
        cursor_mode="HIDDEN",
        cursor_positions=(0.0, 0.0),
        selected_signal=None,
        display_name_separator="_",
        display_name_direction="left",
        display_name_segments=3,
    )
    path = tmp_path / "session.mvc"
    ConfigManager.save(config, path)
    loaded = ConfigManager.load(path)

    assert loaded.display_name_separator == "_"
    assert loaded.display_name_direction == "left"
    assert loaded.display_name_segments == 3


def test_load_missing_display_name_rule_uses_defaults(tmp_path: Path) -> None:
    """A .mvc saved before this field existed must still load cleanly (#89)."""
    path = tmp_path / "old.mvc"
    path.write_text(json.dumps({
        "format_version": "1.0",
        "measurement_path": "/data/test.mf4",
        "signals": [],
        "zoom": {"x_range": [0.0, 1.0], "y_ranges": {}},
        "axes": {"shared": [], "linked": []},
        "cursors": {"mode": "HIDDEN", "positions": [0.0, 0.0]},
        "selection": None,
    }), encoding="utf-8")

    loaded = ConfigManager.load(path)

    assert loaded.display_name_separator == "."
    assert loaded.display_name_direction == "right"
    assert loaded.display_name_segments == 1


def test_load_pre_rename_axes_keys_drops_grouping_silently(tmp_path: Path) -> None:
    """A .mvc saved before #95 renamed the 'shared'/'linked' axes keys to
    'merged'/'synced' must still load cleanly — axis grouping is silently
    lost (not restored) rather than raising, since no migration was added
    (negligible real-world .mvc usage at rename time)."""
    path = tmp_path / "pre_rename.mvc"
    path.write_text(json.dumps({
        "format_version": "1.0",
        "measurement_path": "/data/test.mf4",
        "signals": [],
        "zoom": {"x_range": [0.0, 1.0], "y_ranges": {}},
        "axes": {"shared": [["Speed", "Torque"]], "linked": [["RPM", "Load"]]},
        "cursors": {"mode": "HIDDEN", "positions": [0.0, 0.0]},
        "selection": None,
    }), encoding="utf-8")

    loaded = ConfigManager.load(path)

    assert loaded.merged_groups == ()
    assert loaded.synced_groups == ()


def test_round_trip_layout(tmp_path: Path) -> None:
    config = _make_config()
    window_geometry = {"x": 10, "y": 20, "width": 1400, "height": 900, "maximized": False}
    splitter_sizes = {
        "left": [400, 200], "right": [300, 150],
        "content": [900, 300], "outer": [260, 940],
        "left_panel": {"pinned": True, "width": 260},
    }
    config = dataclasses.replace(
        config, window_geometry=window_geometry, splitter_sizes=splitter_sizes
    )
    path = tmp_path / "session.mvc"
    ConfigManager.save(config, path)
    loaded = ConfigManager.load(path)

    assert loaded.window_geometry == window_geometry
    assert loaded.splitter_sizes == splitter_sizes


def test_load_missing_layout_defaults_to_none(tmp_path: Path) -> None:
    """A .mvc saved before layout persistence existed must still load cleanly (#77)."""
    config = _make_config()
    path = tmp_path / "session.mvc"
    ConfigManager.save(config, path)
    loaded = ConfigManager.load(path)

    assert loaded.window_geometry is None
    assert loaded.splitter_sizes is None


def test_load_malformed_layout_ignored(tmp_path: Path) -> None:
    mvc = tmp_path / "session.mvc"
    mvc.write_text(
        json.dumps({"signals": [], "window_geometry": "not-a-dict", "splitter_sizes": [1, 2]}),
        encoding="utf-8",
    )
    loaded = ConfigManager.load(mvc)
    assert loaded.window_geometry is None
    assert loaded.splitter_sizes is None


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
        merged_groups=(),
        synced_groups=(),
        cursor_mode="HIDDEN",
        cursor_positions=(0.0, 0.0),
        selected_signal=None,
        display_name_separator=".",
        display_name_direction="right",
        display_name_segments=1,
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
