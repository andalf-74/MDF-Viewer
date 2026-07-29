# Requirements: Label Lists

Part of the `docs/requirements/` collection — the single source of truth for
*what* the application does. This file covers bulk import and export of
signal selections via the group-based, line-oriented plain-text label list
format used by Vector CANape ("`.lab`" files) — see #143.

**Out of scope here:** how any of this is presented on screen (see
`docs/ui.md`) and how it is implemented across Model/View/Controller (see
`docs/architecture.md`). A requirement below should read the same regardless
of which layer ends up owning it.

**Conventions:** requirements are numbered `REQ-LABEL-NNN`, grouped by
sub-topic with gaps left for insertion. Each testable statement is tagged
inline so it can be cited from an issue or a test via
`@pytest.mark.requirement("REQ-LABEL-NNN")`.

---

## File Format

A valid file's first line is exactly `[Measurement]`; an import is rejected
with a specific "this doesn't look like a Label List file" error if the
first line does not match exactly [REQ-LABEL-010]. Every subsequent line
whose entire content is wrapped in a single leading `[` and trailing `]`
starts a new named group, using everything between those two characters as
the group's name verbatim, including any further `[`/`]` characters nested
inside it [REQ-LABEL-011]. Within a group, every line that is not blank and
does not itself open a new group is a candidate signal name belonging to
that group, one per line [REQ-LABEL-012]. A blank line or the start of the
next group ends the current group's list of candidate signal names
[REQ-LABEL-013].

## Encoding

An import first attempts to decode the file as UTF-8, and falls back to
decoding it as Windows-1252 if that fails, so that legacy CANape-exported
files are still readable [REQ-LABEL-020]. Exporting a label list always
writes the file as UTF-8 [REQ-LABEL-021].

(The Windows-1252 fallback path is a candidate for a logged event once #126
Logging exists; no such logging exists yet, so this is noted here rather
than tagged as a requirement.)

## Import — Matching Candidate Signals

Each candidate signal name is looked up by an exact match against the
channel names of every currently loaded measurement, not only the Primary
measurement [REQ-LABEL-030]. A candidate name that matches a channel in
more than one currently loaded measurement is added from every measurement
it matches in, not just one [REQ-LABEL-031]. A candidate name that matches
no channel in any currently loaded measurement is not added, and is
recorded as not found for the post-import summary [REQ-LABEL-032]. A
candidate name whose match is found but fails to load (e.g. a corrupt
block, or non-numeric samples) is treated the same as not found for the
post-import summary [REQ-LABEL-033].

## Import — Stripe Creation

Import creates one new Plot Stripe per group in the file, added to the
currently active tab, named after that group instead of the default
"Stripe N" auto-naming (`plotting.md` REQ-PLOT-291) [REQ-LABEL-040]. A
matched candidate that is already an active signal elsewhere in the tab is
not added again; it is recorded as already active for the post-import
summary instead [REQ-LABEL-041]. A group is only given a stripe if at least
one of its candidates was newly added as a result; a group whose every
candidate was either not found or already active produces no stripe
[REQ-LABEL-042]. Import never adds matched signals into an existing stripe
that happens to share a group's name; every group always creates a new
stripe [REQ-LABEL-043].

## Import — Result Summary

After import finishes, a summary dialog lists every not-found candidate
name and every already-active candidate name, each in its own separate
list of plain, selectable text [REQ-LABEL-050]. No summary dialog is
shown if the import produced neither a not-found nor an already-active
entry [REQ-LABEL-051].

## Export

Exporting the active tab's signals writes one group per stripe in that tab,
using each stripe's own name as the group name; stripes belonging to any
other open tab are not included [REQ-LABEL-060]. Each active real signal in
an exported stripe is written using its native MDF channel name, not its
on-screen display name [REQ-LABEL-061]. A virtual signal is excluded from
the exported group it would otherwise belong to [REQ-LABEL-062]. A stripe
with no exportable active signals — whether because it has none, or
because its only signals are virtual — produces no group in the exported
file [REQ-LABEL-063].

## Menu Integration

The File menu gains "Import Labels…" and "Export Labels…" entries,
positioned near the existing Save Workspace / Save Workspace As… entries
[REQ-LABEL-070]. Both entries open a standard file dialog filtered to
`*.lab` files [REQ-LABEL-071]. "Import Labels…" is enabled whenever at
least one measurement is loaded [REQ-LABEL-072]. "Export Labels…" is
enabled whenever the active tab has at least one active signal
[REQ-LABEL-073].
