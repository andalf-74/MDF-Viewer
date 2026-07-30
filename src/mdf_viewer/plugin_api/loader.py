"""Plugin loader and discovery (#74) — the piece that finally does something
with #71/#72/#73: scans a real plugins directory, imports each plugin
package, instantiates and activates its declared Plugin classes, and
deactivates them again on shutdown.

Also implements on-demand Rescan/Reload (#150) — discovering plugins added
after startup, and reactivating one plugin's code from disk without
restarting the app.

App-side bootstrapping code, not part of the plugin-author-facing
contract — a plugin never imports this module. Kept in this package for
cohesion with types.py/registry.py/context.py/plugin.py.
"""

from __future__ import annotations

import hashlib
import importlib.util
import logging
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from mdf_viewer.plugin_api.context import PluginContext
from mdf_viewer.plugin_api.plugin import Plugin

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QMainWindow

    from mdf_viewer.controller.app_controller import AppController
    from mdf_viewer.settings import Settings

logger = logging.getLogger("mdf_viewer.plugin_api")


def _default_plugins_dir() -> Path:
    """Where plugins live when Settings.plugins_dir hasn't overridden it (REQ-PLUGIN-250/251).

    Packaged (installer or portable): next to the running executable, so a
    portable install's plugins travel with it when the whole folder is
    copied elsewhere. Running from source: relative to this file's own
    location (assumes an editable `pip install -e .` checkout, this
    project's documented dev workflow — not a non-editable wheel install,
    which isn't a supported way to run this app today).
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent / "plugins"
    # loader.py -> plugin_api -> mdf_viewer -> src -> repo root
    return Path(__file__).resolve().parents[3] / "plugins"


def resolve_plugins_dir(settings: "Settings") -> Path:
    """The effective plugins directory: Settings override, or the computed default (REQ-PLUGIN-252)."""
    return settings.plugins_dir or _default_plugins_dir()


@dataclass
class PluginLoadResult:
    """Summary of one load_all()/rescan()/set_enabled() run, for testability."""

    loaded: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)


@dataclass
class _ActivePlugin:
    """Bookkeeping for one currently-active plugin (#150) — enough to find,
    reload, and clean up after it later without re-scanning the whole
    plugins directory."""

    instance: Plugin
    module_name: str
    entry_path: Path


@dataclass
class PluginPackageInfo:
    """One row of the Plugin Overview list (#160) — a plugin *package*
    (folder), independent of whether it is enabled, active, or has ever
    been imported. Folder name is the canonical identity throughout this
    feature (REQ-PLUGIN-461/462) — a disabled folder's declared
    `Plugin.name` is never known, since it is never imported."""

    folder_name: str
    enabled: bool
    active_plugin_names: list[str] = field(default_factory=list)
    failed: bool = False
    failure_reason: str | None = None
    metadata: list[dict] = field(default_factory=list)


class PluginLoader:
    """Discovers, activates, reloads, and deactivates plugin packages
    (REQ-PLUGIN-240-280, 360-401)."""

    def __init__(
        self,
        app: "AppController",
        plugins_dir: Path,
        tab_name_provider: Callable[[int], str] | None = None,
        settings: "Settings | None" = None,
        main_window: "QMainWindow | None" = None,
        app_version: str = "",
    ) -> None:
        self._app = app
        self._plugins_dir = plugins_dir
        self._tab_name_provider = tab_name_provider
        self._settings = settings
        self._main_window = main_window
        self._app_version = app_version
        self._active: dict[str, _ActivePlugin] = {}
        # folder_name -> last failure reason (#160). Folder-keyed so it
        # survives independent of the plugin *name* declared inside — a
        # folder that fails to import has no name to key by at all.
        self._failed: dict[str, str] = {}

    def load_all(self) -> PluginLoadResult:
        """Discover and activate every plugin package, at startup (REQ-PLUGIN-240-243, 260-261)."""
        return self._scan_and_activate()

    def rescan(self) -> PluginLoadResult:
        """Re-scan the plugins directory on demand, activating anything not
        currently active — a new folder, or one that failed before, are
        retried identically every time rather than remembered as
        permanently broken (REQ-PLUGIN-360). Never re-activates an
        already-active plugin (REQ-PLUGIN-361): an active plugin's folder
        is skipped before any import is even attempted, so its module is
        never re-executed by a Rescan.
        """
        return self._scan_and_activate()

    def active_plugin_names(self) -> list[str]:
        """Every currently-active plugin's name, sorted (#150) — backs the
        "Reload Plugin" submenu."""
        return sorted(self._active.keys())

    def reload_one(self, name: str) -> bool:
        """Stop *name*, purge its cached module(s), and reactivate a
        freshly re-imported copy from disk (REQ-PLUGIN-370). Returns
        False — leaving the plugin unloaded, never rolled back to the
        copy that was running before — if it isn't currently active, its
        package no longer declares a class with this name, or the
        freshly reactivated copy's activate() fails (REQ-PLUGIN-372).
        """
        active = self._active.get(name)
        if active is None:
            logger.error("Cannot reload '%s' — not currently active", name)
            return False

        pkg_name = active.entry_path.parent.name
        self._deactivate_one(active)

        try:
            classes = self._import_plugin_classes(pkg_name, active.entry_path)
        except Exception:
            logger.exception("Failed to re-import plugin package '%s' for reload", pkg_name)
            # F2 fix: this early return used to leave _failed untouched, so
            # a plugin that failed to reload looked neither active nor
            # failed to the Plugin Overview list (#160) — indistinguishable
            # from one the user deliberately disabled.
            self._failed[pkg_name] = "Failed to re-import plugin package for reload"
            return False

        matching = next((cls for cls in classes if cls.name == name), None)
        if matching is None:
            logger.error(
                "Reload failed — '%s' no longer declares a plugin named '%s'", pkg_name, name,
            )
            self._failed[pkg_name] = f"Package no longer declares a plugin named '{name}'"
            return False

        seen_names = set(self._active.keys())
        result = PluginLoadResult()
        self._activate_one(matching, seen_names, active.entry_path, active.module_name, result)
        if name in self._active:
            self._failed.pop(pkg_name, None)
        else:
            self._failed[pkg_name] = "Plugin failed to reactivate after reload"
        return name in self._active

    def _scan_and_activate(self) -> PluginLoadResult:
        result = PluginLoadResult()
        try:
            self._plugins_dir.mkdir(parents=True, exist_ok=True)
            entries = sorted(self._plugins_dir.iterdir()) if self._plugins_dir.is_dir() else []
        except Exception:
            logger.exception("Failed to scan plugins directory '%s'", self._plugins_dir)
            return result

        active_entry_paths = {ap.entry_path for ap in self._active.values()}
        seen_names: set[str] = set(self._active.keys())
        disabled = self._settings.disabled_plugins if self._settings is not None else set()
        for entry in entries:
            init_py = entry / "__init__.py"
            if not entry.is_dir() or not init_py.is_file():
                continue
            if entry.name in disabled:
                # Disabled (#160) — never imported at all, not even to read
                # its declared name (REQ-PLUGIN-461/465). Checked before the
                # already-active check below since a disabled folder is
                # never active either.
                continue
            resolved_init_py = init_py.resolve()
            if resolved_init_py in active_entry_paths:
                # Already active — skipped before import is even attempted,
                # so an already-active plugin's module is never re-executed
                # and never reported as a duplicate-name failure (#150).
                continue
            self._activate_folder(entry, seen_names, result)
        return result

    def _activate_folder(
        self, entry: Path, seen_names: set[str], result: PluginLoadResult,
    ) -> None:
        """Import *entry*'s `__init__.py` and activate every class it
        declares, tracking folder-level (not per-class) failure state in
        `self._failed` (#160).

        A folder is only cleared from `self._failed` if every class it
        declares activates successfully this pass — one failing class
        among several from a "toolsuite" folder still marks the whole
        folder as failed, not just that one class, so a partial failure
        is never silently hidden by a sibling's success (F1 fix from the
        #160 architecture review).
        """
        init_py = entry / "__init__.py"
        folder_name = entry.name
        try:
            classes = self._import_plugin_classes(folder_name, init_py)
        except Exception:
            logger.exception("Failed to load plugin package '%s'", folder_name)
            result.failed.append(folder_name)
            self._failed[folder_name] = "Failed to import plugin package"
            return

        resolved_init_py = init_py.resolve()
        module_name = self._module_name_for(folder_name, init_py)
        any_failed = False
        for cls in classes:
            failed_before = len(result.failed)
            self._activate_one(cls, seen_names, resolved_init_py, module_name, result)
            if len(result.failed) > failed_before:
                any_failed = True
        if any_failed:
            self._failed[folder_name] = "One or more plugins in this package failed to activate"
        else:
            self._failed.pop(folder_name, None)

    def _module_name_for(self, pkg_name: str, init_py: Path) -> str:
        """The deterministic sys.modules name a package is imported under —
        a hash of its resolved folder path, so the same folder always maps
        to the same synthesized name (needed for reload_one() to find/purge
        the right cache entries)."""
        path_hash = hashlib.sha1(str(init_py.parent.resolve()).encode()).hexdigest()[:12]
        return f"_mdf_viewer_plugin_{path_hash}_{pkg_name}"

    def _import_plugin_classes(self, pkg_name: str, init_py: Path) -> list[type[Plugin]]:
        """Import *pkg_name*'s `__init__.py` and return its declared PLUGINS list."""
        module_name = self._module_name_for(pkg_name, init_py)

        spec = importlib.util.spec_from_file_location(
            module_name, init_py, submodule_search_locations=[str(init_py.parent)],
        )
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot create import spec for '{init_py}'")

        module = importlib.util.module_from_spec(spec)
        # Registered in sys.modules *before* exec_module() runs — a relative
        # import inside __init__.py's own body (e.g. `from . import sibling`,
        # needed for a multi-file "toolsuite" package) resolves against this
        # entry, so it must already be there when that import statement runs.
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
            plugins = getattr(module, "PLUGINS", None)
            if not isinstance(plugins, list) or not plugins:
                raise ValueError(f"'{pkg_name}' must define a non-empty PLUGINS list")
            for cls in plugins:
                if not (isinstance(cls, type) and issubclass(cls, Plugin)):
                    raise TypeError(f"'{pkg_name}'.PLUGINS contains a non-Plugin entry: {cls!r}")
        except Exception:
            sys.modules.pop(module_name, None)
            raise

        return plugins

    def _activate_one(
        self,
        cls: type[Plugin],
        seen_names: set[str],
        entry_path: Path,
        module_name: str,
        result: PluginLoadResult,
    ) -> None:
        try:
            instance = cls()
        except Exception:
            logger.exception("Failed to instantiate plugin '%s'", cls.__name__)
            result.failed.append(cls.__name__)
            return

        if instance.name in seen_names:
            logger.error("Duplicate plugin name '%s' — skipping", instance.name)
            result.failed.append(instance.name)
            return

        context = PluginContext(
            plugin_name=instance.name,
            app=self._app,
            registry=self._app.plugin_registry,
            tab_name_provider=self._tab_name_provider,
            settings=self._settings,
            main_window=self._main_window,
            app_version=self._app_version,
        )
        if instance.start(context):
            seen_names.add(instance.name)
            self._active[instance.name] = _ActivePlugin(
                instance=instance, module_name=module_name, entry_path=entry_path,
            )
            result.loaded.append(instance.name)
            logger.info("Activated plugin '%s'", instance.name)
        else:
            result.failed.append(instance.name)

    def _purge_module_cache(self, module_name: str) -> None:
        """Drop *module_name* and every submodule reachable under it
        (`module_name.sibling`, from a toolsuite package's relative
        imports) from sys.modules — otherwise a stale cached submodule can
        silently survive a Reload while the top-level file gets fresh code
        (REQ-PLUGIN-371)."""
        prefix = module_name + "."
        for key in [k for k in sys.modules if k == module_name or k.startswith(prefix)]:
            sys.modules.pop(key, None)

    def _purge_bytecode_cache(self, plugin_dir: Path) -> None:
        """Delete every on-disk `__pycache__` under *plugin_dir* before a
        reload's re-import (REQ-PLUGIN-371).

        Separate from `_purge_module_cache()`: that one only clears the
        in-memory `sys.modules` entry, but Python's compiled `.pyc` cache
        lives on disk, keyed by the source file's path, and its timestamp
        based invalidation check truncates to whole seconds — two rapid
        rewrites of the same plugin file within one second are otherwise
        indistinguishable to it, so a Reload could silently re-serve the
        pre-edit bytecode instead of the code just saved to disk.
        """
        for cache_dir in plugin_dir.rglob("__pycache__"):
            shutil.rmtree(cache_dir, ignore_errors=True)

    def _deactivate_one(self, active: "_ActivePlugin") -> None:
        """Stop one active plugin and purge its cached module(s)/bytecode —
        shared by reload_one() (#150) and set_enabled(False) (#160), so a
        plugin disabled mid-session and later re-enabled always re-imports
        fresh code rather than risking a stale cached submodule (the same
        class of bug REQ-PLUGIN-371 already fixed for Reload)."""
        active.instance.stop()
        logger.info("Deactivated plugin '%s'", active.instance.name)
        del self._active[active.instance.name]
        self._purge_module_cache(active.module_name)
        self._purge_bytecode_cache(active.entry_path.parent)

    def deactivate_all(self) -> None:
        """Deactivate every active plugin (REQ-PLUGIN-270). Idempotent."""
        module_names = {ap.module_name for ap in self._active.values()}
        for active in self._active.values():
            active.instance.stop()
        self._active.clear()
        for module_name in module_names:
            self._purge_module_cache(module_name)

    def _active_folder_names(self) -> dict[str, list[str]]:
        """Reverse index: plugin-package folder name -> every currently
        active plugin name loaded from it — a "toolsuite" folder can have
        more than one (#160)."""
        result: dict[str, list[str]] = {}
        for name, active in self._active.items():
            result.setdefault(active.entry_path.parent.name, []).append(name)
        return result

    def active_plugin_names_for(self, folder_name: str) -> list[str]:
        """Every currently active plugin name loaded from *folder_name*,
        queried live (#160) — call this immediately before disabling a
        folder, never from a cached `PluginPackageInfo` snapshot, so UI
        teardown always matches the loader's true current state rather
        than what was true when the Overview dialog was last populated."""
        return self._active_folder_names().get(folder_name, [])

    def list_packages(self) -> list[PluginPackageInfo]:
        """Every discovered plugin package, independent of its enabled,
        active, or failed state (REQ-PLUGIN-460) — the Plugin Overview
        dialog's data source. Never imports a disabled package
        (REQ-PLUGIN-461). Prunes any stale disabled-folder settings entry
        for a folder no longer found on disk (REQ-PLUGIN-510).
        """
        try:
            entries = sorted(self._plugins_dir.iterdir()) if self._plugins_dir.is_dir() else []
        except Exception:
            logger.exception("Failed to scan plugins directory '%s'", self._plugins_dir)
            return []

        folder_names = {
            entry.name for entry in entries
            if entry.is_dir() and (entry / "__init__.py").is_file()
        }

        if self._settings is not None:
            self._settings.prune_disabled_plugins(folder_names)
            disabled = self._settings.disabled_plugins
        else:
            disabled = set()

        active_by_folder = self._active_folder_names()

        packages: list[PluginPackageInfo] = []
        for folder_name in sorted(folder_names):
            active_names = active_by_folder.get(folder_name, [])
            metadata = [
                {
                    "name": self._active[n].instance.name,
                    "version": self._active[n].instance.version,
                    "description": self._active[n].instance.description,
                    "author": self._active[n].instance.author,
                }
                for n in active_names
            ]
            packages.append(PluginPackageInfo(
                folder_name=folder_name,
                enabled=folder_name not in disabled,
                active_plugin_names=active_names,
                failed=folder_name in self._failed,
                failure_reason=self._failed.get(folder_name),
                metadata=metadata,
            ))
        return packages

    def set_enabled(self, folder_name: str, enabled: bool) -> PluginLoadResult:
        """Enable or disable one plugin package immediately (#160).

        Persists via `Settings` (a no-op there if settings aren't wired).
        Enabling takes the same action a targeted Rescan of just this one
        folder would; disabling takes the same action the disable-half of
        Reload already does for every plugin currently active from this
        folder. Folder name is the canonical identity here (REQ-PLUGIN-462)
        — a deliberately different identity from `reload_one()`'s existing
        plugin-*name*-keyed one, which this does not change.
        """
        result = PluginLoadResult()
        if self._settings is not None:
            self._settings.set_plugin_disabled(folder_name, not enabled)

        if enabled:
            if folder_name in self._active_folder_names():
                return result  # already active — nothing to do
            entry = self._plugins_dir / folder_name
            seen_names = set(self._active.keys())
            self._activate_folder(entry, seen_names, result)
        else:
            for name in self._active_folder_names().get(folder_name, []):
                self._deactivate_one(self._active[name])
            # F5 fix: a previously-failed folder that's now disabled no
            # longer shows a stale error — nothing is being attempted for
            # it while it stays disabled.
            self._failed.pop(folder_name, None)
        return result
