"""PluginContext — the only object a plugin is allowed to import (#71).

One instance is constructed per plugin (at plugin-load time — #72/#74's
job), so error logs and any future per-plugin permission scoping can
always be attributed to a specific plugin. Every read accessor returns a
read-only projection (``plugin_api.types``); the live, mutable
``ActiveSignal``/``LoadedMeasurement`` objects the application uses
internally are never handed to a plugin directly.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable

import numpy as np

from mdf_viewer.enums import CursorMode
from mdf_viewer.model.virtual_measurement_loader import VirtualMeasurementLoader
from mdf_viewer.model.virtual_signal import VirtualSignal
from mdf_viewer.plugin_api.registry import (
    DockWidgetMode,
    DockWidgetRegistration,
    MenuActionRegistration,
    TabTypeRegistration,
)
from mdf_viewer.plugin_api.types import (
    PluginCursorMovedEvent,
    PluginFileLoadedEvent,
    PluginMeasurementClosedEvent,
    PluginMeasurementView,
    PluginSelectionChangedEvent,
    PluginSignalAddedEvent,
    PluginSignalRemovedEvent,
    PluginSignalView,
    PluginTabCursor,
    PluginTabSignals,
)

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QWidget

    from mdf_viewer.controller.app_controller import AppController
    from mdf_viewer.model.signal_data import SignalData
    from mdf_viewer.model.signal_metadata import SignalMetadata
    from mdf_viewer.view_model.active_signal import ActiveSignal
    from mdf_viewer.plugin_api.registry import PluginRegistry

logger = logging.getLogger("mdf_viewer.plugin_api")

# EventBus's own registered signal names (controller/events.py) — the only
# names a plugin may subscribe to. Every name here MUST have a matching
# branch in PluginContext._translate_event() (#149) — that method's final
# `else` raises loudly rather than ever forwarding a raw, untranslated
# payload, and tests/plugin_api/test_context_registration.py cross-checks
# this set against EventBus's own real signal attributes, so a future event
# added to one but not the other is caught immediately rather than silently
# leaking a live ActiveSignal/TabWorkspace to plugins.
_KNOWN_EVENTS = frozenset(
    {
        "file_loaded", "signal_added", "signal_removed", "selection_changed",
        "cursor_moved", "measurement_closed",
    }
)


class PluginContext:
    """Per-plugin facade over the application (REQ-PLUGIN-060)."""

    def __init__(
        self,
        plugin_name: str,
        app: "AppController",
        registry: "PluginRegistry",
        tab_name_provider: Callable[[int], str] | None = None,
    ) -> None:
        self._plugin_name = plugin_name
        self._app = app
        self._registry = registry
        self._tab_name_provider = tab_name_provider
        # (event_name, wrapped_handler) pairs, for unsubscribe_all() teardown.
        self._subscriptions: list[tuple[str, Callable[[Any], None]]] = []

    def _tab_name(self, index: int) -> str:
        if self._tab_name_provider is not None:
            return self._tab_name_provider(index)
        return f"Tab {index + 1}"

    def _to_signal_view(self, active: "ActiveSignal") -> PluginSignalView:
        """Build a PluginSignalView for *active* — the one place that knows
        how (shared by the read surface and event translation, #149)."""
        measurement_view = (
            PluginMeasurementView.from_measurement(
                active.measurement, is_primary=active.measurement is self._app.primary_measurement,
            )
            if active.measurement is not None
            else None
        )
        token = self._app.token_for_signal(active)
        return PluginSignalView.from_active(active, token, measurement_view)

    def _tab_index_for(self, workspace: object) -> int | None:
        """Resolve a raw TabWorkspace to its tab index, or None if it's since
        been removed (#149) — never hand a plugin the TabWorkspace itself."""
        for index, ws in enumerate(self._app.all_workspaces()):
            if ws is workspace:
                return index
        return None

    # ------------------------------------------------------------------
    # Read access (REQ-PLUGIN-070/080/090/100/110)
    # ------------------------------------------------------------------

    @property
    def active_signals(self) -> list[PluginTabSignals]:
        """Every tab's active signals, in tab order (REQ-PLUGIN-070)."""
        active_index = self._app.active_tab_index
        result = []
        for index, workspace in enumerate(self._app.all_workspaces()):
            signals = [self._to_signal_view(active) for active in workspace.active]
            result.append(
                PluginTabSignals(
                    tab_index=index,
                    tab_name=self._tab_name(index),
                    is_active=index == active_index,
                    signals=tuple(signals),
                )
            )
        return result

    @property
    def measurements(self) -> list[PluginMeasurementView]:
        """Every loaded measurement, with which one is Primary (REQ-PLUGIN-100)."""
        primary = self._app.primary_measurement
        return [
            PluginMeasurementView.from_measurement(m, is_primary=m is primary)
            for m in self._app.measurements
        ]

    @property
    def cursor_positions(self) -> list[PluginTabCursor]:
        """Current cursor state of every tab (REQ-PLUGIN-110)."""
        active_index = self._app.active_tab_index
        result = []
        for index, workspace in enumerate(self._app.all_workspaces()):
            if workspace.cursor_ctrl is None:
                mode, positions = CursorMode.HIDDEN, ()
            else:
                snapshot = workspace.cursor_ctrl.snapshot()
                try:
                    mode = CursorMode[snapshot.get("mode", "HIDDEN")]
                except KeyError:
                    mode = CursorMode.HIDDEN
                positions = tuple(snapshot.get("positions", []))
            result.append(
                PluginTabCursor(
                    tab_index=index,
                    tab_name=self._tab_name(index),
                    is_active=index == active_index,
                    mode=mode,
                    positions=positions,
                )
            )
        return result

    def get_samples(self, signal_view: PluginSignalView) -> tuple["np.ndarray", "np.ndarray"] | None:
        """Timestamps/values for *signal_view*, or None if it's since been removed (REQ-PLUGIN-090).

        Always returns copies, never the application's live arrays.
        """
        active = self._app.find_active_signal_by_id(signal_view._signal_token)
        if active is None:
            return None
        return active.display_timestamps.copy(), active.data.samples.copy()

    # ------------------------------------------------------------------
    # UI registration — stubs: recorded here, rendered by #73 (REQ-PLUGIN-120/130)
    # ------------------------------------------------------------------

    def register_menu_action(self, label: str, callback: Callable[[], None]) -> None:
        """Register an entry in the application's single "Plugins" menu.

        No per-plugin placement control (REQ-PLUGIN-120) — every plugin's
        actions land in the same fixed menu. Recorded in the shared
        PluginRegistry; not rendered into the real menu bar until #73.
        """
        self._registry.add_menu_action(
            MenuActionRegistration(plugin_name=self._plugin_name, label=label, callback=callback)
        )

    def register_dock_widget(
        self, title: str, widget_factory: "Callable[[], QWidget]", mode: DockWidgetMode,
    ) -> None:
        """Register a dock widget, shown either docked (right-side drawer) or as a dialog.

        No free-form area placement (REQ-PLUGIN-130) — the plugin picks one
        of these two fixed modes. Recorded in the shared PluginRegistry; not
        rendered into the real UI until #73.
        """
        self._registry.add_dock_widget(
            DockWidgetRegistration(
                plugin_name=self._plugin_name, title=title, widget_factory=widget_factory, mode=mode,
            )
        )

    def register_tab_type(
        self, type_id: str, display_name: str, view_factory: "Callable[[], QWidget]",
    ) -> None:
        """Register a tab type — a template a user can create any number of
        independent tab instances from (#148), unlike register_dock_widget's
        single cached instance. *type_id* must be globally unique (rejected,
        logged, if it collides with another plugin's or the reserved
        built-in "plot" type). Recorded in the shared PluginRegistry; not
        rendered into the real UI until MainWindow's tab-creation code
        reads it.
        """
        self._registry.add_tab_type(
            TabTypeRegistration(
                plugin_name=self._plugin_name, type_id=type_id, display_name=display_name,
                view_factory=view_factory,
            )
        )

    # ------------------------------------------------------------------
    # Virtual measurement contribution (#147)
    # ------------------------------------------------------------------

    def create_virtual_signal(
        self,
        name: str,
        resolver: "Callable[[], tuple[SignalData, SignalMetadata]]",
        *,
        unit: str = "",
        comment: str = "",
    ) -> VirtualSignal:
        """Create a virtual signal, not yet attached to any measurement (REQ-PLUGIN-290).

        *resolver* is called by the application only when the signal is
        actually needed for display (REQ-VMEAS-140) — never eagerly here.
        Returns the real VirtualSignal instance directly, not an opaque
        token: unlike a PluginSignalView (which wraps live, shared,
        app-mutated state a plugin could otherwise hold a stale reference
        to), this is data the plugin itself just created and nothing else
        mutates concurrently.
        """
        from mdf_viewer.model.signal_metadata import SignalMetadata

        template = SignalMetadata(name=name, unit=unit, comment=comment)
        return VirtualSignal(name=name, resolver=resolver, template=template)

    def create_virtual_measurement(self) -> VirtualMeasurementLoader:
        """Create an empty virtual measurement (REQ-PLUGIN-291).

        Not yet visible anywhere — attach signals via attach_virtual_signal(),
        then call register_virtual_measurement() to add it to the pool.
        """
        return VirtualMeasurementLoader(owner_plugin=self._plugin_name)

    def attach_virtual_signal(
        self, measurement: VirtualMeasurementLoader, signal: VirtualSignal
    ) -> None:
        """Attach *signal* to *measurement*'s channel tree (REQ-PLUGIN-291).

        Callable any number of times before register_virtual_measurement().
        """
        measurement.attach(signal)

    def register_virtual_measurement(self, measurement: VirtualMeasurementLoader, label: str) -> None:
        """Add *measurement* to the application's measurement pool (REQ-PLUGIN-292).

        Makes it visible in the Signal Browser and everywhere else a real
        measurement would be, attributed to this plugin for later teardown
        (REQ-PLUGIN-300/301) and user-close notification (REQ-PLUGIN-302).
        """
        self._app.add_virtual_measurement(measurement, label, owner_plugin=self._plugin_name)

    # ------------------------------------------------------------------
    # Event subscription (REQ-PLUGIN-140/150)
    # ------------------------------------------------------------------

    def _translate_event(self, event_name: str, payload: Any) -> Any:
        """Translate a raw EventBus payload into the plugin-safe equivalent (#149).

        Every branch here corresponds to one of _KNOWN_EVENTS; the final
        `else` is a deliberate loud failure, not a silent passthrough — a
        future event added to EventBus without a matching branch here must
        never fall through to forwarding a raw, live payload to a plugin.
        """
        if event_name == "file_loaded":
            return PluginFileLoadedEvent(
                path=payload.path, tab_index=self._tab_index_for(payload.tab),
            )
        if event_name == "signal_added":
            return PluginSignalAddedEvent(
                signal=self._to_signal_view(payload.signal),
                tab_index=self._tab_index_for(payload.tab),
            )
        if event_name == "signal_removed":
            return PluginSignalRemovedEvent(
                signal=self._to_signal_view(payload.signal),
                tab_index=self._tab_index_for(payload.tab),
            )
        if event_name == "selection_changed":
            return PluginSelectionChangedEvent(
                selected=tuple(self._to_signal_view(a) for a in payload.selected),
                tab_index=self._tab_index_for(payload.tab),
            )
        if event_name == "cursor_moved":
            return PluginCursorMovedEvent(
                positions=tuple(payload.positions),
                mode=payload.mode,
                tab_index=self._tab_index_for(payload.tab),
            )
        if event_name == "measurement_closed":
            return PluginMeasurementClosedEvent(label=payload.label, is_virtual=payload.is_virtual)
        raise AssertionError(f"no plugin-safe translation registered for event '{event_name}'")

    def subscribe(self, event_name: str, handler: Callable[[Any], None]) -> None:
        """Subscribe *handler* to one of AppController.events' signals.

        *event_name* must be one of "file_loaded", "signal_added",
        "signal_removed", "selection_changed", "cursor_moved" (EventBus's
        own registered signal names). The raw payload is never forwarded
        as-is — it's translated into a read-only plugin-facing equivalent
        first (REQ-PLUGIN-080, #149): a signal becomes a PluginSignalView,
        the raw TabWorkspace becomes a tab_index. A raising *handler* is
        caught and logged, never propagated (REQ-PLUGIN-150) — the emitting
        EventBus keeps working for every other subscriber.
        """
        if event_name not in _KNOWN_EVENTS:
            raise ValueError(f"Unknown plugin event '{event_name}'")

        def wrapped(payload: Any) -> None:
            try:
                handler(self._translate_event(event_name, payload))
            except Exception:
                logger.exception(
                    "Plugin '%s' handler for event '%s' failed", self._plugin_name, event_name,
                )

        getattr(self._app.events, event_name).connect(wrapped)
        self._subscriptions.append((event_name, wrapped))

    def unsubscribe_all(self) -> None:
        """Disconnect every handler this context ever subscribed (plugin unload, #72).

        Safe to call more than once, and safe even if a signal was already
        disconnected some other way — mirrors the try/except TypeError
        idiom already established in view/plot_stripe.py for Qt signal teardown.
        """
        for event_name, wrapped in self._subscriptions:
            signal = getattr(self._app.events, event_name)
            try:
                signal.disconnect(wrapped)
            except TypeError:
                pass
        self._subscriptions.clear()

    def _teardown(self) -> None:
        """Undo everything this plugin registered/subscribed (#72).

        Framework-internal — called only by Plugin.start()'s failure path
        and Plugin.stop(), never by a plugin itself (unlike subscribe()/
        register_menu_action()/etc., which are the plugin-author-facing
        contract).
        """
        self.unsubscribe_all()
        self._registry.remove_registrations_for(self._plugin_name)
        # Appended last, deliberately after unsubscribe_all(): this
        # plugin's own measurement_closed subscription (if any) is already
        # gone by the time remove_virtual_measurements_for() below triggers
        # close_measurement()'s measurement_closed emission for its own
        # measurements — no redundant "your own measurement was closed"
        # callback while already mid-teardown (#147, REQ-PLUGIN-301). Other,
        # still-active plugins remain subscribed and do receive it.
        self._app.remove_virtual_measurements_for(self._plugin_name)
