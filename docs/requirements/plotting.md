# Requirements: Plotting

Part of the `docs/requirements/` collection (see CLAUDE.md's "Requirements
Workflow" for conventions and ID scheme). This is the largest domain in
the app today: what happens to a signal once it has been added, and how
the user views, selects, zooms, and measures it.

**Out of scope here:** discovering/loading channel data (`mdf-support.md`)
and requesting that a channel be added (`signal-browser.md`); exact
widget/panel/menu layout (`docs/ui.md`); the high-level shape of what a
saved session captures, which is `file-handling.md` REQ-FILE-061 — this
file only adds nuances specific to plotting state that aren't obvious
from that summary.

---

## Curve Rendering

All active signals share a single X (time, seconds) axis: panning or
zooming X moves every signal in lockstep [REQ-PLOT-010]. Each active
signal has its own Y-axis by default, with its own scale, units, and
color [REQ-PLOT-011]. A floating-point signal's Y-axis tick labels are
rounded to a fixed number of significant figures rather than showing raw
floating-point noise [REQ-PLOT-012]. A signal known to hold integer or
discrete values (e.g. a gear or flag channel) gets a Y-axis restricted to
whole-number ticks, with no fractional or duplicate ticks
[REQ-PLOT-013]. A signal with an enum mapping shows its enum text labels
on the Y-axis instead of raw numeric values when that signal's "Y-axis
enum display" option is enabled [REQ-PLOT-014].

## Adding and Removing Active Signals

A channel that is already active is never added a second time
(REQ-BROWSER-040 covers the user-facing consequence of this)
[REQ-PLOT-020]. Each newly added signal is assigned the next color from a
fixed palette, cycling back to the start once the palette is exhausted,
so distinct signals stay visually distinguishable up to the palette size
before colors repeat [REQ-PLOT-021]. A newly added signal defaults to
step-mode rendering if its underlying data type is an integer type, and
to linear interpolation otherwise (see REQ-PLOT-120 for the meaning of
step mode) [REQ-PLOT-022]. Removing a signal that is not currently active
is a no-op [REQ-PLOT-023]. Removing the last remaining member of a Shared
or Linked axis group dissolves that group and gives the removed signal's
former group-mates back independent axes; a group that shrinks to exactly
one remaining member is dissolved the same way [REQ-PLOT-024]. Removing
the signal that is the current single selection clears the selection
[REQ-PLOT-025].

## Y-Axis Grouping: Independent, Shared, and Linked

By default every active signal has its own independent Y-axis
[REQ-PLOT-030]. **Sharing** two or more signals' Y-axes merges them onto
one common axis with one common scale — they are drawn against the exact
same numeric range because there is only one axis; the shared axis is
shown in a neutral color rather than any one member's signal color
[REQ-PLOT-031]. **Linking** two or more signals' Y-axes keeps each
signal's own independent axis (own scale, own color, own units) but
forces every linked signal's Y range to match whenever any one of them is
panned or zoomed [REQ-PLOT-032]. A signal can be in at most one of
Sharing or Linking at a time — requesting the other relationship for a
signal that's already in one is rejected [REQ-PLOT-033]. Sharing or
linking requires at least two target signals [REQ-PLOT-034]. A signal can
be removed from its Shared or Linked group without affecting the other
members (beyond the single-member auto-dissolve in REQ-PLOT-024)
[REQ-PLOT-035]. Shared and Linked group membership is part of a saved
session, keyed by signal name; a session member that no longer resolves
by name on restore is dropped from the group rather than failing the
whole restore [REQ-PLOT-036].

## Signal Selection and Z-Order

Clicking on a curve (or, for a marker-displaying signal, near one of its
markers) selects that signal; a click that hits nothing passes through
without changing the selection or blocking panning [REQ-PLOT-040]. When
more than one signal's rendering overlaps at the same screen point, the
topmost one by Z-order is selected [REQ-PLOT-041]. Z-order between
unselected signals is controlled by a preference: either the top row of
the Active Signals Table renders on top, or the bottom row does
[REQ-PLOT-042]. Regardless of that preference, the currently selected
signal(s) are always drawn above every unselected signal
[REQ-PLOT-043]. The selected signal's line renders thicker than its
configured width by a fixed, user-configurable amount, so the current
selection is visually obvious even at the signal's normal color and
style [REQ-PLOT-044]. Enabling "show only selected Y-axis" hides every
Y-axis except those belonging to a currently selected signal (the curves
themselves stay visible; only their axis columns are hidden) — with
nothing selected, or the option disabled, every axis is shown
[REQ-PLOT-045]. For a Shared axis, it stays visible under this option if
any member of that group is selected, not only the exact one that was
clicked [REQ-PLOT-046].

## Panning and Zooming

Scrolling over the plot's interior or its shared X-axis zooms X only;
scrolling while over a specific signal's own Y-axis zooms that signal's Y
only [REQ-PLOT-050]. Dragging inside the plot interior pans X only — an
individual signal's Y range can only be panned by dragging directly on
that signal's own Y-axis [REQ-PLOT-051]. Drawing a rectangle (box zoom)
zooms X to the rectangle's X extent and applies the rectangle's Y extent
to every active signal's Y range at once, regardless of which signal's
axis area the rectangle was drawn over [REQ-PLOT-052]. "Zoom to Fit"
rescales X to the full time span of all active signals (with a small
padding margin) and rescales every signal's Y independently to its own
full data range; it is a no-op with no active signals [REQ-PLOT-053].
"Zoom Y to View" rescales each signal's Y range to fit only the data
currently visible within the current X range, rather than the signal's
full data range; a signal with no data points inside the current X range
is left unchanged [REQ-PLOT-054]. "Swimlanes" arranges every signal (a
Shared group counting as one) into an equal-height horizontal band
spanning the plot's full Y extent, sized to that signal's visible data
range [REQ-PLOT-055]. A signal whose visible Y data has no range (a flat
line) is given a small fixed span rather than a degenerate zero-height
view in any of the above zoom actions [REQ-PLOT-056].

## Zoom History (Undo/Redo)

Every explicit zoom action (Zoom to Fit, Zoom Y to View, Swimlanes, box
zoom, zoom to cursors, etc.) is one undo step [REQ-PLOT-060]. A
continuous zoom/pan gesture (mouse-wheel zooming, click-drag panning) is
treated as a single undo step for the whole gesture, captured once the
gesture settles after a brief pause, not once per intermediate frame
[REQ-PLOT-061]. The number of undo steps retained is configurable (at
least 1); once the limit is reached, the oldest retained step is dropped
to make room for a new one [REQ-PLOT-062]. Performing any new zoom action
after an undo clears the redo history [REQ-PLOT-063]. Undo and redo are
no-ops when their respective history is empty [REQ-PLOT-064]. Loading a
new measurement file clears both the undo and redo history
[REQ-PLOT-065].

## Cursor Modes and Positioning

Cursors have three states: hidden, one cursor shown, or two cursors shown
— there is never more than two at once [REQ-PLOT-070]. A single toggle
cycles hidden → one → two → hidden; two additional actions toggle cursor
1 and cursor 2 independently on/off [REQ-PLOT-071]. Cursors can be
labeled either by fixed position ("Cursor 1"/"Cursor 2", left-to-right
order irrelevant) or dynamically by screen position ("Cursor L"/"Cursor
R", reassigned to track whichever cursor is currently further left) —
which scheme is active is a user preference, and each scheme has its own
independent pair of configurable cursor colors [REQ-PLOT-072]. Whether
cursor positions are remembered across a hide → show cycle is a user
preference; when not persistent (or the first time cursors are shown
after loading a file), showing cursors places them at fixed positions
relative to the current view (roughly a quarter and three-quarters of
the way across) rather than reusing old positions [REQ-PLOT-073].
Loading a new measurement file always resets cursors to hidden, requiring
the user to re-show them, regardless of the persistence preference
[REQ-PLOT-074].

## Cursor Value Labels and Interpolation

With one cursor shown, every active signal displays its value at that
cursor [REQ-PLOT-080]. With two cursors shown, only the cursor currently
nearest the mouse pointer shows value labels, so the two cursors' labels
don't clutter the view simultaneously [REQ-PLOT-081]. A signal's value at
a cursor position outside that signal's own recorded time range is not
shown (no extrapolation) rather than displaying a stale or fabricated
value [REQ-PLOT-082]. Between two recorded samples, a signal's value at a
cursor position is linearly interpolated by default, or held at the
preceding sample's value if that signal's step-mode display is enabled
[REQ-PLOT-083]. A signal with an enum mapping shows its enum text label
at the cursor (with the raw value alongside) when that signal's "cursor
enum display" option is enabled, falling back to the plain numeric value
otherwise [REQ-PLOT-084].

## Arrow-Key Cursor Stepping

The arrow keys move the most recently interacted-with cursor by a
configurable step, in one of three units: a number of samples of a
reference signal, a number of screen pixels, or an amount of time
[REQ-PLOT-090]. The reference signal for sample-based stepping is the
currently selected signal, or the first active signal if none is
selected; stepping is a no-op if there is no signal to reference
[REQ-PLOT-091]. Stepping never moves a cursor beyond the reference
signal's (or, for pixel/time stepping without a reference, the current
view's) time range — it clamps at the boundary rather than moving out of
range [REQ-PLOT-092]. Stepping is a no-op if no cursor is currently the
"active" one to move (e.g. two cursors are shown but neither has been
interacted with yet) [REQ-PLOT-093].

## Delta-Time Line

A delta-time indicator, showing the time difference between the two
cursors, is available only while both cursors are shown [REQ-PLOT-100].
Whether it is drawn in the plot at all is a separate user preference from
whether two cursors are shown; when hidden from the plot, the
corresponding column in the Active Signals Table still shows and updates
live [REQ-PLOT-101]. The delta-time line's vertical position is
independently draggable and is remembered once the user has moved it,
defaulting to a fixed position near the top of the view the first time
it is shown [REQ-PLOT-102]. Its horizontal position always tracks the
midpoint between the two cursors' current positions, and its label
updates live as either cursor moves [REQ-PLOT-103]. Per-signal delta
values (shown in the Active Signals Table) are that signal's value at
cursor 2 minus its value at cursor 1, and are left blank if either
cursor's value can't be determined for that signal [REQ-PLOT-104].

## Off-Screen Cursor Indicators

When a cursor's position falls outside the currently visible time range,
an indicator is pinned to the corresponding edge of the plot in that
cursor's color, rather than the cursor simply disappearing from view
[REQ-PLOT-110]. Clicking that indicator moves ("fetches") the cursor to
the clicked position rather than only scrolling the view to reveal it
[REQ-PLOT-111]. The delta-time line has the same off-screen indicator
behavior when its vertical position is out of the visible Y range, shown
only while the delta-time line itself is enabled [REQ-PLOT-112]. All
off-screen indicators are hidden whenever cursors are hidden
[REQ-PLOT-113].

## Active Signal Display Properties

Each active signal has independently configurable: color; display mode
(line only, line with markers, or markers only); marker shape (from a
fixed set of shapes); line width (within a fixed numeric range); line
style (from a fixed set of styles); and step-mode on/off [REQ-PLOT-120].
The marker shape control is not applicable (and disabled) when display
mode is "line only"; line width and line style are not applicable when
display mode is "markers only" [REQ-PLOT-121]. Setting a
property while multiple signals are selected applies it to every selected
signal at once [REQ-PLOT-122].

## Enum Display

A signal with an enum (value-to-text) mapping has three independent
toggles controlling where its enum labels are shown instead of raw
numeric values: in the Active Signals Table's value column, in cursor
value labels, and on its Y-axis — each can be turned on or off separately
per signal [REQ-PLOT-130]. These toggles are only available for a signal
that actually has an enum mapping [REQ-PLOT-131].

## Active Signals Table Interaction

Multiple signals can be selected in the table at once, and the display
property controls (REQ-PLOT-120) show only the values that are identical
across the current multi-selection, leaving mismatched fields blank
rather than showing an arbitrary member's value [REQ-PLOT-140]. Removing
signals is available whenever at least one is selected, via an explicit
action or a keyboard shortcut, and removes every currently selected
signal [REQ-PLOT-141]. Reordering signals in the table (by dragging a
row) changes their Z-order accordingly [REQ-PLOT-142]. Dragging channels
from the Signal Browser onto the table adds them the same way as the
browser's own add actions [REQ-PLOT-143].

## Signal Info Box

Selecting exactly one signal shows its descriptive information: name,
and — only when the underlying data provides them — unit, data type,
sample count, minimum and maximum values, comment, and any other
file-provided metadata [REQ-PLOT-150]. A signal's sampling raster is
shown as a time interval when it has a fixed raster, or explicitly marked
as variable when it does not, and is only shown at all for signals with
at least two samples [REQ-PLOT-151]. Selecting more than one signal, or
none, does not show single-signal descriptive information
[REQ-PLOT-152].

## Display Name Shortening

A global preference can shorten displayed signal names by splitting each
name on a configured separator and keeping only a configured number of
segments from either the start or the end [REQ-PLOT-160]. A name that
does not contain the configured separator, or the rule being disabled,
leaves that signal's displayed name unchanged [REQ-PLOT-161]. This
setting affects only how a signal's name is displayed — the underlying
channel name used to locate and reload the signal is unaffected
[REQ-PLOT-162].

## Session Persistence Notes

Beyond the summary in `file-handling.md` REQ-FILE-061, restoring a saved
session's display-name-shortening parameters (separator, direction,
segment count) also becomes the new global default for that preference
going forward — but whether the shortening rule is enabled at all remains
governed solely by the global preference, not saved per session
[REQ-PLOT-170]. A signal's current Y-axis grid on/off state is not part
of a saved session [REQ-PLOT-171].
