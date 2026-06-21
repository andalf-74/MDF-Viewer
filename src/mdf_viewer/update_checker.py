"""Checks GitHub releases for a newer version of MDF-Viewer."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

RELEASES_API_URL = (
    "https://api.github.com/repos/andalf-74/MDF-Viewer/releases/latest"
)
_TIMEOUT = 10  # seconds


class UpdateCheckError(Exception):
    pass


@dataclass
class ReleaseInfo:
    tag: str   # e.g. "v2.0"
    url: str   # GitHub release page URL


def fetch_latest_release() -> ReleaseInfo:
    """Fetch the latest release from GitHub. Raises UpdateCheckError on failure."""
    try:
        req = urllib.request.Request(
            RELEASES_API_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": "MDF-Viewer",
            },
        )
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        return ReleaseInfo(tag=data["tag_name"], url=data["html_url"])
    except (urllib.error.URLError, KeyError, json.JSONDecodeError, OSError) as exc:
        raise UpdateCheckError(f"Could not check for updates: {exc}") from exc


def is_newer(tag: str, current_version: str) -> bool:
    """Return True if tag (e.g. 'v2.0') is strictly newer than current_version (e.g. '1.5')."""
    def _parse(v: str) -> tuple[int, ...]:
        try:
            return tuple(int(x) for x in v.lstrip("v").split("."))
        except ValueError:
            return (0,)

    return _parse(tag) > _parse(current_version)
