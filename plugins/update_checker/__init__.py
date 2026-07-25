"""Update Checker — first-party plugin (#76).

Converts the built-in update checker into a plugin: a "Check for
Update…" menu action, a background check on startup (gated by its own
preferences-page setting), and the setting itself. Ships in the real
installer/portable build — see installer/mdf_viewer.spec — unlike the
dev-mode-only example plugins (signal_statistics, tab_type_fixture,
preferences_fixture).
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from PyQt6.QtCore import QThread, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QApplication, QCheckBox, QMessageBox, QVBoxLayout, QWidget

from mdf_viewer.plugin_api.plugin import Plugin

from .checker import UpdateCheckError, fetch_latest_release, is_newer

if TYPE_CHECKING:
    from mdf_viewer.plugin_api.context import PluginContext

# Module-level, not per-instance: keeps a running _UpdateCheckThread's
# Python object alive until it finishes naturally, independent of the
# plugin instance's own lifetime or of QThread's Qt-parent chain (which is
# None in a headless/test context with no real main window). Destroying a
# QThread object while its underlying OS thread `isRunning()` is a fatal
# Qt abort, not a catchable Python exception — reproduced by
# deactivate_all() running immediately after load_all() in a test with no
# main_window. See _UpdateCheckThread's own comment for the full picture.
_LIVE_THREADS: set["_UpdateCheckThread"] = set()


@contextmanager
def _busy_cursor():
    """Local duplicate of mdf_viewer.view.widgets.busy_cursor — a plugin
    may only import mdf_viewer.plugin_api, not reach into internal view
    modules."""
    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    QApplication.processEvents()
    try:
        yield
    finally:
        QApplication.restoreOverrideCursor()


class _UpdateCheckThread(QThread):
    update_available = pyqtSignal(str, str)  # tag, url

    def __init__(self, current_version: str, parent=None) -> None:
        super().__init__(parent)
        self._current = current_version

    def run(self) -> None:
        try:
            release = fetch_latest_release()
            if is_newer(release.tag, self._current):
                self.update_available.emit(release.tag, release.url)
        except UpdateCheckError:
            pass


class UpdateCheckerPlugin(Plugin):
    """Checks GitHub for a newer released version of MDF-Viewer."""

    name = "Update Checker"
    version = "1.0"
    description = "Checks GitHub for a newer released version of MDF-Viewer."
    author = "MDF-Viewer"

    def __init__(self) -> None:
        self._context: "PluginContext | None" = None
        self._thread: _UpdateCheckThread | None = None

    def activate(self, context: "PluginContext") -> None:
        self._context = context
        context.register_menu_action("Check for Update…", self._on_check_for_update)
        context.register_preferences_page("Update Checker", self._build_preferences_page)
        if context.get_setting("check_for_updates", True):
            self._start_check()

    def deactivate(self) -> None:
        """Disconnect an in-flight check's signal so a late result can never
        reach this now-inactive instance (e.g. Reload mid-check, #150) — not
        a synchronous `.wait()`, which would freeze the GUI thread for up to
        the network timeout on every Reload. `self._thread` is `None` here
        whenever the check already finished naturally on its own
        (`_on_thread_finished` clears it before scheduling `deleteLater()`),
        so this only ever touches a thread that is still genuinely running.
        `RuntimeError` is also caught, not just `TypeError`: PyQt raises it
        (not `TypeError`) when the underlying C++ object has already been
        destroyed, which is possible if `deleteLater()`'s deferred deletion
        lands between the `is not None` check above and this call.
        """
        if self._thread is not None:
            try:
                self._thread.update_available.disconnect(self._on_update_available)
            except (TypeError, RuntimeError):
                pass
            self._thread = None

    def _build_preferences_page(self) -> "QWidget":
        """Called once, the first time the Plugin Preferences dialog needs
        this plugin's tab; the returned widget is cached and reused across
        every later opening (#159)."""
        context = self._context
        assert context is not None
        page = QWidget()
        layout = QVBoxLayout(page)
        checkbox = QCheckBox("Check for updates on startup")
        checkbox.setChecked(bool(context.get_setting("check_for_updates", True)))
        checkbox.toggled.connect(
            lambda checked: context.set_setting("check_for_updates", checked)
        )
        layout.addWidget(checkbox)
        layout.addStretch()
        return page

    def _start_check(self) -> None:
        assert self._context is not None
        thread = _UpdateCheckThread(self._context.app_version, self._context.main_window)
        self._thread = thread
        _LIVE_THREADS.add(thread)
        thread.update_available.connect(self._on_update_available)
        thread.finished.connect(lambda: self._on_thread_finished(thread))
        thread.start()

    def _on_thread_finished(self, thread: "_UpdateCheckThread") -> None:
        """A check completed on its own (found nothing, failed, or emitted
        `update_available`) — clean it up here rather than only in
        `deactivate()`, so `self._thread` never outlives the real,
        underlying C++ object `deleteLater()` is about to destroy.
        """
        _LIVE_THREADS.discard(thread)
        if self._thread is thread:
            self._thread = None
        thread.deleteLater()

    def _on_check_for_update(self) -> None:
        assert self._context is not None
        with _busy_cursor():
            try:
                release = fetch_latest_release()
            except UpdateCheckError as exc:
                QMessageBox.warning(self._context.main_window, "Update Check Failed", str(exc))
                return
        if is_newer(release.tag, self._context.app_version):
            self._on_update_available(release.tag, release.url)
        else:
            QMessageBox.information(
                self._context.main_window,
                "Up to Date",
                f"MDF-Viewer {self._context.app_version} is the latest version.",
            )

    def _on_update_available(self, tag: str, url: str) -> None:
        assert self._context is not None
        msg = QMessageBox(self._context.main_window)
        msg.setWindowTitle("Update Available")
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setText(f"Version <b>{tag}</b> is available.")
        msg.setInformativeText(f"You are running version {self._context.app_version}.")
        open_btn = msg.addButton("Open Release Page", QMessageBox.ButtonRole.ActionRole)
        msg.addButton(QMessageBox.StandardButton.Close)
        msg.exec()
        if msg.clickedButton() is open_btn:
            QDesktopServices.openUrl(QUrl(url))


PLUGINS = [UpdateCheckerPlugin]
