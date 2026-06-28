"""ConfigManager — save and load .mvc viewer configuration files.

A .mvc file is a JSON document that captures the full viewer session:
active signals, axis grouping, zoom state, cursor state, and the path to
the measurement file.

Path-mode options (stored in Settings.config_path_mode):
  "absolute" — measurement path is stored as an absolute path
  "relative" — measurement path is stored relative to the .mvc file's directory
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from mdf_viewer.errors import ConfigLoadError
from mdf_viewer.model.viewer_config import SignalConfig, ViewerConfig

CONFIG_FILE_FILTER = "MDF Viewer Config (*.mvc);;All Files (*)"
CONFIG_FORMAT_VERSION = "1.0"


class ConfigManager:

    @staticmethod
    def save(config: ViewerConfig, path: Path, path_mode: str = "absolute") -> None:
        """Serialize *config* to *path* as a JSON .mvc file.

        *path_mode* controls how the measurement path is stored:
          "absolute" — stored as-is (an absolute path string)
          "relative" — stored relative to *path*'s parent directory
        """
        meas_path = config.measurement_path
        if path_mode == "relative" and meas_path:
            try:
                meas_path = os.path.relpath(meas_path, path.parent)
            except ValueError:
                # Cannot make relative (e.g. different drive on Windows) — keep absolute
                pass

        data = {
            "format_version": config.format_version,
            "measurement_path": meas_path,
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
                }
                for s in config.signals
            ],
            "zoom": {
                "x_range": list(config.x_range),
                "y_ranges": {k: list(v) for k, v in config.y_ranges.items()},
            },
            "axes": {
                "shared": [list(g) for g in config.shared_groups],
                "linked": [list(g) for g in config.linked_groups],
            },
            "cursors": {
                "mode": config.cursor_mode,
                "positions": list(config.cursor_positions),
            },
            "selection": config.selected_signal,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    @staticmethod
    def load(path: Path) -> ViewerConfig:
        """Parse *path* and return a ViewerConfig.

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
            signals = tuple(
                SignalConfig(
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
                )
                for s in data.get("signals", [])
            )

            zoom = data.get("zoom", {})
            x_range_raw = zoom.get("x_range", [0.0, 1.0])
            x_range: tuple[float, float] = (float(x_range_raw[0]), float(x_range_raw[1]))
            y_ranges: dict[str, tuple[float, float]] = {
                k: (float(v[0]), float(v[1]))
                for k, v in zoom.get("y_ranges", {}).items()
            }

            axes = data.get("axes", {})
            shared_groups = tuple(
                tuple(str(n) for n in g) for g in axes.get("shared", [])
            )
            linked_groups = tuple(
                tuple(str(n) for n in g) for g in axes.get("linked", [])
            )

            cursors = data.get("cursors", {})
            cursor_mode = str(cursors.get("mode", "HIDDEN"))
            cursor_pos_raw = cursors.get("positions", [0.0, 0.0])
            cursor_positions: tuple[float, float] = (
                float(cursor_pos_raw[0]),
                float(cursor_pos_raw[1]),
            )

            selection = data.get("selection")
            selected_signal = str(selection) if selection is not None else None

        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise ConfigLoadError(
                f"'{path.name}' has an unexpected structure: {exc}"
            ) from exc

        return ViewerConfig(
            format_version=str(data.get("format_version", CONFIG_FORMAT_VERSION)),
            measurement_path=str(data.get("measurement_path", "")),
            signals=signals,
            x_range=x_range,
            y_ranges=y_ranges,
            shared_groups=shared_groups,
            linked_groups=linked_groups,
            cursor_mode=cursor_mode,
            cursor_positions=cursor_positions,
            selected_signal=selected_signal,
        )

    @staticmethod
    def resolve_measurement_path(raw: str, config_path: Path) -> Path | None:
        """Resolve the raw measurement path stored in a config file.

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
