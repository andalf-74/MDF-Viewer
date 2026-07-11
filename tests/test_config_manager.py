"""Tests for ConfigManager — save, load, and path resolution (#106: full
multi-tab/stripe/measurement workspace shape, plus migration from the
pre-#106 flat single-tab/single-measurement shape)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from mdf_viewer.config_manager import CONFIG_FORMAT_VERSION, ConfigManager
from mdf_viewer.errors import ConfigLoadError
from mdf_viewer.model.viewer_config import (
    MeasurementConfig,
    SignalConfig,
    SignalRef,
    StripeConfig,
    TabConfig,
    ViewerConfig,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_signal(**kwargs) -> SignalConfig:
    defaults = dict(
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
    defaults.update(kwargs)
    return SignalConfig(**defaults)


def _ref(name: str, measurement_index: int = 0) -> SignalRef:
    return SignalRef(name=name, measurement_index=measurement_index)


def _make_tab(**kwargs) -> TabConfig:
    defaults = dict(
        name="Tab 1",
        stripes=(StripeConfig(name="Stripe 1", size=1),),
        active_stripe_index=0,
        signals=(_make_signal(),),
        x_range=(0.0, 10.0),
        y_ranges=((_ref("Speed"), (0.0, 200.0)),),
        merged_groups=((_ref("Speed"), _ref("Torque")),),
        synced_groups=(),
        cursor_mode="ONE",
        cursor_positions=(3.5, 0.0),
        selected_signal=_ref("Speed"),
        page_splitter_sizes=(500, 260),
        ast_column_widths=(),
    )
    defaults.update(kwargs)
    return TabConfig(**defaults)


def _make_config(measurement_path: str = "/data/test.mf4", **kwargs) -> ViewerConfig:
    defaults = dict(
        format_version=CONFIG_FORMAT_VERSION,
        measurements=(MeasurementConfig(path=measurement_path, label="M1", offset_s=0.0),),
        primary_measurement_index=0,
        measurements_synchronized=False,
        tabs=(_make_tab(),),
        active_tab_index=0,
        display_name_separator=".",
        display_name_direction="right",
        display_name_segments=1,
    )
    defaults.update(kwargs)
    return ViewerConfig(**defaults)


# ---------------------------------------------------------------------------
# Round-trip
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-FILE-060")
def test_save_creates_file(tmp_path: Path) -> None:
    config = _make_config()
    path = tmp_path / "session.mvc"
    ConfigManager.save(config, path)
    assert path.exists()


@pytest.mark.requirement("REQ-FILE-061")
def test_round_trip_signal_fields(tmp_path: Path) -> None:
    config = _make_config()
    path = tmp_path / "session.mvc"
    ConfigManager.save(config, path)
    loaded = ConfigManager.load(path)

    assert len(loaded.tabs) == 1
    assert len(loaded.tabs[0].signals) == 1
    s = loaded.tabs[0].signals[0]
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


@pytest.mark.requirement("REQ-FILE-090")
def test_round_trip_signal_stripe_and_measurement_index(tmp_path: Path) -> None:
    config = _make_config(tabs=(_make_tab(signals=(_make_signal(stripe_index=2, measurement_index=1),)),))
    path = tmp_path / "session.mvc"
    ConfigManager.save(config, path)
    loaded = ConfigManager.load(path)

    s = loaded.tabs[0].signals[0]
    assert s.stripe_index == 2
    assert s.measurement_index == 1


@pytest.mark.requirement("REQ-FILE-090")
def test_round_trip_stripes(tmp_path: Path) -> None:
    config = _make_config(tabs=(_make_tab(
        stripes=(StripeConfig(name="Vibration", size=300), StripeConfig(name="Temp", size=150)),
        active_stripe_index=1,
    ),))
    path = tmp_path / "session.mvc"
    ConfigManager.save(config, path)
    loaded = ConfigManager.load(path)

    tab = loaded.tabs[0]
    assert tab.stripes == (StripeConfig(name="Vibration", size=300), StripeConfig(name="Temp", size=150))
    assert tab.active_stripe_index == 1


@pytest.mark.requirement("REQ-FILE-091")
def test_round_trip_multiple_tabs(tmp_path: Path) -> None:
    config = _make_config(
        tabs=(_make_tab(name="Engine"), _make_tab(name="Chassis")),
        active_tab_index=1,
    )
    path = tmp_path / "session.mvc"
    ConfigManager.save(config, path)
    loaded = ConfigManager.load(path)

    assert [t.name for t in loaded.tabs] == ["Engine", "Chassis"]
    assert loaded.active_tab_index == 1


@pytest.mark.requirement("REQ-FILE-092")
def test_round_trip_multiple_measurements(tmp_path: Path) -> None:
    config = _make_config(
        measurements=(
            MeasurementConfig(path="/data/a.mf4", label="M1", offset_s=0.0),
            MeasurementConfig(path="/data/b.mf4", label="M2", offset_s=1.5),
        ),
        primary_measurement_index=1,
        measurements_synchronized=True,
    )
    path = tmp_path / "session.mvc"
    ConfigManager.save(config, path)
    loaded = ConfigManager.load(path)

    assert loaded.measurements == (
        MeasurementConfig(path="/data/a.mf4", label="M1", offset_s=0.0),
        MeasurementConfig(path="/data/b.mf4", label="M2", offset_s=1.5),
    )
    assert loaded.primary_measurement_index == 1
    assert loaded.measurements_synchronized is True


@pytest.mark.requirement("REQ-FILE-061")
def test_round_trip_zoom(tmp_path: Path) -> None:
    config = _make_config()
    path = tmp_path / "session.mvc"
    ConfigManager.save(config, path)
    loaded = ConfigManager.load(path)

    tab = loaded.tabs[0]
    assert tab.x_range == (0.0, 10.0)
    assert tab.y_ranges == ((_ref("Speed"), (0.0, 200.0)),)


@pytest.mark.requirement("REQ-FILE-061")
def test_round_trip_axes(tmp_path: Path) -> None:
    config = _make_config()
    path = tmp_path / "session.mvc"
    ConfigManager.save(config, path)
    loaded = ConfigManager.load(path)

    tab = loaded.tabs[0]
    assert tab.merged_groups == ((_ref("Speed"), _ref("Torque")),)
    assert tab.synced_groups == ()


@pytest.mark.requirement("REQ-FILE-061")
def test_round_trip_cursors(tmp_path: Path) -> None:
    config = _make_config()
    path = tmp_path / "session.mvc"
    ConfigManager.save(config, path)
    loaded = ConfigManager.load(path)

    tab = loaded.tabs[0]
    assert tab.cursor_mode == "ONE"
    assert tab.cursor_positions == (3.5, 0.0)


@pytest.mark.requirement("REQ-FILE-061")
def test_round_trip_display_name_rule_custom_values(tmp_path: Path) -> None:
    """The display-name-shortening rule *parameters* used for this session
    round-trip through a saved .mvc — not whether the rule is enabled,
    which stays governed solely by Preferences (#89)."""
    config = _make_config(
        tabs=(_make_tab(
            merged_groups=(), synced_groups=(), cursor_mode="HIDDEN",
            cursor_positions=(0.0, 0.0), selected_signal=None,
            page_splitter_sizes=(500, 260), ast_column_widths=(),
        ),),
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


@pytest.mark.requirement("REQ-FILE-067")
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


@pytest.mark.requirement("REQ-FILE-067")
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

    assert loaded.tabs[0].merged_groups == ()
    assert loaded.tabs[0].synced_groups == ()


@pytest.mark.requirement("REQ-FILE-061")
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


@pytest.mark.requirement("REQ-FILE-067")
def test_load_missing_layout_defaults_to_none(tmp_path: Path) -> None:
    """A .mvc saved before layout persistence existed must still load cleanly (#77)."""
    config = _make_config()
    path = tmp_path / "session.mvc"
    ConfigManager.save(config, path)
    loaded = ConfigManager.load(path)

    assert loaded.window_geometry is None
    assert loaded.splitter_sizes is None


@pytest.mark.requirement("REQ-FILE-067")
def test_load_malformed_layout_ignored(tmp_path: Path) -> None:
    mvc = tmp_path / "session.mvc"
    mvc.write_text(
        json.dumps({"signals": [], "window_geometry": "not-a-dict", "splitter_sizes": [1, 2]}),
        encoding="utf-8",
    )
    loaded = ConfigManager.load(mvc)
    assert loaded.window_geometry is None
    assert loaded.splitter_sizes is None


@pytest.mark.requirement("REQ-FILE-061")
def test_round_trip_selection(tmp_path: Path) -> None:
    config = _make_config()
    path = tmp_path / "session.mvc"
    ConfigManager.save(config, path)
    loaded = ConfigManager.load(path)

    assert loaded.tabs[0].selected_signal == _ref("Speed")


@pytest.mark.requirement("REQ-FILE-061")
def test_round_trip_no_selection(tmp_path: Path) -> None:
    config = _make_config(tabs=(_make_tab(
        signals=(), merged_groups=(), synced_groups=(),
        cursor_mode="HIDDEN", cursor_positions=(0.0, 0.0),
        x_range=(0.0, 1.0), y_ranges=(), selected_signal=None,
    ),))
    path = tmp_path / "session.mvc"
    ConfigManager.save(config, path)
    loaded = ConfigManager.load(path)
    assert loaded.tabs[0].selected_signal is None


# ---------------------------------------------------------------------------
# Migration from the pre-#106 flat shape
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-FILE-096")
def test_load_pre_106_flat_file_synthesizes_single_tab_and_measurement(tmp_path: Path) -> None:
    """A .mvc saved before stripes/tabs/multi-measurement existed loads
    into one default tab/stripe and one (Primary) measurement (REQ-FILE-096)."""
    path = tmp_path / "old.mvc"
    path.write_text(json.dumps({
        "format_version": "1.0",
        "measurement_path": "/data/test.mf4",
        "signals": [
            {"name": "Speed", "group_name": "Engine", "color": [255, 85, 85],
             "line_width": 1, "line_style": "solid", "display_mode": "line",
             "marker_shape": "circle", "step_mode": False,
             "enum_display_table": True, "enum_display_cursor": False,
             "enum_display_yaxis": False},
        ],
        "zoom": {"x_range": [0.0, 10.0], "y_ranges": {"Speed": [0.0, 200.0]}},
        "axes": {"merged": [["Speed", "Torque"]], "synced": []},
        "cursors": {"mode": "ONE", "positions": [3.5, 0.0]},
        "selection": "Speed",
    }), encoding="utf-8")

    loaded = ConfigManager.load(path)

    assert len(loaded.tabs) == 1
    assert loaded.active_tab_index == 0
    tab = loaded.tabs[0]
    assert tab.name == "Tab 1"
    assert len(tab.stripes) == 1
    assert tab.active_stripe_index == 0
    assert [s.name for s in tab.signals] == ["Speed"]
    assert tab.x_range == (0.0, 10.0)
    assert tab.merged_groups == ((_ref("Speed"), _ref("Torque")),)
    assert tab.selected_signal == _ref("Speed")

    assert len(loaded.measurements) == 1
    assert loaded.measurements[0].path == "/data/test.mf4"
    assert loaded.primary_measurement_index == 0
    assert loaded.measurements_synchronized is False


@pytest.mark.requirement("REQ-FILE-096")
def test_load_pre_106_flat_file_with_no_measurement_path(tmp_path: Path) -> None:
    path = tmp_path / "empty.mvc"
    path.write_text(json.dumps({"signals": []}), encoding="utf-8")
    loaded = ConfigManager.load(path)
    assert loaded.measurements == ()


@pytest.mark.requirement("REQ-FILE-093")
def test_load_pre_measurement_aware_groups_shape_migrates(tmp_path: Path) -> None:
    """A .mvc saved by the first #106 M6 pass (before merged/synced groups,
    y_ranges, and selection became measurement-aware) stores bare name
    strings/a name-keyed y_ranges dict rather than SignalRef records —
    must still load cleanly, defaulting measurement_index to 0 (REQ-FILE-067
    forward-compat precedent)."""
    path = tmp_path / "pre_fix.mvc"
    path.write_text(json.dumps({
        "format_version": "2.0",
        "measurements": [{"path": "/data/test.mf4", "label": "M1", "offset_s": 0.0}],
        "primary_measurement_index": 0,
        "measurements_synchronized": False,
        "active_tab_index": 0,
        "tabs": [{
            "name": "Tab 1",
            "active_stripe_index": 0,
            "stripes": [{"name": "Stripe 1", "size": 1}],
            "signals": [],
            "zoom": {"x_range": [0.0, 10.0], "y_ranges": {"Speed": [0.0, 200.0]}},
            "axes": {"merged": [["Speed", "Torque"]], "synced": []},
            "cursors": {"mode": "HIDDEN", "positions": [0.0, 0.0]},
            "selection": "Speed",
        }],
    }), encoding="utf-8")

    loaded = ConfigManager.load(path)

    tab = loaded.tabs[0]
    assert tab.y_ranges == ((_ref("Speed"), (0.0, 200.0)),)
    assert tab.merged_groups == ((_ref("Speed"), _ref("Torque")),)
    assert tab.selected_signal == _ref("Speed")


@pytest.mark.requirement("REQ-FILE-090")
def test_round_trip_page_splitter_sizes(tmp_path: Path) -> None:
    config = _make_config(tabs=(_make_tab(page_splitter_sizes=(700, 320)),))
    path = tmp_path / "session.mvc"
    ConfigManager.save(config, path)
    loaded = ConfigManager.load(path)
    assert loaded.tabs[0].page_splitter_sizes == (700, 320)


@pytest.mark.requirement("REQ-FILE-090")
def test_round_trip_ast_column_widths(tmp_path: Path) -> None:
    config = _make_config(tabs=(_make_tab(ast_column_widths=(28, 150, 60, 60, 70)),))
    path = tmp_path / "session.mvc"
    ConfigManager.save(config, path)
    loaded = ConfigManager.load(path)
    assert loaded.tabs[0].ast_column_widths == (28, 150, 60, 60, 70)


@pytest.mark.requirement("REQ-FILE-067")
def test_load_missing_page_splitter_and_column_widths_use_defaults(tmp_path: Path) -> None:
    """A .mvc saved before this capture existed must still load cleanly."""
    path = tmp_path / "pre_fix.mvc"
    path.write_text(json.dumps({
        "format_version": "2.0",
        "measurements": [], "primary_measurement_index": 0,
        "measurements_synchronized": False, "active_tab_index": 0,
        "tabs": [{
            "name": "Tab 1", "active_stripe_index": 0,
            "stripes": [{"name": "Stripe 1", "size": 1}], "signals": [],
            "zoom": {"x_range": [0.0, 1.0], "y_ranges": {}},
            "axes": {"merged": [], "synced": []},
            "cursors": {"mode": "HIDDEN", "positions": [0.0, 0.0]},
            "selection": None,
        }],
    }), encoding="utf-8")

    loaded = ConfigManager.load(path)

    assert loaded.tabs[0].page_splitter_sizes == (500, 260)
    assert loaded.tabs[0].ast_column_widths == ()


@pytest.mark.requirement("REQ-FILE-090")
def test_saved_file_always_uses_new_nested_shape(tmp_path: Path) -> None:
    """save() always writes the new "tabs"/"measurements" shape, even for
    a plain single-tab/single-measurement session — no reason to keep
    writing the old flat shape once #106 exists."""
    config = _make_config()
    path = tmp_path / "session.mvc"
    ConfigManager.save(config, path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "tabs" in raw
    assert "measurements" in raw
    assert "measurement_path" not in raw
    assert "signals" not in raw  # now nested under tabs[0]["signals"]


# ---------------------------------------------------------------------------
# Path mode
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-FILE-063")
def test_save_absolute_stores_full_path(tmp_path: Path) -> None:
    meas = tmp_path / "measurement.mf4"
    meas.touch()
    config = _make_config(measurement_path=str(meas))
    mvc = tmp_path / "sub" / "session.mvc"
    ConfigManager.save(config, mvc, path_mode="absolute")
    loaded = ConfigManager.load(mvc)
    assert Path(loaded.measurements[0].path).is_absolute()


@pytest.mark.requirement("REQ-FILE-063")
def test_save_relative_stores_relative_path(tmp_path: Path) -> None:
    meas = tmp_path / "data" / "measurement.mf4"
    meas.parent.mkdir()
    meas.touch()
    config = _make_config(measurement_path=str(meas))
    mvc = tmp_path / "configs" / "session.mvc"
    ConfigManager.save(config, mvc, path_mode="relative")
    loaded = ConfigManager.load(mvc)
    assert not Path(loaded.measurements[0].path).is_absolute()


@pytest.mark.requirement("REQ-FILE-063")
def test_save_relative_stores_every_measurements_path(tmp_path: Path) -> None:
    meas_a = tmp_path / "data" / "a.mf4"
    meas_b = tmp_path / "data" / "b.mf4"
    meas_a.parent.mkdir()
    meas_a.touch()
    meas_b.touch()
    config = _make_config(measurements=(
        MeasurementConfig(path=str(meas_a), label="M1", offset_s=0.0),
        MeasurementConfig(path=str(meas_b), label="M2", offset_s=2.0),
    ))
    mvc = tmp_path / "configs" / "session.mvc"
    ConfigManager.save(config, mvc, path_mode="relative")
    loaded = ConfigManager.load(mvc)
    assert not Path(loaded.measurements[0].path).is_absolute()
    assert not Path(loaded.measurements[1].path).is_absolute()
    assert loaded.measurements[1].offset_s == 2.0


# ---------------------------------------------------------------------------
# resolve_measurement_path
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-FILE-064")
def test_resolve_absolute_existing_path(tmp_path: Path) -> None:
    meas = tmp_path / "test.mf4"
    meas.touch()
    result = ConfigManager.resolve_measurement_path(str(meas), tmp_path / "any.mvc")
    assert result == meas


@pytest.mark.requirement("REQ-FILE-065")
def test_resolve_absolute_missing_path_returns_none(tmp_path: Path) -> None:
    result = ConfigManager.resolve_measurement_path(
        str(tmp_path / "missing.mf4"), tmp_path / "any.mvc"
    )
    assert result is None


@pytest.mark.requirement("REQ-FILE-064")
def test_resolve_relative_existing_path(tmp_path: Path) -> None:
    meas = tmp_path / "data" / "test.mf4"
    meas.parent.mkdir()
    meas.touch()
    mvc = tmp_path / "configs" / "session.mvc"
    relative = "../data/test.mf4"
    result = ConfigManager.resolve_measurement_path(relative, mvc)
    assert result is not None
    assert result.resolve() == meas.resolve()


@pytest.mark.requirement("REQ-FILE-065")
def test_resolve_relative_missing_returns_none(tmp_path: Path) -> None:
    mvc = tmp_path / "session.mvc"
    result = ConfigManager.resolve_measurement_path("../nope.mf4", mvc)
    assert result is None


@pytest.mark.requirement("REQ-FILE-065")
def test_resolve_empty_string_returns_none(tmp_path: Path) -> None:
    result = ConfigManager.resolve_measurement_path("", tmp_path / "any.mvc")
    assert result is None


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-FILE-068")
@pytest.mark.requirement("REQ-NFR-010")
def test_load_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ConfigLoadError):
        ConfigManager.load(tmp_path / "nonexistent.mvc")


@pytest.mark.requirement("REQ-FILE-068")
@pytest.mark.requirement("REQ-NFR-010")
def test_load_invalid_json_raises(tmp_path: Path) -> None:
    bad = tmp_path / "bad.mvc"
    bad.write_text("this is not json", encoding="utf-8")
    with pytest.raises(ConfigLoadError):
        ConfigManager.load(bad)


@pytest.mark.requirement("REQ-FILE-067")
def test_load_missing_signals_key_returns_empty_list(tmp_path: Path) -> None:
    mvc = tmp_path / "session.mvc"
    mvc.write_text('{"measurement_path": "/x.mf4"}', encoding="utf-8")
    loaded = ConfigManager.load(mvc)
    assert loaded.tabs[0].signals == ()


@pytest.mark.requirement("REQ-FILE-067")
def test_load_tolerates_missing_optional_signal_fields(tmp_path: Path) -> None:
    mvc = tmp_path / "session.mvc"
    mvc.write_text(
        '{"signals": [{"name": "RPM"}]}',
        encoding="utf-8",
    )
    loaded = ConfigManager.load(mvc)
    assert len(loaded.tabs[0].signals) == 1
    s = loaded.tabs[0].signals[0]
    assert s.name == "RPM"
    assert s.group_name == ""
    assert s.line_width == 1
    assert s.stripe_index == 0
    assert s.measurement_index == 0
