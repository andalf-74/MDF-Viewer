"""SignalInfoBox — bottom-right panel showing metadata for the selected signal.

Driven by the Active Signals Table selection. Displays a SignalMetadata: name,
unit, sample count, min, max, comment, and any extra fields. Read-only.
"""

from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QFormLayout,
    QFrame,
    QLabel,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.view.measurement_info_box import _add_row, _clear_form


class SignalInfoBox(QWidget):
    """Read-only display of the selected signal's metadata."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(80)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        self._placeholder = QLabel("No signal selected.")
        self._placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._stack.addWidget(self._placeholder)  # index 0

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

    def set_metadata(self, meta: SignalMetadata) -> None:
        """Populate the form from a SignalMetadata and show it."""
        _clear_form(self._form)
        for label, value in _metadata_rows(meta):
            _add_row(self._form, label, value)
        self._stack.setCurrentIndex(1)

    def show_multi_selection(self) -> None:
        """Show the 'multiple signals selected' placeholder."""
        self._placeholder.setText("Multiple signals selected.")
        self._stack.setCurrentIndex(0)

    def clear(self) -> None:
        """Remove all rows and show the placeholder."""
        self._placeholder.setText("No signal selected.")
        _clear_form(self._form)
        self._stack.setCurrentIndex(0)


# ---------------------------------------------------------------------------
# Row builder
# ---------------------------------------------------------------------------

def _metadata_rows(meta: SignalMetadata) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = [("Name", meta.name)]
    if meta.unit:
        rows.append(("Unit", meta.unit))
    if meta.data_type:
        rows.append(("Data type", meta.data_type))
    if meta.sample_count is not None:
        rows.append(("Samples", f"{meta.sample_count:,}"))
    if meta.min_value is not None:
        rows.append(("Min", _format_number(meta.min_value)))
    if meta.max_value is not None:
        rows.append(("Max", _format_number(meta.max_value)))
    if meta.comment:
        rows.append(("Comment", meta.comment))
    for key, value in meta.extra.items():
        rows.append((str(key), str(value)))
    return rows


def _format_number(value: float) -> str:
    return f"{value:.6g}"
