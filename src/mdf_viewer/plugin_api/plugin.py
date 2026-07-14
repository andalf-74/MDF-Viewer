"""Plugin — the base class a plugin author implements against (#72).

``PluginContext`` (``plugin_api.context``) is what a plugin *receives*;
``Plugin`` is what a plugin author *writes*. ``activate(context)`` is the
only place a plugin can ever register anything (menu actions, dock
widgets, event subscriptions), so it is mandatory; ``deactivate()`` and
the five event handler methods are optional, since the base class's own
``start()``/``stop()`` lifecycle entry points (called by the future
plugin loader, #74) already handle auto-wiring and teardown regardless
of what a plugin overrides.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from mdf_viewer.plugin_api.context import PluginContext

logger = logging.getLogger("mdf_viewer.plugin_api")

# EventBus signal name -> Plugin handler method name (#70's five events,
# plus #147's measurement_closed).
_EVENT_HANDLER_NAMES = {
    "file_loaded": "on_file_loaded",
    "signal_added": "on_signal_added",
    "signal_removed": "on_signal_removed",
    "selection_changed": "on_selection_changed",
    "cursor_moved": "on_cursor_moved",
    "measurement_closed": "on_measurement_closed",
}


class Plugin:
    """Base class for a plugin (REQ-PLUGIN-160-190).

    Metadata (``name``/``version``/``description``/``author``) is declared
    as plain class attributes on a subclass. ``context``/``_active`` are
    likewise class-level defaults rather than instance attributes set in
    ``__init__`` — a subclass needs no constructor of its own, and one that
    defines ``__init__`` doesn't have to remember to call
    ``super().__init__()`` for lifecycle state to exist.
    """

    name: str = ""
    version: str = ""
    description: str = ""
    author: str = ""

    context: "PluginContext | None" = None
    _active: bool = False

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if not cls.name:
            raise ValueError(f"{cls.__name__} must set a non-empty 'name'")

    # ------------------------------------------------------------------
    # Plugin-author-facing hooks
    # ------------------------------------------------------------------

    def activate(self, context: "PluginContext") -> None:
        """Called once, when the plugin is loaded (REQ-PLUGIN-170).

        Mandatory — the only place a plugin can ever register a menu
        action, a dock widget, or an event subscription.
        """
        raise NotImplementedError(f"{type(self).__name__} must implement activate()")

    def deactivate(self) -> None:
        """Called once, when the plugin is unloaded (REQ-PLUGIN-171). Optional."""

    def on_file_loaded(self, event: Any) -> None:
        """Override to receive `file_loaded` events (REQ-PLUGIN-180/181)."""

    def on_signal_added(self, event: Any) -> None:
        """Override to receive `signal_added` events (REQ-PLUGIN-180/181)."""

    def on_signal_removed(self, event: Any) -> None:
        """Override to receive `signal_removed` events (REQ-PLUGIN-180/181)."""

    def on_selection_changed(self, event: Any) -> None:
        """Override to receive `selection_changed` events (REQ-PLUGIN-180/181)."""

    def on_cursor_moved(self, event: Any) -> None:
        """Override to receive `cursor_moved` events (REQ-PLUGIN-180/181)."""

    def on_measurement_closed(self, event: Any) -> None:
        """Override to receive `measurement_closed` events (#147, REQ-PLUGIN-302).

        Fires for any measurement close, real or virtual — broadcast, not
        targeted; check `event.is_virtual` and your own bookkeeping to tell
        whether this was a measurement your plugin contributed.
        """

    @property
    def is_active(self) -> bool:
        return self._active

    # ------------------------------------------------------------------
    # Framework-facing lifecycle entry points — called by the future
    # plugin loader (#74), never by a plugin itself.
    # ------------------------------------------------------------------

    def start(self, context: "PluginContext") -> bool:
        """Activate this plugin. Idempotent. Returns True on success.

        On failure, tears down whatever *context* had already recorded
        before ``activate()`` raised (REQ-PLUGIN-172) — otherwise a
        partial registration/subscription from a failed activation would
        leak forever, since a plugin that never became active is never
        later passed to stop().
        """
        if self._active:
            return True
        self.context = context
        try:
            self.activate(context)
        except Exception:
            logger.exception("Plugin '%s' failed to activate", self.name)
            context._teardown()
            self.context = None
            return False
        self._auto_wire_events(context)
        self._active = True
        return True

    def stop(self) -> None:
        """Deactivate this plugin. Idempotent — no-op if not active.

        Always tears down and resets lifecycle state, even if
        deactivate() or teardown itself raises, so bookkeeping never
        desyncs from reality (REQ-PLUGIN-171/172's "exactly once").
        """
        if not self._active:
            return
        context = self.context
        assert context is not None
        try:
            self.deactivate()
        except Exception:
            logger.exception("Plugin '%s' failed to deactivate", self.name)
        finally:
            try:
                context._teardown()
            except Exception:
                logger.exception("Plugin '%s' failed to tear down", self.name)
            finally:
                self.context = None
                self._active = False

    def _auto_wire_events(self, context: "PluginContext") -> None:
        for event_name, handler_name in _EVENT_HANDLER_NAMES.items():
            if getattr(type(self), handler_name) is not getattr(Plugin, handler_name):
                context.subscribe(event_name, getattr(self, handler_name))
