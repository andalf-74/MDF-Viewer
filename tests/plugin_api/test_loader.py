"""Tests for the plugin loader and discovery (#74)."""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from mdf_viewer.plugin_api.loader import PluginLoader, _default_plugins_dir, resolve_plugins_dir
from mdf_viewer.plugin_api.plugin import Plugin
from mdf_viewer.plugin_api.registry import PluginRegistry


def _write_single_file_plugin(plugins_dir: Path, pkg_name: str, plugin_name: str) -> None:
    pkg = plugins_dir / pkg_name
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        textwrap.dedent(f"""
            from mdf_viewer.plugin_api.plugin import Plugin

            class _TestPlugin(Plugin):
                name = "{plugin_name}"

                def activate(self, context) -> None:
                    pass

            PLUGINS = [_TestPlugin]
            """),
        encoding="utf-8",
    )


def _write_multi_file_plugin(plugins_dir: Path, pkg_name: str, plugin_name: str) -> None:
    """A toolsuite-style package whose __init__.py imports a sibling module."""
    pkg = plugins_dir / pkg_name
    pkg.mkdir(parents=True)
    (pkg / "helper.py").write_text('GREETING = "hello from sibling"\n', encoding="utf-8")
    (pkg / "__init__.py").write_text(
        textwrap.dedent(f"""
            from mdf_viewer.plugin_api.plugin import Plugin
            from . import helper

            class _TestPlugin(Plugin):
                name = "{plugin_name}"

                def activate(self, context) -> None:
                    pass

            assert helper.GREETING == "hello from sibling"
            PLUGINS = [_TestPlugin]
            """),
        encoding="utf-8",
    )


@pytest.fixture()
def loader(tmp_path: Path) -> PluginLoader:
    return PluginLoader(app=MagicMock(), plugins_dir=tmp_path / "plugins")


# ---------------------------------------------------------------------------
# _default_plugins_dir / resolve_plugins_dir (REQ-PLUGIN-250/251/252)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLUGIN-250")
def test_default_plugins_dir_frozen_is_next_to_executable(monkeypatch) -> None:
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Program\MDF-Viewer\MDF-Viewer.exe")
    assert _default_plugins_dir() == Path(r"C:\Program\MDF-Viewer") / "plugins"


@pytest.mark.requirement("REQ-PLUGIN-251")
def test_default_plugins_dir_dev_mode_is_relative_to_source(monkeypatch) -> None:
    monkeypatch.delattr(sys, "frozen", raising=False)
    path = _default_plugins_dir()
    assert path.name == "plugins"
    assert (path.parent / "src" / "mdf_viewer").is_dir()


@pytest.mark.requirement("REQ-PLUGIN-252")
def test_resolve_plugins_dir_uses_settings_override_when_set(tmp_path: Path) -> None:
    settings = MagicMock()
    settings.plugins_dir = tmp_path / "custom"
    assert resolve_plugins_dir(settings) == tmp_path / "custom"


def test_resolve_plugins_dir_falls_back_to_default_when_unset() -> None:
    settings = MagicMock()
    settings.plugins_dir = None
    assert resolve_plugins_dir(settings) == _default_plugins_dir()


# ---------------------------------------------------------------------------
# _import_plugin_classes (REQ-PLUGIN-241/242/243)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLUGIN-242")
def test_import_single_file_plugin(tmp_path: Path, loader: PluginLoader) -> None:
    _write_single_file_plugin(tmp_path, "exporter_plugin", "Exporter")
    classes = loader._import_plugin_classes(
        "exporter_plugin", tmp_path / "exporter_plugin" / "__init__.py",
    )
    assert len(classes) == 1
    assert classes[0].name == "Exporter"
    assert issubclass(classes[0], Plugin)


def test_import_multi_file_plugin_with_relative_import(tmp_path: Path, loader: PluginLoader) -> None:
    """The concrete regression test for the Plan-review's top catch: a
    package whose __init__.py does `from . import helper` must actually
    import successfully, not raise ModuleNotFoundError."""
    _write_multi_file_plugin(tmp_path, "toolsuite", "ToolSuite")
    classes = loader._import_plugin_classes("toolsuite", tmp_path / "toolsuite" / "__init__.py")
    assert len(classes) == 1
    assert classes[0].name == "ToolSuite"


@pytest.mark.requirement("REQ-PLUGIN-243")
def test_import_missing_plugins_list_raises(tmp_path: Path, loader: PluginLoader) -> None:
    pkg = tmp_path / "broken"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("x = 1\n", encoding="utf-8")
    with pytest.raises(ValueError):
        loader._import_plugin_classes("broken", pkg / "__init__.py")


@pytest.mark.requirement("REQ-PLUGIN-243")
def test_import_empty_plugins_list_raises(tmp_path: Path, loader: PluginLoader) -> None:
    pkg = tmp_path / "broken"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("PLUGINS = []\n", encoding="utf-8")
    with pytest.raises(ValueError):
        loader._import_plugin_classes("broken", pkg / "__init__.py")


@pytest.mark.requirement("REQ-PLUGIN-243")
def test_import_non_plugin_entry_raises(tmp_path: Path, loader: PluginLoader) -> None:
    pkg = tmp_path / "broken"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("class NotAPlugin: pass\nPLUGINS = [NotAPlugin]\n", encoding="utf-8")
    with pytest.raises(TypeError):
        loader._import_plugin_classes("broken", pkg / "__init__.py")


def test_import_failure_does_not_leave_module_in_sys_modules(tmp_path: Path, loader: PluginLoader) -> None:
    pkg = tmp_path / "broken"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("PLUGINS = []\n", encoding="utf-8")
    before = set(sys.modules)
    with pytest.raises(ValueError):
        loader._import_plugin_classes("broken", pkg / "__init__.py")
    assert set(sys.modules) - before == set()


def test_same_named_subfolder_in_different_dirs_does_not_collide(tmp_path: Path) -> None:
    dir_a = tmp_path / "dir_a"
    dir_b = tmp_path / "dir_b"
    _write_single_file_plugin(dir_a, "shared_name", "PluginA")
    _write_single_file_plugin(dir_b, "shared_name", "PluginB")

    loader_a = PluginLoader(app=MagicMock(), plugins_dir=dir_a)
    loader_b = PluginLoader(app=MagicMock(), plugins_dir=dir_b)

    classes_a = loader_a._import_plugin_classes("shared_name", dir_a / "shared_name" / "__init__.py")
    classes_b = loader_b._import_plugin_classes("shared_name", dir_b / "shared_name" / "__init__.py")

    assert classes_a[0].name == "PluginA"
    assert classes_b[0].name == "PluginB"


# ---------------------------------------------------------------------------
# load_all / _activate_one / deactivate_all (REQ-PLUGIN-260/261/270/280)
# ---------------------------------------------------------------------------

def _make_app() -> MagicMock:
    app = MagicMock()
    app.plugin_registry = PluginRegistry()
    return app


@pytest.mark.requirement("REQ-PLUGIN-280")
def test_load_all_on_missing_directory_creates_it_and_returns_empty(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    loader = PluginLoader(app=_make_app(), plugins_dir=plugins_dir)

    result = loader.load_all()

    assert result.loaded == []
    assert result.failed == []
    assert plugins_dir.is_dir()


@pytest.mark.requirement("REQ-PLUGIN-280")
def test_load_all_scan_failure_is_caught(tmp_path: Path) -> None:
    """An unreadable/blocked plugins_dir (here: a file sitting where a
    directory is expected) must not crash the app (REQ-PLUGIN-280)."""
    plugins_dir = tmp_path / "plugins"
    plugins_dir.write_text("not a directory", encoding="utf-8")
    loader = PluginLoader(app=_make_app(), plugins_dir=plugins_dir)

    result = loader.load_all()  # must not raise

    assert result.loaded == []


@pytest.mark.requirement("REQ-PLUGIN-260")
def test_load_all_activates_a_real_plugin(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    _write_single_file_plugin(plugins_dir, "exporter_plugin", "Exporter")
    loader = PluginLoader(app=_make_app(), plugins_dir=plugins_dir)

    result = loader.load_all()

    assert result.loaded == ["Exporter"]
    assert result.failed == []


@pytest.mark.requirement("REQ-PLUGIN-261")
def test_load_all_rejects_duplicate_plugin_name(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    _write_single_file_plugin(plugins_dir, "plugin_a", "SameName")
    _write_single_file_plugin(plugins_dir, "plugin_b", "SameName")
    loader = PluginLoader(app=_make_app(), plugins_dir=plugins_dir)

    result = loader.load_all()

    assert result.loaded == ["SameName"]
    assert result.failed == ["SameName"]


def test_load_all_skips_a_plugin_whose_activate_raises(tmp_path: Path) -> None:
    pkg = tmp_path / "plugins" / "bad_plugin"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        textwrap.dedent("""
            from mdf_viewer.plugin_api.plugin import Plugin

            class _BadPlugin(Plugin):
                name = "Bad"

                def activate(self, context) -> None:
                    raise ValueError("boom")

            PLUGINS = [_BadPlugin]
            """),
        encoding="utf-8",
    )
    loader = PluginLoader(app=_make_app(), plugins_dir=tmp_path / "plugins")

    result = loader.load_all()  # must not raise

    assert result.loaded == []
    assert result.failed == ["Bad"]


def test_load_all_threads_tab_name_provider_into_context(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    pkg = plugins_dir / "tab_reader_plugin"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        textwrap.dedent("""
            from mdf_viewer.plugin_api.plugin import Plugin

            class _TabReaderPlugin(Plugin):
                name = "TabReader"
                seen_tab_name = None

                def activate(self, context) -> None:
                    type(self).seen_tab_name = context._tab_name(0)

            PLUGINS = [_TabReaderPlugin]
            """),
        encoding="utf-8",
    )
    loader = PluginLoader(
        app=_make_app(), plugins_dir=plugins_dir, tab_name_provider=lambda i: f"Custom Tab {i}",
    )

    loader.load_all()

    module = sys.modules[loader._loaded_module_names[0]]
    assert module._TabReaderPlugin.seen_tab_name == "Custom Tab 0"


def test_deactivate_all_stops_every_started_plugin(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    pkg = plugins_dir / "tracked_plugin"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        textwrap.dedent("""
            from mdf_viewer.plugin_api.plugin import Plugin

            class _TrackedPlugin(Plugin):
                name = "Tracked"
                deactivate_calls = 0

                def activate(self, context) -> None:
                    pass

                def deactivate(self) -> None:
                    type(self).deactivate_calls += 1

            PLUGINS = [_TrackedPlugin]
            """),
        encoding="utf-8",
    )
    loader = PluginLoader(app=_make_app(), plugins_dir=plugins_dir)
    loader.load_all()
    module_name = loader._loaded_module_names[0]
    module = sys.modules[module_name]

    loader.deactivate_all()

    assert module._TrackedPlugin.deactivate_calls == 1
    assert module_name not in sys.modules

    loader.deactivate_all()  # must be safe to call twice
    assert module._TrackedPlugin.deactivate_calls == 1
