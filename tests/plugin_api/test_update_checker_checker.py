"""Tests for plugins/update_checker/checker.py — version comparison and
network fetch (#76).

Imports the real, committed checker.py directly by file path rather than
through the full PluginLoader — these are pure-function unit tests with no
dependency on plugin lifecycle machinery, mirroring how the equivalent
core-module tests worked before the module moved into the plugin package.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_CHECKER_PATH = (
    Path(__file__).resolve().parents[2] / "plugins" / "update_checker" / "checker.py"
)


def _load_checker():
    module_name = "_update_checker_checker_under_test"
    spec = importlib.util.spec_from_file_location(module_name, _CHECKER_PATH)
    module = importlib.util.module_from_spec(spec)
    # Registered in sys.modules before exec_module() — @dataclass's own
    # machinery looks up its defining module there, mirroring the same
    # requirement PluginLoader._import_plugin_classes() already works
    # around for the real plugin-loading path.
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_checker = _load_checker()
ReleaseInfo = _checker.ReleaseInfo
UpdateCheckError = _checker.UpdateCheckError
fetch_latest_release = _checker.fetch_latest_release
is_newer = _checker.is_newer


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
    @pytest.mark.requirement("REQ-UPDATE-010")
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
