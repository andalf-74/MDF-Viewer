"""Persistent application settings stored as a JSON file.

Config path:
  Windows : %APPDATA%\\mdf-viewer\\settings.json
  Linux   : ~/.config/mdf-viewer/settings.json
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

MAX_RECENT = 4

# Default cursor line colors as (R, G, B) tuples
DEFAULT_CURSOR_COLOR_C1 = (220, 220, 50)
DEFAULT_CURSOR_COLOR_C2 = (255, 140, 0)
DEFAULT_CURSOR_COLOR_CL = (220, 220, 50)
DEFAULT_CURSOR_COLOR_CR = (50, 150, 255)
DEFAULT_DELTA_TIME_COLOR = (200, 200, 200)

# Default arrow-key step settings
DEFAULT_CURSOR_STEP_UNIT = "samples"   # "samples" | "pixels" | "time"
DEFAULT_CURSOR_STEP_SAMPLES = 1        # number of samples per key press
DEFAULT_CURSOR_STEP_PIXELS = 1         # number of pixels per key press
DEFAULT_CURSOR_STEP_TIME_MS = 10.0     # milliseconds per key press

# Default zoom undo history depth
DEFAULT_MAX_UNDO_STEPS = 1

# Default signal Z-order ("top_first" = top table row on top, "bottom_first" = bottom row on top)
DEFAULT_SIGNAL_Z_ORDER = "top_first"

# Default line-width boost applied to the currently selected signal (0 = disabled)
DEFAULT_SELECTED_LINE_BOOST = 1


def _default_config_path() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home())) / "mdf-viewer"
    else:
        base = Path.home() / ".config" / "mdf-viewer"
    return base / "settings.json"


class Settings:
    """Read/write application settings from a JSON file."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path if path is not None else _default_config_path()
        self._recent: list[Path] = []
        self._check_for_updates: bool = True
        self._cursor_persistent: bool = True
        self._cursor_mode: str = "1/2"
        self._cursor_color_c1: tuple[int, int, int] = DEFAULT_CURSOR_COLOR_C1
        self._cursor_color_c2: tuple[int, int, int] = DEFAULT_CURSOR_COLOR_C2
        self._cursor_color_cl: tuple[int, int, int] = DEFAULT_CURSOR_COLOR_CL
        self._cursor_color_cr: tuple[int, int, int] = DEFAULT_CURSOR_COLOR_CR
        self._show_delta_time_in_plot: bool = True
        self._delta_time_color: tuple[int, int, int] = DEFAULT_DELTA_TIME_COLOR
        self._cursor_step_unit: str = DEFAULT_CURSOR_STEP_UNIT
        self._cursor_step_samples: int = DEFAULT_CURSOR_STEP_SAMPLES
        self._cursor_step_pixels: int = DEFAULT_CURSOR_STEP_PIXELS
        self._cursor_step_time_ms: float = DEFAULT_CURSOR_STEP_TIME_MS
        self._max_undo_steps: int = DEFAULT_MAX_UNDO_STEPS
        self._signal_z_order: str = DEFAULT_SIGNAL_Z_ORDER
        self._selected_line_boost: int = DEFAULT_SELECTED_LINE_BOOST
        self._load()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_recent(self, path: str | os.PathLike) -> None:
        """Prepend path to the recent files list, dedup, trim, and save."""
        p = Path(path).resolve()
        self._recent = [p] + [r for r in self._recent if r != p]
        self._recent = self._recent[:MAX_RECENT]
        self._save()

    def recent_files(self) -> list[Path]:
        """Return the current recent files list (may include missing paths)."""
        return list(self._recent)

    @property
    def check_for_updates(self) -> bool:
        return self._check_for_updates

    @check_for_updates.setter
    def check_for_updates(self, value: bool) -> None:
        self._check_for_updates = value
        self._save()

    @property
    def cursor_persistent(self) -> bool:
        return self._cursor_persistent

    @cursor_persistent.setter
    def cursor_persistent(self, value: bool) -> None:
        self._cursor_persistent = value
        self._save()

    @property
    def cursor_mode(self) -> str:
        return self._cursor_mode

    @cursor_mode.setter
    def cursor_mode(self, value: str) -> None:
        self._cursor_mode = value
        self._save()

    @property
    def cursor_color_c1(self) -> tuple[int, int, int]:
        return self._cursor_color_c1

    @cursor_color_c1.setter
    def cursor_color_c1(self, value: tuple[int, int, int]) -> None:
        self._cursor_color_c1 = value
        self._save()

    @property
    def cursor_color_c2(self) -> tuple[int, int, int]:
        return self._cursor_color_c2

    @cursor_color_c2.setter
    def cursor_color_c2(self, value: tuple[int, int, int]) -> None:
        self._cursor_color_c2 = value
        self._save()

    @property
    def cursor_color_cl(self) -> tuple[int, int, int]:
        return self._cursor_color_cl

    @cursor_color_cl.setter
    def cursor_color_cl(self, value: tuple[int, int, int]) -> None:
        self._cursor_color_cl = value
        self._save()

    @property
    def cursor_color_cr(self) -> tuple[int, int, int]:
        return self._cursor_color_cr

    @cursor_color_cr.setter
    def cursor_color_cr(self, value: tuple[int, int, int]) -> None:
        self._cursor_color_cr = value
        self._save()

    @property
    def show_delta_time_in_plot(self) -> bool:
        return self._show_delta_time_in_plot

    @show_delta_time_in_plot.setter
    def show_delta_time_in_plot(self, value: bool) -> None:
        self._show_delta_time_in_plot = value
        self._save()

    @property
    def delta_time_color(self) -> tuple[int, int, int]:
        return self._delta_time_color

    @delta_time_color.setter
    def delta_time_color(self, value: tuple[int, int, int]) -> None:
        self._delta_time_color = value
        self._save()

    @property
    def cursor_step_unit(self) -> str:
        return self._cursor_step_unit

    @cursor_step_unit.setter
    def cursor_step_unit(self, value: str) -> None:
        self._cursor_step_unit = value
        self._save()

    @property
    def cursor_step_samples(self) -> int:
        return self._cursor_step_samples

    @cursor_step_samples.setter
    def cursor_step_samples(self, value: int) -> None:
        self._cursor_step_samples = value
        self._save()

    @property
    def cursor_step_pixels(self) -> int:
        return self._cursor_step_pixels

    @cursor_step_pixels.setter
    def cursor_step_pixels(self, value: int) -> None:
        self._cursor_step_pixels = value
        self._save()

    @property
    def cursor_step_time_ms(self) -> float:
        return self._cursor_step_time_ms

    @cursor_step_time_ms.setter
    def cursor_step_time_ms(self, value: float) -> None:
        self._cursor_step_time_ms = value
        self._save()

    @property
    def max_undo_steps(self) -> int:
        return self._max_undo_steps

    @max_undo_steps.setter
    def max_undo_steps(self, value: int) -> None:
        self._max_undo_steps = max(1, int(value))
        self._save()

    @property
    def signal_z_order(self) -> str:
        return self._signal_z_order

    @signal_z_order.setter
    def signal_z_order(self, value: str) -> None:
        self._signal_z_order = value
        self._save()

    @property
    def selected_line_boost(self) -> int:
        return self._selected_line_boost

    @selected_line_boost.setter
    def selected_line_boost(self, value: int) -> None:
        self._selected_line_boost = max(0, min(5, int(value)))
        self._save()

    def get_and_prune(self) -> list[Path]:
        """Return only paths that exist on disk; save if any were removed."""
        existing = [p for p in self._recent if p.exists()]
        if len(existing) != len(self._recent):
            self._recent = existing
            self._save()
        return list(existing)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load(self) -> None:
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            self._recent = [Path(p) for p in data.get("recent_files", [])]
            self._check_for_updates = bool(data.get("check_for_updates", True))
            self._cursor_persistent = bool(data.get("cursor_persistent", True))
            self._cursor_mode = str(data.get("cursor_mode", "1/2"))
            self._cursor_color_c1 = self._load_color(data, "cursor_color_c1", DEFAULT_CURSOR_COLOR_C1)
            self._cursor_color_c2 = self._load_color(data, "cursor_color_c2", DEFAULT_CURSOR_COLOR_C2)
            self._cursor_color_cl = self._load_color(data, "cursor_color_cl", DEFAULT_CURSOR_COLOR_CL)
            self._cursor_color_cr = self._load_color(data, "cursor_color_cr", DEFAULT_CURSOR_COLOR_CR)
            self._show_delta_time_in_plot = bool(data.get("show_delta_time_in_plot", True))
            self._delta_time_color = self._load_color(data, "delta_time_color", DEFAULT_DELTA_TIME_COLOR)
            self._cursor_step_unit = str(data.get("cursor_step_unit", DEFAULT_CURSOR_STEP_UNIT))
            self._cursor_step_samples = int(data.get("cursor_step_samples", DEFAULT_CURSOR_STEP_SAMPLES))
            self._cursor_step_pixels = int(data.get("cursor_step_pixels", DEFAULT_CURSOR_STEP_PIXELS))
            self._cursor_step_time_ms = float(data.get("cursor_step_time_ms", DEFAULT_CURSOR_STEP_TIME_MS))
            self._max_undo_steps = max(1, int(data.get("max_undo_steps", DEFAULT_MAX_UNDO_STEPS)))
            self._signal_z_order = str(data.get("signal_z_order", DEFAULT_SIGNAL_Z_ORDER))
            self._selected_line_boost = max(0, min(5, int(data.get("selected_line_boost", DEFAULT_SELECTED_LINE_BOOST))))
        except (FileNotFoundError, json.JSONDecodeError, TypeError, KeyError):
            self._recent = []
            self._check_for_updates = True
            self._cursor_persistent = True
            self._cursor_mode = "1/2"
            self._cursor_color_c1 = DEFAULT_CURSOR_COLOR_C1
            self._cursor_color_c2 = DEFAULT_CURSOR_COLOR_C2
            self._cursor_color_cl = DEFAULT_CURSOR_COLOR_CL
            self._cursor_color_cr = DEFAULT_CURSOR_COLOR_CR
            self._show_delta_time_in_plot = True
            self._delta_time_color = DEFAULT_DELTA_TIME_COLOR
            self._cursor_step_unit = DEFAULT_CURSOR_STEP_UNIT
            self._cursor_step_samples = DEFAULT_CURSOR_STEP_SAMPLES
            self._cursor_step_pixels = DEFAULT_CURSOR_STEP_PIXELS
            self._cursor_step_time_ms = DEFAULT_CURSOR_STEP_TIME_MS
            self._max_undo_steps = DEFAULT_MAX_UNDO_STEPS
            self._signal_z_order = DEFAULT_SIGNAL_Z_ORDER
            self._selected_line_boost = DEFAULT_SELECTED_LINE_BOOST

    @staticmethod
    def _load_color(
        data: dict, key: str, default: tuple[int, int, int]
    ) -> tuple[int, int, int]:
        val = data.get(key)
        if isinstance(val, list) and len(val) == 3:
            return (int(val[0]), int(val[1]), int(val[2]))
        return default

    def _save(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(
                {
                    "recent_files": [str(p) for p in self._recent],
                    "check_for_updates": self._check_for_updates,
                    "cursor_persistent": self._cursor_persistent,
                    "cursor_mode": self._cursor_mode,
                    "cursor_color_c1": list(self._cursor_color_c1),
                    "cursor_color_c2": list(self._cursor_color_c2),
                    "cursor_color_cl": list(self._cursor_color_cl),
                    "cursor_color_cr": list(self._cursor_color_cr),
                    "show_delta_time_in_plot": self._show_delta_time_in_plot,
                    "delta_time_color": list(self._delta_time_color),
                    "cursor_step_unit": self._cursor_step_unit,
                    "cursor_step_samples": self._cursor_step_samples,
                    "cursor_step_pixels": self._cursor_step_pixels,
                    "cursor_step_time_ms": self._cursor_step_time_ms,
                    "max_undo_steps": self._max_undo_steps,
                    "signal_z_order": self._signal_z_order,
                    "selected_line_boost": self._selected_line_boost,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
