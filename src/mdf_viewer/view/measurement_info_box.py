"""MeasurementInfoBox — left panel showing file-level MDF metadata.

Always tabbed (#103, REQ-PLOT-318), one tab per loaded measurement, even
when only one is loaded — the tab structure doesn't change as measurements
are added or removed. Each tab shows: a header row with a "Primary
Measurement" checkbox (REQ-PLOT-317) and an editable short-name field
(REQ-FILE-027), then the existing read-only metadata form (file name, MDF
version, author, recording date/time, duration, comment, extra fields).
"""

from __future__ import annotations

import re

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from mdf_viewer.model.loaded_measurement import LoadedMeasurement
from mdf_viewer.model.measurement import MeasurementInfo


class MeasurementInfoBox(QWidget):
    """Tabbed, read-mostly display of every loaded measurement's metadata."""

    # LoadedMeasurement whose "Primary Measurement" checkbox was checked by
    # the user — AppController.set_primary_measurement() decides whether/how
    # to apply it and pushes the result back via set_measurements().
    primary_change_requested = pyqtSignal(object)
    # LoadedMeasurement, new short name — AppController.rename_measurement()
    # decides whether to accept it; a rejected rename is reverted by the
    # next set_measurements() call, which always reflects the model's own
    # current label.
    rename_requested = pyqtSignal(object, str)
    # LoadedMeasurement to replace (#122) — MainWindow._replace_single_measurement()
    # owns the file dialog and carry-over prompting, mirroring the File ▸
    # Replace Measurement submenu's own entry point.
    replace_requested = pyqtSignal(object)
    # LoadedMeasurement to close (#122) — same flow/confirmation as the File ▸
    # Close Measurement submenu, just a second entry point onto the same
    # MainWindow._on_close_measurement_requested().
    close_requested = pyqtSignal(object)

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

        self._tabs = QTabWidget()
        self._stack.addWidget(self._tabs)  # index 1

        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)
        self._pages: list[tuple[LoadedMeasurement, _MeasurementInfoPage]] = []

    def set_measurements(
        self, measurements: list[LoadedMeasurement], primary: LoadedMeasurement | None
    ) -> None:
        """Rebuild the tabs from every loaded measurement (#103).

        Always tabbed, even with exactly one measurement loaded
        (REQ-PLOT-318). Every call fully tears down and rebuilds every
        tab — including the case where only one measurement's short name
        or Primary status changed — so the teardown discipline
        (button-group detach, removeTab, deleteLater) always runs through
        one code path rather than risking a partial/incremental update
        forgetting a step.
        """
        current_index = self._tabs.currentIndex()
        self._teardown_pages()
        for measurement in measurements:
            page = _MeasurementInfoPage()
            page.set_info(measurement.info)
            page.set_name(measurement.label)
            page.set_primary(measurement is primary)
            page.primary_checked.connect(
                lambda m=measurement: self.primary_change_requested.emit(m)
            )
            page.rename_committed.connect(
                lambda text, m=measurement: self.rename_requested.emit(m, text)
            )
            page.replace_clicked.connect(
                lambda m=measurement: self.replace_requested.emit(m)
            )
            page.close_clicked.connect(
                lambda m=measurement: self.close_requested.emit(m)
            )
            self._button_group.addButton(page.checkbox)
            self._tabs.addTab(page, measurement.label)
            self._pages.append((measurement, page))
        if measurements:
            self._stack.setCurrentIndex(1)
            if 0 <= current_index < self._tabs.count():
                self._tabs.setCurrentIndex(current_index)
        else:
            self._stack.setCurrentIndex(0)

    def clear(self) -> None:
        """Remove every tab and show the placeholder."""
        self._teardown_pages()
        self._stack.setCurrentIndex(0)

    def _teardown_pages(self) -> None:
        """Detach and destroy every existing tab page.

        Mirrors the #120 teardown discipline for a new (plain-QWidget,
        not PyQtGraph) site: QTabWidget.removeTab() detaches a page but
        does not destroy it, so deleteLater() is required too. Removing
        from the button group first avoids a moment where an
        about-to-be-destroyed checkbox is still counted toward exclusivity.
        """
        while self._pages:
            _, page = self._pages.pop()
            self._button_group.removeButton(page.checkbox)
            index = self._tabs.indexOf(page)
            if index >= 0:
                self._tabs.removeTab(index)
            page.deleteLater()


class _MeasurementInfoPage(QWidget):
    """One tab's content: Primary checkbox + short-name edit, then the form."""

    # Emitted only when the checkbox becomes checked — unchecking happens
    # only as a side effect of another tab's checkbox becoming checked
    # (QButtonGroup exclusivity), which is never a request to act on.
    primary_checked = pyqtSignal()
    rename_committed = pyqtSignal(str)
    replace_clicked = pyqtSignal()
    close_clicked = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        header = QHBoxLayout()
        self._primary_checkbox = QCheckBox("Primary")
        header.addWidget(self._primary_checkbox)
        header.addWidget(QLabel("Name:"))
        self._name_edit = QLineEdit()
        header.addWidget(self._name_edit)
        layout.addLayout(header)

        actions = QHBoxLayout()
        actions.addStretch()
        self._replace_button = QPushButton("Replace…")
        actions.addWidget(self._replace_button)
        self._close_button = QPushButton("Close")
        actions.addWidget(self._close_button)
        layout.addLayout(actions)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._content = QWidget()
        self._form = QFormLayout(self._content)
        self._form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
        )
        scroll.setWidget(self._content)
        layout.addWidget(scroll)

        self._primary_checkbox.toggled.connect(self._on_toggled)
        self._name_edit.editingFinished.connect(self._on_editing_finished)
        self._replace_button.clicked.connect(self.replace_clicked)
        self._close_button.clicked.connect(self.close_clicked)

    @property
    def checkbox(self) -> QCheckBox:
        return self._primary_checkbox

    @property
    def replace_button(self) -> QPushButton:
        return self._replace_button

    @property
    def close_button(self) -> QPushButton:
        return self._close_button

    def set_info(self, info: MeasurementInfo) -> None:
        for label, value in _measurement_rows(info):
            if label == "Comment":
                _add_wrapped_row(self._form, label, value)
            else:
                _add_row(self._form, label, value)

    def set_name(self, name: str) -> None:
        self._name_edit.setText(name)

    def set_primary(self, is_primary: bool) -> None:
        self._primary_checkbox.setChecked(is_primary)

    def _on_toggled(self, checked: bool) -> None:
        if checked:
            self.primary_checked.emit()

    def _on_editing_finished(self) -> None:
        self.rename_committed.emit(self._name_edit.text())


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
