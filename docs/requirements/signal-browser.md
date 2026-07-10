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

## Tree Structure

When a measurement is loaded, every channel group and every channel
within it (per `mdf-support.md` REQ-MDF-020) is shown in the browser —
none are hidden or omitted at load time — and all groups start expanded
[REQ-BROWSER-010]. Only individual channels are selectable/addable
targets; group nodes exist purely for organization and are not
themselves an addable item [REQ-BROWSER-011]. Loading a new measurement
replaces the browser's contents entirely and clears any active filter, so
the new file's full channel set is immediately visible [REQ-BROWSER-012].

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
[REQ-BROWSER-041].

## Multiple Measurements

When more than one measurement is loaded (`file-handling.md`
"Multiple Measurements"), a selector above the channel tree lets the
user pick which loaded measurement's channels the tree currently
displays; with exactly one measurement loaded, no selector is shown and
the tree simply shows that measurement's channels as today
[REQ-BROWSER-050]. Switching the selector replaces the tree's contents
with the selected measurement's channel hierarchy and clears any active
filter, the same as loading a new measurement does today
(REQ-BROWSER-012) [REQ-BROWSER-051]. An add-signal request always adds
the channel from whichever measurement is currently selected in the tree
(REQ-BROWSER-050) [REQ-BROWSER-052].
