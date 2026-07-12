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
[REQ-FILE-061]. A session's per-tab stripe layout and full
multi-measurement state are also captured — see "Session Scope: Stripes,
Tabs, and Multi-Measurement" below.

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

## Session Scope: Stripes, Tabs, and Multi-Measurement

Extends "Session Persistence" above to the full workspace introduced by
Plot Stripes (`plotting.md` "Plot Stripes"), Main Widget Tabs
(`plotting.md` "Main Widget Tabs"), and Multiple Measurements
(`plotting.md` "Multiple Measurements") — previously out of scope for a
saved session, each deferred to this section as those features shipped.

A saved session captures, per tab: its name; its plot-stripe layout
(stripe count, sizes, and names); which stripe each active signal is
assigned to; and the row order of active signals within each stripe
[REQ-FILE-090]. A saved session also captures which stripe is currently
active within each tab, the order and names of the tabs themselves, and
which tab is currently active in the window [REQ-FILE-091]. A saved
session captures the full set of loaded measurements: each one's file
path, short name, and X-axis time offset; which measurement is
designated Primary; and whether Synchronize Measurements is active
[REQ-FILE-092]. A saved session also captures, per tab, the width of the
divider between the plot area and the Active Signals Table, and the
Active Signals Table's own column widths (REQ-FILE-090 addendum, found
missing during #106 M6 live-testing).

Each active signal's saved state records which of the session's
measurements it was captured from (by short name, falling back to load
order for a session saved before short names existed), so restoring
re-resolves it against that same measurement rather than an arbitrary
one when multiple measurements are loaded [REQ-FILE-093]. This
disambiguation applies everywhere a saved tab refers back to a specific
signal by name — Y-axis zoom range, Merged/Synced axis group membership,
and the selected signal — not just the resolve-to-a-channel step itself:
a bare name is ambiguous whenever the same channel name is active from
two different loaded measurements in the same tab, a real gap found via
#106 M6 live-testing (a saved Merged group re-formed against the wrong
measurement's same-named signal). Restoring a
session replaces the entire current application state — every tab and
every loaded measurement — the same way opening a `.mvc` file already
replaces the single active tab's state today (REQ-FILE-013) [REQ-FILE-094].
Every tab's signals are resolved using the same by-name resolution,
ambiguous-match picker, and near-match detection as a single-tab session
(REQ-FILE-066); every tab's near-match and not-found signals are batched
into one confirmation dialog and one summary at the end of the load,
rather than one dialog per tab [REQ-FILE-095].

A session file saved before stripe, tab, or multi-measurement support
existed loads exactly as it did before this extension: its signals load
into a single default tab and stripe, and its measurement path loads as
the sole (and Primary) loaded measurement — the same forward-compatible
defaulting already used for other fields added after a file was written
(REQ-FILE-067) [REQ-FILE-096].

When a saved session references more than one measurement, a missing
measurement is not prompted for individually the way a single-measurement
session's missing file is (REQ-FILE-065 continues to apply unchanged
when a session has exactly one measurement); instead every measurement
that can't be found is listed together in one dialog offering to
continue without them or cancel the whole load [REQ-FILE-097].
Continuing drops each unresolved measurement from the restored set,
folds any of its signals into the usual not-found summary (REQ-FILE-031),
and reassigns Primary to the first-loaded of whatever remains if the
originally-Primary measurement was itself one of the dropped ones
(mirroring REQ-PLOT-321's close-measurement reassignment) [REQ-FILE-098].

Applying a saved session's signal selection to a measurement other than
the one it was captured from is a separate, related capability — see
#105 — and is out of scope here, which always restores against the
session's own recorded measurement(s).

## Replacing a Single Measurement

Extends "Multiple Measurements" above and reuses the signal-carryover
machinery from "Active Signals When Replacing a File" — previously,
swapping in a corrected file for one already-loaded measurement required
discarding and re-adding it (Close Measurement, REQ-FILE-028, followed by
Add, REQ-FILE-022), losing that measurement's short name, load-order
position, and any manual alignment along the way (#122).

A File ▸ Replace Measurement submenu lists every currently loaded
measurement by its short name, mirroring REQ-FILE-029's Close Measurement
submenu; selecting one opens a file-open dialog for its replacement
[REQ-FILE-100]. The same operation is also available as a "Replace…"
button on that measurement's own tab in the Measurement Info Box,
alongside its short-name field and Primary Measurement checkbox
[REQ-FILE-101]. The file-open dialog invoked by either entry point
accepts exactly one file; loading further files alongside a replaced
measurement is Add's job (REQ-FILE-022), not this operation
[REQ-FILE-102].

When the newly selected file opens successfully, the replaced
measurement's short name, load-order position, X-axis offset_s, and
Synchronized state all carry over unchanged onto the new file, and if it
was the Primary measurement it remains Primary — only its underlying file
and channel data change [REQ-FILE-103]. The replaced measurement's own
active signals follow the same carry-over preference and by-name
re-resolution, near-match, and ambiguous-match handling already used for a
whole-pool Replace (REQ-FILE-030 through REQ-FILE-036), scoped to only
that measurement; every other loaded measurement's active signals, tabs,
cursors, and zoom state are untouched, since they were never part of this
operation [REQ-FILE-104]. An "always discard" carry-over preference
proceeds immediately without an additional confirmation step, silently
dropping the replaced measurement's active signals the same way it would
during a whole-pool Replace [REQ-FILE-105].

If the newly selected file fails to open, the measurement being replaced
is left exactly as it was before the attempt — its channel tree, active
signals, cursors, and zoom state all untouched — and the failure is
reported in an error dialog naming the file, the same as an Add failure
(REQ-FILE-024) [REQ-FILE-106]. A successful replacement adds the newly
selected file's path to the Recent Files list, the same as any other
successful load (REQ-FILE-053) [REQ-FILE-107].

Dropping a file directly onto a specific measurement's row to replace it
is not implemented by this feature — drag-and-drop continues to only
trigger the whole-pool Replace/Add prompt (REQ-FILE-020); a per-row drop
target may be added later if requested.

Alongside the new "Replace…" button, the Measurement Info Box's own tab
for a measurement also gains a "Close" button that closes that specific
measurement through the same flow, and same active-signal warning, as
the File ▸ Close Measurement submenu (REQ-FILE-028/029) — an additional
entry point for an existing capability, not a behavior change
[REQ-FILE-108].

## Applying a Config to Already-Loaded Measurements

Extends "Session Persistence" and "Session Scope: Stripes, Tabs, and
Multi-Measurement" above — resolves the cross-reference to #105 left at
the end of that section. Where opening a `.mvc` file (REQ-FILE-013,
REQ-FILE-094) always loads that session's own recorded measurement
file(s), Apply Config takes only a `.mvc` file's workspace — tabs,
stripes, and signal selections — and re-targets it onto whichever
measurement(s) are already loaded, without opening any file the config
refers to (#105).

A File ▸ Apply Config… menu item, separate from Open… and Save
Workspace/Save Workspace As…, is enabled only once at least one
measurement is already loaded, and opens a file dialog filtered to
`.mvc` files [REQ-FILE-110]. Dropping a `.mvc` file onto the window, or
opening one via Open…, always continues to mean a full session load
that loads that session's own measurement file(s) (REQ-FILE-013); it
never offers to apply onto already-loaded measurements instead, keeping
the two entry points fully separate [REQ-FILE-111].

Before anything is applied, every measurement slot recorded in the
chosen config is shown in one combined dialog, each offering every
currently-loaded measurement (by its live short name) or "None" as its
target; the config's own recorded file name is shown alongside each
slot for context, since that file is never opened [REQ-FILE-112]. Each
slot defaults to the currently-loaded measurement at the same load-order
position, when one exists at that position, or "None" otherwise; every
slot always offers every currently-loaded measurement regardless of
whether another slot currently targets it, and picking one for a slot
that another slot already targets reassigns it to the newer selection,
resetting that other slot to "None" — so a currently-loaded measurement
is never mapped to more than one slot at once, without ever removing a
choice from a slot's own dropdown [REQ-FILE-113]. Canceling this dialog aborts the entire Apply
Config action with nothing changed, the same as canceling the
missing-measurement dialog during a normal multi-measurement session
load (REQ-FILE-097) [REQ-FILE-114].

Once every slot is mapped (or left as "None"), applying the config
replaces every currently open tab with the config's own tabs, stripes,
and signal placement, the same full-workspace replace already used for
a normal session load (REQ-FILE-094) — window geometry, splitter sizes,
and the saved display-name-shortening parameters are applied the same
way a normal session load already applies them too [REQ-FILE-115]. The
current measurement pool itself is never changed by this operation — no
measurement is opened, closed, or reordered, and the pool's current
Primary measurement and Synchronize Measurements state are left exactly
as they were; the config's own saved Primary/Sync fields are not applied
[REQ-FILE-116].

Each saved signal resolves against whichever currently-loaded measurement
its own slot was mapped to, using the same by-name resolution, near-match
detection, ambiguous-match picker, and not-found summary already used for
a normal session load (REQ-FILE-031 through REQ-FILE-036, REQ-FILE-066)
[REQ-FILE-117]. A signal whose slot was left "None" is folded into the
same not-found summary without attempting resolution, the same as a
saved measurement that failed to load during a normal session restore
(REQ-FILE-098) [REQ-FILE-118].

After the config has been applied, a "Save Workspace As…" dialog opens
immediately so the result can be saved as a new workspace file distinct
from the one that was applied; canceling that dialog leaves the applied
workspace live and unsaved rather than undoing the apply, and the
current workspace's save path is not set to the applied config's own
path, so a subsequent plain "Save Workspace" is never able to silently
overwrite the original file with a different measurement mapping
[REQ-FILE-119].
