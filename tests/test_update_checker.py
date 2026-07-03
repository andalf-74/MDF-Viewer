"""Tests for update_checker — version comparison and network fetch."""

from __future__ import annotations

import json
from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest

from mdf_viewer.update_checker import (
    ReleaseInfo,
    UpdateCheckError,
    fetch_latest_release,
    is_newer,
)


# ---------------------------------------------------------------------------
# is_newer
# ---------------------------------------------------------------------------

class TestIsNewer:
    def test_newer_minor(self):
        assert is_newer("v2.0", "1.5") is True

    def test_newer_patch(self):
        assert is_newer("v1.6", "1.5") is True

    def test_same_version(self):
        assert is_newer("v1.5", "1.5") is False

    def test_older_version(self):
        assert is_newer("v1.4", "1.5") is False

    def test_strips_v_prefix(self):
        assert is_newer("v2.0", "1.5") is True

    def test_no_v_prefix(self):
        assert is_newer("2.0", "1.5") is True

    def test_major_bump(self):
        assert is_newer("v3.0", "2.9") is True

    def test_multi_part_version(self):
        assert is_newer("v1.5.1", "1.5.0") is True

    def test_multi_part_same(self):
        assert is_newer("v1.5.0", "1.5.0") is False


# ---------------------------------------------------------------------------
# fetch_latest_release
# ---------------------------------------------------------------------------

def _mock_response(tag: str, html_url: str) -> MagicMock:
    payload = json.dumps({"tag_name": tag, "html_url": html_url}).encode()
    mock = MagicMock()
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    mock.read.return_value = payload
    return mock


class TestFetchLatestRelease:
    @pytest.mark.requirement("REQ-NFR-030")
    def test_returns_release_info(self):
        mock_resp = _mock_response("v2.0", "https://github.com/example/releases/tag/v2.0")
        with patch("urllib.request.urlopen", return_value=mock_resp):
            info = fetch_latest_release()
        assert isinstance(info, ReleaseInfo)
        assert info.tag == "v2.0"
        assert "v2.0" in info.url

    @pytest.mark.requirement("REQ-NFR-033")
    def test_raises_on_network_error(self):
        import urllib.error
        with patch("urllib.request.urlopen", side_effect=urllib.error.URLError("timeout")):
            with pytest.raises(UpdateCheckError, match="Could not check"):
                fetch_latest_release()

    @pytest.mark.requirement("REQ-NFR-033")
    def test_raises_on_invalid_json(self):
        mock = MagicMock()
        mock.__enter__ = lambda s: s
        mock.__exit__ = MagicMock(return_value=False)
        mock.read.return_value = b"not json"
        with patch("urllib.request.urlopen", return_value=mock):
            with pytest.raises(UpdateCheckError):
                fetch_latest_release()

    @pytest.mark.requirement("REQ-NFR-033")
    def test_raises_on_missing_key(self):
        mock = MagicMock()
        mock.__enter__ = lambda s: s
        mock.__exit__ = MagicMock(return_value=False)
        mock.read.return_value = json.dumps({"other": "data"}).encode()
        with patch("urllib.request.urlopen", return_value=mock):
            with pytest.raises(UpdateCheckError):
                fetch_latest_release()
