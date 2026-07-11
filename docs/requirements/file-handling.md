# Requirements: File Handling

Part of the `docs/requirements/` collection — the single source of truth for
*what* the application does. This file covers opening measurement files,
recovering from load failures, recently-opened tracking, and saving/restoring
a viewer session via `.mvc` config files.

**Out of scope here:** how any of this is presented on screen (see
`docs/ui.md`) and how it is implemented across Model/View/Controller (see
`docs/architecture.md`). A requirement below should read the same regardless
of which layer ends up owning it.

**Conventions:** requirements are numbered `REQ-FILE-NNN`, grouped by
sub-topic with gaps left for insertion. Each testable statement is tagged
inline so it can be cited from an issue or a test via
`@pytest.mark.requirement("REQ-FILE-NNN")`.

---

## Loading a Measurement File

The application can hold one or more measurement files open at once —
MDF3 or MDF4, in any combination — with no fixed technical maximum,
though the UI is designed around a small number of simultaneous
measurements (a soft target of up to 3; see "Multiple Measurements"
below) [REQ-FILE-010]. A measurement can be opened via the File ▸ Open
dialog, which allows selecting multiple files at once, by dragging one or
more files onto the main window, or by passing a path as a startup
argument (e.g. via file association / "Open with") [REQ-FILE-011].
Opening one or more files while no measurement is currently loaded loads
them immediately with no prompt, becoming the initial set of loaded
measurements [REQ-FILE-012]. If the opened path is a `.mvc` file rather
than a measurement file, it is handled as a session load (see "Session
Persistence" below) instead of a direct measurement load, regardless of
which entry point was used [REQ-FILE-013].

Opening or dropping one or more files while at least one measurement is
already loaded asks the user, once per operation, whether to Replace
every currently loaded measurement or Add the newly opened file(s)
alongside them; a startup argument never triggers this prompt, since it
only ever runs before anything else has been loaded [REQ-FILE-020].
Replacing clears every currently loaded measurement — channel tree(s),
active signals, cursors, zoom state, and measurement info — and rebuilds
from only the newly opened file(s), the same as an initial load
[REQ-FILE-021]. Adding loads each newly opened file as an additional
measurement alongside what is already open, leaving every existing
measurement's channel tree, active signals, cursors, and zoom state
untouched [REQ-FILE-022]. When opening or dropping multiple files in one
operation, each file loads independently: files that succeed are loaded
per REQ-FILE-021/022 as appropriate, while any failures are collected and
reported together in one error dialog naming each failed file, rather
than aborting the whole operation on the first failure [REQ-FILE-023]. A
failure during an Add never affects any already-loaded measurement — only
the failing file itself is skipped [REQ-FILE-024].

## Multiple Measurements

Once more than one measurement is loaded, each one is independent data:
its own channel tree, its own file-level metadata, and its own pannable
X-axis offset (see `plotting.md` "Multiple Measurements") — signals from
different measurements can be freely mixed into the same or different
plot stripes and tabs [REQ-FILE-025]. A newly added measurement always
starts with its X-axis offset at zero, i.e. its own raw recorded time; no
automatic alignment between measurements is attempted — manual alignment
is a deliberate user action (see `plotting.md`) [REQ-FILE-026]. Each
loaded measurement has a user-facing short name, defaulting to "M1",
"M2", ... in load order, used to identify its X-axis row and to prefix
its signals' displayed names (see `plotting.md`, `signal-browser.md`); it
is user-editable via the Measurement Info panel, and an edit that would
duplicate another currently-loaded measurement's short name is rejected,
reverting to the name it held before the edit, so short names stay
unique at all times. The load-order position behind this default is
never reused just because closing a measurement freed it up — it only
resets when every measurement is replaced at once (REQ-FILE-021), the
same fresh-start point that already resets every measurement's offset
and Synchronized state; closing one measurement and then adding another
therefore continues from the next never-yet-used default rather than
reissuing a name a still-loaded or since-renamed measurement might
collide with [REQ-FILE-027]. Closing a measurement that has no
active signals in any tab or stripe removes it immediately with no
confirmation; closing one with at least one active signal shows a
warning offering "Close anyway" or "Cancel", mirroring stripe and tab
close (REQ-PLOT-194, REQ-PLOT-252) — confirming removes that
measurement's X-axis row and every one of its signals from every tab and
stripe [REQ-FILE-028]. A File ▸ Close Measurement submenu lists every
currently loaded measurement by its short name (REQ-FILE-027); selecting
one closes that specific measurement through the same flow as any other
close (REQ-FILE-028) [REQ-FILE-029].

## Active Signals When Replacing a File

Whether currently active signals carry over into the newly loaded
measurement is controlled by a preference with three modes: always carry
them over silently, ask the user each time, or always discard them
[REQ-FILE-030]. When signals are carried over, each one is re-resolved by
name against the new file: a single unambiguous match is re-added
automatically; multiple channels sharing that name (e.g. across channel
groups) prompt the user to pick which one; names with no match in the new
file are reported to the user in a summary rather than silently dropped
[REQ-FILE-031].

A signal name with no exact match is additionally checked for a near
match: another channel whose name is identical up to its own last
backslash ("\"), differing only in what follows it — covering a signal
recorded under a different measurement protocol or source, e.g.
"...FZGG_NAB_AKT\ETKC:1" against "...FZGG_NAB_AKT\XCP:1" [REQ-FILE-032]. A
signal name containing no backslash is never treated as a near-match
candidate, on either side of the comparison [REQ-FILE-033]. Near-match
detection runs unconditionally whenever signals are resolved by name
(REQ-FILE-031, REQ-FILE-066) — there is no separate preference to disable
it [REQ-FILE-034]. Exactly one near-match candidate is added to a pending
list, presented for confirmation once every signal has been resolved
(REQ-FILE-036); more than one near-match candidate for the same signal is
offered through the same ambiguous-match picker used for multiple exact
matches (REQ-FILE-031), and canceling that picker treats the signal as not
found rather than retrying [REQ-FILE-035]. Once every signal has been
resolved, any pending near-match signals are shown together in one
confirmation dialog, each listing the original name and its matched
candidate name with a checkbox that starts checked; accepted rows are
added as if they had matched exactly, and declined rows are folded into
the same not-found summary as signals with no match at all
[REQ-FILE-036].

## Load Failure Handling

The application must never crash because a measurement file is malformed,
incomplete, or otherwise unreadable [REQ-FILE-040]. If opening or reading
a file fails during an initial load or a Replace (REQ-FILE-021), the load
attempt ends with no measurement open — any previously loaded
measurement's channel tree and active signals are not restored — and the
failure is reported to the user in an error dialog naming the file; a
failure during an Add (REQ-FILE-022) instead leaves every already-loaded
measurement untouched, per REQ-FILE-024 [REQ-FILE-041].

## Recently Opened Files

Up to 4 most-recently-opened paths are persisted across application
restarts, most recent first [REQ-FILE-050]. Both measurement files and
`.mvc` session files share this same recent list [REQ-FILE-051] and are
shown to the user for quick reopening [REQ-FILE-052]. A path is added to
the recent list only after it has been successfully loaded (or, for a
save, successfully written); a failed load or save is never recorded
[REQ-FILE-053]. Entries that no longer exist on disk are dropped from the
list silently the next time it is presented [REQ-FILE-054].

## Session Persistence (`.mvc` Configuration Files)

A full viewer session can be saved to and restored from a `.mvc` file
[REQ-FILE-060]. A saved session captures: the measurement file path; the
active signals and their per-signal display settings (color, line width
and style, display mode, marker shape, step mode, enum display toggles);
the zoom state (X range and per-axis Y ranges); axis grouping (shared and
linked axis groups); cursor mode and positions; the selected signal; the
display-name-shortening rule; and the window and splitter layout
[REQ-FILE-061].

The measurement path inside a `.mvc` file is stored either as an absolute
path or relative to the `.mvc` file's own directory, per user preference
[REQ-FILE-063]. When a `.mvc` file is opened, its stored measurement path
is resolved and that measurement is loaded automatically if found
[REQ-FILE-064]; if it cannot be found at the resolved location, the user
is prompted to locate it manually, and canceling that prompt aborts the
session load without error [REQ-FILE-065]. Restoring a session's signals
follows the same by-name resolution, ambiguous-match picker, and
not-found reporting behavior as carrying signals over on file replacement
(REQ-FILE-031) [REQ-FILE-066].

A `.mvc` file is versioned, and fields added to the format after a given
file was written are treated as optional and default sensibly when
absent, so older session files remain loadable [REQ-FILE-067]. A
malformed or unreadable `.mvc` file (invalid JSON, missing file,
structurally invalid content) is reported via an error dialog rather than
crashing the application [REQ-FILE-068].

## Prompting to Save on Close

If the "prompt to save on close" preference is enabled and at least one
signal is active, closing the application asks the user to Save, Discard,
or Cancel the close [REQ-FILE-070]. Canceling aborts the close entirely;
saving writes to the session's current config path, or prompts for a new
path if the session has not been saved before [REQ-FILE-071].

## Startup Behavior

The application never auto-restores the previous session on startup —
every launch begins with no file loaded, unless a measurement or `.mvc`
path is supplied via a startup argument [REQ-FILE-080].
