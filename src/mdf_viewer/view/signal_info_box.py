"""SignalInfoBox — bottom-right panel showing metadata for the selected signal.

Driven by the Active Signals Table selection. Displays a SignalMetadata: name,
unit, sample count, min, max, comment, and any other available fields.
Read-only.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget


class SignalInfoBox(QWidget):
    """Read-only display of the selected signal's metadata."""

    # To be implemented:
    #   set_metadata(signal_metadata) -> render all available fields
    #   clear() when no signal is selected
