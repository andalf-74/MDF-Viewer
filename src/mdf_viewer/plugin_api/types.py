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
    """Read-only view of one loaded measurement (REQ-PLUGIN-100)."""

    path: str
    label: str
    offset_s: float
    is_primary: bool

    @classmethod
    def from_measurement(cls, measurement: "LoadedMeasurement", *, is_primary: bool) -> "PluginMeasurementView":
        loader = measurement.loader
        path = str(loader._path) if loader.is_open and loader._path is not None else ""
        return cls(path=path, label=measurement.label, offset_s=measurement.offset_s, is_primary=is_primary)


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
