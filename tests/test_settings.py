"""Tests for Settings — recent files persistence."""

from __future__ import annotations

from pathlib import Path

import pytest

from mdf_viewer.settings import MAX_RECENT, Settings


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
