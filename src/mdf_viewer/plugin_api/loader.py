"""Plugin loader and discovery (#74) — the piece that finally does something
with #71/#72/#73: scans a real plugins directory, imports each plugin
package, instantiates and activates its declared Plugin classes, and
deactivates them again on shutdown.

App-side bootstrapping code, not part of the plugin-author-facing
contract — a plugin never imports this module. Kept in this package for
cohesion with types.py/registry.py/context.py/plugin.py.
"""

from __future__ import annotations

import hashlib
import importlib.util
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Callable

from mdf_viewer.plugin_api.context import PluginContext
from mdf_viewer.plugin_api.plugin import Plugin

if TYPE_CHECKING:
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
    """Summary of one load_all() run, for testability."""

    loaded: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)


class PluginLoader:
    """Discovers, activates, and deactivates plugin packages (REQ-PLUGIN-240-280)."""

    def __init__(
        self,
        app: "AppController",
        plugins_dir: Path,
        tab_name_provider: Callable[[int], str] | None = None,
    ) -> None:
        self._app = app
        self._plugins_dir = plugins_dir
        self._tab_name_provider = tab_name_provider
        self._started: list[Plugin] = []
        self._loaded_module_names: list[str] = []

    def load_all(self) -> PluginLoadResult:
        """Discover and activate every plugin package (REQ-PLUGIN-240-243, 260-261)."""
        result = PluginLoadResult()
        try:
            self._plugins_dir.mkdir(parents=True, exist_ok=True)
            entries = sorted(self._plugins_dir.iterdir()) if self._plugins_dir.is_dir() else []
        except Exception:
            logger.exception("Failed to scan plugins directory '%s'", self._plugins_dir)
            return result

        seen_names: set[str] = set()
        for entry in entries:
            init_py = entry / "__init__.py"
            if not entry.is_dir() or not init_py.is_file():
                continue
            try:
                classes = self._import_plugin_classes(entry.name, init_py)
            except Exception:
                logger.exception("Failed to load plugin package '%s'", entry.name)
                result.failed.append(entry.name)
                continue
            for cls in classes:
                self._activate_one(cls, seen_names, result)
        return result

    def _import_plugin_classes(self, pkg_name: str, init_py: Path) -> list[type[Plugin]]:
        """Import *pkg_name*'s `__init__.py` and return its declared PLUGINS list."""
        path_hash = hashlib.sha1(str(init_py.parent.resolve()).encode()).hexdigest()[:12]
        module_name = f"_mdf_viewer_plugin_{path_hash}_{pkg_name}"

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

        self._loaded_module_names.append(module_name)
        return plugins

    def _activate_one(
        self, cls: type[Plugin], seen_names: set[str], result: PluginLoadResult,
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
        )
        if instance.start(context):
            seen_names.add(instance.name)
            self._started.append(instance)
            result.loaded.append(instance.name)
        else:
            result.failed.append(instance.name)

    def deactivate_all(self) -> None:
        """Deactivate every started plugin (REQ-PLUGIN-270). Idempotent."""
        for plugin in self._started:
            plugin.stop()
        self._started.clear()
        for module_name in self._loaded_module_names:
            sys.modules.pop(module_name, None)
        self._loaded_module_names.clear()
