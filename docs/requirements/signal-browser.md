# Requirements: Signal Browser

Part of the `docs/requirements/` collection (see CLAUDE.md's "Requirements
Workflow" for conventions and ID scheme). This file covers browsing,
filtering, and requesting to add channels discovered per `mdf-support.md`
— i.e. the behavior of the panel that turns a channel hierarchy into
selectable, addable signals.

**Out of scope here:** what a channel hierarchy contains and how it's
read from the file (`mdf-support.md`); what happens to a signal once it
is actually added to the plot (active-signal display, colors, axes — a
future `plotting.md`); exact widget/panel layout (`docs/ui.md`).

---

## Signal List Structure

When one or more measurements are loaded, every channel across every
channel group in every loaded measurement (per `mdf-support.md`
REQ-MDF-020) is shown in the browser as a single flat list, sorted
alphabetically by channel name — none are hidden or omitted at load time
[REQ-BROWSER-010]. Channel-group membership is not used to organize the
list — there are no group nodes, collapsible or otherwise; every row is
an individually selectable/addable channel [REQ-BROWSER-011]. Replacing
the loaded measurement(s) (`file-handling.md` REQ-FILE-021) rebuilds the
flat list from scratch; adding a measurement (REQ-FILE-022) appends its
channels into the existing list — either way, any active text filter is
cleared, so the currently available channel set is immediately visible
[REQ-BROWSER-012]. The channel group a row belongs to, and any other
per-channel metadata not otherwise shown, is available as a tooltip on
hover, even though it plays no role in organizing the list
[REQ-BROWSER-013].

## Filtering

The user can narrow the visible channels by typing into a filter field
[REQ-BROWSER-020]. Filtering is case-insensitive [REQ-BROWSER-021] and
supports `*`/`?` wildcard matching when either character is present in
the filter text, otherwise it matches as a plain substring
[REQ-BROWSER-022]. A channel that matches keeps its parent channel group
visible even if the group name itself doesn't match, so filtered results
stay navigable by group [REQ-BROWSER-023]. Filtering is applied after a
short pause in typing rather than on every keystroke, so it stays
responsive on large channel trees [REQ-BROWSER-024].

## Selecting and Requesting to Add Signals

Multiple channels can be selected at once [REQ-BROWSER-030]. A request to
add one or more signals to the plot can be made three ways: double-
clicking a single channel; selecting one or more channels and clicking an
explicit "Add Signal" action; or dragging the current selection out of
the browser [REQ-BROWSER-031]. The add action is only available when at
least one channel is selected [REQ-BROWSER-032].

## Result of an Add-Signal Request

A channel that is already active in the current tab's plot is skipped
rather than added a second time — the same channel can be independently
active in another tab at the same time (see "Main Widget Tabs" in
`plotting.md`) — and the user is told how many (if any) requested
channels were skipped for this reason [REQ-BROWSER-040]. When adding
multiple channels at once, a failure reading one channel's samples is
reported to the user without aborting the remaining requested channels
[REQ-BROWSER-041]. The "already active" check (REQ-BROWSER-040)
considers a channel's specific measurement, not just its name — the
same-named channel from a different measurement is a distinct addable
channel [REQ-BROWSER-042].

## Multiple Measurements

When more than one measurement is loaded (`file-handling.md`
"Multiple Measurements"), every channel in the flat list (REQ-BROWSER-010)
is prefixed with its measurement's short name (`file-handling.md`
REQ-FILE-027) in brackets, e.g. `[M1] Drehzahl`, so identically-named
channels from different measurements stay distinguishable; with exactly
one measurement loaded, no prefix is shown [REQ-BROWSER-050]. The list's
alphabetical sort (REQ-BROWSER-010) is keyed on the channel name itself,
not the prefix, so identically-named channels from different
measurements land adjacent to each other in the list [REQ-BROWSER-051].
A measurement filter above the list lets the user narrow it to "All" or
one specific loaded measurement; it is shown only when more than one
measurement is loaded, and defaults to "All" [REQ-BROWSER-052]. The text
filter (REQ-BROWSER-020) and the measurement filter (REQ-BROWSER-052)
compose: typing a search term narrows further within whichever
measurement(s) the measurement filter currently selects, rather than one
control overriding the other [REQ-BROWSER-053]. An add-signal request
always adds the specific channel shown in its row, from that row's own
measurement, even when another row with the same channel name exists for
a different measurement [REQ-BROWSER-054].
