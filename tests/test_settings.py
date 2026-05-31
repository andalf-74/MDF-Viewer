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
