"""Tab Type Fixture — minimal plugin exercising register_tab_type() (#148).

Registers one trivial non-plot tab type (a static QLabel) purely to make
#148's tab-lifecycle bug surface (create/switch/close/reorder, .mvc
restore) actually live-testable — the same role Signal Statistics (#75)
played for #71-#74, but built alongside its own groundwork issue rather
than as a later follow-up, since #148's bug surface (tab lifecycle, a
3-phase .mvc restore) is much harder to verify with unit tests alone.

Not shipped in the packaged app (installer/portable) — lives in the
repo's plugins/ directory, already #74's own default dev-mode discovery
directory, so it's auto-discovered with zero extra wiring, matching
signal_statistics's precedent exactly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel

from mdf_viewer.plugin_api.plugin import Plugin

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QWidget

    from mdf_viewer.plugin_api.context import PluginContext


class TabTypeFixturePlugin(Plugin):
    """Registers one static-content non-plot tab type."""

    name = "Tab Type Fixture"
    version = "1.0"
    description = "Minimal non-plot tab type for exercising register_tab_type()."
    author = "MDF-Viewer"

    def activate(self, context: "PluginContext") -> None:
        context.register_tab_type("fixture_tab", "Fixture Tab", self._build_view)

    def _build_view(self) -> "QWidget":
        """Called fresh by MainWindow every time a new tab of this type is
        created (#148) — unlike a dock widget's single cached instance."""
        label = QLabel("Tab Type Fixture — static content, no live data.")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label


PLUGINS = [TabTypeFixturePlugin]
