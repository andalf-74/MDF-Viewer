"""ViewerConfig — pure-data snapshot of a saved viewer session (#106: a full
workspace snapshot across every tab, every stripe, and every loaded
measurement, not just the single active tab and first measurement).

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
    # Position within its tab's saved workspace (#106) — index into that
    # TabConfig's own stripes/ViewerConfig's measurements. Default 0 matches
    # today's single-stripe/single-measurement behavior for files saved
    # before #106.
    stripe_index: int = 0
    measurement_index: int = 0


@dataclass(frozen=True)
class StripeConfig:
    """One plot stripe's saved layout (#106, #97/#100)."""

    name: str
    size: int


@dataclass(frozen=True)
class SignalRef:
    """A saved reference to one specific active signal — its name plus
    which of the session's measurements it came from (#106, REQ-FILE-093).

    Used wherever a saved tab needs to point back at a specific signal
    (zoom Y-range, axis grouping, selection) instead of a bare name —
    a bare name is ambiguous whenever the same channel name is active
    from two different loaded measurements in the same tab.
    """

    name: str
    measurement_index: int


@dataclass(frozen=True)
class TabConfig:
    """One tab's complete saved workspace (#106, #99)."""

    name: str
    stripes: tuple[StripeConfig, ...]
    active_stripe_index: int
    signals: tuple[SignalConfig, ...]
    x_range: tuple[float, float]
    y_ranges: tuple[tuple[SignalRef, tuple[float, float]], ...]
    merged_groups: tuple[tuple[SignalRef, ...], ...]  # each inner tuple = one merged group
    synced_groups: tuple[tuple[SignalRef, ...], ...]  # each inner tuple = one synced group
    cursor_mode: str                                  # "HIDDEN" | "ONE" | "TWO"
    cursor_positions: tuple[float, float]
    selected_signal: SignalRef | None
    # Per-tab plot|AST divider width and the AST's own column widths
    # (#106) — genuinely new capture points beyond the original
    # REQ-FILE-090 scope, folded in after live-testing surfaced the gap.
    page_splitter_sizes: tuple[int, int] = (500, 260)
    ast_column_widths: tuple[int, ...] = ()


@dataclass(frozen=True)
class MeasurementConfig:
    """One loaded measurement's saved state (#106, #101/#102/#103)."""

    path: str                                         # raw — abs or relative, not yet resolved
    label: str
    offset_s: float


@dataclass(frozen=True)
class ViewerConfig:
    """Complete snapshot of an active viewer session — every tab, every
    stripe, and every loaded measurement (#106)."""

    format_version: str
    measurements: tuple[MeasurementConfig, ...]
    primary_measurement_index: int
    measurements_synchronized: bool
    tabs: tuple[TabConfig, ...]
    active_tab_index: int
    # Display-name-shortening rule *parameters* used by this session — not
    # whether the rule is enabled, which stays governed solely by Preferences.
    display_name_separator: str
    display_name_direction: str                       # "left" | "right"
    display_name_segments: int
    # Opaque to everything except MainWindow, which captures/applies them —
    # keeps window/splitter geometry out of the Model/Controller's vocabulary.
    window_geometry: dict | None = None                # {x, y, width, height, maximized}
    splitter_sizes: dict | None = None                 # {left, right, content, outer, left_panel, info_drawer}
