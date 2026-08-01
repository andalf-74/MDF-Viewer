# Requirements: Logging

Part of the `docs/requirements/` collection — the single source of truth for
*what* the application does. This file covers application-level diagnostic
logging: writing a persistent record of lifecycle events, operation
successes/failures, and errors to a log file, and the user-facing controls
for it — see #126.

**Out of scope here:** how any of this is presented on screen (see
`docs/ui.md`) and how it is implemented across Model/View/Controller (see
`docs/architecture.md`). A requirement below should read the same regardless
of which layer ends up owning it. Also out of scope: an in-app log viewer
(logging writes to a file only, there is no in-app panel that displays log
entries — a separate in-session, non-persisted status bar message history is
covered by `docs/requirements/status-bar.md`, which also feeds non-routine
status messages into this log per REQ-STATUS-014), and any new
`PluginContext` API — a plugin obtains a logger the same way core modules
already do, via Python's standard `logging` module, and is captured
automatically once the conditions in REQ-LOG-034 are met.

**Conventions:** requirements are numbered `REQ-LOG-NNN`, grouped by
sub-topic with gaps left for insertion. Each testable statement is tagged
inline so it can be cited from an issue or a test via
`@pytest.mark.requirement("REQ-LOG-NNN")`.

---

## Log File & Rotation

The application writes log entries to a file named `mdf_viewer.log` inside a
`logs` subdirectory of the same platform-appropriate configuration directory
that stores `settings.json` [REQ-LOG-010]. The log file rotates once it
reaches 5 MB, keeping up to 3 rotated backups before the oldest is discarded
[REQ-LOG-011]. Each log entry records a timestamp, its level, the
originating logger name, and the message [REQ-LOG-012].

## Enablement & Levels

Logging is enabled at the INFO level by default, so a fresh install with no
prior `settings.json` starts capturing lifecycle events and errors from
first launch [REQ-LOG-020]. The user can disable logging entirely, in which
case no log file is written and no log handler is active [REQ-LOG-021]. When
enabled, the user can select the minimum captured level from DEBUG, INFO,
WARNING, or ERROR [REQ-LOG-022]. The enabled state and selected level are
persisted in `settings.json` and restored on the next launch [REQ-LOG-023].
Changing the enabled state or the level in Preferences takes effect
immediately, without requiring an application restart [REQ-LOG-024].

## Logged Events

Application startup and application shutdown are each logged as one INFO
entry [REQ-LOG-030]. Opening a measurement file is logged at INFO level on
success and at ERROR level on failure, with the failure reason included in
the message [REQ-LOG-031]. Closing a measurement is logged at INFO level
[REQ-LOG-032]. Loading, reloading, enabling, and disabling a plugin are each
logged at INFO level on success and at ERROR level on failure
[REQ-LOG-033]. Any message logged via Python's standard `logging` module by
core code or by a plugin, at or above the currently selected level, is
written to the log file while logging is enabled — no additional
registration or API call is required beyond obtaining a logger the standard
way [REQ-LOG-034]. An uncaught exception that would otherwise only print a
traceback to the console is also written to the log file, together with its
traceback, before the default exception handling proceeds [REQ-LOG-035].

Routine, high-frequency user actions (adding/removing/arranging signals,
zooming, cursor movement, and similar) are not part of this event set; the
log is a diagnostic and lifecycle trail, not a UI-action journal.

## Preferences UI

The Preferences dialog's General tab includes a checkbox to enable or
disable logging [REQ-LOG-040]. The General tab includes a dropdown to select
the minimum captured log level, enabled only while logging is enabled
[REQ-LOG-041]. The General tab includes a button that opens the log file's
containing folder in the operating system's file browser [REQ-LOG-042].
Clicking that button creates the log folder first if it does not already
exist, then opens it [REQ-LOG-043].
