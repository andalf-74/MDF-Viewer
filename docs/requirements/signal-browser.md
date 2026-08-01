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

## Signal List Structure (Flat Mode)

In Flat mode (REQ-BROWSER-060), when one or more measurements are loaded, every channel across every
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
[REQ-BROWSER-022]. In Tree mode (REQ-BROWSER-070), a channel that matches keeps its
ancestor Channel Group and Measurement nodes visible and expanded even
if their own names don't match, so filtered results stay reachable
within the hierarchy [REQ-BROWSER-023]. Filtering is applied after a
short pause in typing rather than on every keystroke, so it stays
responsive on large channel trees [REQ-BROWSER-024]. In Tree mode,
clearing the filter returns the tree to its default expand state
(REQ-BROWSER-072) rather than leaving branches expanded from the
search [REQ-BROWSER-025].

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

In Flat mode, when more than one measurement is loaded (`file-handling.md`
"Multiple Measurements"), every channel in the flat list (REQ-BROWSER-010)
is prefixed with its measurement's short name (`file-handling.md`
REQ-FILE-027) in brackets, e.g. `[M1] Drehzahl`, so identically-named
channels from different measurements stay distinguishable; with exactly
one measurement loaded, no prefix is shown [REQ-BROWSER-050]. In Flat
mode, the list's alphabetical sort (REQ-BROWSER-010) is keyed on the
channel name itself, not the prefix, so identically-named channels from
different measurements land adjacent to each other in the list
[REQ-BROWSER-051]. In Flat mode, a measurement filter above the list
lets the user narrow it to "All" or one specific loaded measurement; it
is shown only when more than one measurement is loaded, and defaults to
"All" [REQ-BROWSER-052]. In Flat mode, the text filter (REQ-BROWSER-020)
and the measurement filter (REQ-BROWSER-052) compose: typing a search
term narrows further within whichever measurement(s) the measurement
filter currently selects, rather than one control overriding the other
[REQ-BROWSER-053]. An add-signal request always adds the specific
channel shown in its row, from that row's own measurement, even when
another row with the same channel name exists for a different
measurement, regardless of view mode [REQ-BROWSER-054].

## View Mode Selection

The user can choose how the Signal Browser displays loaded channels via
a setting in Preferences → Signals: Flat mode (REQ-BROWSER-010), a
single alphabetical list across all measurements, or Tree mode
(REQ-BROWSER-070), a hierarchy grouped by measurement and channel group
[REQ-BROWSER-060]. The view-mode setting is a global, user-level
preference that applies the same way regardless of which workspace tab
or measurement is active, and is not saved as part of a workspace's
`.mvc` file [REQ-BROWSER-061]. Flat mode is the default view mode for a
fresh installation and for any existing settings that predate this
setting, so the Signal Browser's appearance does not change for an
existing user unless they explicitly switch to Tree mode
[REQ-BROWSER-062]. Changing the view mode in Preferences and confirming
with OK immediately rebuilds the Signal Browser's contents in the newly
selected mode, without requiring the application to restart
[REQ-BROWSER-063].

## Tree Structure (Tree Mode)

In Tree mode, every loaded measurement is shown as its own top-level
node, with that measurement's channel groups as child nodes and each
group's channels as leaf nodes, reflecting the same channel hierarchy
read from the file (`mdf-support.md` REQ-MDF-020) that Flat mode instead
flattens into tooltips (REQ-BROWSER-013) [REQ-BROWSER-070]. Measurement
nodes appear in the order their measurements were loaded, and
channel-group and channel nodes within a measurement appear in the order
reported by the file's own channel hierarchy, rather than being
re-sorted alphabetically like Flat mode's list (REQ-BROWSER-051)
[REQ-BROWSER-071]. A measurement node starts expanded and its
channel-group child nodes start collapsed, so a freshly built or
freshly switched-to tree is scannable rather than immediately showing
every channel at once [REQ-BROWSER-072]. A measurement node's own label
carries that measurement's short name (`file-handling.md` REQ-FILE-027)
and, for a virtual measurement, its visual marker
(`virtual-measurements.md` REQ-VMEAS-210); channel and channel-group
labels underneath do not repeat it [REQ-BROWSER-073]. Only channel
(leaf) nodes are selectable, and only a channel node can be dragged or
added via the "Add Signal" action (REQ-BROWSER-031) — a Channel Group or
Measurement node exists purely to organize the hierarchy and cannot be
selected to add its descendant channels in bulk [REQ-BROWSER-074]. The
measurement filter (REQ-BROWSER-052) is not shown in Tree mode, since
collapsing a measurement's own node already narrows the view to the
others [REQ-BROWSER-075].

## Copy Signal Names (#163)

The Ctrl+C keyboard shortcut copies the raw channel names (not the
on-screen display name, and not any measurement-disambiguation prefix)
of the currently selected channel(s) to the system clipboard, one per
line [REQ-BROWSER-080]. Ctrl+C acts only when at least one channel is
selected [REQ-BROWSER-081]. A status bar message reports how many names
were copied [REQ-BROWSER-082].
