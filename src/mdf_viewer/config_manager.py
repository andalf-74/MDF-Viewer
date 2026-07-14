"""ConfigManager — save and load .mvc viewer configuration files.

A .mvc file is a JSON document that captures a full viewer workspace
(#106): every tab (name, stripe layout, active signals and their
per-signal display settings, zoom state, axis grouping, cursor state,
selection) and every loaded measurement (path, short name, offset,
Primary designation, Synchronize state).

Path-mode options (stored in Settings.config_path_mode):
  "absolute" — measurement paths are stored as absolute paths
  "relative" — measurement paths are stored relative to the .mvc file's directory
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from mdf_viewer.errors import ConfigLoadError
from mdf_viewer.model.viewer_config import (
    MeasurementConfig,
    SignalConfig,
    SignalRef,
    StripeConfig,
    TabConfig,
    ViewerConfig,
)

CONFIG_FILE_FILTER = "MDF Viewer Config (*.mvc);;All Files (*)"
CONFIG_FORMAT_VERSION = "2.0"


class ConfigManager:

    @staticmethod
    def save(config: ViewerConfig, path: Path, path_mode: str = "absolute") -> None:
        """Serialize *config* to *path* as a JSON .mvc file.

        *path_mode* controls how each measurement's path is stored:
          "absolute" — stored as-is (an absolute path string)
          "relative" — stored relative to *path*'s parent directory
        Always writes the current (#106) nested tabs/measurements shape,
        even for a single-tab/single-measurement session — see load() for
        the migration path that reads files saved before #106.
        """
        def resolve(p: str) -> str:
            if path_mode == "relative" and p:
                try:
                    return os.path.relpath(p, path.parent)
                except ValueError:
                    # Cannot make relative (e.g. different drive on Windows) — keep absolute
                    return p
            return p

        data = {
            "format_version": config.format_version,
            "measurements": [
                {"path": resolve(m.path), "label": m.label, "offset_s": m.offset_s}
                for m in config.measurements
            ],
            "primary_measurement_index": config.primary_measurement_index,
            "measurements_synchronized": config.measurements_synchronized,
            "active_tab_index": config.active_tab_index,
            "tabs": [ConfigManager._tab_to_dict(t) for t in config.tabs],
            "display_name_rule": {
                "separator": config.display_name_separator,
                "direction": config.display_name_direction,
                "segments": config.display_name_segments,
            },
            "window_geometry": config.window_geometry,
            "splitter_sizes": config.splitter_sizes,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def _ref_to_dict(ref: SignalRef) -> dict:
        return {"name": ref.name, "measurement_index": ref.measurement_index}

    @staticmethod
    def _tab_to_dict(t: TabConfig) -> dict:
        return {
            "name": t.name,
            "active_stripe_index": t.active_stripe_index,
            "stripes": [{"name": s.name, "size": s.size} for s in t.stripes],
            "signals": [
                {
                    "name": s.name,
                    "group_name": s.group_name,
                    "color": list(s.color),
                    "line_width": s.line_width,
                    "line_style": s.line_style,
                    "display_mode": s.display_mode,
                    "marker_shape": s.marker_shape,
                    "step_mode": s.step_mode,
                    "enum_display_table": s.enum_display_table,
                    "enum_display_cursor": s.enum_display_cursor,
                    "enum_display_yaxis": s.enum_display_yaxis,
                    "stripe_index": s.stripe_index,
                    "measurement_index": s.measurement_index,
                    "visible": s.visible,
                }
                for s in t.signals
            ],
            "zoom": {
                "x_range": list(t.x_range),
                "y_ranges": [
                    {"ref": ConfigManager._ref_to_dict(ref), "range": list(rng)}
                    for ref, rng in t.y_ranges
                ],
            },
            "axes": {
                "merged": [
                    [ConfigManager._ref_to_dict(ref) for ref in g] for g in t.merged_groups
                ],
                "synced": [
                    [ConfigManager._ref_to_dict(ref) for ref in g] for g in t.synced_groups
                ],
            },
            "cursors": {
                "mode": t.cursor_mode,
                "positions": list(t.cursor_positions),
            },
            "selection": ConfigManager._ref_to_dict(t.selected_signal) if t.selected_signal else None,
            "page_splitter_sizes": list(t.page_splitter_sizes),
            "ast_column_widths": list(t.ast_column_widths),
            "view_type": t.view_type,
        }

    @staticmethod
    def load(path: Path) -> ViewerConfig:
        """Parse *path* and return a ViewerConfig.

        Reads both the current (#106) nested "tabs"/"measurements" shape
        and the flat single-tab/single-measurement shape used before #106
        — a file with neither top-level key is treated as the old flat
        shape and synthesized into a single-element tabs/measurements list
        (REQ-FILE-096), the same forward-compatible spirit as every other
        field added after a file was written (REQ-FILE-067), just a
        one-time structural translation instead of per-field defaulting.

        Raises ConfigLoadError if the file is missing, not valid JSON, or
        structurally invalid.
        """
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ConfigLoadError(f"Cannot read '{path.name}': {exc}") from exc

        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ConfigLoadError(f"'{path.name}' is not valid JSON: {exc}") from exc

        try:
            if "tabs" in data or "measurements" in data:
                tabs = tuple(ConfigManager._dict_to_tab(t) for t in data.get("tabs", []))
                measurements = tuple(
                    MeasurementConfig(
                        path=str(m.get("path", "")),
                        label=str(m.get("label", "")),
                        offset_s=float(m.get("offset_s", 0.0)),
                    )
                    for m in data.get("measurements", [])
                )
                # None is a valid saved value (#147) — no real measurement
                # was Primary at save time. int(None) would raise, so only
                # coerce when a real index was actually saved.
                raw_primary_index = data.get("primary_measurement_index", 0)
                primary_measurement_index = (
                    int(raw_primary_index) if raw_primary_index is not None else None
                )
                measurements_synchronized = bool(data.get("measurements_synchronized", False))
                active_tab_index = int(data.get("active_tab_index", 0))
            else:
                # Pre-#106 flat file: one implicit tab, one implicit
                # measurement. Reshape into the same tab-dict shape
                # _dict_to_tab() already knows how to parse, rather than
                # duplicating its field-by-field defaulting.
                legacy_tab = {
                    "name": "Tab 1",
                    "active_stripe_index": 0,
                    "stripes": [{"name": "Stripe 1", "size": 1}],
                    "signals": data.get("signals", []),
                    "zoom": data.get("zoom", {}),
                    "axes": data.get("axes", {}),
                    "cursors": data.get("cursors", {}),
                    "selection": data.get("selection"),
                }
                tabs = (ConfigManager._dict_to_tab(legacy_tab),)
                meas_path = str(data.get("measurement_path", ""))
                measurements = (
                    (MeasurementConfig(path=meas_path, label="M1", offset_s=0.0),)
                    if meas_path else ()
                )
                primary_measurement_index = 0
                measurements_synchronized = False
                active_tab_index = 0

            # Absent in files saved before this field existed — default to the
            # same values Settings itself defaults to.
            name_rule = data.get("display_name_rule", {})
            display_name_separator = str(name_rule.get("separator", "."))
            display_name_direction = str(name_rule.get("direction", "right"))
            display_name_segments = max(1, min(10, int(name_rule.get("segments", 1))))

            # Absent in older files, and defensively ignored if malformed —
            # MainWindow applies these opaquely and layout restore is not
            # critical enough to fail the whole config load over.
            window_geometry = data.get("window_geometry")
            if not isinstance(window_geometry, dict):
                window_geometry = None
            splitter_sizes = data.get("splitter_sizes")
            if not isinstance(splitter_sizes, dict):
                splitter_sizes = None

        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ConfigLoadError(
                f"'{path.name}' has an unexpected structure: {exc}"
            ) from exc

        return ViewerConfig(
            format_version=str(data.get("format_version", CONFIG_FORMAT_VERSION)),
            measurements=measurements,
            primary_measurement_index=primary_measurement_index,
            measurements_synchronized=measurements_synchronized,
            tabs=tabs,
            active_tab_index=active_tab_index,
            display_name_separator=display_name_separator,
            display_name_direction=display_name_direction,
            display_name_segments=display_name_segments,
            window_geometry=window_geometry,
            splitter_sizes=splitter_sizes,
        )

    @staticmethod
    def _dict_to_ref(d) -> SignalRef:
        # A pre-#106-groups-fix file stores a bare name string here (no
        # measurement disambiguation existed yet) — default measurement_index
        # to 0, matching every other single-measurement forward-compat
        # default in this format (REQ-FILE-067).
        if isinstance(d, dict):
            return SignalRef(name=str(d.get("name", "")), measurement_index=int(d.get("measurement_index", 0)))
        return SignalRef(name=str(d), measurement_index=0)

    @staticmethod
    def _dict_to_tab(t: dict) -> TabConfig:
        stripes = tuple(
            StripeConfig(name=str(s.get("name", "")), size=int(s.get("size", 1)))
            for s in t.get("stripes", [{"name": "Stripe 1", "size": 1}])
        )
        signals = tuple(ConfigManager._dict_to_signal(s) for s in t.get("signals", []))

        zoom = t.get("zoom", {})
        x_range_raw = zoom.get("x_range", [0.0, 1.0])
        x_range: tuple[float, float] = (float(x_range_raw[0]), float(x_range_raw[1]))
        y_ranges_raw = zoom.get("y_ranges", [])
        if isinstance(y_ranges_raw, dict):
            # Pre-#106-groups-fix flat shape: {name: [y_min, y_max]}.
            y_ranges = tuple(
                (SignalRef(name=str(k), measurement_index=0), (float(v[0]), float(v[1])))
                for k, v in y_ranges_raw.items()
            )
        else:
            y_ranges = tuple(
                (ConfigManager._dict_to_ref(e.get("ref", "")), (float(e["range"][0]), float(e["range"][1])))
                for e in y_ranges_raw
            )

        axes = t.get("axes", {})
        merged_groups = tuple(
            tuple(ConfigManager._dict_to_ref(n) for n in g) for g in axes.get("merged", [])
        )
        synced_groups = tuple(
            tuple(ConfigManager._dict_to_ref(n) for n in g) for g in axes.get("synced", [])
        )

        cursors = t.get("cursors", {})
        cursor_mode = str(cursors.get("mode", "HIDDEN"))
        cursor_pos_raw = cursors.get("positions", [0.0, 0.0])
        cursor_positions: tuple[float, float] = (
            float(cursor_pos_raw[0]),
            float(cursor_pos_raw[1]),
        )

        selection = t.get("selection")
        selected_signal = ConfigManager._dict_to_ref(selection) if selection else None

        page_splitter_raw = t.get("page_splitter_sizes", [500, 260])
        page_splitter_sizes: tuple[int, int] = (
            (int(page_splitter_raw[0]), int(page_splitter_raw[1]))
            if isinstance(page_splitter_raw, list) and len(page_splitter_raw) == 2
            else (500, 260)
        )
        ast_column_widths = tuple(int(w) for w in t.get("ast_column_widths", []))
        view_type = str(t.get("view_type", "plot"))

        return TabConfig(
            name=str(t.get("name", "Tab 1")),
            stripes=stripes,
            active_stripe_index=int(t.get("active_stripe_index", 0)),
            signals=signals,
            x_range=x_range,
            y_ranges=y_ranges,
            merged_groups=merged_groups,
            synced_groups=synced_groups,
            cursor_mode=cursor_mode,
            cursor_positions=cursor_positions,
            selected_signal=selected_signal,
            page_splitter_sizes=page_splitter_sizes,
            ast_column_widths=ast_column_widths,
            view_type=view_type,
        )

    @staticmethod
    def _dict_to_signal(s: dict) -> SignalConfig:
        return SignalConfig(
            name=str(s["name"]),
            group_name=str(s.get("group_name", "")),
            color=tuple(int(v) for v in s.get("color", [200, 200, 200])),  # type: ignore[arg-type]
            line_width=int(s.get("line_width", 1)),
            line_style=str(s.get("line_style", "solid")),
            display_mode=str(s.get("display_mode", "line")),
            marker_shape=str(s.get("marker_shape", "circle")),
            step_mode=bool(s.get("step_mode", False)),
            enum_display_table=bool(s.get("enum_display_table", True)),
            enum_display_cursor=bool(s.get("enum_display_cursor", False)),
            enum_display_yaxis=bool(s.get("enum_display_yaxis", False)),
            stripe_index=int(s.get("stripe_index", 0)),
            measurement_index=int(s.get("measurement_index", 0)),
            visible=bool(s.get("visible", True)),
        )

    @staticmethod
    def resolve_measurement_path(raw: str, config_path: Path) -> Path | None:
        """Resolve a raw measurement path stored in a config file.

        *raw* may be absolute or relative to *config_path*'s parent directory.
        Returns the resolved Path if it exists on disk, otherwise None.
        """
        if not raw:
            return None
        p = Path(raw)
        if p.is_absolute():
            return p if p.exists() else None
        resolved = (config_path.parent / p).resolve()
        return resolved if resolved.exists() else None
