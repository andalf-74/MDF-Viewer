"""Tests for PreferencesDialog's Shortcuts tab (#111)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest
from pytestqt.qtbot import QtBot

from PyQt6.QtGui import QKeySequence

from mdf_viewer.settings import Settings
from mdf_viewer.view.keymap_presets import ACTION_IDS, DEFAULT_PRESET, keymap_to_dict
from mdf_viewer.view.preferences_dialog import PreferencesDialog


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    return Settings(path=tmp_path / "settings.json")


@pytest.fixture()
def dlg(qtbot: QtBot, settings: Settings) -> PreferencesDialog:
    d = PreferencesDialog(settings)
    qtbot.addWidget(d)
    return d


# ---------------------------------------------------------------------------
# Row population
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-KEYS-051")
def test_every_action_has_a_row(dlg: PreferencesDialog) -> None:
    assert set(dlg._keymap_row_widgets.keys()) == set(ACTION_IDS)


def test_rows_initialised_from_default_preset(dlg: PreferencesDialog) -> None:
    primary_edit, secondary_edit = dlg._keymap_row_widgets["zoom_to_fit"]
    assert primary_edit.keySequence() == QKeySequence("Ctrl+0")
    assert secondary_edit.keySequence() == QKeySequence("F")


def test_rows_initialised_from_saved_settings(qtbot: QtBot, settings: Settings) -> None:
    settings.keymap = {"undo": {"primary": "Ctrl+9", "secondary": None}}
    dlg = PreferencesDialog(settings)
    qtbot.addWidget(dlg)
    primary_edit, _ = dlg._keymap_row_widgets["undo"]
    assert primary_edit.keySequence() == QKeySequence("Ctrl+9")


@pytest.mark.requirement("REQ-KEYS-061")
def test_status_label_starts_as_default(dlg: PreferencesDialog) -> None:
    assert "Default" in dlg._keymap_status_label.text()


# ---------------------------------------------------------------------------
# Rebinding + _apply()
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-KEYS-052")
def test_rebind_field_updates_working_copy(dlg: PreferencesDialog) -> None:
    primary_edit, _ = dlg._keymap_row_widgets["undo"]
    primary_edit.setKeySequence(QKeySequence("Ctrl+9"))
    dlg._on_keymap_field_edited("undo", "primary")
    assert dlg._keymap_working["undo"][0] == QKeySequence("Ctrl+9")


@pytest.mark.requirement("REQ-KEYS-060")
def test_apply_persists_the_working_copy(dlg: PreferencesDialog, settings: Settings) -> None:
    primary_edit, _ = dlg._keymap_row_widgets["undo"]
    primary_edit.setKeySequence(QKeySequence("Ctrl+9"))
    dlg._on_keymap_field_edited("undo", "primary")
    dlg._apply()
    assert settings.keymap["undo"] == {"primary": "Ctrl+9", "secondary": None}


@pytest.mark.requirement("REQ-KEYS-061")
def test_rebind_sets_status_label_to_custom(dlg: PreferencesDialog) -> None:
    primary_edit, _ = dlg._keymap_row_widgets["undo"]
    primary_edit.setKeySequence(QKeySequence("Ctrl+9"))
    dlg._on_keymap_field_edited("undo", "primary")
    assert dlg._keymap_status_label.text() == "Current: Custom"


def test_clearing_a_field_unbinds_it(dlg: PreferencesDialog) -> None:
    primary_edit, _ = dlg._keymap_row_widgets["zoom_y_to_view"]
    primary_edit.setKeySequence(QKeySequence())
    dlg._on_keymap_field_edited("zoom_y_to_view", "primary")
    assert dlg._keymap_working["zoom_y_to_view"][0].isEmpty()


def test_setting_secondary_to_empty_stores_none(dlg: PreferencesDialog) -> None:
    _, secondary_edit = dlg._keymap_row_widgets["zoom_to_fit"]
    secondary_edit.setKeySequence(QKeySequence())
    dlg._on_keymap_field_edited("zoom_to_fit", "secondary")
    assert dlg._keymap_working["zoom_to_fit"][1] is None


# ---------------------------------------------------------------------------
# Conflict handling (REQ-KEYS-040)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-KEYS-040")
def test_conflicting_rebind_is_blocked_and_reverted(dlg: PreferencesDialog) -> None:
    undo_primary, _ = dlg._keymap_row_widgets["undo"]
    redo_primary, _ = dlg._keymap_row_widgets["redo"]
    # Try to bind Undo to Redo's existing key (Ctrl+Shift+Z).
    undo_primary.setKeySequence(QKeySequence("Ctrl+Shift+Z"))

    with patch("mdf_viewer.view.preferences_dialog.QMessageBox.warning") as mock_warning:
        dlg._on_keymap_field_edited("undo", "primary")

    mock_warning.assert_called_once()
    assert dlg._keymap_working["undo"][0] == QKeySequence("Ctrl+Z")  # unchanged
    assert undo_primary.keySequence() == QKeySequence("Ctrl+Z")  # field reverted


@pytest.mark.requirement("REQ-KEYS-040")
def test_conflict_message_names_the_other_action(dlg: PreferencesDialog) -> None:
    undo_primary, _ = dlg._keymap_row_widgets["undo"]
    undo_primary.setKeySequence(QKeySequence("Ctrl+Shift+Z"))

    with patch("mdf_viewer.view.preferences_dialog.QMessageBox.warning") as mock_warning:
        dlg._on_keymap_field_edited("undo", "primary")

    message = mock_warning.call_args[0][2]
    assert "Redo" in message


@pytest.mark.requirement("REQ-KEYS-040")
def test_conflict_warning_not_shown_twice_on_reentrant_editing_finished(
    dlg: PreferencesDialog,
) -> None:
    """Regression for #111 live-testing: showing the modal QMessageBox
    moves focus off the edit field, and QKeySequenceEdit.editingFinished
    fires on focus-out too — without a reentrancy guard, that re-enters
    this same handler for the same still-conflicting value and shows a
    second warning before the first call has reverted anything. Simulated
    here by having the mocked warning itself re-enter the handler, the
    same way a real focus-out during the modal's nested event loop would."""
    undo_primary, _ = dlg._keymap_row_widgets["undo"]
    undo_primary.setKeySequence(QKeySequence("Ctrl+Shift+Z"))

    call_count = 0

    def fake_warning(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            dlg._on_keymap_field_edited("undo", "primary")  # simulated reentrant call

    with patch(
        "mdf_viewer.view.preferences_dialog.QMessageBox.warning", side_effect=fake_warning
    ):
        dlg._on_keymap_field_edited("undo", "primary")

    assert call_count == 1
    assert dlg._keymap_working["undo"][0] == QKeySequence("Ctrl+Z")


def test_no_conflict_between_an_actions_own_primary_and_secondary(dlg: PreferencesDialog) -> None:
    """Zoom to Fit's own Ctrl+0/F pair must not flag itself as a conflict."""
    primary_edit, secondary_edit = dlg._keymap_row_widgets["zoom_to_fit"]
    secondary_edit.setKeySequence(QKeySequence("F"))
    with patch("mdf_viewer.view.preferences_dialog.QMessageBox.warning") as mock_warning:
        dlg._on_keymap_field_edited("zoom_to_fit", "secondary")
    mock_warning.assert_not_called()


# ---------------------------------------------------------------------------
# Reset (per-row and reset-all)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-KEYS-054")
def test_reset_row_restores_default(dlg: PreferencesDialog) -> None:
    primary_edit, _ = dlg._keymap_row_widgets["undo"]
    primary_edit.setKeySequence(QKeySequence("Ctrl+9"))
    dlg._on_keymap_field_edited("undo", "primary")

    dlg._reset_keymap_row("undo")

    assert dlg._keymap_working["undo"][0] == QKeySequence("Ctrl+Z")
    assert primary_edit.keySequence() == QKeySequence("Ctrl+Z")


@pytest.mark.requirement("REQ-KEYS-055")
def test_reset_all_restores_every_action(dlg: PreferencesDialog) -> None:
    primary_edit, _ = dlg._keymap_row_widgets["undo"]
    primary_edit.setKeySequence(QKeySequence("Ctrl+9"))
    dlg._on_keymap_field_edited("undo", "primary")

    dlg._on_keymap_reset_all()

    for action_id in ACTION_IDS:
        assert dlg._keymap_working[action_id] == DEFAULT_PRESET[action_id]
    assert dlg._keymap_status_label.text() == "Current: Default"


# ---------------------------------------------------------------------------
# Preset selector
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-KEYS-053")
def test_selecting_mda_preset_updates_rows(dlg: PreferencesDialog) -> None:
    dlg._on_keymap_preset_selected("MDA")
    primary_edit, _ = dlg._keymap_row_widgets["zoom_to_fit"]
    assert primary_edit.keySequence() == QKeySequence("Ctrl+F12")
    assert dlg._keymap_status_label.text() == "Current: MDA"


@pytest.mark.requirement("REQ-KEYS-053")
def test_selecting_canape_preset_updates_rows(dlg: PreferencesDialog) -> None:
    dlg._on_keymap_preset_selected("CANape")
    primary_edit, _ = dlg._keymap_row_widgets["save_workspace"]
    assert primary_edit.keySequence() == QKeySequence("F2")
    assert dlg._keymap_status_label.text() == "Current: CANape"


def test_selecting_unknown_preset_name_is_a_noop(dlg: PreferencesDialog) -> None:
    dlg._on_keymap_preset_selected("")  # combo's initial no-selection state
    assert dlg._keymap_status_label.text() == "Current: Default"


# ---------------------------------------------------------------------------
# .mvck Load/Save-As (#111 M5)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-KEYS-032")
def test_load_mvck_replaces_the_working_copy(dlg: PreferencesDialog, tmp_path: Path) -> None:
    from mdf_viewer.view.keymap_presets import save_mvck, CANAPE_PRESET

    path = tmp_path / "mine.mvck"
    save_mvck(path, CANAPE_PRESET, "My CANape Copy")

    with patch(
        "mdf_viewer.view.preferences_dialog.QFileDialog.getOpenFileName",
        return_value=(str(path), ""),
    ):
        dlg._on_keymap_load_clicked()

    primary_edit, _ = dlg._keymap_row_widgets["save_workspace"]
    assert primary_edit.keySequence() == QKeySequence("F2")
    assert dlg._keymap_status_label.text() == "Current: My CANape Copy"


def test_load_mvck_cancelled_dialog_does_nothing(dlg: PreferencesDialog) -> None:
    with patch(
        "mdf_viewer.view.preferences_dialog.QFileDialog.getOpenFileName",
        return_value=("", ""),
    ):
        dlg._on_keymap_load_clicked()
    assert dlg._keymap_status_label.text() == "Current: Default"


def test_load_mvck_invalid_file_shows_error(dlg: PreferencesDialog, tmp_path: Path) -> None:
    bad_path = tmp_path / "bad.mvck"
    bad_path.write_text("not json", encoding="utf-8")
    with patch(
        "mdf_viewer.view.preferences_dialog.QFileDialog.getOpenFileName",
        return_value=(str(bad_path), ""),
    ), patch(
        "mdf_viewer.view.preferences_dialog.QMessageBox.critical"
    ) as mock_critical:
        dlg._on_keymap_load_clicked()
    mock_critical.assert_called_once()


@pytest.mark.requirement("REQ-KEYS-031")
def test_save_mvck_writes_the_working_copy(dlg: PreferencesDialog, tmp_path: Path) -> None:
    primary_edit, _ = dlg._keymap_row_widgets["undo"]
    primary_edit.setKeySequence(QKeySequence("Ctrl+9"))
    dlg._on_keymap_field_edited("undo", "primary")

    out_path = tmp_path / "saved.mvck"
    with patch(
        "mdf_viewer.view.preferences_dialog.QFileDialog.getSaveFileName",
        return_value=(str(out_path), ""),
    ):
        dlg._on_keymap_save_clicked()

    from mdf_viewer.view.keymap_presets import load_mvck
    keymap, label = load_mvck(out_path)
    assert keymap["undo"][0] == QKeySequence("Ctrl+9")
    assert label == "saved"
    assert dlg._keymap_status_label.text() == "Current: saved"


def test_save_mvck_cancelled_dialog_does_nothing(dlg: PreferencesDialog, tmp_path: Path) -> None:
    with patch(
        "mdf_viewer.view.preferences_dialog.QFileDialog.getSaveFileName",
        return_value=("", ""),
    ):
        dlg._on_keymap_save_clicked()
    assert dlg._keymap_status_label.text() == "Current: Default"
