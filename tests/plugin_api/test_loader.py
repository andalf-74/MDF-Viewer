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

    module_name = loader._active["TabReader"].module_name
    module = sys.modules[module_name]
    assert module._TabReaderPlugin.seen_tab_name == "Custom Tab 0"


@pytest.mark.requirement("REQ-PLUGIN-410")
def test_load_all_threads_settings_into_context(tmp_path: Path) -> None:
    from mdf_viewer.settings import Settings

    plugins_dir = tmp_path / "plugins"
    pkg = plugins_dir / "settings_user_plugin"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        textwrap.dedent("""
            from mdf_viewer.plugin_api.plugin import Plugin

            class _SettingsUserPlugin(Plugin):
                name = "SettingsUser"
                seen_value = None

                def activate(self, context) -> None:
                    context.set_setting("threshold", 42)
                    type(self).seen_value = context.get_setting("threshold", None)

            PLUGINS = [_SettingsUserPlugin]
            """),
        encoding="utf-8",
    )
    real_settings = Settings(path=tmp_path / "settings.json")
    loader = PluginLoader(app=_make_app(), plugins_dir=plugins_dir, settings=real_settings)

    loader.load_all()

    module_name = loader._active["SettingsUser"].module_name
    module = sys.modules[module_name]
    assert module._SettingsUserPlugin.seen_value == 42
    assert real_settings.get_plugin_setting("SettingsUser", "threshold", None) == 42


@pytest.mark.requirement("REQ-PLUGIN-450")
def test_load_all_threads_main_window_into_context(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    pkg = plugins_dir / "window_user_plugin"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        textwrap.dedent("""
            from mdf_viewer.plugin_api.plugin import Plugin

            class _WindowUserPlugin(Plugin):
                name = "WindowUser"
                seen_window = "unset"

                def activate(self, context) -> None:
                    type(self).seen_window = context.main_window

            PLUGINS = [_WindowUserPlugin]
            """),
        encoding="utf-8",
    )
    sentinel_window = object()
    loader = PluginLoader(app=_make_app(), plugins_dir=plugins_dir, main_window=sentinel_window)

    loader.load_all()

    module_name = loader._active["WindowUser"].module_name
    module = sys.modules[module_name]
    assert module._WindowUserPlugin.seen_window is sentinel_window


@pytest.mark.requirement("REQ-PLUGIN-452")
def test_load_all_threads_app_version_into_context(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    pkg = plugins_dir / "version_user_plugin"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        textwrap.dedent("""
            from mdf_viewer.plugin_api.plugin import Plugin

            class _VersionUserPlugin(Plugin):
                name = "VersionUser"
                seen_version = None

                def activate(self, context) -> None:
                    type(self).seen_version = context.app_version

            PLUGINS = [_VersionUserPlugin]
            """),
        encoding="utf-8",
    )
    loader = PluginLoader(app=_make_app(), plugins_dir=plugins_dir, app_version="2.3")

    loader.load_all()

    module_name = loader._active["VersionUser"].module_name
    module = sys.modules[module_name]
    assert module._VersionUserPlugin.seen_version == "2.3"


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
    module_name = loader._active["Tracked"].module_name
    module = sys.modules[module_name]

    loader.deactivate_all()

    assert module._TrackedPlugin.deactivate_calls == 1
    assert module_name not in sys.modules

    loader.deactivate_all()  # must be safe to call twice
    assert module._TrackedPlugin.deactivate_calls == 1


# ---------------------------------------------------------------------------
# rescan (#150, REQ-PLUGIN-360/361)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLUGIN-361")
def test_rescan_skips_already_active_plugin_without_reimporting(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    marker = tmp_path / "import_marker.txt"
    marker_repr = repr(str(marker))
    pkg = plugins_dir / "counted_plugin"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        textwrap.dedent(f"""
            from pathlib import Path
            from mdf_viewer.plugin_api.plugin import Plugin

            with Path({marker_repr}).open("a", encoding="utf-8") as _f:
                _f.write("x")

            class _CountedPlugin(Plugin):
                name = "Counted"

                def activate(self, context) -> None:
                    pass

            PLUGINS = [_CountedPlugin]
            """),
        encoding="utf-8",
    )
    loader = PluginLoader(app=_make_app(), plugins_dir=plugins_dir)

    first = loader.load_all()
    assert first.loaded == ["Counted"]
    assert marker.read_text(encoding="utf-8") == "x"

    second = loader.rescan()

    assert second.loaded == []
    assert second.failed == []
    assert marker.read_text(encoding="utf-8") == "x"  # not re-imported


@pytest.mark.requirement("REQ-PLUGIN-360")
def test_rescan_retries_a_previously_failed_folder(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    pkg = plugins_dir / "flaky_plugin"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("PLUGINS = []\n", encoding="utf-8")
    loader = PluginLoader(app=_make_app(), plugins_dir=plugins_dir)

    first = loader.load_all()
    assert first.loaded == []
    assert first.failed == ["flaky_plugin"]

    (pkg / "__init__.py").write_text(
        textwrap.dedent("""
            from mdf_viewer.plugin_api.plugin import Plugin

            class _FixedPlugin(Plugin):
                name = "Fixed"

                def activate(self, context) -> None:
                    pass

            PLUGINS = [_FixedPlugin]
            """),
        encoding="utf-8",
    )

    second = loader.rescan()

    assert second.loaded == ["Fixed"]
    assert second.failed == []


@pytest.mark.requirement("REQ-PLUGIN-360")
def test_rescan_activates_a_genuinely_new_folder(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    loader = PluginLoader(app=_make_app(), plugins_dir=plugins_dir)

    first = loader.load_all()
    assert first.loaded == []

    _write_single_file_plugin(plugins_dir, "new_plugin", "NewOne")
    second = loader.rescan()

    assert second.loaded == ["NewOne"]


# ---------------------------------------------------------------------------
# reload_one (#150, REQ-PLUGIN-370/371/372)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLUGIN-370")
def test_reload_one_reactivates_with_fresh_code(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    pkg = plugins_dir / "reloadable"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        textwrap.dedent("""
            from mdf_viewer.plugin_api.plugin import Plugin

            class _V1(Plugin):
                name = "Reloadable"
                version = "1"

                def activate(self, context) -> None:
                    pass

            PLUGINS = [_V1]
            """),
        encoding="utf-8",
    )
    loader = PluginLoader(app=_make_app(), plugins_dir=plugins_dir)
    loader.load_all()
    assert loader._active["Reloadable"].instance.version == "1"

    (pkg / "__init__.py").write_text(
        textwrap.dedent("""
            from mdf_viewer.plugin_api.plugin import Plugin

            class _V2(Plugin):
                name = "Reloadable"
                version = "2"

                def activate(self, context) -> None:
                    pass

            PLUGINS = [_V2]
            """),
        encoding="utf-8",
    )

    ok = loader.reload_one("Reloadable")

    assert ok is True
    assert loader._active["Reloadable"].instance.version == "2"


def test_reload_one_returns_false_when_not_active(tmp_path: Path) -> None:
    loader = PluginLoader(app=_make_app(), plugins_dir=tmp_path / "plugins")
    assert loader.reload_one("Nonexistent") is False


@pytest.mark.requirement("REQ-PLUGIN-372")
def test_reload_one_failed_activate_leaves_plugin_unloaded_no_rollback(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    pkg = plugins_dir / "flaky"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        textwrap.dedent("""
            from mdf_viewer.plugin_api.plugin import Plugin

            class _Good(Plugin):
                name = "Flaky"

                def activate(self, context) -> None:
                    pass

            PLUGINS = [_Good]
            """),
        encoding="utf-8",
    )
    loader = PluginLoader(app=_make_app(), plugins_dir=plugins_dir)
    loader.load_all()
    assert "Flaky" in loader._active

    (pkg / "__init__.py").write_text(
        textwrap.dedent("""
            from mdf_viewer.plugin_api.plugin import Plugin

            class _Bad(Plugin):
                name = "Flaky"

                def activate(self, context) -> None:
                    raise ValueError("boom")

            PLUGINS = [_Bad]
            """),
        encoding="utf-8",
    )

    ok = loader.reload_one("Flaky")

    assert ok is False
    assert "Flaky" not in loader._active


@pytest.mark.requirement("REQ-PLUGIN-371")
def test_reload_one_purges_submodule_cache_for_multi_file_package(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    _write_multi_file_plugin(plugins_dir, "toolsuite", "ToolSuite")
    loader = PluginLoader(app=_make_app(), plugins_dir=plugins_dir)
    loader.load_all()
    active = loader._active["ToolSuite"]
    submodule_name = f"{active.module_name}.helper"
    original_submodule = sys.modules[submodule_name]

    ok = loader.reload_one("ToolSuite")

    assert ok is True
    new_active = loader._active["ToolSuite"]
    new_submodule_name = f"{new_active.module_name}.helper"
    assert new_submodule_name == submodule_name  # same folder, same synthesized name
    # A fresh module object proves the stale cache entry was purged before
    # reload re-imported it — otherwise Python's `from . import helper`
    # would have resolved back to the same cached (stale) object.
    assert sys.modules[new_submodule_name] is not original_submodule


# ---------------------------------------------------------------------------
# active_plugin_names (#150)
# ---------------------------------------------------------------------------

def test_active_plugin_names_reflects_current_state(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    _write_single_file_plugin(plugins_dir, "plugin_a", "Alpha")
    _write_single_file_plugin(plugins_dir, "plugin_b", "Bravo")
    loader = PluginLoader(app=_make_app(), plugins_dir=plugins_dir)

    assert loader.active_plugin_names() == []

    loader.load_all()

    assert loader.active_plugin_names() == ["Alpha", "Bravo"]

    loader.reload_one("Alpha")

    assert loader.active_plugin_names() == ["Alpha", "Bravo"]


# ---------------------------------------------------------------------------
# Plugin Overview / enable-disable (#160, REQ-PLUGIN-460-510)
# ---------------------------------------------------------------------------

def _write_toolsuite_plugin(
    plugins_dir: Path, pkg_name: str, good_name: str, bad_name: str | None = None,
) -> None:
    """A folder declaring two classes — optionally one that raises in
    activate() — for the F1 partial-failure scenario."""
    pkg = plugins_dir / pkg_name
    pkg.mkdir(parents=True)
    lines = [
        "from mdf_viewer.plugin_api.plugin import Plugin",
        "",
        "class _Good(Plugin):",
        f'    name = "{good_name}"',
        "",
        "    def activate(self, context) -> None:",
        "        pass",
        "",
    ]
    plugins_list = "_Good"
    if bad_name is not None:
        lines += [
            "class _Bad(Plugin):",
            f'    name = "{bad_name}"',
            "",
            "    def activate(self, context) -> None:",
            '        raise ValueError("boom")',
            "",
        ]
        plugins_list = "_Good, _Bad"
    lines.append(f"PLUGINS = [{plugins_list}]")
    (pkg / "__init__.py").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _make_settings(tmp_path: Path):
    from mdf_viewer.settings import Settings

    return Settings(path=tmp_path / "settings.json")


@pytest.mark.requirement("REQ-PLUGIN-465")
def test_disabled_folder_is_never_imported(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    marker = tmp_path / "import_marker.txt"
    marker_repr = repr(str(marker))
    pkg = plugins_dir / "disabled_plugin"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        textwrap.dedent(f"""
            from pathlib import Path
            from mdf_viewer.plugin_api.plugin import Plugin

            with Path({marker_repr}).open("a", encoding="utf-8") as _f:
                _f.write("x")

            class _Disabled(Plugin):
                name = "Disabled"

                def activate(self, context) -> None:
                    pass

            PLUGINS = [_Disabled]
            """),
        encoding="utf-8",
    )
    settings = _make_settings(tmp_path)
    settings.set_plugin_disabled("disabled_plugin", True)
    loader = PluginLoader(app=_make_app(), plugins_dir=plugins_dir, settings=settings)

    result = loader.load_all()

    assert result.loaded == []
    assert result.failed == []
    assert not marker.exists()


@pytest.mark.requirement("REQ-PLUGIN-471")
def test_disabled_check_is_a_noop_without_settings_wired(tmp_path: Path) -> None:
    """A loader with no settings wired never treats anything as disabled —
    matches every other #160 method's None-settings guard."""
    plugins_dir = tmp_path / "plugins"
    _write_single_file_plugin(plugins_dir, "plugin_a", "Alpha")
    loader = PluginLoader(app=_make_app(), plugins_dir=plugins_dir)  # settings=None

    result = loader.load_all()

    assert result.loaded == ["Alpha"]


def test_toolsuite_partial_failure_marks_whole_folder_failed(tmp_path: Path) -> None:
    """F1 fix: a folder with two classes, one of which fails, must not have
    its failure silently cleared by the sibling class's success."""
    plugins_dir = tmp_path / "plugins"
    _write_toolsuite_plugin(plugins_dir, "toolsuite", good_name="Good", bad_name="Bad")
    loader = PluginLoader(app=_make_app(), plugins_dir=plugins_dir)

    result = loader.load_all()

    assert result.loaded == ["Good"]
    assert result.failed == ["Bad"]
    assert loader._failed.get("toolsuite") is not None

    packages = {p.folder_name: p for p in loader.list_packages()}
    assert packages["toolsuite"].failed is True
    assert packages["toolsuite"].active_plugin_names == ["Good"]


def test_folder_success_clears_prior_failure(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    pkg = plugins_dir / "flaky"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("PLUGINS = []\n", encoding="utf-8")
    loader = PluginLoader(app=_make_app(), plugins_dir=plugins_dir)
    loader.load_all()
    assert loader._failed.get("flaky") is not None

    (pkg / "__init__.py").write_text(
        textwrap.dedent("""
            from mdf_viewer.plugin_api.plugin import Plugin

            class _Fixed(Plugin):
                name = "Fixed"

                def activate(self, context) -> None:
                    pass

            PLUGINS = [_Fixed]
            """),
        encoding="utf-8",
    )
    loader.rescan()

    assert loader._failed.get("flaky") is None


# ---------------------------------------------------------------------------
# list_packages (#160, REQ-PLUGIN-460/461/490/491/500/501/510)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLUGIN-460")
def test_list_packages_includes_never_imported_disabled_folder(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    _write_single_file_plugin(plugins_dir, "never_enabled", "NeverEnabled")
    settings = _make_settings(tmp_path)
    settings.set_plugin_disabled("never_enabled", True)
    loader = PluginLoader(app=_make_app(), plugins_dir=plugins_dir, settings=settings)
    loader.load_all()

    packages = {p.folder_name: p for p in loader.list_packages()}

    pkg = packages["never_enabled"]
    assert pkg.enabled is False
    assert pkg.active_plugin_names == []
    assert pkg.failed is False
    assert pkg.metadata == []


@pytest.mark.requirement("REQ-PLUGIN-501")
def test_list_packages_shows_metadata_for_active_plugin(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    pkg_dir = plugins_dir / "described"
    pkg_dir.mkdir(parents=True)
    (pkg_dir / "__init__.py").write_text(
        textwrap.dedent("""
            from mdf_viewer.plugin_api.plugin import Plugin

            class _Described(Plugin):
                name = "Described"
                version = "1.2"
                description = "does a thing"
                author = "someone"

                def activate(self, context) -> None:
                    pass

            PLUGINS = [_Described]
            """),
        encoding="utf-8",
    )
    loader = PluginLoader(app=_make_app(), plugins_dir=plugins_dir)
    loader.load_all()

    packages = {p.folder_name: p for p in loader.list_packages()}

    pkg = packages["described"]
    assert pkg.enabled is True
    assert pkg.active_plugin_names == ["Described"]
    assert pkg.metadata == [
        {"name": "Described", "version": "1.2", "description": "does a thing", "author": "someone"}
    ]


@pytest.mark.requirement("REQ-PLUGIN-490")
def test_list_packages_shows_failure_reason(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    pkg = plugins_dir / "broken"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("PLUGINS = []\n", encoding="utf-8")
    loader = PluginLoader(app=_make_app(), plugins_dir=plugins_dir)
    loader.load_all()

    packages = {p.folder_name: p for p in loader.list_packages()}

    pkg_info = packages["broken"]
    assert pkg_info.failed is True
    assert pkg_info.failure_reason is not None
    assert pkg_info.enabled is True  # failed, but not disabled — distinguishable


@pytest.mark.requirement("REQ-PLUGIN-510")
def test_list_packages_prunes_stale_disabled_entry(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    _write_single_file_plugin(plugins_dir, "keep_me", "KeepMe")
    settings = _make_settings(tmp_path)
    settings.set_plugin_disabled("removed_folder", True)
    settings.set_plugin_disabled("keep_me", True)
    loader = PluginLoader(app=_make_app(), plugins_dir=plugins_dir, settings=settings)

    loader.list_packages()

    assert settings.disabled_plugins == {"keep_me"}


def test_list_packages_missing_directory_returns_empty(tmp_path: Path) -> None:
    loader = PluginLoader(app=_make_app(), plugins_dir=tmp_path / "does_not_exist")
    assert loader.list_packages() == []


def test_list_packages_enabled_folder_never_scanned_yet(tmp_path: Path) -> None:
    """A folder present on disk, enabled, but never touched by load_all()/
    rescan() — list_packages() does its own independent directory scan, so
    it must still report it correctly (enabled, inactive, not failed)."""
    plugins_dir = tmp_path / "plugins"
    _write_single_file_plugin(plugins_dir, "untouched", "Untouched")
    loader = PluginLoader(app=_make_app(), plugins_dir=plugins_dir)

    packages = {p.folder_name: p for p in loader.list_packages()}

    pkg = packages["untouched"]
    assert pkg.enabled is True
    assert pkg.active_plugin_names == []
    assert pkg.failed is False
    assert pkg.metadata == []


# ---------------------------------------------------------------------------
# set_enabled (#160, REQ-PLUGIN-462/480-483)
# ---------------------------------------------------------------------------

@pytest.mark.requirement("REQ-PLUGIN-482")
def test_set_enabled_true_activates_a_disabled_folder(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    _write_single_file_plugin(plugins_dir, "plugin_a", "Alpha")
    settings = _make_settings(tmp_path)
    settings.set_plugin_disabled("plugin_a", True)
    loader = PluginLoader(app=_make_app(), plugins_dir=plugins_dir, settings=settings)
    loader.load_all()
    assert loader.active_plugin_names() == []

    result = loader.set_enabled("plugin_a", True)

    assert result.loaded == ["Alpha"]
    assert loader.active_plugin_names() == ["Alpha"]
    assert settings.is_plugin_disabled("plugin_a") is False


@pytest.mark.requirement("REQ-PLUGIN-481")
def test_set_enabled_false_deactivates_an_active_folder(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    _write_single_file_plugin(plugins_dir, "plugin_a", "Alpha")
    settings = _make_settings(tmp_path)
    loader = PluginLoader(app=_make_app(), plugins_dir=plugins_dir, settings=settings)
    loader.load_all()
    assert loader.active_plugin_names() == ["Alpha"]

    loader.set_enabled("plugin_a", False)

    assert loader.active_plugin_names() == []
    assert settings.is_plugin_disabled("plugin_a") is True


@pytest.mark.requirement("REQ-PLUGIN-462")
def test_set_enabled_false_deactivates_every_plugin_in_a_toolsuite_folder(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    pkg = plugins_dir / "toolsuite"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        textwrap.dedent("""
            from mdf_viewer.plugin_api.plugin import Plugin

            class _A(Plugin):
                name = "A"

                def activate(self, context) -> None:
                    pass

            class _B(Plugin):
                name = "B"

                def activate(self, context) -> None:
                    pass

            PLUGINS = [_A, _B]
            """),
        encoding="utf-8",
    )
    settings = _make_settings(tmp_path)
    loader = PluginLoader(app=_make_app(), plugins_dir=plugins_dir, settings=settings)
    loader.load_all()
    assert sorted(loader.active_plugin_names()) == ["A", "B"]

    loader.set_enabled("toolsuite", False)

    assert loader.active_plugin_names() == []


def test_set_enabled_true_on_already_active_folder_does_not_reimport(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    marker = tmp_path / "import_marker.txt"
    marker_repr = repr(str(marker))
    pkg = plugins_dir / "counted"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        textwrap.dedent(f"""
            from pathlib import Path
            from mdf_viewer.plugin_api.plugin import Plugin

            with Path({marker_repr}).open("a", encoding="utf-8") as _f:
                _f.write("x")

            class _Counted(Plugin):
                name = "Counted"

                def activate(self, context) -> None:
                    pass

            PLUGINS = [_Counted]
            """),
        encoding="utf-8",
    )
    loader = PluginLoader(app=_make_app(), plugins_dir=plugins_dir)
    loader.load_all()
    assert marker.read_text(encoding="utf-8") == "x"

    result = loader.set_enabled("counted", True)

    assert result.loaded == []
    assert marker.read_text(encoding="utf-8") == "x"  # not re-imported


def test_set_enabled_false_on_inactive_folder_still_persists_setting(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    loader = PluginLoader(app=_make_app(), plugins_dir=tmp_path / "plugins", settings=settings)

    loader.set_enabled("never_existed", False)

    assert settings.is_plugin_disabled("never_existed") is True


@pytest.mark.requirement("REQ-PLUGIN-491")
def test_set_enabled_false_clears_stale_failure_state(tmp_path: Path) -> None:
    """F5 fix: disabling a previously-failed folder must not leave a stale
    error indicator behind — nothing is being attempted for it anymore."""
    plugins_dir = tmp_path / "plugins"
    pkg = plugins_dir / "broken"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("PLUGINS = []\n", encoding="utf-8")
    settings = _make_settings(tmp_path)
    loader = PluginLoader(app=_make_app(), plugins_dir=plugins_dir, settings=settings)
    loader.load_all()
    assert loader._failed.get("broken") is not None

    loader.set_enabled("broken", False)

    assert loader._failed.get("broken") is None
    packages = {p.folder_name: p for p in loader.list_packages()}
    assert packages["broken"].failed is False
    assert packages["broken"].enabled is False


def test_set_enabled_true_folder_deleted_after_discovery_fails_gracefully(tmp_path: Path) -> None:
    """F7: a folder that was enabled but whose directory vanished between
    being listed and the toggle must not raise out of set_enabled()."""
    plugins_dir = tmp_path / "plugins"
    loader = PluginLoader(app=_make_app(), plugins_dir=plugins_dir)

    result = loader.set_enabled("never_existed_on_disk", True)  # must not raise

    assert result.loaded == []
    assert result.failed == ["never_existed_on_disk"]
    assert loader._failed.get("never_existed_on_disk") is not None


def test_set_enabled_without_settings_wired_still_acts_but_does_not_persist(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    _write_single_file_plugin(plugins_dir, "plugin_a", "Alpha")
    loader = PluginLoader(app=_make_app(), plugins_dir=plugins_dir)  # settings=None
    loader.load_all()

    result = loader.set_enabled("plugin_a", False)  # must not raise

    assert result is not None
    assert loader.active_plugin_names() == []


# ---------------------------------------------------------------------------
# active_plugin_names_for (#160)
# ---------------------------------------------------------------------------

def test_active_plugin_names_for_reflects_live_state(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    pkg = plugins_dir / "toolsuite"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        textwrap.dedent("""
            from mdf_viewer.plugin_api.plugin import Plugin

            class _A(Plugin):
                name = "A"

                def activate(self, context) -> None:
                    pass

            class _B(Plugin):
                name = "B"

                def activate(self, context) -> None:
                    pass

            PLUGINS = [_A, _B]
            """),
        encoding="utf-8",
    )
    loader = PluginLoader(app=_make_app(), plugins_dir=plugins_dir)

    assert loader.active_plugin_names_for("toolsuite") == []

    loader.load_all()

    assert sorted(loader.active_plugin_names_for("toolsuite")) == ["A", "B"]

    loader.reload_one("A")

    assert sorted(loader.active_plugin_names_for("toolsuite")) == ["A", "B"]


# ---------------------------------------------------------------------------
# reload_one failure-tracking (#160, F2 fix)
# ---------------------------------------------------------------------------

def test_reload_one_reimport_failure_sets_failed_state(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    pkg = plugins_dir / "reloadable"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        textwrap.dedent("""
            from mdf_viewer.plugin_api.plugin import Plugin

            class _V1(Plugin):
                name = "Reloadable"

                def activate(self, context) -> None:
                    pass

            PLUGINS = [_V1]
            """),
        encoding="utf-8",
    )
    loader = PluginLoader(app=_make_app(), plugins_dir=plugins_dir)
    loader.load_all()
    assert loader._failed.get("reloadable") is None

    (pkg / "__init__.py").write_text("this is not valid python (((", encoding="utf-8")

    ok = loader.reload_one("Reloadable")

    assert ok is False
    assert loader._failed.get("reloadable") is not None


def test_reload_one_class_no_longer_declared_sets_failed_state(tmp_path: Path) -> None:
    plugins_dir = tmp_path / "plugins"
    pkg = plugins_dir / "renamed"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text(
        textwrap.dedent("""
            from mdf_viewer.plugin_api.plugin import Plugin

            class _Original(Plugin):
                name = "Original"

                def activate(self, context) -> None:
                    pass

            PLUGINS = [_Original]
            """),
        encoding="utf-8",
    )
    loader = PluginLoader(app=_make_app(), plugins_dir=plugins_dir)
    loader.load_all()

    (pkg / "__init__.py").write_text(
        textwrap.dedent("""
            from mdf_viewer.plugin_api.plugin import Plugin

            class _Renamed(Plugin):
                name = "SomethingElse"

                def activate(self, context) -> None:
                    pass

            PLUGINS = [_Renamed]
            """),
        encoding="utf-8",
    )

    ok = loader.reload_one("Original")

    assert ok is False
    assert loader._failed.get("renamed") is not None
