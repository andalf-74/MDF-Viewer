"""Protocol definitions for the controller-view boundary.

Each protocol declares exactly the methods a controller calls on its view
dependencies. Concrete view classes satisfy these structurally — no
inheritance needed. Controllers use these under TYPE_CHECKING so the
boundary is explicit without introducing runtime imports.

Interface segregation is applied deliberately: ActiveSignalsTable is split
into SignalTableProtocol (AppController's slice) and CursorValueSinkProtocol
(CursorController's slice), so each controller declares only what it uses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from PyQt6.QtGui import QColor
    from mdf_viewer.controller.cursor_controller import CursorMode
    from mdf_viewer.model.measurement import MeasurementInfo
    from mdf_viewer.model.mdf_loader import ChannelGroupInfo
    from mdf_viewer.model.signal_metadata import SignalMetadata
    from mdf_viewer.view_model.active_signal import ActiveSignal


# ---------------------------------------------------------------------------
# AppController view dependencies
# ---------------------------------------------------------------------------

class SignalBrowserProtocol(Protocol):
    def populate(self, groups: list[ChannelGroupInfo]) -> None: ...
    def clear(self) -> None: ...


class PlotAreaProtocol(Protocol):
    def add_signal(self, active: ActiveSignal) -> None: ...
    def remove_signal(self, active: ActiveSignal) -> None: ...
    def recolor_signal(self, active: ActiveSignal, color: QColor) -> None: ...
    def set_step_mode(self, active: ActiveSignal, step_mode: bool) -> None: ...
    def set_y_grid(self, active: ActiveSignal, enabled: bool) -> None: ...
    def swimlanes(self, signals: list[ActiveSignal]) -> bool: ...


class SignalTableProtocol(Protocol):
    """AppController's slice of ActiveSignalsTable — row lifecycle only."""

    def add_row(self, active: ActiveSignal) -> None: ...
    def remove_row(self, active: ActiveSignal) -> None: ...
    def clear(self) -> None: ...


class MeasurementInfoProtocol(Protocol):
    def set_info(self, info: MeasurementInfo) -> None: ...
    def clear(self) -> None: ...


class SignalInfoProtocol(Protocol):
    def set_metadata(self, metadata: SignalMetadata) -> None: ...
    def clear(self) -> None: ...


# ---------------------------------------------------------------------------
# CursorController view dependencies
# ---------------------------------------------------------------------------

class CursorViewProtocol(Protocol):
    # pyqtSignal(int, float) — connected in CursorController.__init__
    cursor_moved: Any

    def apply_mode(self, mode: CursorMode, positions: list[float]) -> None: ...
    def update_labels(
        self,
        signals: list[ActiveSignal],
        positions: list[float],
        mode: CursorMode,
    ) -> None: ...
    def remove_labels_for(self, active: ActiveSignal) -> None: ...
    def clear_labels(self) -> None: ...
    def recolor_labels(self, active: ActiveSignal, color: Any) -> None: ...
    def set_line_colors(self, color0: tuple, color1: tuple) -> None: ...


class CursorValueSinkProtocol(Protocol):
    """CursorController's slice of ActiveSignalsTable — cursor value columns only."""

    def update_cursor_values(
        self, active: ActiveSignal, c1: str, c2: str, delta: str
    ) -> None: ...
    def show_cursor_columns(self, show: bool) -> None: ...
    def set_cursor_column_headers(self, c3: str, c4: str) -> None: ...
