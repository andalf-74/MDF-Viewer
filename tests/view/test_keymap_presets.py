"""Tests for keymap_presets.py (#111)."""

from __future__ import annotations

import pytest

from mdf_viewer.view import keymap_presets as kp


def test_all_three_presets_cover_every_action_id() -> None:
    for preset in (kp.DEFAULT_PRESET, kp.MDA_PRESET, kp.CANAPE_PRESET):
        assert set(preset.keys()) == set(kp.ACTION_IDS)


def test_default_zoom_to_fit_keeps_both_bindings() -> None:
    primary, secondary = kp.DEFAULT_PRESET["zoom_to_fit"]
    assert primary.toString() == "Ctrl+0"
    assert secondary.toString() == "F"


def test_default_move_to_new_stripe_starts_unbound() -> None:
    assert kp.DEFAULT_PRESET["ast_move_to_new_stripe"][0].isEmpty()


@pytest.mark.requirement("REQ-KEYS-015")
def test_default_cursor_toggle_is_ctrl_r_in_all_presets() -> None:
    for preset in (kp.DEFAULT_PRESET, kp.MDA_PRESET, kp.CANAPE_PRESET):
        assert preset["cursor_toggle"][0].toString() == "Ctrl+R"


@pytest.mark.requirement("REQ-KEYS-013")
def test_167_actions_share_one_default_across_all_presets() -> None:
    shared = {
        "save_workspace_as": "Ctrl+Shift+S",
        "new_stripe": "Ctrl+Shift+N",
        "sync_measurements": "Ctrl+M",
        "preferences": "Ctrl+,",
    }
    for action_id, expected in shared.items():
        for preset in (kp.DEFAULT_PRESET, kp.MDA_PRESET, kp.CANAPE_PRESET):
            assert preset[action_id][0].toString() == expected


@pytest.mark.requirement("REQ-KEYS-014")
def test_new_tab_differs_only_in_mda_preset() -> None:
    assert kp.DEFAULT_PRESET["new_tab"][0].toString() == "Ctrl+T"
    assert kp.CANAPE_PRESET["new_tab"][0].toString() == "Ctrl+T"
    assert kp.MDA_PRESET["new_tab"][0].toString() == "Ctrl+N"


@pytest.mark.requirement("REQ-SEARCH-011")
def test_default_search_binding_is_ctrl_f() -> None:
    primary, secondary = kp.DEFAULT_PRESET["search"]
    assert primary.toString() == "Ctrl+F"
    assert secondary is None


@pytest.mark.requirement("REQ-KEYS-022")
def test_mda_preset_overrides_only_its_five_actions() -> None:
    overridden = {
        "zoom_to_fit": "Ctrl+F12",
        "ast_y_autozoom": "Ctrl+D",
        "ast_toggle_visibility": "Ctrl+W",
        "ast_move_to_new_stripe": "Ctrl+T",
        "new_tab": "Ctrl+N",
    }
    for action_id in kp.ACTION_IDS:
        primary, secondary = kp.MDA_PRESET[action_id]
        if action_id in overridden:
            assert primary.toString() == overridden[action_id]
            assert secondary is None
        else:
            assert kp.MDA_PRESET[action_id] == kp.DEFAULT_PRESET[action_id]


@pytest.mark.requirement("REQ-KEYS-023")
def test_canape_preset_overrides_only_its_eight_actions() -> None:
    overridden = {
        "zoom_to_fit": "F",
        "swimlanes": "Ctrl+B",
        "save_workspace": "F2",
        "exit": "Alt+X",
        "cursor1_toggle": ".",
        "cursor2_toggle": ",",
        "cursor_step_left": "Ctrl+Left",
        "cursor_step_right": "Ctrl+Right",
    }
    for action_id in kp.ACTION_IDS:
        primary, secondary = kp.CANAPE_PRESET[action_id]
        if action_id in overridden:
            assert primary.toString() == overridden[action_id]
        else:
            assert kp.CANAPE_PRESET[action_id] == kp.DEFAULT_PRESET[action_id]


def test_builtin_presets_dict_has_all_three() -> None:
    assert set(kp.BUILTIN_PRESETS) == {"Default", "MDA", "CANape"}


# ---------------------------------------------------------------------------
# resolve_keymap() (#167 postmortem — stale built-in-preset snapshots)
# ---------------------------------------------------------------------------

def test_resolve_keymap_ignores_stale_value_under_a_builtin_preset_label() -> None:
    """A stored dict claiming a stale (pre-change) value for an action
    under a still-"Default"-labelled settings file must be overridden by
    the live DEFAULT_PRESET, not honoured."""
    stale = kp.keymap_to_dict(kp.DEFAULT_PRESET)
    stale["cursor_toggle"] = {"primary": "", "secondary": None}
    resolved = kp.resolve_keymap(stale, "Default")
    assert resolved["cursor_toggle"][0].toString() == "Ctrl+R"


def test_resolve_keymap_uses_live_mda_preset() -> None:
    resolved = kp.resolve_keymap({}, "MDA")
    assert resolved["new_tab"][0].toString() == "Ctrl+N"


def test_resolve_keymap_honours_a_real_customization() -> None:
    custom = kp.keymap_to_dict(kp.DEFAULT_PRESET)
    custom["undo"] = {"primary": "Ctrl+9", "secondary": None}
    resolved = kp.resolve_keymap(custom, "Custom")
    assert resolved["undo"][0].toString() == "Ctrl+9"


def test_resolve_keymap_honours_a_loaded_mvck_labels_own_values() -> None:
    """A loaded .mvck file's label (e.g. "My CANape Copy") is never a
    built-in preset name, so its own stored values stay frozen even if
    they happen to equal an outdated built-in preset's old values."""
    custom = kp.keymap_to_dict(kp.DEFAULT_PRESET)
    custom["cursor_toggle"] = {"primary": "", "secondary": None}
    resolved = kp.resolve_keymap(custom, "My CANape Copy")
    assert resolved["cursor_toggle"][0].isEmpty()


# ---------------------------------------------------------------------------
# keymap_to_dict / keymap_from_dict round-trip
# ---------------------------------------------------------------------------

def test_round_trip_preserves_bindings() -> None:
    data = kp.keymap_to_dict(kp.DEFAULT_PRESET)
    restored = kp.keymap_from_dict(data)
    for action_id in kp.ACTION_IDS:
        orig_primary, orig_secondary = kp.DEFAULT_PRESET[action_id]
        new_primary, new_secondary = restored[action_id]
        assert new_primary.toString() == orig_primary.toString()
        orig_sec_str = orig_secondary.toString() if orig_secondary else None
        new_sec_str = new_secondary.toString() if new_secondary else None
        assert new_sec_str == orig_sec_str


def test_keymap_from_dict_falls_back_to_default_for_missing_action() -> None:
    data = kp.keymap_to_dict(kp.DEFAULT_PRESET)
    del data["undo"]
    restored = kp.keymap_from_dict(data)
    assert restored["undo"][0].toString() == kp.DEFAULT_PRESET["undo"][0].toString()


def test_keymap_from_dict_ignores_unknown_action_id() -> None:
    data = kp.keymap_to_dict(kp.DEFAULT_PRESET)
    data["totally_unknown_action"] = {"primary": "Ctrl+9", "secondary": None}
    restored = kp.keymap_from_dict(data)
    assert "totally_unknown_action" not in restored


# ---------------------------------------------------------------------------
# save_mvck / load_mvck
# ---------------------------------------------------------------------------

def test_save_and_load_mvck_round_trip(tmp_path) -> None:
    path = tmp_path / "mine.mvck"
    kp.save_mvck(path, kp.CANAPE_PRESET, "My CANape Copy")
    keymap, label = kp.load_mvck(path)
    assert label == "My CANape Copy"
    assert keymap["zoom_to_fit"][0].toString() == "F"


def test_load_mvck_missing_label_falls_back_to_filename(tmp_path) -> None:
    path = tmp_path / "unlabeled.mvck"
    path.write_text('{"keymap": {}}', encoding="utf-8")
    _, label = kp.load_mvck(path)
    assert label == "unlabeled"


def test_load_mvck_raises_on_unreadable_file(tmp_path) -> None:
    path = tmp_path / "does_not_exist.mvck"
    with pytest.raises(kp.KeymapValidationError):
        kp.load_mvck(path)


def test_load_mvck_raises_on_invalid_json(tmp_path) -> None:
    path = tmp_path / "bad.mvck"
    path.write_text("not json at all", encoding="utf-8")
    with pytest.raises(kp.KeymapValidationError):
        kp.load_mvck(path)


def test_load_mvck_raises_on_missing_keymap_key(tmp_path) -> None:
    path = tmp_path / "bad_shape.mvck"
    path.write_text('{"label": "X"}', encoding="utf-8")
    with pytest.raises(kp.KeymapValidationError):
        kp.load_mvck(path)


def test_load_mvck_raises_when_keymap_entry_is_not_a_dict(tmp_path) -> None:
    path = tmp_path / "bad_entry.mvck"
    path.write_text('{"keymap": {"undo": "not-a-dict"}}', encoding="utf-8")
    with pytest.raises(kp.KeymapValidationError):
        kp.load_mvck(path)
