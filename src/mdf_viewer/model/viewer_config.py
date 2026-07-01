"""ViewerConfig — pure-data snapshot of a saved viewer session.

No Qt, no PyQtGraph.  Serialized to/from JSON by ConfigManager.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SignalConfig:
    """Display state for one active signal."""

    name: str
    group_name: str
    color: tuple[int, int, int]
    line_width: int
    line_style: str
    display_mode: str
    marker_shape: str
    step_mode: bool
    enum_display_table: bool
    enum_display_cursor: bool
    enum_display_yaxis: bool


@dataclass(frozen=True)
class ViewerConfig:
    """Complete snapshot of an active viewer session."""

    format_version: str
    measurement_path: str                             # raw — abs or relative, not yet resolved
    signals: tuple[SignalConfig, ...]
    x_range: tuple[float, float]
    y_ranges: dict[str, tuple[float, float]]          # signal name → (y_min, y_max)
    shared_groups: tuple[tuple[str, ...], ...]        # each inner tuple = one shared group
    linked_groups: tuple[tuple[str, ...], ...]        # each inner tuple = one linked group
    cursor_mode: str                                  # "HIDDEN" | "ONE" | "TWO"
    cursor_positions: tuple[float, float]
    selected_signal: str | None
    # Display-name-shortening rule *parameters* used by this session — not
    # whether the rule is enabled, which stays governed solely by Preferences.
    display_name_separator: str
    display_name_direction: str                       # "left" | "right"
    display_name_segments: int
