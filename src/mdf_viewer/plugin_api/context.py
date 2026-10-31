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
from mdf_viewer.errors import MdfLoadError
from mdf_viewer.model.virtual_measurement_loader import VirtualMeasurementLoader
from mdf_viewer.model.virtual_signal import VirtualSignal
from mdf_viewer.plugin_api.errors import ChannelLoadError
from mdf_viewer.plugin_api.registry import (
    DockWidgetMode,
    DockWidgetRegistration,
    MenuActionRegistration,
    PreferencesPageRegistration,
    TabTypeRegistration,
)
from mdf_viewer.plugin_api.types import (
    PluginChannelView,
    PluginCursorMovedEvent,
    PluginFileLoadedEvent,
    PluginMeasurementClosedEvent,
    PluginMeasurementUpdatedEvent,
    PluginMeasurementView,
    PluginSelectionChangedEvent,
    PluginSignalAddedEvent,
    PluginSignalRemovedEvent,
    PluginSignalView,
    PluginTabCursor,
    PluginTabSignals,
)

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QMainWindow, QWidget

    from mdf_viewer.controller.app_controller import AppController
    from mdf_viewer.model.loaded_measurement import LoadedMeasurement
    from mdf_viewer.model.signal_data import SignalData
    from mdf_viewer.model.signal_metadata import SignalMetadata
    from mdf_viewer.view_model.active_signal import ActiveSignal
    from mdf_viewer.plugin_api.registry import PluginRegistry
    from mdf_viewer.settings import Settings

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
        "cursor_moved", "measurement_closed", "measurement_updated",
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
        settings: "Settings | None" = None,
        main_window: "QMainWindow | None" = None,
        app_version: str = "",
    ) -> None:
        self._plugin_name = plugin_name
        self._app = app
        self._registry = registry
        self._tab_name_provider = tab_name_provider
        self._settings = settings
        self._main_window = main_window
        self._app_version = app_version
        # (event_name, wrapped_handler) pairs, for unsubscribe_all() teardown.
        self._subscriptions: list[tuple[str, Callable[[Any], None]]] = []
        # Flattened channel_tree() per measurement token, file-backed
        # measurements only (#189): their tree never changes while the
        # token lives, and a Replace… mints a new token. Holds metadata,
        # never PluginChannelViews, so each call builds views with the
        # measurement's current offset/Primary state. Virtual trees change
        # on attach/detach (#162) and are never cached.
        self._channel_cache: dict[int, list["SignalMetadata"]] = {}

    def _tab_name(self, index: int) -> str:
        if self._tab_name_provider is not None:
            return self._tab_name_provider(index)
        return f"Tab {index + 1}"

    def _to_signal_view(self, active: "ActiveSignal") -> PluginSignalView:
        """Build a PluginSignalView for *active* — the one place that knows
        how (shared by the read surface and event translation, #149)."""
        measurement_view = (
            self._to_measurement_view(active.measurement)
            if active.measurement is not None
            else None
        )
        token = self._app.token_for_signal(active)
        channel = (
            self._channel_for(active, measurement_view)
            if active.measurement is not None and measurement_view is not None
            else None
        )
        return PluginSignalView.from_active(active, token, measurement_view, channel)

    def _channel_for(
        self, active: "ActiveSignal", measurement_view: PluginMeasurementView,
    ) -> PluginChannelView:
        """The channel *active* was loaded from (REQ-PLUGIN-574).

        Descriptive fields come from the channel_tree() entry — what the
        Signal Browser and list_channels() show — not from active.metadata,
        since load_signal() extracts name/unit/comment differently. Falls
        back to active.metadata if the tree can't be read or no longer has
        the entry; equality only uses the handle, so either way it equals
        the list_channels() entry for the same channel.
        """
        meta = active.metadata
        for candidate in self._channel_metadata(active.measurement, measurement_view.key):
            if (candidate.group_index, candidate.channel_index) == (meta.group_index, meta.channel_index):
                meta = candidate
                break
        return PluginChannelView.from_metadata(meta, measurement_view)

    def _channel_metadata(self, measurement: "LoadedMeasurement", token: int) -> list["SignalMetadata"]:
        """*measurement*'s channels in Signal Browser order — group by
        group, channels in stored order (REQ-PLUGIN-571). `[]` (logged) if
        the tree can't be read: enumeration never raises a loader error at
        a plugin."""
        cached = self._channel_cache.get(token)
        if cached is not None:
            return cached
        try:
            channels = [ch for group in measurement.loader.channel_tree() for ch in group.channels]
        except Exception:
            logger.exception("Could not enumerate channels of measurement '%s'", measurement.label)
            return []
        if measurement.owner_plugin is None:
            # Forget lists for measurements closed since (dead tokens are
            # never looked up again, and tokens are never reused).
            for stale in [t for t in self._channel_cache if self._app.find_measurement_by_token(t) is None]:
                del self._channel_cache[stale]
            self._channel_cache[token] = channels
        return channels


    def _to_measurement_view(self, measurement: "LoadedMeasurement") -> PluginMeasurementView:
        """Build a PluginMeasurementView for *measurement* — the one place
        that knows how, so every view carries a live token (#189)."""
        return PluginMeasurementView.from_measurement(
            measurement,
            is_primary=measurement is self._app.primary_measurement,
            token=self._app.token_for_measurement(measurement),
        )

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
        return [self._to_measurement_view(m) for m in self._app.measurements]

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
    # Reading any loaded channel (#189, REQ-PLUGIN-570-586)
    # ------------------------------------------------------------------

    def list_channels(self, measurement: PluginMeasurementView) -> list[PluginChannelView]:
        """Every channel of *measurement* — exactly what the Signal Browser
        shows for it, in the file's own order; for a virtual measurement,
        in attach order (REQ-PLUGIN-570/571).

        An empty list if *measurement* has since been closed or replaced
        (REQ-PLUGIN-575), or if its channels can't be enumerated (logged).
        """
        live = self._app.find_measurement_by_token(measurement.key)
        if live is None:
            return []
        view = self._to_measurement_view(live)
        return [
            PluginChannelView.from_metadata(meta, view)
            for meta in self._channel_metadata(live, view.key)
        ]

    def find_channels(
        self, name: str, measurement: PluginMeasurementView | None = None,
    ) -> list[PluginChannelView]:
        """Every channel named exactly *name* (case-sensitive) — across
        all loaded measurements in pool order, or within *measurement* only
        (REQ-PLUGIN-573). Disambiguating several matches is the plugin's
        job. An empty list for a closed or replaced *measurement*.
        """
        if measurement is not None:
            candidates = [measurement]
        else:
            candidates = self.measurements
        return [ch for m in candidates for ch in self.list_channels(m) if ch.name == name]

    def load_samples(self, channel: PluginChannelView) -> tuple["np.ndarray", "np.ndarray"] | None:
        """Timestamps and values of *channel*, plotted or not (REQ-PLUGIN-580).

        Timestamps include the measurement's time offset as it is right now,
        matching get_samples() for the same signal when plotted
        (REQ-PLUGIN-581); both arrays are copies (REQ-PLUGIN-582). None if
        the measurement has since been closed or replaced, or a virtual
        channel has been detached (REQ-PLUGIN-583). Raises ChannelLoadError
        if the channel can't be provided as numeric samples, or on any
        other read failure (REQ-PLUGIN-584/585). Reading a virtual channel
        runs its resolver (REQ-PLUGIN-586).

        Synchronous: call it from the GUI thread only. Each call reads
        afresh; there is no caching contract.
        """
        measurement = self._app.find_measurement_by_token(channel._measurement_token)
        if measurement is None:
            return None
        loader = measurement.loader
        if isinstance(loader, VirtualMeasurementLoader) and not loader.has_channel(channel._channel_index):
            return None
        try:
            data, _metadata = loader.load_signal(channel._group_index, channel._channel_index)
        except MdfLoadError as exc:
            raise ChannelLoadError(str(exc)) from exc
        except Exception as exc:
            raise ChannelLoadError(f"Unexpected error reading '{channel.name}': {exc}") from exc
        return data.timestamps + measurement.offset_s, data.samples.copy()

    # ------------------------------------------------------------------
    # Application window/version access (#76, REQ-PLUGIN-450-452)
    # ------------------------------------------------------------------

    @property
    def main_window(self) -> "QMainWindow | None":
        """The application's real main window, for parenting a plugin's own
        modal dialogs (REQ-PLUGIN-450).

        Unlike every other accessor on this class, this is the live object
        itself, not a read-only projection (REQ-PLUGIN-451) — the same way
        a dock widget's or preferences page's `widget_factory` already
        deals in real, live `QWidget`s. `None` only in a test/headless
        context with no window constructed.

        `activate()` runs before the window is shown — a plugin that calls
        `.exec()` on a modal dialog synchronously from inside `activate()`
        itself would block application startup until the dialog is
        dismissed. Only show dialogs from a later callback (a menu action,
        an event handler, a background thread's result), not from
        `activate()` directly.
        """
        return self._main_window

    @property
    def app_version(self) -> str:
        """The running application's own version string, e.g. `"2.2"`
        (REQ-PLUGIN-452) — for a plugin that needs to compare against it
        (e.g. an update checker) without importing `mdf_viewer.__version__`
        directly, which would reach outside the documented plugin-import
        boundary.
        """
        return self._app_version

    # ------------------------------------------------------------------
    # Per-plugin settings (#159, REQ-PLUGIN-410-414)
    # ------------------------------------------------------------------

    def get_setting(self, key: str, default: Any = None) -> Any:
        """Read this plugin's own persisted setting (REQ-PLUGIN-410).

        Returns *default*, without persisting it, if the key was never set
        or no settings backend is available (REQ-PLUGIN-412). Usable at any
        point after this context exists — including from `activate()`
        itself, or from inside a preferences page's `widget_factory` — with
        no narrower lifecycle restriction (REQ-PLUGIN-413).
        """
        if self._settings is None:
            return default
        return self._settings.get_plugin_setting(self._plugin_name, key, default)

    def set_setting(self, key: str, value: Any) -> None:
        """Persist this plugin's own setting (REQ-PLUGIN-410/411).

        A no-op (logged, not raised) if no settings backend is available —
        that absence is not this plugin's fault. *key*/*value* validation
        (non-empty str key, JSON-safe value) happens in `Settings` itself.
        """
        if self._settings is None:
            logger.debug(
                "Plugin '%s' called set_setting('%s', ...) with no settings backend available",
                self._plugin_name, key,
            )
            return
        self._settings.set_plugin_setting(self._plugin_name, key, value)

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

    def register_preferences_page(
        self, title: str, widget_factory: "Callable[[], QWidget]",
    ) -> None:
        """Register this plugin's preferences page — at most one per plugin
        (REQ-PLUGIN-420/422), shown as one tab in the shared "Plugin
        Preferences…" dialog. A second call from the same plugin is
        rejected and logged; the first registration wins. Recorded in the
        shared PluginRegistry; not rendered into the real UI until #159's
        MainWindow wiring.
        """
        self._registry.add_preferences_page(
            PreferencesPageRegistration(
                plugin_name=self._plugin_name, title=title, widget_factory=widget_factory,
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

        Callable at any point in *measurement*'s lifetime, not only before
        register_virtual_measurement() (REQ-VMEAS-121, #162) — if
        *measurement* is already registered, the Signal Browser reflects
        the new signal immediately (REQ-PLUGIN-520).
        """
        measurement.attach(signal)
        self._app.notify_virtual_measurement_changed(measurement, signal.name, "attached")

    def detach_virtual_signal(
        self, measurement: VirtualMeasurementLoader, signal: VirtualSignal
    ) -> None:
        """Detach *signal* from *measurement*'s channel tree, by identity
        (REQ-PLUGIN-521/522, #162). If *signal* is currently plotted
        anywhere, it is removed from every plot immediately (REQ-VMEAS-135).
        A no-op if *signal* was never attached to *measurement*.
        """
        channel_index = measurement.detach(signal)
        if channel_index is not None:
            self._app.notify_virtual_measurement_changed(
                measurement, signal.name, "detached", channel_index=channel_index
            )

    def register_virtual_measurement(self, measurement: VirtualMeasurementLoader, label: str) -> None:
        """Add *measurement* to the application's measurement pool (REQ-PLUGIN-292).

        Makes it visible in the Signal Browser and everywhere else a real
        measurement would be, attributed to this plugin for later teardown
        (REQ-PLUGIN-300/301) and user-close notification (REQ-PLUGIN-302).
        A no-op, logged, if *measurement* (the same instance) is already
        registered (REQ-PLUGIN-540, #162) — a plugin can call this
        defensively without tracking registration state itself.
        """
        if self._app.find_measurement_by_loader(measurement) is not None:
            logger.info(
                "Plugin '%s' tried to register virtual measurement '%s' again — already registered, ignored",
                self._plugin_name, label,
            )
            return
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
        if event_name == "measurement_updated":
            return PluginMeasurementUpdatedEvent(
                label=payload.label,
                is_virtual=payload.is_virtual,
                signal_name=payload.signal_name,
                change=payload.change,
            )
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
