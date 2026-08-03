# Requirements: Signal Value Search

Part of the `docs/requirements/` collection — the single source of truth for
*what* the application does. This file covers searching for a value, or a
combination of values across multiple signals, among the signals active in
the current tab, and jumping Cursor 1 to the timestamp that matches — see
#110.

**Out of scope here:** a value-range/"between" operator, per-signal
tolerance/fuzzy matching, choosing an interpolation mode other than
last-known-value for evaluating a multi-signal search, and searching across
more than one tab at once — all deferred to a future issue if actually
needed. Also out of scope: how any of this is presented on screen beyond the
requirements below (see `docs/ui.md`) and how it is implemented across
Model/View/Controller (see `docs/architecture.md`).

**Conventions:** requirements are numbered `REQ-SEARCH-NNN`, grouped by
sub-topic with gaps left for insertion. Each testable statement is tagged
inline so it can be cited from an issue or a test via
`@pytest.mark.requirement("REQ-SEARCH-NNN")`.

---

## Entry Points

`Edit → Search...` opens the Search dialog with every signal row's value
left blank [REQ-SEARCH-010]. Ctrl+F is the default keyboard shortcut for
opening the Search dialog [REQ-SEARCH-011], and it is rebindable alongside
every other action in Preferences → Shortcuts (see
`docs/requirements/keyboard-shortcuts.md`) [REQ-SEARCH-012]. The Active
Signals Table's context menu offers a "Search..." entry that opens the same
dialog with the currently selected signal(s) pre-filled with the `=`
operator and that signal's current Cursor 1 value, or left blank if no
cursor is currently shown [REQ-SEARCH-013]. Only one Search dialog can be
open at a time; triggering either entry point while one is already open
brings it to the front and re-applies any context-menu pre-fill instead of
opening a second dialog [REQ-SEARCH-014]. The Search dialog is non-modal, so
the rest of the application remains usable while it is open [REQ-SEARCH-015].
The dialog shows the name of the tab it is currently searching in
[REQ-SEARCH-016]. Any change to which tab is active while the dialog is
open — the user switching to a different existing tab, the tab the dialog
was searching in being closed (the application always makes some other tab
active in that case), or a new tab becoming active as a side effect of its
own creation (New Tab, Duplicate Tab, Copy Signals to New Tab) — rebuilds
the dialog's rows for the newly active tab [REQ-SEARCH-017]: a row whose
signal has a matching-named signal in the new tab carries its operator and
value forward, a row with no match in the new tab is dropped, and each of
the new tab's signals with no matching old row gets a fresh blank row
[REQ-SEARCH-018]. Closing the tab the dialog was searching in when it was
the only tab open leaves no tab for the dialog to search, so the dialog
closes itself automatically in that case [REQ-SEARCH-060].

## Search Criteria

The Search dialog lists one row per signal currently active in the current
tab, across all of its stripes [REQ-SEARCH-020]. Each row shows the signal's
display name — the same shortened-and-measurement-prefixed name shown in the
Active Signals Table, not the raw channel name — an operator selector, and a
value field [REQ-SEARCH-021]. The operator
selector offers equals, not-equals, greater-than, less-than,
greater-than-or-equal, and less-than-or-equal, defaulting to equals
[REQ-SEARCH-022]. A row with an empty value field is excluded from the
search [REQ-SEARCH-023]. Signals belonging to different loaded measurements
can be included in the same search [REQ-SEARCH-024]. The Search action is
disabled while no row has a value entered [REQ-SEARCH-025].

## Search Evaluation

Each included row's condition is evaluated against its signal's last-known
value at a given point in time — the most recent sample at or before that
time — never a value interpolated between samples [REQ-SEARCH-030]. A
search's conjunction (every included row's condition, all must hold) is
evaluated at every timestamp of the fastest-raster signal among only the
rows included in that search [REQ-SEARCH-031]. All timestamps are compared
on the shared display timeline used elsewhere in the application, so each
signal's own measurement offset is applied before evaluation
[REQ-SEARCH-032].

## Search Execution

Clicking Search with no search already in progress for the current criteria
scans from the beginning of the time range for the first timestamp where
every included row's condition holds [REQ-SEARCH-040]. Clicking Search again
with the same criteria as the previous search continues scanning from just
after the previously found timestamp, finding the next match
[REQ-SEARCH-041]. Changing any row's operator or value discards the previous
match position, so the next Search click scans from the beginning again
[REQ-SEARCH-042]. When no timestamp satisfies the search, the dialog shows
an inline message reporting that no match was found, and remains open
[REQ-SEARCH-043].

## Search Result

When a match is found, Cursor 1 (or Cursor L, when delta-time cursor
labeling is active) is moved to the matched timestamp [REQ-SEARCH-050]. If
cursors are currently hidden when a match is found, cursor mode switches
from hidden to Cursor 1 shown [REQ-SEARCH-051]. Cursor 2 (or Cursor R) is
not moved by a search result [REQ-SEARCH-052]. The plot view is recentered
on the matched timestamp, keeping the current zoom width unchanged, across
every stripe in the tab [REQ-SEARCH-053]. The Search dialog remains open
after a match is found, so another search can be run immediately
[REQ-SEARCH-054].
