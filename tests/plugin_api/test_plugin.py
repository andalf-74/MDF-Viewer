"""Tests for the Plugin base class (#72)."""

from __future__ import annotations

import pytest

from mdf_viewer.plugin_api.plugin import Plugin


@pytest.mark.requirement("REQ-PLUGIN-161")
def test_subclass_without_name_raises_at_class_definition_time() -> None:
    with pytest.raises(ValueError, match="name"):

        class NoNamePlugin(Plugin):
            def activate(self, context) -> None:
                pass


@pytest.mark.requirement("REQ-PLUGIN-160")
def test_subclass_needs_no_init_of_its_own() -> None:
    class MinimalPlugin(Plugin):
        name = "Minimal"

        def activate(self, context) -> None:
            pass

    plugin = MinimalPlugin()
    assert plugin.is_active is False
    assert plugin.context is None


@pytest.mark.requirement("REQ-PLUGIN-170")
def test_default_activate_raises_not_implemented() -> None:
    class NoActivatePlugin(Plugin):
        name = "NoActivate"

    with pytest.raises(NotImplementedError):
        NoActivatePlugin().activate(context=None)


@pytest.mark.requirement("REQ-PLUGIN-171")
def test_default_deactivate_and_handlers_are_noop() -> None:
    class MinimalPlugin(Plugin):
        name = "Minimal"

        def activate(self, context) -> None:
            pass

    plugin = MinimalPlugin()
    plugin.deactivate()
    plugin.on_file_loaded(None)
    plugin.on_signal_added(None)
    plugin.on_signal_removed(None)
    plugin.on_selection_changed(None)
    plugin.on_cursor_moved(None)


def test_metadata_defaults_to_empty_strings() -> None:
    class MinimalPlugin(Plugin):
        name = "Minimal"

        def activate(self, context) -> None:
            pass

    plugin = MinimalPlugin()
    assert plugin.version == ""
    assert plugin.description == ""
    assert plugin.author == ""
