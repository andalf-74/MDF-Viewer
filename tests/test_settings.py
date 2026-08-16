"""Tests for Settings — recent files persistence."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mdf_viewer.settings import (
    DEFAULT_CURSOR_COLOR_C1,
    DEFAULT_CURSOR_COLOR_C2,
    DEFAULT_CURSOR_COLOR_CL,
    DEFAULT_CURSOR_COLOR_CR,
    MAX_RECENT,
    UPDATE_CHECKER_PLUGIN_NAME,
    Settings,
)


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(path=tmp_path / "settings.json")


# ---------------------------------------------------------------------------
# Initial state
# ---------------------------------------------------------------------------

def test_recent_files_initially_empty(settings: Settings) -> None:
    assert settings.recent_files() == []


# ---------------------------------------------------------------------------
# add_recent
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-FILE-050")
def test_add_recent_adds_to_front(settings: Settings, tmp_path: Path) -> None:
    a, b = tmp_path / "a.mf4", tmp_path / "b.mf4"
    a.touch()
    b.touch()
    settings.add_recent(a)
    settings.add_recent(b)
    assert settings.recent_files()[0] == b.resolve()


@pytest.mark.requirement("REQ-FILE-050")
def test_add_recent_deduplicates(settings: Settings, tmp_path: Path) -> None:
    p = tmp_path / "file.mf4"
    p.touch()
    settings.add_recent(p)
    settings.add_recent(p)
    assert len(settings.recent_files()) == 1


@pytest.mark.requirement("REQ-FILE-050")
def test_add_recent_moves_existing_entry_to_front(
    settings: Settings, tmp_path: Path
) -> None:
    a, b = tmp_path / "a.mf4", tmp_path / "b.mf4"
    a.touch()
    b.touch()
    settings.add_recent(a)
    settings.add_recent(b)
    settings.add_recent(a)
    files = settings.recent_files()
    assert files[0] == a.resolve()
    assert len(files) == 2


@pytest.mark.requirement("REQ-FILE-050")
def test_add_recent_trims_to_max(settings: Settings, tmp_path: Path) -> None:
    for i in range(MAX_RECENT + 2):
        p = tmp_path / f"{i}.mf4"
        p.touch()
        settings.add_recent(p)
    assert len(settings.recent_files()) == MAX_RECENT


@pytest.mark.requirement("REQ-FILE-051")
def test_add_recent_mixes_mvc_and_measurement_files(
    settings: Settings, tmp_path: Path
) -> None:
    mvc = tmp_path / "session.mvc"
    mdf = tmp_path / "data.mf4"
    mvc.touch()
    mdf.touch()
    settings.add_recent(mdf)
    settings.add_recent(mvc)
    assert settings.recent_files() == [mvc.resolve(), mdf.resolve()]


@pytest.mark.requirement("REQ-FILE-050")
def test_add_recent_persists_across_instances(
    settings: Settings, tmp_path: Path
) -> None:
    p = tmp_path / "file.mf4"
    p.touch()
    settings.add_recent(p)
    reloaded = Settings(path=settings._path)
    assert reloaded.recent_files() == [p.resolve()]


# ---------------------------------------------------------------------------
# Robustness: loading
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-NFR-020")
@pytest.mark.requirement("REQ-NFR-010")
def test_load_handles_missing_file(tmp_path: Path) -> None:
    s = Settings(path=tmp_path / "nonexistent" / "settings.json")
    assert s.recent_files() == []


@pytest.mark.requirement("REQ-NFR-020")
@pytest.mark.requirement("REQ-NFR-010")
def test_load_handles_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("not valid json", encoding="utf-8")
    assert Settings(path=path).recent_files() == []


@pytest.mark.requirement("REQ-NFR-020")
def test_load_handles_missing_key(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{}", encoding="utf-8")
    assert Settings(path=path).recent_files() == []


# ---------------------------------------------------------------------------
# get_and_prune
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-FILE-054")
def test_get_and_prune_returns_only_existing(
    settings: Settings, tmp_path: Path
) -> None:
    existing = tmp_path / "exists.mf4"
    missing = tmp_path / "gone.mf4"
    existing.touch()
    settings.add_recent(missing)
    settings.add_recent(existing)
    assert settings.get_and_prune() == [existing.resolve()]


@pytest.mark.requirement("REQ-FILE-054")
def test_get_and_prune_saves_pruned_list(settings: Settings, tmp_path: Path) -> None:
    existing = tmp_path / "exists.mf4"
    missing = tmp_path / "gone.mf4"
    existing.touch()
    settings.add_recent(missing)
    settings.add_recent(existing)
    settings.get_and_prune()
    assert Settings(path=settings._path).recent_files() == [existing.resolve()]


@pytest.mark.requirement("REQ-FILE-054")
def test_get_and_prune_noop_when_all_exist(
    settings: Settings, tmp_path: Path
) -> None:
    p = tmp_path / "file.mf4"
    p.touch()
    settings.add_recent(p)
    result = settings.get_and_prune()
    assert result == [p.resolve()]


@pytest.mark.requirement("REQ-FILE-054")
def test_get_and_prune_empty_list(settings: Settings) -> None:
    assert settings.get_and_prune() == []


# ---------------------------------------------------------------------------
# check_for_updates migration (#76, REQ-UPDATE-320)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-UPDATE-320")
def test_check_for_updates_migrates_old_top_level_key_into_plugin_setting(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"check_for_updates": False}), encoding="utf-8")

    s = Settings(path=path)

    assert s.get_plugin_setting(UPDATE_CHECKER_PLUGIN_NAME, "check_for_updates", True) is False


@pytest.mark.requirement("REQ-UPDATE-320")
def test_check_for_updates_migration_does_not_fire_without_old_key(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{}", encoding="utf-8")

    s = Settings(path=path)

    assert s.get_plugin_setting(UPDATE_CHECKER_PLUGIN_NAME, "check_for_updates", "missing") == "missing"


@pytest.mark.requirement("REQ-UPDATE-320")
def test_check_for_updates_old_key_is_dropped_on_next_save(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"check_for_updates": False}), encoding="utf-8")
    s = Settings(path=path)

    s.add_recent(tmp_path)  # any change that triggers a _save()

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert "check_for_updates" not in raw
    assert raw["plugin_settings"][UPDATE_CHECKER_PLUGIN_NAME]["check_for_updates"] is False


# ---------------------------------------------------------------------------
# cursor_persistent
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-073")
def test_cursor_persistent_default_true(settings: Settings) -> None:
    assert settings.cursor_persistent is True


@pytest.mark.requirement("REQ-PLOT-073")
def test_cursor_persistent_can_be_disabled(settings: Settings) -> None:
    settings.cursor_persistent = False
    assert settings.cursor_persistent is False


@pytest.mark.requirement("REQ-NFR-021")
def test_cursor_persistent_persists(settings: Settings) -> None:
    settings.cursor_persistent = False
    reloaded = Settings(path=settings._path)
    assert reloaded.cursor_persistent is False


@pytest.mark.requirement("REQ-NFR-020")
def test_cursor_persistent_defaults_to_true_on_missing_key(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{}", encoding="utf-8")
    assert Settings(path=path).cursor_persistent is True


# ---------------------------------------------------------------------------
# cursor_mode
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-072")
def test_cursor_mode_default_12(settings: Settings) -> None:
    assert settings.cursor_mode == "1/2"


@pytest.mark.requirement("REQ-PLOT-072")
def test_cursor_mode_can_be_changed(settings: Settings) -> None:
    settings.cursor_mode = "L/R"
    assert settings.cursor_mode == "L/R"


@pytest.mark.requirement("REQ-NFR-021")
def test_cursor_mode_persists(settings: Settings) -> None:
    settings.cursor_mode = "L/R"
    reloaded = Settings(path=settings._path)
    assert reloaded.cursor_mode == "L/R"


@pytest.mark.requirement("REQ-NFR-020")
def test_cursor_mode_defaults_to_12_on_missing_key(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{}", encoding="utf-8")
    assert Settings(path=path).cursor_mode == "1/2"


# ---------------------------------------------------------------------------
# cursor colors
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-072")
def test_cursor_colors_default(settings: Settings) -> None:
    assert settings.cursor_color_c1 == DEFAULT_CURSOR_COLOR_C1
    assert settings.cursor_color_c2 == DEFAULT_CURSOR_COLOR_C2
    assert settings.cursor_color_cl == DEFAULT_CURSOR_COLOR_CL
    assert settings.cursor_color_cr == DEFAULT_CURSOR_COLOR_CR


@pytest.mark.requirement("REQ-PLOT-072")
def test_cursor_colors_can_be_changed(settings: Settings) -> None:
    settings.cursor_color_c1 = (1, 2, 3)
    settings.cursor_color_c2 = (4, 5, 6)
    settings.cursor_color_cl = (7, 8, 9)
    settings.cursor_color_cr = (10, 11, 12)
    assert settings.cursor_color_c1 == (1, 2, 3)
    assert settings.cursor_color_c2 == (4, 5, 6)
    assert settings.cursor_color_cl == (7, 8, 9)
    assert settings.cursor_color_cr == (10, 11, 12)


@pytest.mark.requirement("REQ-NFR-021")
def test_cursor_colors_persist(settings: Settings) -> None:
    settings.cursor_color_c1 = (1, 2, 3)
    settings.cursor_color_cr = (10, 11, 12)
    reloaded = Settings(path=settings._path)
    assert reloaded.cursor_color_c1 == (1, 2, 3)
    assert reloaded.cursor_color_cr == (10, 11, 12)


@pytest.mark.requirement("REQ-NFR-020")
def test_cursor_colors_default_on_missing_key(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{}", encoding="utf-8")
    s = Settings(path=path)
    assert s.cursor_color_c1 == DEFAULT_CURSOR_COLOR_C1
    assert s.cursor_color_cr == DEFAULT_CURSOR_COLOR_CR


@pytest.mark.requirement("REQ-NFR-020")
def test_cursor_colors_default_on_malformed_value(tmp_path: Path) -> None:
    import json
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"cursor_color_c1": "bad", "cursor_color_cr": [1, 2]}), encoding="utf-8")
    s = Settings(path=path)
    assert s.cursor_color_c1 == DEFAULT_CURSOR_COLOR_C1
    assert s.cursor_color_cr == DEFAULT_CURSOR_COLOR_CR


# ---------------------------------------------------------------------------
# show_delta_time_in_plot / delta_time_color
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-101")
def test_show_delta_time_default_true(settings: Settings) -> None:
    assert settings.show_delta_time_in_plot is True


@pytest.mark.requirement("REQ-PLOT-101")
def test_show_delta_time_can_be_disabled(settings: Settings) -> None:
    settings.show_delta_time_in_plot = False
    assert settings.show_delta_time_in_plot is False


@pytest.mark.requirement("REQ-NFR-021")
def test_show_delta_time_persists(settings: Settings) -> None:
    settings.show_delta_time_in_plot = False
    reloaded = Settings(path=settings._path)
    assert reloaded.show_delta_time_in_plot is False


@pytest.mark.requirement("REQ-NFR-020")
def test_show_delta_time_defaults_on_missing_key(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{}", encoding="utf-8")
    assert Settings(path=path).show_delta_time_in_plot is True


@pytest.mark.requirement("REQ-PLOT-101")
def test_delta_time_color_default(settings: Settings) -> None:
    from mdf_viewer.settings import DEFAULT_DELTA_TIME_COLOR
    assert settings.delta_time_color == DEFAULT_DELTA_TIME_COLOR


@pytest.mark.requirement("REQ-PLOT-101")
def test_delta_time_color_can_be_changed(settings: Settings) -> None:
    settings.delta_time_color = (1, 2, 3)
    assert settings.delta_time_color == (1, 2, 3)


@pytest.mark.requirement("REQ-NFR-021")
def test_delta_time_color_persists(settings: Settings) -> None:
    settings.delta_time_color = (1, 2, 3)
    reloaded = Settings(path=settings._path)
    assert reloaded.delta_time_color == (1, 2, 3)


# ---------------------------------------------------------------------------
# plot_background_color (#117)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-015")
def test_plot_background_color_default(settings: Settings) -> None:
    from mdf_viewer.settings import DEFAULT_PLOT_BACKGROUND_COLOR
    assert settings.plot_background_color == DEFAULT_PLOT_BACKGROUND_COLOR


@pytest.mark.requirement("REQ-PLOT-015")
def test_plot_background_color_can_be_changed(settings: Settings) -> None:
    settings.plot_background_color = (64, 64, 64)
    assert settings.plot_background_color == (64, 64, 64)


@pytest.mark.requirement("REQ-NFR-021")
def test_plot_background_color_persists(settings: Settings) -> None:
    settings.plot_background_color = (64, 64, 64)
    reloaded = Settings(path=settings._path)
    assert reloaded.plot_background_color == (64, 64, 64)


@pytest.mark.requirement("REQ-PLOT-015")
def test_plot_background_color_defaults_on_malformed_settings_file(tmp_path) -> None:
    from mdf_viewer.settings import DEFAULT_PLOT_BACKGROUND_COLOR
    path = tmp_path / "settings.json"
    path.write_text("not json", encoding="utf-8")
    assert Settings(path=path).plot_background_color == DEFAULT_PLOT_BACKGROUND_COLOR


# ---------------------------------------------------------------------------
# max_undo_steps
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-062")
def test_max_undo_steps_default(settings: Settings) -> None:
    from mdf_viewer.settings import DEFAULT_MAX_UNDO_STEPS
    assert settings.max_undo_steps == DEFAULT_MAX_UNDO_STEPS


@pytest.mark.requirement("REQ-PLOT-062")
def test_max_undo_steps_default_is_1(settings: Settings) -> None:
    assert settings.max_undo_steps == 1


@pytest.mark.requirement("REQ-PLOT-062")
def test_max_undo_steps_can_be_changed(settings: Settings) -> None:
    settings.max_undo_steps = 10
    assert settings.max_undo_steps == 10


@pytest.mark.requirement("REQ-NFR-021")
def test_max_undo_steps_persists(settings: Settings) -> None:
    settings.max_undo_steps = 5
    reloaded = Settings(path=settings._path)
    assert reloaded.max_undo_steps == 5


@pytest.mark.requirement("REQ-PLOT-062")
def test_max_undo_steps_clamps_below_1(settings: Settings) -> None:
    settings.max_undo_steps = 0
    assert settings.max_undo_steps == 1


@pytest.mark.requirement("REQ-NFR-020")
def test_max_undo_steps_defaults_on_missing_key(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{}", encoding="utf-8")
    assert Settings(path=path).max_undo_steps == 1


# signal_z_order


@pytest.mark.requirement("REQ-PLOT-042")
def test_signal_z_order_default(settings: Settings) -> None:
    from mdf_viewer.settings import DEFAULT_SIGNAL_Z_ORDER
    assert settings.signal_z_order == DEFAULT_SIGNAL_Z_ORDER


@pytest.mark.requirement("REQ-PLOT-042")
def test_signal_z_order_default_is_top_first(settings: Settings) -> None:
    assert settings.signal_z_order == "top_first"


@pytest.mark.requirement("REQ-PLOT-042")
def test_signal_z_order_can_be_changed(settings: Settings) -> None:
    settings.signal_z_order = "bottom_first"
    assert settings.signal_z_order == "bottom_first"


@pytest.mark.requirement("REQ-NFR-021")
def test_signal_z_order_persists(settings: Settings) -> None:
    settings.signal_z_order = "bottom_first"
    reloaded = Settings(path=settings._path)
    assert reloaded.signal_z_order == "bottom_first"


@pytest.mark.requirement("REQ-NFR-020")
def test_signal_z_order_defaults_on_missing_key(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{}", encoding="utf-8")
    assert Settings(path=path).signal_z_order == "top_first"


# selected_line_boost


@pytest.mark.requirement("REQ-PLOT-044")
def test_selected_line_boost_default(settings: Settings) -> None:
    from mdf_viewer.settings import DEFAULT_SELECTED_LINE_BOOST
    assert settings.selected_line_boost == DEFAULT_SELECTED_LINE_BOOST


@pytest.mark.requirement("REQ-PLOT-044")
def test_selected_line_boost_default_is_1(settings: Settings) -> None:
    assert settings.selected_line_boost == 1


@pytest.mark.requirement("REQ-PLOT-044")
def test_selected_line_boost_can_be_changed(settings: Settings) -> None:
    settings.selected_line_boost = 3
    assert settings.selected_line_boost == 3


@pytest.mark.requirement("REQ-NFR-021")
def test_selected_line_boost_persists(settings: Settings) -> None:
    settings.selected_line_boost = 3
    reloaded = Settings(path=settings._path)
    assert reloaded.selected_line_boost == 3


@pytest.mark.requirement("REQ-PLOT-044")
def test_selected_line_boost_zero_allowed(settings: Settings) -> None:
    settings.selected_line_boost = 0
    assert settings.selected_line_boost == 0


@pytest.mark.requirement("REQ-PLOT-044")
def test_selected_line_boost_clamps_above_5(settings: Settings) -> None:
    settings.selected_line_boost = 99
    assert settings.selected_line_boost == 5


@pytest.mark.requirement("REQ-PLOT-044")
def test_selected_line_boost_clamps_below_0(settings: Settings) -> None:
    settings.selected_line_boost = -1
    assert settings.selected_line_boost == 0


@pytest.mark.requirement("REQ-NFR-020")
def test_selected_line_boost_defaults_on_missing_key(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{}", encoding="utf-8")
    assert Settings(path=path).selected_line_boost == 1


# ---------------------------------------------------------------------------
# display name rule settings
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-160")
def test_display_name_rule_enabled_default_false(settings: Settings) -> None:
    assert settings.display_name_rule_enabled is False


@pytest.mark.requirement("REQ-PLOT-160")
def test_display_name_separator_default(settings: Settings) -> None:
    assert settings.display_name_separator == "."


@pytest.mark.requirement("REQ-PLOT-160")
def test_display_name_direction_default(settings: Settings) -> None:
    assert settings.display_name_direction == "right"


@pytest.mark.requirement("REQ-PLOT-160")
def test_display_name_segments_default(settings: Settings) -> None:
    assert settings.display_name_segments == 1


@pytest.mark.requirement("REQ-NFR-021")
def test_display_name_rule_persists(settings: Settings) -> None:
    settings.display_name_rule_enabled = True
    settings.display_name_separator = "_"
    settings.display_name_direction = "left"
    settings.display_name_segments = 2
    reloaded = Settings(path=settings._path)
    assert reloaded.display_name_rule_enabled is True
    assert reloaded.display_name_separator == "_"
    assert reloaded.display_name_direction == "left"
    assert reloaded.display_name_segments == 2


@pytest.mark.requirement("REQ-PLOT-160")
def test_display_name_segments_clamps(settings: Settings) -> None:
    settings.display_name_segments = 0
    assert settings.display_name_segments == 1
    settings.display_name_segments = 99
    assert settings.display_name_segments == 10


@pytest.mark.requirement("REQ-NFR-020")
def test_display_name_defaults_on_missing_key(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{}", encoding="utf-8")
    s = Settings(path=path)
    assert s.display_name_rule_enabled is False
    assert s.display_name_separator == "."
    assert s.display_name_direction == "right"
    assert s.display_name_segments == 1


# ---------------------------------------------------------------------------
# apply_display_name_rule
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLOT-161")
def test_apply_rule_disabled_returns_full_name(settings: Settings) -> None:
    from mdf_viewer.settings import apply_display_name_rule
    settings.display_name_rule_enabled = False
    assert apply_display_name_rule("a.b.c", settings) == "a.b.c"


@pytest.mark.requirement("REQ-PLOT-160")
def test_apply_rule_right_one_segment(settings: Settings) -> None:
    from mdf_viewer.settings import apply_display_name_rule
    settings.display_name_rule_enabled = True
    settings.display_name_separator = "."
    settings.display_name_direction = "right"
    settings.display_name_segments = 1
    assert apply_display_name_rule("ZF_DTI._.AutoDiagPosition.PosADP", settings) == "PosADP"


@pytest.mark.requirement("REQ-PLOT-160")
def test_apply_rule_right_two_segments(settings: Settings) -> None:
    from mdf_viewer.settings import apply_display_name_rule
    settings.display_name_rule_enabled = True
    settings.display_name_separator = "."
    settings.display_name_direction = "right"
    settings.display_name_segments = 2
    assert apply_display_name_rule("ZF_DTI._.AutoDiagPosition.PosADP", settings) == "AutoDiagPosition.PosADP"


@pytest.mark.requirement("REQ-PLOT-160")
def test_apply_rule_left_one_segment(settings: Settings) -> None:
    from mdf_viewer.settings import apply_display_name_rule
    settings.display_name_rule_enabled = True
    settings.display_name_separator = "."
    settings.display_name_direction = "left"
    settings.display_name_segments = 1
    assert apply_display_name_rule("ZF_DTI._.AutoDiagPosition.PosADP", settings) == "ZF_DTI"


@pytest.mark.requirement("REQ-PLOT-161")
def test_apply_rule_separator_not_found_returns_full_name(settings: Settings) -> None:
    from mdf_viewer.settings import apply_display_name_rule
    settings.display_name_rule_enabled = True
    settings.display_name_separator = "/"
    assert apply_display_name_rule("no_slash_here", settings) == "no_slash_here"


@pytest.mark.requirement("REQ-PLOT-161")
def test_apply_rule_empty_separator_returns_full_name(settings: Settings) -> None:
    from mdf_viewer.settings import apply_display_name_rule
    settings.display_name_rule_enabled = True
    settings.display_name_separator = ""
    assert apply_display_name_rule("a.b.c", settings) == "a.b.c"


@pytest.mark.requirement("REQ-PLOT-160")
def test_apply_rule_segments_exceeds_parts_returns_all(settings: Settings) -> None:
    from mdf_viewer.settings import apply_display_name_rule
    settings.display_name_rule_enabled = True
    settings.display_name_separator = "."
    settings.display_name_direction = "right"
    settings.display_name_segments = 10
    assert apply_display_name_rule("a.b", settings) == "a.b"


# show_only_selected_y_axis


@pytest.mark.requirement("REQ-PLOT-045")
def test_show_only_selected_y_axis_default(settings: Settings) -> None:
    from mdf_viewer.settings import DEFAULT_SHOW_ONLY_SELECTED_Y_AXIS
    assert settings.show_only_selected_y_axis == DEFAULT_SHOW_ONLY_SELECTED_Y_AXIS


@pytest.mark.requirement("REQ-PLOT-045")
def test_show_only_selected_y_axis_default_is_false(settings: Settings) -> None:
    assert settings.show_only_selected_y_axis is False


@pytest.mark.requirement("REQ-PLOT-045")
def test_show_only_selected_y_axis_can_be_enabled(settings: Settings) -> None:
    settings.show_only_selected_y_axis = True
    assert settings.show_only_selected_y_axis is True


@pytest.mark.requirement("REQ-NFR-021")
def test_show_only_selected_y_axis_persists(settings: Settings) -> None:
    settings.show_only_selected_y_axis = True
    reloaded = Settings(path=settings._path)
    assert reloaded.show_only_selected_y_axis is True


@pytest.mark.requirement("REQ-NFR-020")
def test_show_only_selected_y_axis_defaults_on_missing_key(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{}", encoding="utf-8")
    assert Settings(path=path).show_only_selected_y_axis is False


# ---------------------------------------------------------------------------
# keep_signals_on_load
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-FILE-030")
def test_keep_signals_on_load_default_is_always(settings: Settings) -> None:
    assert settings.keep_signals_on_load == "always"


@pytest.mark.requirement("REQ-FILE-030")
def test_keep_signals_on_load_can_be_set_to_ask(settings: Settings) -> None:
    settings.keep_signals_on_load = "ask"
    assert settings.keep_signals_on_load == "ask"


@pytest.mark.requirement("REQ-FILE-030")
def test_keep_signals_on_load_can_be_set_to_never(settings: Settings) -> None:
    settings.keep_signals_on_load = "never"
    assert settings.keep_signals_on_load == "never"


@pytest.mark.requirement("REQ-NFR-021")
def test_keep_signals_on_load_persists(settings: Settings) -> None:
    settings.keep_signals_on_load = "ask"
    reloaded = Settings(path=settings._path)
    assert reloaded.keep_signals_on_load == "ask"


@pytest.mark.requirement("REQ-FILE-030")
@pytest.mark.requirement("REQ-NFR-020")
def test_keep_signals_on_load_invalid_value_falls_back_to_default(settings: Settings) -> None:
    settings.keep_signals_on_load = "bogus"
    assert settings.keep_signals_on_load == "always"


@pytest.mark.requirement("REQ-NFR-020")
def test_keep_signals_on_load_defaults_on_missing_key(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{}", encoding="utf-8")
    assert Settings(path=path).keep_signals_on_load == "always"


# ---------------------------------------------------------------------------
# config_path_mode
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-FILE-063")
def test_config_path_mode_default_is_absolute(settings: Settings) -> None:
    assert settings.config_path_mode == "absolute"


@pytest.mark.requirement("REQ-FILE-063")
def test_config_path_mode_can_be_set_to_relative(settings: Settings) -> None:
    settings.config_path_mode = "relative"
    assert settings.config_path_mode == "relative"


@pytest.mark.requirement("REQ-FILE-063")
@pytest.mark.requirement("REQ-NFR-020")
def test_config_path_mode_invalid_falls_back_to_default(settings: Settings) -> None:
    settings.config_path_mode = "bogus"
    assert settings.config_path_mode == "absolute"


@pytest.mark.requirement("REQ-NFR-021")
def test_config_path_mode_persists(settings: Settings) -> None:
    settings.config_path_mode = "relative"
    reloaded = Settings(path=settings._path)
    assert reloaded.config_path_mode == "relative"


@pytest.mark.requirement("REQ-NFR-020")
def test_config_path_mode_defaults_on_missing_key(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{}", encoding="utf-8")
    assert Settings(path=path).config_path_mode == "absolute"


# ---------------------------------------------------------------------------
# signal_browser_view_mode
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-BROWSER-062")
def test_signal_browser_view_mode_default_is_flat(settings: Settings) -> None:
    assert settings.signal_browser_view_mode == "flat"


@pytest.mark.requirement("REQ-BROWSER-060")
def test_signal_browser_view_mode_can_be_set_to_tree(settings: Settings) -> None:
    settings.signal_browser_view_mode = "tree"
    assert settings.signal_browser_view_mode == "tree"


@pytest.mark.requirement("REQ-BROWSER-062")
@pytest.mark.requirement("REQ-NFR-020")
def test_signal_browser_view_mode_invalid_falls_back_to_default(settings: Settings) -> None:
    settings.signal_browser_view_mode = "bogus"
    assert settings.signal_browser_view_mode == "flat"


@pytest.mark.requirement("REQ-BROWSER-061")
def test_signal_browser_view_mode_persists(settings: Settings) -> None:
    settings.signal_browser_view_mode = "tree"
    reloaded = Settings(path=settings._path)
    assert reloaded.signal_browser_view_mode == "tree"


@pytest.mark.requirement("REQ-BROWSER-062")
def test_signal_browser_view_mode_defaults_on_missing_key(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{}", encoding="utf-8")
    assert Settings(path=path).signal_browser_view_mode == "flat"


@pytest.mark.requirement("REQ-BROWSER-062")
@pytest.mark.requirement("REQ-NFR-020")
def test_signal_browser_view_mode_corrupt_value_on_disk_falls_back_to_default(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"signal_browser_view_mode": "bogus"}), encoding="utf-8")
    assert Settings(path=path).signal_browser_view_mode == "flat"


# ---------------------------------------------------------------------------
# prompt_save_config_on_close
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-FILE-070")
def test_prompt_save_config_on_close_default_true(settings: Settings) -> None:
    assert settings.prompt_save_config_on_close is True


@pytest.mark.requirement("REQ-FILE-070")
def test_prompt_save_config_on_close_can_be_disabled(settings: Settings) -> None:
    settings.prompt_save_config_on_close = False
    assert settings.prompt_save_config_on_close is False


@pytest.mark.requirement("REQ-NFR-021")
def test_prompt_save_config_on_close_persists(settings: Settings) -> None:
    settings.prompt_save_config_on_close = False
    reloaded = Settings(path=settings._path)
    assert reloaded.prompt_save_config_on_close is False


@pytest.mark.requirement("REQ-NFR-020")
def test_prompt_save_config_on_close_defaults_on_missing_key(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{}", encoding="utf-8")
    assert Settings(path=path).prompt_save_config_on_close is True


# ---------------------------------------------------------------------------
# _default_config_path — per-user app-data convention (REQ-NFR-041)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-NFR-041")
def test_default_config_path_windows_uses_appdata(monkeypatch) -> None:
    from mdf_viewer.settings import _default_config_path
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.setenv("APPDATA", r"C:\Users\test\AppData\Roaming")
    path = _default_config_path()
    assert path == Path(r"C:\Users\test\AppData\Roaming") / "mdf-viewer" / "settings.json"


@pytest.mark.requirement("REQ-NFR-041")
def test_default_config_path_windows_falls_back_to_home_without_appdata(monkeypatch) -> None:
    from mdf_viewer.settings import _default_config_path
    monkeypatch.setattr("sys.platform", "win32")
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setattr(Path, "home", lambda: Path("/home/fallback"))
    path = _default_config_path()
    assert path == Path("/home/fallback") / "mdf-viewer" / "settings.json"


@pytest.mark.requirement("REQ-NFR-041")
def test_default_config_path_linux_uses_xdg_style_dir(monkeypatch) -> None:
    from mdf_viewer.settings import _default_config_path
    monkeypatch.setattr("sys.platform", "linux")
    monkeypatch.setattr(Path, "home", lambda: Path("/home/test"))
    path = _default_config_path()
    assert path == Path("/home/test") / ".config" / "mdf-viewer" / "settings.json"


# ---------------------------------------------------------------------------
# plugins_dir (#74)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLUGIN-252")
def test_plugins_dir_defaults_to_none(settings: Settings) -> None:
    assert settings.plugins_dir is None


def test_plugins_dir_round_trips_through_save_and_load(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    s1 = Settings(path=path)
    s1.plugins_dir = tmp_path / "custom_plugins"

    s2 = Settings(path=path)

    assert s2.plugins_dir == tmp_path / "custom_plugins"


def test_plugins_dir_setter_persists_immediately(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    s1 = Settings(path=path)
    s1.plugins_dir = tmp_path / "custom_plugins"

    raw = json.loads(path.read_text(encoding="utf-8"))

    assert raw["plugins_dir"] == str(tmp_path / "custom_plugins")


def test_plugins_dir_handles_missing_key_in_saved_file(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"check_for_updates": False}), encoding="utf-8")

    s = Settings(path=path)

    assert s.plugins_dir is None


# ---------------------------------------------------------------------------
# Per-plugin settings (#159)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLUGIN-410")
def test_get_plugin_setting_returns_default_when_never_set(settings: Settings) -> None:
    assert settings.get_plugin_setting("my_plugin", "threshold", 42) == 42


@pytest.mark.requirement("REQ-PLUGIN-412")
def test_get_plugin_setting_does_not_persist_a_read(settings: Settings, monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(settings, "_save", lambda: calls.append(1))

    settings.get_plugin_setting("my_plugin", "threshold", 42)

    assert calls == []


@pytest.mark.requirement("REQ-PLUGIN-410")
def test_set_plugin_setting_then_get_returns_value(settings: Settings) -> None:
    settings.set_plugin_setting("my_plugin", "threshold", 42)
    assert settings.get_plugin_setting("my_plugin", "threshold", None) == 42


@pytest.mark.requirement("REQ-PLUGIN-410")
def test_set_plugin_setting_namespaces_by_plugin_name(settings: Settings) -> None:
    settings.set_plugin_setting("plugin_a", "key", "a-value")
    settings.set_plugin_setting("plugin_b", "key", "b-value")

    assert settings.get_plugin_setting("plugin_a", "key", None) == "a-value"
    assert settings.get_plugin_setting("plugin_b", "key", None) == "b-value"


@pytest.mark.requirement("REQ-PLUGIN-410")
def test_set_plugin_setting_persists_across_reload(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    s1 = Settings(path=path)
    s1.set_plugin_setting("my_plugin", "threshold", 42)

    s2 = Settings(path=path)

    assert s2.get_plugin_setting("my_plugin", "threshold", None) == 42


@pytest.mark.requirement("REQ-PLUGIN-411")
def test_set_plugin_setting_rejects_non_str_key(settings: Settings, caplog) -> None:
    settings.set_plugin_setting("my_plugin", 1, "value")
    assert settings.get_plugin_setting("my_plugin", 1, "missing") == "missing"
    assert "my_plugin" in caplog.text


@pytest.mark.requirement("REQ-PLUGIN-411")
def test_set_plugin_setting_rejects_empty_str_key(settings: Settings, caplog) -> None:
    settings.set_plugin_setting("my_plugin", "", "value")
    assert settings.get_plugin_setting("my_plugin", "", "missing") == "missing"


@pytest.mark.requirement("REQ-PLUGIN-411")
def test_set_plugin_setting_rejects_non_json_safe_value(settings: Settings, caplog) -> None:
    settings.set_plugin_setting("my_plugin", "key", {1, 2, 3})
    assert settings.get_plugin_setting("my_plugin", "key", "missing") == "missing"
    assert "my_plugin" in caplog.text


@pytest.mark.requirement("REQ-PLUGIN-411")
def test_set_plugin_setting_rejects_non_str_dict_keys_nested_in_value(
    settings: Settings, caplog
) -> None:
    settings.set_plugin_setting("my_plugin", "key", {1: "x"})
    assert settings.get_plugin_setting("my_plugin", "key", "missing") == "missing"


@pytest.mark.requirement("REQ-PLUGIN-411")
def test_set_plugin_setting_rejects_nan_and_infinity_floats(settings: Settings) -> None:
    settings.set_plugin_setting("my_plugin", "key", float("nan"))
    settings.set_plugin_setting("my_plugin", "other", float("inf"))
    assert settings.get_plugin_setting("my_plugin", "key", "missing") == "missing"
    assert settings.get_plugin_setting("my_plugin", "other", "missing") == "missing"


@pytest.mark.requirement("REQ-PLUGIN-411")
def test_set_plugin_setting_accepts_nested_list_and_dict_of_primitives(
    settings: Settings,
) -> None:
    value = {"a": [1, 2.5, True, None, {"nested": "ok"}]}
    settings.set_plugin_setting("my_plugin", "key", value)
    assert settings.get_plugin_setting("my_plugin", "key", None) == value


@pytest.mark.requirement("REQ-PLUGIN-410")
def test_load_falls_back_to_empty_dict_when_plugin_settings_key_is_malformed(
    tmp_path: Path,
) -> None:
    path = tmp_path / "settings.json"
    path.write_text(
        json.dumps({"check_for_updates": False, "plugin_settings": ["not", "a", "dict"]}),
        encoding="utf-8",
    )

    s = Settings(path=path)

    assert s.get_plugin_setting("anything", "key", "missing") == "missing"


def test_plugin_settings_defaults_on_missing_key(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"check_for_updates": False}), encoding="utf-8")

    s = Settings(path=path)

    assert s.get_plugin_setting("anything", "key", "missing") == "missing"


# ---------------------------------------------------------------------------
# disabled_plugins / Plugin Overview (#160)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLUGIN-471")
def test_disabled_plugins_defaults_to_empty(settings: Settings) -> None:
    assert settings.disabled_plugins == set()
    assert settings.is_plugin_disabled("some_plugin") is False


@pytest.mark.requirement("REQ-PLUGIN-470")
def test_set_plugin_disabled_round_trips_through_save_and_load(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    s1 = Settings(path=path)
    s1.set_plugin_disabled("broken_plugin", True)

    s2 = Settings(path=path)

    assert s2.is_plugin_disabled("broken_plugin") is True
    assert s2.disabled_plugins == {"broken_plugin"}


@pytest.mark.requirement("REQ-PLUGIN-470")
def test_set_plugin_disabled_persists_immediately(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    s = Settings(path=path)
    s.set_plugin_disabled("broken_plugin", True)

    raw = json.loads(path.read_text(encoding="utf-8"))

    assert raw["disabled_plugins"] == ["broken_plugin"]


def test_set_plugin_disabled_false_removes_from_set(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    s = Settings(path=path)
    s.set_plugin_disabled("broken_plugin", True)
    s.set_plugin_disabled("broken_plugin", False)

    assert s.is_plugin_disabled("broken_plugin") is False
    assert s.disabled_plugins == set()


def test_disabled_plugins_handles_missing_key_in_saved_file(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"check_for_updates": False}), encoding="utf-8")

    s = Settings(path=path)

    assert s.disabled_plugins == set()


@pytest.mark.requirement("REQ-PLUGIN-510")
def test_prune_disabled_plugins_removes_stale_entries(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    s = Settings(path=path)
    s.set_plugin_disabled("gone", True)
    s.set_plugin_disabled("still_here", True)

    s.prune_disabled_plugins({"still_here"})

    assert s.disabled_plugins == {"still_here"}


@pytest.mark.requirement("REQ-PLUGIN-510")
def test_prune_disabled_plugins_persists_the_removal(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    s1 = Settings(path=path)
    s1.set_plugin_disabled("gone", True)
    s1.prune_disabled_plugins(set())

    s2 = Settings(path=path)

    assert s2.disabled_plugins == set()


def test_prune_disabled_plugins_noop_does_not_resave(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    s = Settings(path=path)
    s.set_plugin_disabled("still_here", True)
    mtime_before = path.stat().st_mtime_ns

    s.prune_disabled_plugins({"still_here"})

    assert path.stat().st_mtime_ns == mtime_before


# ---------------------------------------------------------------------------
# keymap / keymap_preset_label (#111)
# ---------------------------------------------------------------------------

def test_keymap_defaults_to_empty_dict(settings: Settings) -> None:
    assert settings.keymap == {}


def test_keymap_preset_label_defaults_to_default(settings: Settings) -> None:
    assert settings.keymap_preset_label == "Default"


def test_cursor_value_display_defaults_to_active(settings: Settings) -> None:
    assert settings.cursor_value_display == "active"


@pytest.mark.requirement("REQ-PLOT-080")
def test_cursor_value_display_round_trips_through_save_and_load(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    s1 = Settings(path=path)
    s1.cursor_value_display = "both"

    s2 = Settings(path=path)

    assert s2.cursor_value_display == "both"


@pytest.mark.requirement("REQ-KEYS-060")
def test_keymap_round_trips_through_save_and_load(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    s1 = Settings(path=path)
    s1.keymap = {"undo": {"primary": "Ctrl+Z", "secondary": None}}

    s2 = Settings(path=path)

    assert s2.keymap == {"undo": {"primary": "Ctrl+Z", "secondary": None}}


@pytest.mark.requirement("REQ-KEYS-061")
def test_keymap_preset_label_round_trips_through_save_and_load(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    s1 = Settings(path=path)
    s1.keymap_preset_label = "CANape"

    s2 = Settings(path=path)

    assert s2.keymap_preset_label == "CANape"


def test_keymap_setter_persists_immediately(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    s = Settings(path=path)
    s.keymap = {"undo": {"primary": "Ctrl+Z", "secondary": None}}

    raw = json.loads(path.read_text(encoding="utf-8"))

    assert raw["keymap"] == {"undo": {"primary": "Ctrl+Z", "secondary": None}}
    assert raw["keymap_preset_label"] == "Default"


def test_keymap_falls_back_to_empty_dict_when_malformed(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"keymap": ["not", "a", "dict"]}), encoding="utf-8")

    s = Settings(path=path)

    assert s.keymap == {}


def test_keymap_defaults_on_missing_key(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text(json.dumps({"check_for_updates": False}), encoding="utf-8")

    s = Settings(path=path)

    assert s.keymap == {}
    assert s.keymap_preset_label == "Default"
