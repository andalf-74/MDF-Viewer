"""Read-only projections handed to plugins (#71).

Every dataclass here is frozen — a plugin can read but never mutate what
it's given, and never receives the live, mutable ``ActiveSignal``/
``LoadedMeasurement`` objects the application uses internally (in
particular, never their PyQtGraph ``curve``/``view_box`` handles).

Construction always happens through the ``from_active``/``from_measurement``
factories below, called by ``PluginContext`` (which alone knows about
application-wide facts these types don't, like which measurement is
Primary) — never by constructing these dataclasses ad hoc elsewhere.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from PyQt6.QtGui import QColor

    from mdf_viewer.enums import CursorMode
    from mdf_viewer.model.loaded_measurement import LoadedMeasurement
    from mdf_viewer.model.signal_metadata import SignalMetadata
    from mdf_viewer.view_model.active_signal import ActiveSignal


@dataclass(frozen=True)
class PluginMeasurementView:
    """Read-only view of one loaded measurement (REQ-PLUGIN-100).

    A snapshot: `offset_s` and `is_primary` are as they were when the view
    was built, so two views of the same measurement taken at different
    times may compare unequal. Use `key` (or `same_measurement()`) to tell
    whether two views refer to the same loaded measurement (REQ-PLUGIN-560).
    """

    path: str
    label: str
    offset_s: float
    is_primary: bool
    is_virtual: bool
    # Opaque, controller-minted handle (#189) — stops resolving once the
    # measurement is closed or replaced (REQ-PLUGIN-561/562).
    _measurement_token: int = field(repr=False)

    @property
    def key(self) -> int:
        """Opaque identity of the loaded measurement this view describes,
        stable across offset/Primary changes — usable as a dict key. A
        Replace… gives the replacement a different key (REQ-PLUGIN-562)."""
        return self._measurement_token

    def same_measurement(self, other: "PluginMeasurementView") -> bool:
        """Whether *other* describes the same loaded measurement as this view."""
        return self._measurement_token == other._measurement_token

    @classmethod
    def from_measurement(
        cls, measurement: "LoadedMeasurement", *, is_primary: bool, token: int,
    ) -> "PluginMeasurementView":
        loader = measurement.loader
        # loader.path (the public MeasurementLoader surface, #147), not the
        # MdfLoader-only private _path — a virtual measurement's loader
        # has no _path attribute at all and would AttributeError here.
        path = str(loader.path) if loader.is_open and loader.path is not None else ""
        return cls(
            path=path,
            label=measurement.label,
            offset_s=measurement.offset_s,
            is_primary=is_primary,
            is_virtual=measurement.owner_plugin is not None,
            _measurement_token=token,
        )


@dataclass(frozen=True)
class PluginChannelView:
    """Read-only handle to one channel of a loaded measurement (#189,
    REQ-PLUGIN-572) — listed or found whether or not it is plotted, and
    read via ``PluginContext.load_samples()``.

    Equality and hashing use only the hidden handle (measurement token,
    channel group index, channel index), never the descriptive fields: the
    same channel then compares equal however it was obtained — from
    ``list_channels()``, ``find_channels()``, or a plotted signal's
    ``channel`` — and stays usable as a dict key across offset or Primary
    changes. A handle dies with its measurement (close or Replace…), or,
    for a virtual channel, when it is detached.
    """

    name: str = field(compare=False)
    unit: str = field(compare=False)
    comment: str = field(compare=False)
    group_name: str = field(compare=False)
    measurement: PluginMeasurementView = field(compare=False)
    _measurement_token: int = field(repr=False)
    _group_index: int = field(repr=False)
    _channel_index: int = field(repr=False)

    @classmethod
    def from_metadata(
        cls, metadata: "SignalMetadata", measurement_view: PluginMeasurementView,
    ) -> "PluginChannelView":
        return cls(
            name=metadata.name,
            unit=metadata.unit,
            comment=metadata.comment,
            group_name=metadata.group_name,
            measurement=measurement_view,
            _measurement_token=measurement_view.key,
            _group_index=metadata.group_index if metadata.group_index is not None else -1,
            _channel_index=metadata.channel_index if metadata.channel_index is not None else -1,
        )


@dataclass(frozen=True)
class PluginSignalView:
    """Read-only view of one active signal (REQ-PLUGIN-080).

    Deliberately excludes sample data (REQ-PLUGIN-090, fetched separately
    via ``PluginContext.get_samples()``) and the live ``curve``/``view_box``
    PyQtGraph handles.
    """

    metadata: "SignalMetadata"
    color: "QColor"
    display_mode: str
    marker_shape: str
    line_width: int
    line_style: str
    visible: bool
    measurement: PluginMeasurementView | None
    # The channel this signal was loaded from (REQ-PLUGIN-574) — None only
    # when the signal has no owning measurement (same case as `measurement`).
    channel: "PluginChannelView | None"
    # Opaque handle for PluginContext.get_samples() — a controller-minted
    # token, never id(active_signal) (see docs/architecture.md's #71 entry
    # for why that would be unsafe for a handle a plugin can hold indefinitely).
    _signal_token: int = field(repr=False)

    @classmethod
    def from_active(
        cls,
        active: "ActiveSignal",
        token: int,
        measurement_view: PluginMeasurementView | None,
        channel: "PluginChannelView | None" = None,
    ) -> "PluginSignalView":
        return cls(
            metadata=active.metadata,
            color=active.color,
            display_mode=active.display_mode,
            marker_shape=active.marker_shape,
            line_width=active.line_width,
            line_style=active.line_style,
            visible=active.visible,
            measurement=measurement_view,
            channel=channel,
            _signal_token=token,
        )


@dataclass(frozen=True)
class PluginTabSignals:
    """Active signals of one tab (REQ-PLUGIN-070)."""

    tab_index: int
    tab_name: str
    is_active: bool
    signals: tuple[PluginSignalView, ...]


@dataclass(frozen=True)
class PluginTabCursor:
    """Cursor state of one tab (REQ-PLUGIN-110)."""

    tab_index: int
    tab_name: str
    is_active: bool
    mode: "CursorMode"
    positions: tuple[float, ...]


# ---------------------------------------------------------------------------
# Event payloads delivered via PluginContext.subscribe() (#149)
#
# Mirror controller/events.py's dataclasses, but translated: `tab` (the raw
# TabWorkspace — plot/table/cursor_ctrl/zoom_ctrl all directly reachable)
# becomes `tab_index`, and any ActiveSignal becomes a PluginSignalView.
# Never construct these from a raw EventBus payload directly — always via
# PluginContext's own translation, the single place that knows how to build
# a PluginSignalView / resolve a tab index.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PluginFileLoadedEvent:
    path: str
    tab_index: int | None


@dataclass(frozen=True)
class PluginSignalAddedEvent:
    signal: PluginSignalView
    tab_index: int | None


@dataclass(frozen=True)
class PluginSignalRemovedEvent:
    signal: PluginSignalView
    tab_index: int | None


@dataclass(frozen=True)
class PluginSelectionChangedEvent:
    selected: tuple[PluginSignalView, ...]
    tab_index: int | None


@dataclass(frozen=True)
class PluginCursorMovedEvent:
    positions: tuple[float, ...]
    mode: "CursorMode"
    tab_index: int | None


@dataclass(frozen=True)
class PluginMeasurementClosedEvent:
    """Fires for any measurement close, real or virtual (#147) — broadcast,
    not targeted; a plugin checks `is_virtual` (and its own bookkeeping,
    e.g. a label it recognizes) to tell whether this was its own."""

    label: str
    is_virtual: bool
    # The closed measurement as it was when closed, including its `key`,
    # so a plugin can tell which handles it holds are now dead
    # (REQ-PLUGIN-591, #189). Last and defaulted for compatibility.
    measurement: PluginMeasurementView | None = None


@dataclass(frozen=True)
class PluginMeasurementUpdatedEvent:
    """Fires when a virtual measurement's channel tree gains or loses a
    signal after registration (#162). Carries the affected signal's name
    as a plain string, not a PluginSignalView — the signal may never have
    been plotted, so there is no live ActiveSignal to build a view from."""

    label: str
    is_virtual: bool
    signal_name: str
    change: str  # "attached" | "detached"
