"""StatusMessageHistory — in-session record of status bar messages (#125).

Plain data, owned by `MainWindow`: nothing outside the View layer needs to
read this, so it deliberately has no `AppController`/`PluginContext`
involvement (see REQ-STATUS-010/011 in `docs/requirements/status-bar.md`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class StatusMessageEntry:
    """One recorded status bar message."""

    timestamp: datetime
    text: str

    def formatted(self) -> str:
        return f"{self.timestamp.strftime('%H:%M:%S')}  {self.text}"


@dataclass
class StatusMessageHistory:
    """Unbounded, session-only list of every status message shown (REQ-STATUS-012)."""

    entries: list[StatusMessageEntry] = field(default_factory=list)

    def record(self, text: str, timestamp: datetime | None = None) -> StatusMessageEntry:
        entry = StatusMessageEntry(timestamp=timestamp or datetime.now(), text=text)
        self.entries.append(entry)
        return entry

    def as_text(self) -> str:
        return "\n".join(entry.formatted() for entry in self.entries)
