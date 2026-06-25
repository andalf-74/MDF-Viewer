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
    def set_display_mode(self, active: ActiveSignal, mode: str, shape: str) -> None: ...
    def set_y_grid(self, active: ActiveSignal, enabled: bool) -> None: ...
    def swimlanes(self, signals: list[ActiveSignal]) -> bool: ...
    def zoom_to_fit(self) -> None: ...
    def zoom_y_to_view(self) -> bool: ...
    def zoom_to_x_range(self, x_min: float, x_max: float) -> None: ...


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
    def show_multi_selection(self) -> None: ...
    def clear(self) -> None: ...
    def set_properties(self, mode: str | None, shape: str | None) -> None: ...
    def enable_properties(self, enabled: bool) -> None: ...


# ---------------------------------------------------------------------------
# CursorController view dependencies
# ---------------------------------------------------------------------------

class CursorViewProtocol(Protocol):
    # pyqtSignal(int, float) — connected in CursorController.__init__
    cursor_moved: Any
    # pyqtSignal(int) — connected in CursorController.__init__
    cursor_clicked: Any
    # pyqtSignal(float) — connected in CursorController.__init__
    delta_line_moved: Any
    # pyqtSignal(int, float) — emitted when a cursor chevron is clicked
    cursor_fetch_requested: Any
    # pyqtSignal(float) — emitted when the delta-time chevron is clicked
    delta_fetch_requested: Any

    def apply_mode(self, mode: CursorMode, positions: list[float]) -> None: ...
    def update_labels(
        self,
        signals: list[ActiveSignal],
        positions: list[float],
        mode: CursorMode,
    ) -> None: ...
    def update_delta_time(
        self,
        x1: float,
        x2: float,
        delta_t_str: str,
        y_pos: float | None,
        show: bool,
        color: tuple,
    ) -> None: ...
    def remove_labels_for(self, active: ActiveSignal) -> None: ...
    def clear_labels(self) -> None: ...
    def recolor_labels(self, active: ActiveSignal, color: Any) -> None: ...
    def set_line_colors(self, color0: tuple, color1: tuple) -> None: ...
    def set_cursor_names(self, name0: str, name1: str) -> None: ...


class CursorValueSinkProtocol(Protocol):
    """CursorController's slice of ActiveSignalsTable — cursor value columns only."""

    def update_cursor_values(
        self, active: ActiveSignal, c1: str, c2: str, delta: str
    ) -> None: ...
    def show_cursor_columns(self, show: bool) -> None: ...
    def set_cursor_column_headers(self, c3: str, c4: str) -> None: ...
    def set_delta_column_header(self, text: str) -> None: ...
