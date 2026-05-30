"""MeasurementInfoBox — bottom-left panel showing file-level MDF metadata.

Displays a MeasurementInfo: file name, author, recording date/time, MDF
version, duration, comment, and any other available fields. Read-only.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget


class MeasurementInfoBox(QWidget):
    """Read-only display of file-level measurement metadata."""

    # To be implemented:
    #   set_info(measurement_info) -> render all available fields
