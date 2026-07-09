"""AppController event bus — plugin groundwork (#70).

Purely additive: AppController keeps every direct call it already makes to
the view layer (plot, table, cursor controller, ...) and *also* emits these
events so future subscribers (plugins via PluginContext, or internal modules
later) can observe lifecycle changes without AppController knowing about them.

Payloads are dataclasses rather than positional signal arguments so that
later fields (e.g. stripe/measurement context, once multi-measurement support
lands) can be added without changing any pyqtSignal's registered signature.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from PyQt6.QtCore import QObject, pyqtSignal

if TYPE_CHECKING:
    from mdf_viewer.controller.cursor_controller import CursorMode
    from mdf_viewer.view_model.active_signal import ActiveSignal


@dataclass(frozen=True)
class FileLoadedEvent:
    path: str
    tab: object | None = None


@dataclass(frozen=True)
class SignalAddedEvent:
    signal: ActiveSignal
    stripe: object | None = None
    tab: object | None = None


@dataclass(frozen=True)
class SignalRemovedEvent:
    signal: ActiveSignal
    tab: object | None = None


@dataclass(frozen=True)
class SelectionChangedEvent:
    selected: list[ActiveSignal] = field(default_factory=list)
    tab: object | None = None


@dataclass(frozen=True)
class CursorMovedEvent:
    positions: list[float]
    mode: "CursorMode"
    tab: object | None = None


class EventBus(QObject):
    """Qt signals for AppController lifecycle events. Owned by AppController."""

    file_loaded = pyqtSignal(object)       # FileLoadedEvent
    signal_added = pyqtSignal(object)      # SignalAddedEvent
    signal_removed = pyqtSignal(object)    # SignalRemovedEvent
    selection_changed = pyqtSignal(object) # SelectionChangedEvent
    cursor_moved = pyqtSignal(object)      # CursorMovedEvent
