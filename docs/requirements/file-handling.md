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

The application shows exactly one measurement file at a time — MDF3 or
MDF4 — and only one file can be open at once [REQ-FILE-010]. A measurement
can be opened via the File ▸ Open dialog, by dragging a file onto the main
window, or by passing a path as a startup argument (e.g. via file
association / "Open with") [REQ-FILE-011]. Loading a new measurement file
replaces the one currently open: the previous channel tree, active signals,
cursors, zoom state, and measurement info are cleared and rebuilt from the
new file [REQ-FILE-012]. If the opened path is a `.mvc` file rather than a
measurement file, it is handled as a session load (see "Session
Persistence" below) instead of a direct measurement load, regardless of
which of the three entry points was used [REQ-FILE-013].

When a file is dropped onto the main window while another measurement is
already loaded, the user is asked to confirm the replacement before it
happens [REQ-FILE-020]. Opening via the File ▸ Open dialog or a startup
argument does not ask for confirmation, since selecting a file through
either of those is already a deliberate action.

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

## Load Failure Handling

The application must never crash because a measurement file is malformed,
incomplete, or otherwise unreadable [REQ-FILE-040]. If opening or reading
the new file fails, the load attempt ends with no measurement open — the
previous file's channel tree and active signals are not restored — and the
failure is reported to the user in an error dialog naming the file
[REQ-FILE-041].

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
[REQ-FILE-061]. Session persistence is manual only — saving and loading
happen solely through explicit user action (File ▸ Save Config / Save
Config As / Open), never automatically [REQ-FILE-062].

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
