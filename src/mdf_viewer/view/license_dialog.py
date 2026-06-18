from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QMimeData
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from mdf_viewer.license.license_info import LicenseInfo
from mdf_viewer.license.license_manager import LicenseError, LicenseManager


class LicenseDialog(QDialog):
    """Import or view a license key file.

    Opened in view mode when a license is already active; import mode otherwise.
    """

    def __init__(
        self,
        manager: LicenseManager,
        current: LicenseInfo | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._manager = manager
        self._current = current
        self.setWindowTitle("License")
        self.setMinimumWidth(420)
        self._build_ui()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        if self._current is not None:
            self._build_view(layout)
        else:
            self._build_import(layout)

    def _build_view(self, layout: QVBoxLayout) -> None:
        info = self._current
        self.setWindowTitle("License Information")

        def row(label: str, value: str) -> QLabel:
            lbl = QLabel(f"<b>{label}:</b> {value}")
            lbl.setWordWrap(True)
            return lbl

        layout.addWidget(row("Licensed to", info.licensee_name))
        layout.addWidget(row("Email", info.licensee_email))
        layout.addWidget(row("License type", info.tier_display))
        layout.addWidget(row("Issued", info.issued_at.isoformat()))
        layout.addWidget(row("Updates until", info.updates_until.isoformat()))

        if info.updates_expired:
            notice = QLabel(
                f"⚠ Update coverage expired on {info.updates_until.isoformat()}. "
                "You can continue using this version, but newer releases require "
                "a license upgrade."
            )
            notice.setWordWrap(True)
            notice.setStyleSheet("color: #b8860b; font-style: italic;")
            layout.addWidget(notice)

        layout.addSpacing(4)
        change_btn = QPushButton("Change License…")
        change_btn.clicked.connect(self._switch_to_import)
        layout.addWidget(change_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        close_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close_box.rejected.connect(self.reject)
        layout.addWidget(close_box)

    def _build_import(self, layout: QVBoxLayout) -> None:
        self.setWindowTitle("Enter License Key")
        self.setAcceptDrops(True)

        intro = QLabel("Browse to your <b>.lic</b> file or drag and drop it below.")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        self._drop_area = _DropArea()
        self._drop_area.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        self._drop_area.setMinimumHeight(100)
        layout.addWidget(self._drop_area)

        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse)
        layout.addWidget(browse_btn, alignment=Qt.AlignmentFlag.AlignLeft)

        self._status = QLabel()
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ------------------------------------------------------------------
    # Import logic
    # ------------------------------------------------------------------

    def _browse(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Open License File", "", "License files (*.lic);;All files (*)"
        )
        if path:
            self._try_import(Path(path))

    def _try_import(self, path: Path) -> None:
        try:
            info = self._manager.import_license(path)
        except LicenseError as exc:
            self._status.setText(f"<span style='color:red;'>Error: {exc}</span>")
            return

        QMessageBox.information(
            self,
            "License Activated",
            f"License successfully activated for <b>{info.licensee_name}</b>.<br>"
            "Please restart the application for all changes to take effect.",
        )
        self.accept()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            urls = event.mimeData().urls()
            if len(urls) == 1 and urls[0].toLocalFile().endswith(".lic"):
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        path = Path(event.mimeData().urls()[0].toLocalFile())
        self._try_import(path)

    def _switch_to_import(self) -> None:
        self._current = None
        # Rebuild layout
        old_layout = self.layout()
        QWidget().setLayout(old_layout)  # detach and discard
        self._build_ui()

    def accepted_license(self) -> LicenseInfo | None:
        """Returns the newly imported LicenseInfo if the dialog was accepted."""
        if self.result() == QDialog.DialogCode.Accepted:
            return self._manager.load_stored()
        return None


class _DropArea(QFrame):
    """Visual drop target for .lic files."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Sunken)
        layout = QVBoxLayout(self)
        label = QLabel("Drop .lic file here")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("color: gray;")
        layout.addWidget(label)
