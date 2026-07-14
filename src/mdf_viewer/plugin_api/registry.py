"""Plugin UI-contribution registry (#71).

``PluginContext.register_menu_action``/``register_dock_widget`` record a
contribution here; nothing renders it into the real UI yet — that wiring
is #73 (UI extension points in MainWindow). One ``PluginRegistry`` instance
is shared across every plugin's ``PluginContext`` (each entry is tagged
with the owning ``plugin_name``, so sharing one registry is safe and lets
#73 build one combined view — e.g. the single "Plugins" menu — without
needing to poll every plugin separately).

Every registration wraps the plugin-supplied callable in a try/except so a
misbehaving plugin can never crash the application (REQ-PLUGIN-150) —
whoever eventually calls ``invoke()``/``build()`` (#73) gets that safety
for free, without reimplementing it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Literal

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QWidget

logger = logging.getLogger("mdf_viewer.plugin_api")

DockWidgetMode = Literal["docked", "dialog"]


@dataclass(frozen=True)
class MenuActionRegistration:
    """A plugin-registered entry in the application's "Plugins" menu."""

    plugin_name: str
    label: str
    callback: Callable[[], None]

    def invoke(self) -> bool:
        """Run the plugin's callback. Returns True on success, False if it raised (#73)."""
        try:
            self.callback()
        except Exception:
            logger.exception("Plugin '%s' menu action '%s' failed", self.plugin_name, self.label)
            return False
        return True


@dataclass(frozen=True)
class DockWidgetRegistration:
    """A plugin-registered dock widget, docked or shown as a dialog."""

    plugin_name: str
    title: str
    widget_factory: "Callable[[], QWidget]"
    mode: DockWidgetMode

    def build(self) -> "QWidget | None":
        try:
            return self.widget_factory()
        except Exception:
            logger.exception("Plugin '%s' dock widget '%s' failed to build", self.plugin_name, self.title)
            return None


# Reserved for the built-in Plot tab type — a plugin can never register
# this type_id (#148).
RESERVED_TAB_TYPE_IDS = frozenset({"plot"})


@dataclass(frozen=True)
class TabTypeRegistration:
    """A plugin-registered tab type — a template a user can create any
    number of independent tab instances from (#148), unlike a dock
    widget's single cached instance."""

    plugin_name: str
    type_id: str
    display_name: str
    view_factory: "Callable[[], QWidget]"

    def build(self) -> "QWidget | None":
        try:
            return self.view_factory()
        except Exception:
            logger.exception("Plugin '%s' tab type '%s' failed to build", self.plugin_name, self.type_id)
            return None


@dataclass
class PluginRegistry:
    """Shared container of every plugin's UI-contribution registrations."""

    menu_actions: list[MenuActionRegistration] = field(default_factory=list)
    dock_widgets: list[DockWidgetRegistration] = field(default_factory=list)
    tab_types: list[TabTypeRegistration] = field(default_factory=list)

    def add_menu_action(self, registration: MenuActionRegistration) -> None:
        self.menu_actions.append(registration)

    def add_dock_widget(self, registration: DockWidgetRegistration) -> None:
        self.dock_widgets.append(registration)

    def add_tab_type(self, registration: TabTypeRegistration) -> None:
        """Record *registration*, unless its type_id collides with the
        reserved built-in "plot" type or an already-registered one (#148).

        Unlike menu action labels / dock widget titles, type_id must be a
        stable, globally-unique lookup key — a .mvc file stores the bare
        type_id string as the only way to identify which factory recreates
        a tab, so two plugins silently colliding on the same id would make
        restore ambiguous. A collision is logged and the registration
        dropped, not raised — a plugin's own mistake shouldn't crash it.
        """
        existing_ids = RESERVED_TAB_TYPE_IDS | {r.type_id for r in self.tab_types}
        if registration.type_id in existing_ids:
            logger.error(
                "Plugin '%s' tried to register tab type '%s', which is already in use",
                registration.plugin_name, registration.type_id,
            )
            return
        self.tab_types.append(registration)

    def remove_registrations_for(self, plugin_name: str) -> None:
        """Drop every registration belonging to *plugin_name* (plugin unload)."""
        self.menu_actions = [r for r in self.menu_actions if r.plugin_name != plugin_name]
        self.dock_widgets = [r for r in self.dock_widgets if r.plugin_name != plugin_name]
        self.tab_types = [r for r in self.tab_types if r.plugin_name != plugin_name]
