"""Persistent application settings stored as a JSON file.

Config path:
  Windows : %APPDATA%\\mdf-viewer\\settings.json
  Linux   : ~/.config/mdf-viewer/settings.json
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

MAX_RECENT = 4


def _default_config_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home())) / "mdf-viewer"
    else:
        base = Path.home() / ".config" / "mdf-viewer"
    return base / "settings.json"


class Settings:
    """Read/write application settings from a JSON file."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path if path is not None else _default_config_path()
        self._recent: list[Path] = []
        self._check_for_updates: bool = True
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_recent(self, path: str | os.PathLike) -> None:
        """Prepend path to the recent files list, dedup, trim, and save."""
        p = Path(path).resolve()
        self._recent = [p] + [r for r in self._recent if r != p]
        self._recent = self._recent[:MAX_RECENT]
        self._save()

    def recent_files(self) -> list[Path]:
        """Return the current recent files list (may include missing paths)."""
        return list(self._recent)

    @property
    def check_for_updates(self) -> bool:
        return self._check_for_updates

    @check_for_updates.setter
    def check_for_updates(self, value: bool) -> None:
        self._check_for_updates = value
        self._save()

    def get_and_prune(self) -> list[Path]:
        """Return only paths that exist on disk; save if any were removed."""
        existing = [p for p in self._recent if p.exists()]
        if len(existing) != len(self._recent):
            self._recent = existing
            self._save()
        return list(existing)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load(self) -> None:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._recent = [Path(p) for p in data.get("recent_files", [])]
            self._check_for_updates = bool(data.get("check_for_updates", True))
        except (FileNotFoundError, json.JSONDecodeError, TypeError, KeyError):
            self._recent = []
            self._check_for_updates = True

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(
                {
                    "recent_files": [str(p) for p in self._recent],
                    "check_for_updates": self._check_for_updates,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
