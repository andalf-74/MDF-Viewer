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
is a no-op [REQ-PLOT-023]. Removing the last remaining member of a Merged
or Synced axis group dissolves that group and gives the removed signal's
former group-mates back independent axes; a group that shrinks to exactly
one remaining member is dissolved the same way [REQ-PLOT-024]. Removing
the signal that is the current single selection clears the selection
[REQ-PLOT-025].

## Y-Axis Grouping: Independent, Merged, and Synced

By default every active signal has its own independent Y-axis
[REQ-PLOT-030]. **Merging** two or more signals' Y-axes combines them
onto one common axis with one common scale — they are drawn against the
exact same numeric range because there is only one axis; the merged axis
is shown in a neutral color rather than any one member's signal color
[REQ-PLOT-031]. **Syncing** two or more signals' Y-axes keeps each
signal's own independent axis (own scale, own color, own units) but
forces every synced signal's Y range to match whenever any one of them is
panned or zoomed [REQ-PLOT-032]. A signal can be in at most one of
Merging or Syncing at a time — requesting the other relationship for a
signal that's already in one is rejected [REQ-PLOT-033]. Merging or
syncing requires at least two target signals [REQ-PLOT-034]. A signal can
be removed from its Merged or Synced group without affecting the other
members (beyond the single-member auto-dissolve in REQ-PLOT-024)
[REQ-PLOT-035]. Merged and Synced group membership is part of a saved
session, keyed by signal name; a session member that no longer resolves
by name on restore is dropped from the group rather than failing the
whole restore [REQ-PLOT-036]. The context-menu actions that request these
relationships are labeled "Merge Y-Axis" and "Sync Y-Axis"
[REQ-PLOT-037]. A Merged or Synced group's members must all belong to the
same plot stripe (see "Plot Stripes" below); merging or syncing is only
offered between signals that already share a stripe [REQ-PLOT-038].

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
[REQ-PLOT-045]. For a Merged axis, it stays visible under this option if
any member of that group is selected, not only the exact one that was
clicked [REQ-PLOT-046]. Signals in different plot stripes can be selected
simultaneously; selecting a signal in one stripe does not clear the
selection in another stripe [REQ-PLOT-047]. The "show only selected
Y-axis" preference is a single global setting; when enabled, each stripe
independently shows only the axes belonging to its own selected
signal(s), or all of its axes if nothing in that stripe is selected
[REQ-PLOT-048].

## Panning and Zooming

Scrolling over the plot's interior or its shared X-axis zooms X only;
scrolling while over a specific signal's own Y-axis zooms that signal's Y
only [REQ-PLOT-050]. Dragging inside the plot interior pans X only — an
individual signal's Y range can only be panned by dragging directly on
that signal's own Y-axis [REQ-PLOT-051]. Drawing a rectangle (box zoom)
zooms the shared X-axis to the rectangle's X extent across every stripe,
and applies the rectangle's Y extent only to the signals in the stripe
the rectangle was drawn in [REQ-PLOT-052]. "Zoom to Fit" rescales the
shared X-axis to the full time span of all active signals across every
stripe (with a small padding margin); its Y-axis rescaling follows the
All Stripes/Active Stripe scope described in REQ-PLOT-057, and it is a
no-op with no active signals [REQ-PLOT-053]. "Zoom Y to View" rescales Y
to fit only the data currently visible within the current X range, rather
than each signal's full data range, following the same All
Stripes/Active Stripe scope as REQ-PLOT-057; a signal with no data points
inside the current X range is left unchanged [REQ-PLOT-054]. "Swimlanes"
arranges every signal in the active stripe (a Merged group counting as
one) into an equal-height horizontal band spanning that stripe's full Y
extent, sized to that signal's visible data range [REQ-PLOT-055]. A
signal whose visible Y data has no range (a flat line) is given a small
fixed span rather than a degenerate zero-height view in any of the above
zoom actions [REQ-PLOT-056]. A single "All Stripes / Active Stripe only"
toggle governs whether "Zoom to Fit" (REQ-PLOT-053) and "Zoom Y to View"
(REQ-PLOT-054) rescale Y for every stripe or only the currently active
stripe; it does not affect Swimlanes, which always scopes to the active
stripe, or box zoom, which always scopes to the stripe the rectangle was
drawn in [REQ-PLOT-057].

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
[REQ-PLOT-065]. Zoom actions performed in any stripe, and at any All
Stripes/Active Stripe scope, share one undo/redo history for the whole
plot area rather than each stripe keeping its own independent history
[REQ-PLOT-066].

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
cursor's value can't be determined for that signal [REQ-PLOT-104]. With
multiple stripes, the delta-time line is shown only in the currently
active stripe; each stripe remembers its own vertical position for it
independently (REQ-PLOT-102), so switching the active stripe restores
that stripe's own remembered position rather than sharing one position
across stripes [REQ-PLOT-105].

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
from the Signal Browser onto the Active Signals Table adds them the same
way as the browser's own add actions, targeting whichever stripe's
segment received the drop (REQ-PLOT-277) [REQ-PLOT-143].

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

## Info/Properties Drawer

The Signal Info Box (REQ-PLOT-150 through REQ-PLOT-152) is presented in a
dedicated panel to the right of the Active Signals Table, spanning the
full height of the content area independently of the table's own height
[REQ-PLOT-220]. The panel can be pinned, keeping it permanently docked as
a column beside the Active Signals Table, or unpinned, in which case it
stays hidden until revealed [REQ-PLOT-221]. While unpinned, moving the
pointer near the right edge of the window slides the panel into view as
an overlay, and moving the pointer away slides it back out of view
[REQ-PLOT-222]. Revealing or hiding the unpinned panel happens only
through hovering or the pin toggle, never automatically in response to a
signal selection change [REQ-PLOT-223]. A newly created session (no
saved workspace) starts with the panel pinned at a default width of 260
pixels [REQ-PLOT-224]. The panel's pinned/unpinned state and width are
saved to and restored from `.mvc` session files [REQ-PLOT-225].

Within the panel, the Info view and the Properties view are stacked
vertically rather than presented as tabs, each under its own section
label, and divided by a splitter the user can drag to reallocate space
between the two [REQ-PLOT-226]. The Info/Properties
splitter position is saved to and restored from `.mvc` session files
[REQ-PLOT-227]. When no signal is selected, the Info section shows its
"No signal selected" placeholder (REQ-PLOT-152) and the Properties
section is disabled, matching today's single-selection content rules
without requiring a tab switch to see either state [REQ-PLOT-228]. The
panel is a single instance shared across all stripes, showing
information for whichever signal was most recently selected regardless
of which stripe's Active Signals Table the selection came from
[REQ-PLOT-229].

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
[REQ-PLOT-170].

## Plot Stripes

Introduced to let signals of very different units/scales be viewed
without crowding a single Y-axis area (#17/#97). A stripe is a horizontal
region of the plot area; the sections below cover its structure, its
lifecycle, and how signals are assigned to one.

### Structure and Layout

The plot area is composed of one or more horizontal stripes stacked
vertically, sharing a single X-axis and cursors while each stripe keeps
its own independent Y-axes [REQ-PLOT-180]. Only the bottom-most stripe
displays X-axis time-tick labels; every other stripe hides its own
X-axis labels, since the X value at any horizontal position is identical
across all stripes [REQ-PLOT-181]. Cursor lines are drawn once per
stripe, with every stripe's copy kept at the same X position, so they
read as one continuous indicator spanning all stripes [REQ-PLOT-182].
Unlike cursor lines, the delta-time line is not duplicated across every
stripe — it exists once per stripe (each remembering its own position)
but is only ever shown in the currently active stripe; see REQ-PLOT-105
for the full rule. The delta-time line's off-screen edge indicator
(REQ-PLOT-112) depends on the active stripe's own currently visible Y
range; the cursor lines' own off-screen indicators (REQ-PLOT-110) depend
only on the shared X range and are therefore identical across all
stripes [REQ-PLOT-183]. Stripe height is user-resizable by dragging the
divider between two adjacent stripes [REQ-PLOT-184]. Loading a file with
no saved workspace starts with a single stripe [REQ-PLOT-185]. At least
one stripe always exists; the action to delete the last remaining stripe
is unavailable [REQ-PLOT-186].

### Creating and Deleting Stripes

A new stripe can be created via a "Create new Stripe" action on the plot
area's context menu [REQ-PLOT-190]. A new stripe can also be created
directly from a signal via a "Move to new Stripe" action, which creates
the stripe and moves that signal into it in one step [REQ-PLOT-191].
Creating a new stripe redistributes height equally across all stripes,
existing and new [REQ-PLOT-192]. Deleting an empty stripe removes it
immediately without confirmation [REQ-PLOT-193]. Deleting a stripe that
still contains signals shows a warning offering "Delete anyway" — which
removes every signal the stripe contains, then the stripe itself — or
"Cancel" [REQ-PLOT-194]. There is no maximum number of stripes
[REQ-PLOT-195]. A new stripe can also be created via a "New Stripe" action
in the File menu, added to the currently active tab regardless of which
plot-area context menu was last used (#112) [REQ-PLOT-196].

### Signal Assignment to Stripes

A signal can be dragged from the Signal Browser and dropped onto a
specific stripe, which highlights as the drop target while the drag is
over it [REQ-PLOT-200]. Double-clicking a signal in the Signal Browser
adds it to the currently active stripe [REQ-PLOT-201]. A signal can be
moved from its current stripe to a different existing stripe via a
context-menu submenu listing the available stripes [REQ-PLOT-202].
Moving a signal between stripes relocates it; it is never duplicated
into both the source and destination stripe [REQ-PLOT-203].

### Active Stripe / Focus

The active stripe is indicated by a small colored marker on its left
edge [REQ-PLOT-210]. Clicking anywhere inside a stripe makes it the
active stripe [REQ-PLOT-211]. Loading a file with no saved workspace
makes the top stripe active by default [REQ-PLOT-212].

### Per-Stripe Active Signals Table

The Active Signals Table is divided into one segment per stripe, each
positioned directly beside its stripe and showing only that stripe's
active signals [REQ-PLOT-270]. Every segment shares the same column
structure and column widths, so resizing a column applies to every
segment at once [REQ-PLOT-271]. A single header row above all segments
stays fixed at the top of the Active Signals Table area, regardless of
stripe count or sizing [REQ-PLOT-272]. Segments are stacked top-to-bottom
in the same order as their stripes, with a divider between adjacent
segments aligned to the boundary between those stripes in the plot
[REQ-PLOT-273]. A segment's height always matches its stripe's height:
dragging the divider between two stripes in the plot resizes their two
segments in lockstep, and dragging the corresponding divider in the
Active Signals Table resizes the two stripes in lockstep [REQ-PLOT-274].
When a segment holds more rows than fit in its current height, that
segment scrolls independently within its own boundary, leaving the
header and every other segment unaffected [REQ-PLOT-275]. A multi-row
selection can span more than one segment [REQ-PLOT-276]. Dropping
signals from the Signal Browser onto a specific segment adds them to
that segment's stripe, the same way dropping directly onto the stripe in
the plot area does (REQ-PLOT-200) [REQ-PLOT-277]. Clicking anywhere
inside a segment makes its stripe the active stripe, the same as
clicking inside the stripe itself (REQ-PLOT-211) [REQ-PLOT-278].
Dragging a row from one segment into another moves that signal to the
target segment's stripe, inserted at the row position nearest the drop
location, in addition to the existing "Move to Stripe" and "Move to new
Stripe" context-menu actions (REQ-PLOT-202) [REQ-PLOT-279]. The Remove
Signal and Remove All controls remain a single set beneath the whole
Active Signals Table area rather than one pair per segment; Remove All
removes every active signal across every stripe in the tab
[REQ-PLOT-280].

### Stripe Naming

Each stripe has a name, shown as a label on its Active Signals Table
segment [REQ-PLOT-290]. A newly created stripe is auto-named "Stripe N",
where N is a creation-order counter scoped to that stripe's tab, never
reused or renumbered when stripes are reordered or deleted
[REQ-PLOT-291]. A stripe can be renamed by double-clicking its label in
the Active Signals Table segment, the same interaction used to rename a
tab (REQ-PLOT-242) [REQ-PLOT-292]. The "Move to Stripe" context-menu
submenu (REQ-PLOT-202) lists each stripe by its current name rather than
its position [REQ-PLOT-293]. Stripe names are not saved to or restored
from `.mvc` session files; a reloaded session's stripes revert to their
default creation-order names [REQ-PLOT-294].

## Main Widget Tabs

Introduced to let the user build independent workspaces on the same
measurement (#17/#99). The entire plot area — every stripe and its
per-stripe Active Signal Table — lives within a tab; multiple tabs hold
different signal selections and stripe layouts side by side
[REQ-PLOT-230]. Everything scoped to the plot area is independent per
tab: signal selection and the active-signal set, stripe layout and
sizes, the active stripe, cursor state and positions, the current
zoom/pan view, the zoom undo/redo history (REQ-PLOT-060–066), and the
All Stripes/Active Stripe zoom-scope toggle (REQ-PLOT-057)
[REQ-PLOT-231]. The Signal Browser, Measurement Info Box, and the
Info/Properties drawer (REQ-PLOT-220) remain single shared instances
outside the plot area, identical regardless of which tab is active
[REQ-PLOT-232]. The Info/Properties drawer shows each tab's own
most-recently-selected signal, restoring that tab's last selection when
the user switches back to it, rather than showing whichever tab most
recently had a selection anywhere in the app [REQ-PLOT-233]. A channel
can be independently active in more than one tab at the same time; see
REQ-BROWSER-040 for the resulting add-signal behavior [REQ-PLOT-234].

### Tab Lifecycle

A new tab can be created via a "+" control at the end of the tab bar or
a File-menu action; a newly created tab always starts as a plot-stripe
workspace [REQ-PLOT-240]. A newly created tab starts with a single
default stripe and no active signals, the same starting state as
loading a file with no saved workspace [REQ-PLOT-241]. New tabs are
auto-named "Tab 1", "Tab 2", etc. in creation order; a tab can be
renamed by double-clicking its label or via a context-menu "Rename"
action [REQ-PLOT-242]. Tabs can be reordered by dragging a tab to a new
position in the tab bar; order is cosmetic only and has no functional
effect [REQ-PLOT-243]. Ctrl+Tab and Ctrl+Shift+Tab cycle to the next
and previous tab respectively [REQ-PLOT-244].

### Closing Tabs

Each tab shows a close ("×") control, in addition to a context-menu
"Close" action [REQ-PLOT-250]. Closing a tab with no active signals in
any of its stripes closes immediately with no confirmation
[REQ-PLOT-251]. Closing a tab that has at least one active signal in any
of its stripes shows a warning offering "Close anyway" or "Cancel",
mirroring the stripe-deletion warning (REQ-PLOT-194) [REQ-PLOT-252].
Closing a tab activates the tab immediately to its left, or the next
remaining tab if the closed tab was the first [REQ-PLOT-253]. There is
no maximum number of tabs, and closing the last remaining tab is
permitted; the app then shows an empty-state placeholder with a "New
Tab" action rather than auto-creating a replacement tab [REQ-PLOT-254].

### Loading a New Measurement File

Replacing every currently loaded measurement (`file-handling.md`
REQ-FILE-021) preserves the existing tab structure — tabs, their names,
and their stripe layouts; within each tab, signals are re-resolved by
name against the newly opened file(s) the same way single-tab signal
restore already works today, and each tab's zoom, cursor, and undo/redo
state resets independently the same way it already does for a single
plot area [REQ-PLOT-260]. Adding one or more measurements
(`file-handling.md` REQ-FILE-022) instead leaves every existing tab's
signals, zoom, cursor, and undo/redo state completely untouched; only the
newly added measurement's own X-axis row (see "Multiple Measurements"
below) and channel tree become available [REQ-PLOT-261].

## Multiple Measurements

Introduced to let several MDF files be viewed and visually aligned
together (#17/#101). Loading, adding, replacing, and closing individual
measurements is `file-handling.md`'s domain (REQ-FILE-010–028); this
section covers how multiple loaded measurements are represented and
interacted with inside the plot area itself.

### X-Axis Per Measurement

Each loaded measurement gets its own X-axis row, labeled with that
measurement's file-derived label (REQ-FILE-027), stacked below the
bottom-most stripe [REQ-PLOT-300]. Only the bottom-most stripe's area
shows these X-axis rows; every other stripe shows none, the same way a
single stripe's X-axis was hidden before multi-measurement support
(REQ-PLOT-181, generalized to the full stack of per-measurement rows)
[REQ-PLOT-301]. Every measurement is drawn using one shared X-zoom (scale
and range): zooming X, however triggered, always applies to every
measurement in lockstep, with no per-measurement zoom factor
[REQ-PLOT-302]. Dragging inside a stripe's interior pans every
measurement's X in lockstep, extending REQ-PLOT-051 to multiple
measurements; dragging directly on one measurement's own X-axis row
instead pans only that measurement's individual time offset, shifting
its curves relative to every other measurement without changing the
shared zoom/range [REQ-PLOT-303]. A measurement's offset is a signed time
value added to its own recorded timestamps before display; it defaults
to zero on load (REQ-FILE-026) and is not bounded — panning it can shift
its curves arbitrarily far from every other measurement's [REQ-PLOT-304].

### Cursors and Values Across Measurements

A cursor's horizontal position is a single shared "display time,"
identical to today's single-measurement behavior; a signal's value at a
cursor is looked up by subtracting that signal's own measurement's offset
(REQ-PLOT-304) from the cursor's display time before locating the
sample, so cursor values stay correct regardless of how far a
measurement's axis has been panned [REQ-PLOT-305]. Arrow-key cursor
stepping (REQ-PLOT-090–093), off-screen indicators (REQ-PLOT-110–113),
and the delta-time line (REQ-PLOT-100–105) are unaffected by multiple
measurements, continuing to operate purely in this shared display-time
space.

### Signal Identity and Naming

Once two or more measurements are loaded, every active signal's
displayed name is prefixed with its measurement's label (REQ-FILE-027)
in the Active Signals Table and the Signal Info Box, so identically-named
channels from different measurements stay distinguishable; with only one
measurement loaded, no prefix is shown [REQ-PLOT-306]. Cursor value
labels are unaffected — they show only a bare value (REQ-PLOT-080–084),
never a signal name, regardless of measurement count. The measurement
prefix affects only how a signal's name is displayed — the underlying
channel name used to resolve and reload the signal is unaffected, the
same rule as display-name shortening (REQ-PLOT-162) [REQ-PLOT-307].

### Signal Assignment Across Measurements

A signal from any loaded measurement can be added to any stripe in any
tab via the existing Signal Browser add actions (REQ-BROWSER-030/031)
and stripe-assignment rules (REQ-PLOT-200–203); no distinction is made
between a stripe or tab's "own" measurement and any other loaded
measurement [REQ-PLOT-308]. Merged and Synced Y-axis groups
(REQ-PLOT-031–038) can include signals from different measurements,
since group membership is governed only by the stripe-sharing rule
(REQ-PLOT-038), not by measurement [REQ-PLOT-309].
