"""Preferences Fixture — minimal plugin exercising register_preferences_page()
and get_setting()/set_setting() (#159).

Registers one trivial preferences page (a checkbox and a text field) purely
to make #159's Plugin Preferences dialog lifecycle (build-once-and-cache,
live self-save, teardown-on-reload) actually live-testable — the same role
Signal Statistics (#75) played for #71-#74 and Tab Type Fixture (#148)
played for register_tab_type().

Not shipped in the packaged app (installer/portable) — lives in the repo's
plugins/ directory, already #74's own default dev-mode discovery
directory, so it's auto-discovered with zero extra wiring.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QCheckBox, QLabel, QLineEdit, QVBoxLayout, QWidget

from mdf_viewer.plugin_api.plugin import Plugin

if TYPE_CHECKING:
    from mdf_viewer.plugin_api.context import PluginContext


class PreferencesFixturePlugin(Plugin):
    """Registers one preferences page with two live-persisted settings."""

    name = "Preferences Fixture"
    version = "1.0"
    description = "Minimal preferences page for exercising register_preferences_page()."
    author = "MDF-Viewer"

    def activate(self, context: "PluginContext") -> None:
        self._context = context
        context.register_preferences_page("Preferences Fixture", self._build_page)

    def _build_page(self) -> "QWidget":
        """Called once, the first time the Plugin Preferences dialog needs
        this plugin's tab (#159) — the returned widget is then cached and
        reused across every later dialog open, so its live edits (and the
        settings they write) survive a Close/reopen without rebuilding.
        """
        context = self._context
        page = QWidget()
        layout = QVBoxLayout(page)

        checkbox = QCheckBox("Enable Feature X")
        checkbox.setChecked(bool(context.get_setting("feature_x_enabled", False)))
        checkbox.toggled.connect(lambda checked: context.set_setting("feature_x_enabled", checked))
        layout.addWidget(checkbox)

        layout.addWidget(QLabel("Greeting:"))
        line_edit = QLineEdit(str(context.get_setting("greeting", "Hello")))
        line_edit.textChanged.connect(lambda text: context.set_setting("greeting", text))
        layout.addWidget(line_edit)

        layout.addStretch()
        return page


PLUGINS = [PreferencesFixturePlugin]
