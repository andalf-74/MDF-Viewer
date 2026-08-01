# Requirements: Status Bar Message History

Part of the `docs/requirements/` collection — the single source of truth for
*what* the application does. This file covers the in-session history of
status bar messages and the dialog used to review and copy them — see #125.

**Out of scope here:** the existing transient status-bar display mechanism
itself (`show_status()`'s brief on-screen message) predates this file and is
unchanged by #125 — this file only covers *recording* those messages and
presenting that record back to the user. Also out of scope: how any of this
is presented on screen beyond the requirements below (see `docs/ui.md`) and
how it is implemented across Model/View/Controller (see
`docs/architecture.md`); persistence of the history across an application
restart (explicitly session-only, see REQ-STATUS-011); severity/color
distinction between message types (every message is recorded and displayed
uniformly); and auditing which application actions do or don't currently
call `show_status()` (tracked separately as a follow-up issue, not part of
#125).

**Conventions:** requirements are numbered `REQ-STATUS-NNN`, grouped by
sub-topic with gaps left for insertion. Each testable statement is tagged
inline so it can be cited from an issue or a test via
`@pytest.mark.requirement("REQ-STATUS-NNN")`.

---

## Message History Recording

The application records every status bar message shown, together with the
time it was shown, into an in-memory history for the duration of the current
session [REQ-STATUS-010]. The recorded history is not persisted to disk and
is discarded when the application closes, starting empty again on the next
launch [REQ-STATUS-011]. The history retains every recorded message for the
session's duration with no maximum count [REQ-STATUS-012]. Each recorded
message's timestamp is formatted as local time in `HH:MM:SS` [REQ-STATUS-013].
A status message is also written to the application log file at INFO level
(see `docs/requirements/logging.md`) when it is recorded, except for a
message concerning a routine, high-frequency action already excluded from
the log by `docs/requirements/logging.md`'s Logged Events section
[REQ-STATUS-014]. A status message excluded from the log file under
REQ-STATUS-014 is still added to the in-session history described in
REQ-STATUS-010 [REQ-STATUS-015].

## History Access

A dedicated button, positioned on the left side of the status bar and always
visible regardless of whether a transient message is currently displayed,
opens the Status Message History dialog when clicked [REQ-STATUS-020]. The
Status Message History dialog is non-modal, allowing continued interaction
with the main application window while it remains open [REQ-STATUS-021].
Only one instance of the Status Message History dialog exists per session;
clicking the access button while the dialog is already open brings the
existing dialog to the front instead of opening a second one
[REQ-STATUS-022]. The Status Message History dialog updates in real time to
show newly recorded messages while it remains open [REQ-STATUS-023].

## History Dialog Content

The Status Message History dialog displays each recorded message as one
line, prefixed with its `HH:MM:SS` timestamp [REQ-STATUS-030]. The displayed
message text is selectable by the user via standard text-selection
interaction [REQ-STATUS-031]. The Status Message History dialog includes a
"Copy to Clipboard" button that copies the entire recorded history to the
system clipboard as plain text, regardless of any active text selection
[REQ-STATUS-032].
