# Requirements: X-Axis Signal Tabs

Part of the `docs/requirements/` collection — the single source of truth for
*what* the application does. This file covers a distinct tab type in which
the plot area's shared horizontal axis represents the recorded value of a
user-chosen signal ("the axis signal") instead of time — see #86, scoped via
a grill-me into a new, built-in tab type reusing the tab-type mechanism
#148 built, rather than a mode bolted onto the existing time-based tabs.

**Out of scope here:** the individual plot features this tab type reuses
unchanged from the existing plot-stripe tab type — Y-axis grouping, Swimlanes,
signal visibility, the delta-time line, zoom undo/redo, and stripe
lifecycle/layout — which stay governed by `plotting.md`; this file only adds
the rules specific to substituting a signal for time as the shared axis.
Exact widget/panel/menu layout (`docs/ui.md`); per-module API shape
(`docs/api.md`); cross-measurement time alignment mechanics themselves
(`plotting.md`'s "Multiple Measurements" section) — this file only covers
how this tab type *uses* that existing mechanism, not how it works.

**Conventions:** requirements are numbered `REQ-XAXIS-NNN`, grouped by
sub-topic with gaps left for insertion. Each testable statement is tagged
inline so it can be cited from an issue or a test via
`@pytest.mark.requirement("REQ-XAXIS-NNN")`.

---

## Creating an X-Axis Signal Tab

The application offers a distinct tab type, alongside the existing
plot-stripe tab type, in which the shared horizontal axis represents a
chosen signal's recorded value rather than time [REQ-XAXIS-010]. This tab
type is built into the core application, not implemented as a plugin, and
is available with no plugin installed or enabled [REQ-XAXIS-011]. A new
tab of this type can be created by choosing "X-Axis Signal…" from the same
chooser every other new-tab entry point offers (REQ-XAXIS-018), which
prompts for a signal, from any currently loaded measurement, to serve as
the tab's axis signal [REQ-XAXIS-012]. A new tab of this type can also be
created directly from a signal already active in an existing tab, via a
context-menu action that promotes that signal to be the new tab's axis
signal [REQ-XAXIS-013]. Promoting a signal this way copies it rather than
moving it — the signal remains active and plotted in its original tab,
unaffected, since the new tab is a distinct plot context rather than a
rearrangement of the same one [REQ-XAXIS-017]. The signal picker offers only numeric signals
with at least two samples as candidates for the axis signal — a signal
whose own recorded range covers only a small span of the other signals
being viewed is not filtered out at this stage, since the "no
extrapolation" rule (REQ-XAXIS-022) already makes that visually
self-evident rather than needing a separate validation rule
[REQ-XAXIS-014]. This numeric/sample-count filter is not applied to a
virtual signal (#147), since its real sample count and data type are not
known until it is resolved; a virtual signal that turns out unsuitable as
an axis signal fails at resolution or selection time with a clear error
instead, and the user closes the tab and picks a different signal
[REQ-XAXIS-016]. Once a tab of this type is created, its axis signal
cannot be changed; selecting a different axis signal requires creating
another tab [REQ-XAXIS-015]. Every entry point that creates a new tab —
the tab bar's pinned "+" tab and the Edit menu's "New Tab" action — offers
X-Axis Signal Tab as a choice alongside Plot; there is no separate,
dedicated menu action for it [REQ-XAXIS-018].

## The Shared Axis and Curve Rendering

Every other active signal's value at each of the axis signal's own
recorded instants is looked up using the same interpolation-or-step-mode
rule already used for cursor value lookups (`plotting.md` REQ-PLOT-083),
and plotted at an X position equal to the axis signal's own value at that
instant [REQ-XAXIS-020]. Points are drawn in the axis signal's own
recorded temporal order, not sorted by X value, so a curve can visually
move backward or loop across itself when the axis signal is not
monotonic — e.g. a vehicle standstill on a driven-distance axis draws a
vertical smear of every signal's values at that one X position, rather
than being compressed away [REQ-XAXIS-021]. A signal's value is not shown
(no extrapolation) for any instant outside its own recorded time range or
outside the axis signal's own recorded time range, the same
"no extrapolation" rule as REQ-PLOT-082 [REQ-XAXIS-022]. The axis signal
itself is not plotted against itself as a normal active signal with its
own Y-axis [REQ-XAXIS-023]. The resampled position of every curve is
computed on demand and is never stored as a separate signal or
measurement [REQ-XAXIS-024].

## Active Signals Table Representation of the Axis Signal

The axis signal is shown as a single pinned row above the
stripe-segmented area of the tab's Active Signals Table, outside any
individual stripe's segment, labeled with an "(X-axis)" badge
[REQ-XAXIS-030]. The axis signal's row cannot be removed or hidden, and
offers no Y-axis display-property controls, since it has no independent
Y-axis in this tab [REQ-XAXIS-031]. The axis signal's row shows its own
live value at the current cursor position, the same way an ordinary
active signal's row does [REQ-XAXIS-032].

## Cursors

A cursor's position in this tab type is tracked as a time value
internally, exactly as in the existing plot-stripe tab type, even though
it is displayed at the axis signal's own value at that time
[REQ-XAXIS-040]. Dragging a cursor resolves the mouse position to a time
using whichever recorded instant is nearest the cursor's own current time
as a tie-break, whenever more than one recorded instant shares the same
axis-signal value under the pointer [REQ-XAXIS-041]. Clicking directly on
a rendered curve point snaps the cursor to that point's own exact instant
[REQ-XAXIS-042]. A cursor cannot be moved by mouse-dragging through a
span where the axis signal's value does not change (e.g. a vehicle
standstill); arrow-key stepping (REQ-XAXIS-050–052) is unaffected by this
limitation [REQ-XAXIS-043].

## Arrow-Key Cursor Stepping

Arrow-key cursor stepping in this tab type reuses the same three-unit
choice and the same `Settings.cursor_step_unit` setting as the existing
plot-stripe tab type (`plotting.md` REQ-PLOT-090) — no separate setting
and no fourth unit is introduced. In this tab type the "value" unit steps
by an amount of the axis signal's own recorded value rather than time,
since the axis is never time here; "samples" and "pixels" keep their
existing meaning [REQ-XAXIS-050]. Stepping
by axis-signal value advances (or retreats) the cursor's time until the
axis signal's value has changed by at least the configured amount from
the cursor's current position, skipping over any span where the value
does not change [REQ-XAXIS-051]. Stepping by samples of the axis signal
moves the cursor by exactly one of the axis signal's own recorded
instants at a time, regardless of whether its value changed, unaffected
by a standstill span [REQ-XAXIS-052].

## Zoom, Pan, and Reused Plot Features

"Zoom to Fit," "Zoom Y to View," box zoom, Swimlanes, Merged/Synced
Y-axis grouping, signal visibility, and the delta-time line all behave
exactly as documented in `plotting.md` for the existing plot-stripe tab
type, with the axis signal's value substituted for time wherever those
rules refer to the shared X-axis [REQ-XAXIS-060]. This tab type supports
multiple plot stripes, created and managed the same way as the existing
plot-stripe tab type (`plotting.md`'s "Plot Stripes" section)
[REQ-XAXIS-061].

## Multiple Measurements

A signal from any loaded measurement, real or virtual, can be added to
this tab type, using the same measurement offset already applied to that
measurement everywhere else in the application (`plotting.md`
REQ-PLOT-304) [REQ-XAXIS-070]. Changing any measurement's offset
immediately updates every already-open tab of this type that has an
active signal belonging to that measurement [REQ-XAXIS-071]. Changing
the axis signal's own measurement's offset does not change any point's X
position, since the axis signal's own recorded values are unaffected by a
time shift, but does change the value shown for every other active
signal at each X position, since the correspondence between the axis
signal's instants and every other signal's instants has shifted
[REQ-XAXIS-072].

## Persistence

A tab of this type, including its axis signal, every active signal's
display properties, stripe layout, zoom/pan view, and cursor state, is
captured and restored by Save Workspace / Save Workspace As the same way
as the existing plot-stripe tab type (`file-handling.md` REQ-FILE-061)
[REQ-XAXIS-080].
