"""Exceptions raised to plugins by the plugin API (#189)."""

from __future__ import annotations


class ChannelLoadError(Exception):
    """A listed channel exists but can't be provided as numeric samples —
    a string or structure channel, corrupt data, a virtual signal whose
    resolver raises, or any other unexpected read failure
    (REQ-PLUGIN-584/585). The message states the reason."""
