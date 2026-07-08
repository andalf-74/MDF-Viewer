"""MeasurementInfoBox — bottom-left panel showing file-level MDF metadata.

Displays a MeasurementInfo: file name, MDF version, author, recording
date/time, duration, comment, and any extra fields. Read-only.
"""

from __future__ import annotations

import re

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFormLayout,
    QFrame,
    QLabel,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from mdf_viewer.model.measurement import MeasurementInfo


class MeasurementInfoBox(QWidget):
    """Read-only display of file-level measurement metadata."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(80)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        placeholder = QLabel("No file loaded.")
        placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stack.addWidget(placeholder)  # index 0

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._content = QWidget()
        self._form = QFormLayout(self._content)
        self._form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        scroll.setWidget(self._content)
        self._stack.addWidget(scroll)  # index 1

    def set_info(self, info: MeasurementInfo) -> None:
        """Populate the form from a MeasurementInfo and show it."""
        _clear_form(self._form)
        for label, value in _measurement_rows(info):
            if label == "Comment":
                _add_wrapped_row(self._form, label, value)
            else:
                _add_row(self._form, label, value)
        self._stack.setCurrentIndex(1)

    def clear(self) -> None:
        """Remove all rows and show the placeholder."""
        _clear_form(self._form)
        self._stack.setCurrentIndex(0)


# ---------------------------------------------------------------------------
# Shared helpers (imported by SignalInfoBox)
# ---------------------------------------------------------------------------

def _clear_form(form: QFormLayout) -> None:
    while form.rowCount() > 0:
        form.removeRow(0)


def _make_wrapped_value_label(value: str) -> QLabel:
    """QLabel that actually shrinks to its column instead of forcing it wider.

    setWordWrap(True) alone isn't enough: Qt still reports a
    minimumSizeHint() based on the label's longest unbreakable substring
    (e.g. an underscore-separated channel name or comment with no spaces),
    and that minimum propagates up through the form/scroll area to force
    the whole drawer wider than its assigned splitter width. Ignoring the
    horizontal size policy tells the layout not to treat that width as a
    hard minimum, so the label wraps/shrinks to whatever space it's given.
    """
    val = QLabel(value)
    val.setWordWrap(True)
    val.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    return val


def _add_row(form: QFormLayout, label: str, value: str) -> None:
    lbl = QLabel(label + ":")
    lbl.setStyleSheet("font-weight: bold;")
    form.addRow(lbl, _make_wrapped_value_label(value))


def _add_wrapped_row(form: QFormLayout, label: str, value: str) -> None:
    """Add a row whose value wraps on its own full-width line below the label.

    Used for long free-text fields (e.g. Comment) where a side-by-side
    label/field row would squeeze wrapped text into a narrow column.
    """
    lbl = QLabel(label + ":")
    lbl.setStyleSheet("font-weight: bold;")
    form.addRow(lbl)
    form.addRow(_make_wrapped_value_label(value))


def _clean_text(text: str) -> str:
    """Strip XML tags from MDF4 comment fields (asammdf wraps them in XML)."""
    return re.sub(r"<[^>]+>", "", text).strip()


# ---------------------------------------------------------------------------
# Row builders
# ---------------------------------------------------------------------------

def _measurement_rows(info: MeasurementInfo) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = [("File", info.file_name)]
    if info.mdf_version:
        rows.append(("MDF version", info.mdf_version))
    if info.author:
        rows.append(("Author", info.author))
    if info.recorded_at:
        rows.append(("Recorded", info.recorded_at))
    if info.duration_s is not None:
        rows.append(("Duration", _format_duration(info.duration_s)))
    if info.comment:
        rows.append(("Comment", _clean_text(info.comment)))
    for key, value in info.extra.items():
        rows.append((str(key), str(value)))
    return rows


def _format_duration(seconds: float) -> str:
    if seconds < 60:
        return f"{seconds:.3f} s"
    m = int(seconds // 60)
    s = seconds - m * 60
    return f"{m} min {s:.3f} s"
