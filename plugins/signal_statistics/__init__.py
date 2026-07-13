"""Signal Statistics — proof-of-concept built-in plugin (#75).

Shows Min/Max/Mean for the currently selected signal in a dock widget.
Written specifically to validate the full plugin lifecycle (discover ->
load -> activate -> use -> deactivate) end-to-end and serve as a
reference implementation for plugin authors — see docs/architecture.md's
"UI Extension Points in MainWindow (#73)" and the plugin_api package
itself for what a plugin can do.

Not shipped in the packaged app (installer/portable) — this lives in the
repo's plugins/ directory, which is also where the loader (#74) already
looks by default when running from source, so it's discovered with zero
extra wiring. Proving the pipeline works from source is the whole point;
nothing here needs to reach an end user's installed copy.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QFormLayout, QLabel, QWidget

from mdf_viewer.plugin_api.plugin import Plugin

if TYPE_CHECKING:
    from mdf_viewer.plugin_api.context import PluginContext
    from mdf_viewer.plugin_api.types import PluginSelectionChangedEvent

_PLACEHOLDER = "—"  # em dash


class SignalStatisticsPlugin(Plugin):
    """Min/Max/Mean of the currently selected signal, live-updated."""

    name = "Signal Statistics"
    version = "1.0"
    description = "Shows Min/Max/Mean for the currently selected signal."
    author = "MDF-Viewer"

    def __init__(self) -> None:
        self._context: "PluginContext | None" = None
        self._min_label: QLabel | None = None
        self._max_label: QLabel | None = None
        self._mean_label: QLabel | None = None

    def activate(self, context: "PluginContext") -> None:
        self._context = context
        context.register_dock_widget("Signal Statistics", self._build_widget, mode="docked")

    def _build_widget(self) -> QWidget:
        """Called once, lazily, by MainWindow (#73) when it renders the drawer."""
        widget = QWidget()
        layout = QFormLayout(widget)
        self._min_label = QLabel(_PLACEHOLDER)
        self._max_label = QLabel(_PLACEHOLDER)
        self._mean_label = QLabel(_PLACEHOLDER)
        layout.addRow("Min:", self._min_label)
        layout.addRow("Max:", self._max_label)
        layout.addRow("Mean:", self._mean_label)
        return widget

    def on_selection_changed(self, event: "PluginSelectionChangedEvent") -> None:
        if self._min_label is None:
            return  # widget not built yet (register_dock_widget's factory hasn't run)

        if len(event.selected) != 1:
            self._set_labels(_PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER)
            return

        assert self._context is not None
        samples = self._context.get_samples(event.selected[0])
        if samples is None:
            self._set_labels(_PLACEHOLDER, _PLACEHOLDER, _PLACEHOLDER)
            return

        _, values = samples
        self._set_labels(f"{values.min():.4g}", f"{values.max():.4g}", f"{values.mean():.4g}")

    def _set_labels(self, min_text: str, max_text: str, mean_text: str) -> None:
        assert self._min_label is not None and self._max_label is not None and self._mean_label is not None
        self._min_label.setText(min_text)
        self._max_label.setText(max_text)
        self._mean_label.setText(mean_text)


PLUGINS = [SignalStatisticsPlugin]
