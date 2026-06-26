"""Tests for Settings — recent files persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from mdf_viewer.settings import (
    DEFAULT_CURSOR_COLOR_C1,
    DEFAULT_CURSOR_COLOR_C2,
    DEFAULT_CURSOR_COLOR_CL,
    DEFAULT_CURSOR_COLOR_CR,
    MAX_RECENT,
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

def test_add_recent_adds_to_front(settings: Settings, tmp_path: Path) -> None:
    a, b = tmp_path / "a.mf4", tmp_path / "b.mf4"
    a.touch()
    b.touch()
    settings.add_recent(a)
    settings.add_recent(b)
    assert settings.recent_files()[0] == b.resolve()


def test_add_recent_deduplicates(settings: Settings, tmp_path: Path) -> None:
    p = tmp_path / "file.mf4"
    p.touch()
    settings.add_recent(p)
    settings.add_recent(p)
    assert len(settings.recent_files()) == 1


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


def test_add_recent_trims_to_max(settings: Settings, tmp_path: Path) -> None:
    for i in range(MAX_RECENT + 2):
        p = tmp_path / f"{i}.mf4"
        p.touch()
        settings.add_recent(p)
    assert len(settings.recent_files()) == MAX_RECENT


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

def test_load_handles_missing_file(tmp_path: Path) -> None:
    s = Settings(path=tmp_path / "nonexistent" / "settings.json")
    assert s.recent_files() == []


def test_load_handles_invalid_json(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("not valid json", encoding="utf-8")
    assert Settings(path=path).recent_files() == []


def test_load_handles_missing_key(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{}", encoding="utf-8")
    assert Settings(path=path).recent_files() == []


# ---------------------------------------------------------------------------
# get_and_prune
# ---------------------------------------------------------------------------

def test_get_and_prune_returns_only_existing(
    settings: Settings, tmp_path: Path
) -> None:
    existing = tmp_path / "exists.mf4"
    missing = tmp_path / "gone.mf4"
    existing.touch()
    settings.add_recent(missing)
    settings.add_recent(existing)
    assert settings.get_and_prune() == [existing.resolve()]


def test_get_and_prune_saves_pruned_list(settings: Settings, tmp_path: Path) -> None:
    existing = tmp_path / "exists.mf4"
    missing = tmp_path / "gone.mf4"
    existing.touch()
    settings.add_recent(missing)
    settings.add_recent(existing)
    settings.get_and_prune()
    assert Settings(path=settings._path).recent_files() == [existing.resolve()]


def test_get_and_prune_noop_when_all_exist(
    settings: Settings, tmp_path: Path
) -> None:
    p = tmp_path / "file.mf4"
    p.touch()
    settings.add_recent(p)
    result = settings.get_and_prune()
    assert result == [p.resolve()]


def test_get_and_prune_empty_list(settings: Settings) -> None:
    assert settings.get_and_prune() == []


# ---------------------------------------------------------------------------
# check_for_updates
# ---------------------------------------------------------------------------

def test_check_for_updates_default_true(settings: Settings) -> None:
    assert settings.check_for_updates is True


def test_check_for_updates_can_be_disabled(settings: Settings) -> None:
    settings.check_for_updates = False
    assert settings.check_for_updates is False


def test_check_for_updates_persists(settings: Settings) -> None:
    settings.check_for_updates = False
    reloaded = Settings(path=settings._path)
    assert reloaded.check_for_updates is False


def test_check_for_updates_defaults_to_true_on_missing_key(tmp_path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{}", encoding="utf-8")
    assert Settings(path=path).check_for_updates is True


# ---------------------------------------------------------------------------
# cursor_persistent
# ---------------------------------------------------------------------------

def test_cursor_persistent_default_true(settings: Settings) -> None:
    assert settings.cursor_persistent is True


def test_cursor_persistent_can_be_disabled(settings: Settings) -> None:
    settings.cursor_persistent = False
    assert settings.cursor_persistent is False


def test_cursor_persistent_persists(settings: Settings) -> None:
    settings.cursor_persistent = False
    reloaded = Settings(path=settings._path)
    assert reloaded.cursor_persistent is False


def test_cursor_persistent_defaults_to_true_on_missing_key(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{}", encoding="utf-8")
    assert Settings(path=path).cursor_persistent is True


# ---------------------------------------------------------------------------
# cursor_mode
# ---------------------------------------------------------------------------

def test_cursor_mode_default_12(settings: Settings) -> None:
    assert settings.cursor_mode == "1/2"


def test_cursor_mode_can_be_changed(settings: Settings) -> None:
    settings.cursor_mode = "L/R"
    assert settings.cursor_mode == "L/R"


def test_cursor_mode_persists(settings: Settings) -> None:
    settings.cursor_mode = "L/R"
    reloaded = Settings(path=settings._path)
    assert reloaded.cursor_mode == "L/R"


def test_cursor_mode_defaults_to_12_on_missing_key(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{}", encoding="utf-8")
    assert Settings(path=path).cursor_mode == "1/2"


# ---------------------------------------------------------------------------
# cursor colors
# ---------------------------------------------------------------------------

def test_cursor_colors_default(settings: Settings) -> None:
    assert settings.cursor_color_c1 == DEFAULT_CURSOR_COLOR_C1
    assert settings.cursor_color_c2 == DEFAULT_CURSOR_COLOR_C2
    assert settings.cursor_color_cl == DEFAULT_CURSOR_COLOR_CL
    assert settings.cursor_color_cr == DEFAULT_CURSOR_COLOR_CR


def test_cursor_colors_can_be_changed(settings: Settings) -> None:
    settings.cursor_color_c1 = (1, 2, 3)
    settings.cursor_color_c2 = (4, 5, 6)
    settings.cursor_color_cl = (7, 8, 9)
    settings.cursor_color_cr = (10, 11, 12)
    assert settings.cursor_color_c1 == (1, 2, 3)
    assert settings.cursor_color_c2 == (4, 5, 6)
    assert settings.cursor_color_cl == (7, 8, 9)
    assert settings.cursor_color_cr == (10, 11, 12)


def test_cursor_colors_persist(settings: Settings) -> None:
    settings.cursor_color_c1 = (1, 2, 3)
    settings.cursor_color_cr = (10, 11, 12)
    reloaded = Settings(path=settings._path)
    assert reloaded.cursor_color_c1 == (1, 2, 3)
    assert reloaded.cursor_color_cr == (10, 11, 12)


def test_cursor_colors_default_on_missing_key(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{}", encoding="utf-8")
    s = Settings(path=path)
    assert s.cursor_color_c1 == DEFAULT_CURSOR_COLOR_C1
    assert s.cursor_color_cr == DEFAULT_CURSOR_COLOR_CR


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

def test_show_delta_time_default_true(settings: Settings) -> None:
    assert settings.show_delta_time_in_plot is True


def test_show_delta_time_can_be_disabled(settings: Settings) -> None:
    settings.show_delta_time_in_plot = False
    assert settings.show_delta_time_in_plot is False


def test_show_delta_time_persists(settings: Settings) -> None:
    settings.show_delta_time_in_plot = False
    reloaded = Settings(path=settings._path)
    assert reloaded.show_delta_time_in_plot is False


def test_show_delta_time_defaults_on_missing_key(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{}", encoding="utf-8")
    assert Settings(path=path).show_delta_time_in_plot is True


def test_delta_time_color_default(settings: Settings) -> None:
    from mdf_viewer.settings import DEFAULT_DELTA_TIME_COLOR
    assert settings.delta_time_color == DEFAULT_DELTA_TIME_COLOR


def test_delta_time_color_can_be_changed(settings: Settings) -> None:
    settings.delta_time_color = (1, 2, 3)
    assert settings.delta_time_color == (1, 2, 3)


def test_delta_time_color_persists(settings: Settings) -> None:
    settings.delta_time_color = (1, 2, 3)
    reloaded = Settings(path=settings._path)
    assert reloaded.delta_time_color == (1, 2, 3)


# ---------------------------------------------------------------------------
# max_undo_steps
# ---------------------------------------------------------------------------

def test_max_undo_steps_default(settings: Settings) -> None:
    from mdf_viewer.settings import DEFAULT_MAX_UNDO_STEPS
    assert settings.max_undo_steps == DEFAULT_MAX_UNDO_STEPS


def test_max_undo_steps_default_is_1(settings: Settings) -> None:
    assert settings.max_undo_steps == 1


def test_max_undo_steps_can_be_changed(settings: Settings) -> None:
    settings.max_undo_steps = 10
    assert settings.max_undo_steps == 10


def test_max_undo_steps_persists(settings: Settings) -> None:
    settings.max_undo_steps = 5
    reloaded = Settings(path=settings._path)
    assert reloaded.max_undo_steps == 5


def test_max_undo_steps_clamps_below_1(settings: Settings) -> None:
    settings.max_undo_steps = 0
    assert settings.max_undo_steps == 1


def test_max_undo_steps_defaults_on_missing_key(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{}", encoding="utf-8")
    assert Settings(path=path).max_undo_steps == 1


# signal_z_order


def test_signal_z_order_default(settings: Settings) -> None:
    from mdf_viewer.settings import DEFAULT_SIGNAL_Z_ORDER
    assert settings.signal_z_order == DEFAULT_SIGNAL_Z_ORDER


def test_signal_z_order_default_is_top_first(settings: Settings) -> None:
    assert settings.signal_z_order == "top_first"


def test_signal_z_order_can_be_changed(settings: Settings) -> None:
    settings.signal_z_order = "bottom_first"
    assert settings.signal_z_order == "bottom_first"


def test_signal_z_order_persists(settings: Settings) -> None:
    settings.signal_z_order = "bottom_first"
    reloaded = Settings(path=settings._path)
    assert reloaded.signal_z_order == "bottom_first"


def test_signal_z_order_defaults_on_missing_key(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{}", encoding="utf-8")
    assert Settings(path=path).signal_z_order == "top_first"


# selected_line_boost


def test_selected_line_boost_default(settings: Settings) -> None:
    from mdf_viewer.settings import DEFAULT_SELECTED_LINE_BOOST
    assert settings.selected_line_boost == DEFAULT_SELECTED_LINE_BOOST


def test_selected_line_boost_default_is_1(settings: Settings) -> None:
    assert settings.selected_line_boost == 1


def test_selected_line_boost_can_be_changed(settings: Settings) -> None:
    settings.selected_line_boost = 3
    assert settings.selected_line_boost == 3


def test_selected_line_boost_persists(settings: Settings) -> None:
    settings.selected_line_boost = 3
    reloaded = Settings(path=settings._path)
    assert reloaded.selected_line_boost == 3


def test_selected_line_boost_zero_allowed(settings: Settings) -> None:
    settings.selected_line_boost = 0
    assert settings.selected_line_boost == 0


def test_selected_line_boost_clamps_above_5(settings: Settings) -> None:
    settings.selected_line_boost = 99
    assert settings.selected_line_boost == 5


def test_selected_line_boost_clamps_below_0(settings: Settings) -> None:
    settings.selected_line_boost = -1
    assert settings.selected_line_boost == 0


def test_selected_line_boost_defaults_on_missing_key(tmp_path: Path) -> None:
    path = tmp_path / "settings.json"
    path.write_text("{}", encoding="utf-8")
    assert Settings(path=path).selected_line_boost == 1


# ---------------------------------------------------------------------------
# display name rule settings
# ---------------------------------------------------------------------------

def test_display_name_rule_enabled_default_false(settings: Settings) -> None:
    assert settings.display_name_rule_enabled is False


def test_display_name_separator_default(settings: Settings) -> None:
    assert settings.display_name_separator == "."


def test_display_name_direction_default(settings: Settings) -> None:
    assert settings.display_name_direction == "right"


def test_display_name_segments_default(settings: Settings) -> None:
    assert settings.display_name_segments == 1


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


def test_display_name_segments_clamps(settings: Settings) -> None:
    settings.display_name_segments = 0
    assert settings.display_name_segments == 1
    settings.display_name_segments = 99
    assert settings.display_name_segments == 10


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

def test_apply_rule_disabled_returns_full_name(settings: Settings) -> None:
    from mdf_viewer.settings import apply_display_name_rule
    settings.display_name_rule_enabled = False
    assert apply_display_name_rule("a.b.c", settings) == "a.b.c"


def test_apply_rule_right_one_segment(settings: Settings) -> None:
    from mdf_viewer.settings import apply_display_name_rule
    settings.display_name_rule_enabled = True
    settings.display_name_separator = "."
    settings.display_name_direction = "right"
    settings.display_name_segments = 1
    assert apply_display_name_rule("ZF_DTI._.AutoDiagPosition.PosADP", settings) == "PosADP"


def test_apply_rule_right_two_segments(settings: Settings) -> None:
    from mdf_viewer.settings import apply_display_name_rule
    settings.display_name_rule_enabled = True
    settings.display_name_separator = "."
    settings.display_name_direction = "right"
    settings.display_name_segments = 2
    assert apply_display_name_rule("ZF_DTI._.AutoDiagPosition.PosADP", settings) == "AutoDiagPosition.PosADP"


def test_apply_rule_left_one_segment(settings: Settings) -> None:
    from mdf_viewer.settings import apply_display_name_rule
    settings.display_name_rule_enabled = True
    settings.display_name_separator = "."
    settings.display_name_direction = "left"
    settings.display_name_segments = 1
    assert apply_display_name_rule("ZF_DTI._.AutoDiagPosition.PosADP", settings) == "ZF_DTI"


def test_apply_rule_separator_not_found_returns_full_name(settings: Settings) -> None:
    from mdf_viewer.settings import apply_display_name_rule
    settings.display_name_rule_enabled = True
    settings.display_name_separator = "/"
    assert apply_display_name_rule("no_slash_here", settings) == "no_slash_here"


def test_apply_rule_empty_separator_returns_full_name(settings: Settings) -> None:
    from mdf_viewer.settings import apply_display_name_rule
    settings.display_name_rule_enabled = True
    settings.display_name_separator = ""
    assert apply_display_name_rule("a.b.c", settings) == "a.b.c"


def test_apply_rule_segments_exceeds_parts_returns_all(settings: Settings) -> None:
    from mdf_viewer.settings import apply_display_name_rule
    settings.display_name_rule_enabled = True
    settings.display_name_separator = "."
    settings.display_name_direction = "right"
    settings.display_name_segments = 10
    assert apply_display_name_rule("a.b", settings) == "a.b"
