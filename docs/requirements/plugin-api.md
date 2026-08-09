# Requirements: Plugin API

Part of the `docs/requirements/` collection — the single source of truth for
*what* the application does. This covers the programmatic surface the
application exposes so that plugins (and, potentially, other internal
modules) can observe and eventually extend it. A plugin developer is a
consumer of application behavior just like an end user — a requirement here
is no less real for being observable only through code rather than the UI.

This file will grow alongside the wider Plugin Architecture epic (#43):
the event bus (#70, covered below), the `PluginContext` API facade (#71),
plugin lifecycle (#72), UI extension points (#73), and plugin loader/
discovery (#74) will each add their own section as they land.

**Out of scope here:** how any of this is implemented across Model/View/
Controller (see `docs/architecture.md`). A requirement below should read
the same regardless of which layer ends up owning it.

**Conventions:** requirements are numbered `REQ-PLUGIN-NNN`, grouped by
sub-topic with gaps left for insertion. Each testable statement is tagged
inline so it can be cited from an issue or a test via
`@pytest.mark.requirement("REQ-PLUGIN-NNN")`.

---

## Lifecycle Events (#70)

The application exposes an event bus that fires on key lifecycle changes,
independently of whatever else is subscribed to it — today nothing consumes
these events, but plugins (once `PluginContext` lands) and internal modules
may subscribe without the application needing to know who is listening.

The application fires a `file_loaded` event, carrying the loaded file's
path, whenever a measurement file is successfully opened [REQ-PLUGIN-010].
The application fires a `signal_added` event, carrying the added signal and
the stripe it was added to, whenever a signal is added to the plot
[REQ-PLUGIN-020]. The application fires a `signal_removed` event, carrying
the removed signal, whenever a signal is removed from the plot
[REQ-PLUGIN-030]. The application fires a `selection_changed` event,
carrying the current signal selection, whenever the active signal selection
changes [REQ-PLUGIN-040]. The application fires a `cursor_moved` event,
carrying the new cursor positions and cursor mode, whenever a visible
cursor's position changes [REQ-PLUGIN-050].

**Resolved for #71, enforced for #149:** event payloads that carry a signal
(`signal_added`, `signal_removed`) still pass the live, mutable
`ActiveSignal` internally — #70's event bus is unchanged. `PluginContext`
(below) exposes a narrower, read-only projection instead of that raw
object; a plugin never receives the live `ActiveSignal` (or its PyQtGraph
`curve`/`view_box` handles) through either the event bus or the context.
Every event's `tab` field is likewise the raw internal `TabWorkspace`
internally — carrying that tab's actual `plot`/`table`/`cursor_ctrl`/
`zoom_ctrl` objects — and is translated the same way (#149; see
REQ-PLUGIN-141).

---

## PluginContext API Facade (#71)

`PluginContext` is the only object a plugin is allowed to import from the
application — once published, its shape is a compatibility promise (version
negotiation itself is deferred to #74, the plugin loader). Each plugin
receives its own `PluginContext` instance, identified by the plugin's own
name/id, so the application can attribute errors and (eventually) scope
permissions per plugin rather than per call [REQ-PLUGIN-060].

### Reading signals

The application exposes the active signals across every tab, grouped by
tab, together with an indication of which tab is currently active
[REQ-PLUGIN-070]. Each signal is exposed as a read-only projection carrying
its metadata, display color, display mode and style, visibility, and its
source measurement reference — never the live, mutable `ActiveSignal` and
never its PyQtGraph `curve`/`view_box` handles [REQ-PLUGIN-080]. The
projection does not carry sample data; a plugin fetches a signal's
timestamps and values only through a separate, explicit call, so that
routine access to the signal list never pays the cost of copying sample
arrays a plugin doesn't need [REQ-PLUGIN-090].

### Reading measurement and cursor state

The application exposes the full list of currently loaded measurements
(path, short name, offset) together with which one is marked Primary
[REQ-PLUGIN-100]. The application exposes the current cursor positions
across every tab, grouped by tab, readable on demand in addition to the
existing `cursor_moved` event, so a plugin does not need to have been
subscribed since startup to know the current position [REQ-PLUGIN-110].

### Registering UI contributions

A plugin can register a menu action; every registered action appears
under one dedicated "Plugins" top-level menu, with no per-plugin placement
control [REQ-PLUGIN-120]. A plugin can register a dock widget as either a
tabbed panel docked into the existing right-side drawer, or a standalone
dialog, chosen by the plugin at registration time, with no free-form area
placement [REQ-PLUGIN-130]. Registration in #71 records the contribution
for later use; the application does not yet render registered menu actions
or dock widgets in the UI — that wiring belongs to #73.

### Subscribing to events

A plugin can subscribe to any of the events described above (Lifecycle
Events) through its own context [REQ-PLUGIN-140]. The payload delivered
to a plugin's handler is translated into the same kind of read-only
projection the read surface above uses — a signal becomes the same
read-only projection REQ-PLUGIN-080 describes, and a tab is identified by
its index rather than the raw internal tab object — never the live,
mutable objects the application uses internally [REQ-PLUGIN-141]. Every
event the application bus can emit has such a translation; none is ever
forwarded to a plugin unchanged [REQ-PLUGIN-142].

### Error isolation

An exception raised by a plugin's callback — an event handler or a
registered menu action's handler — is caught and logged at the point the
application invokes it; the application continues running rather than
propagating the exception [REQ-PLUGIN-150].

### Out of scope for #71

Registering a custom file-format reader, and contributing synthetic/
computed signals as if they were loaded from a file, are both explicitly
out of scope here. Both converge on a single future concept — a plugin
contributing a "virtual measurement" that behaves like any other loaded
measurement to the rest of the app — tracked separately in
[#147](https://github.com/andalf-74/MDF-Viewer/issues/147).

---

## Plugin Base Class and Lifecycle (#72)

A plugin author implements against a `Plugin` base class rather than
`PluginContext` directly — `PluginContext` is what a plugin *receives*,
`Plugin` is what a plugin author *writes*.

### Metadata

A plugin declares its own name, version, description, and author as
class-level attributes [REQ-PLUGIN-160]. A plugin whose name is left
unset is rejected at construction, with a clear error, rather than being
silently loaded under an anonymous or generic identity — every other
per-plugin mechanism (error attribution, registration tagging) depends on
a real name existing [REQ-PLUGIN-161].

### Activation

A plugin's `activate(context)` method is called exactly once, when the
plugin is loaded, and is the only point at which it can register menu
actions, dock widgets, or event subscriptions — a plugin that does not
implement it can never do anything, so implementing it is mandatory, not
optional [REQ-PLUGIN-170]. A plugin's `deactivate()` method is called
exactly once, when the plugin is unloaded (application shutdown, or a
future explicit disable), and is optional — a plugin that implements no
teardown of its own still has its event subscriptions and UI
registrations automatically removed [REQ-PLUGIN-171]. If `activate()`
raises, the plugin is treated as having failed to activate rather than
as successfully active, and its `deactivate()` is not later called for
it [REQ-PLUGIN-172].

### Event handler methods

A plugin may override any of five optional handler methods, one per
lifecycle event described above (`on_file_loaded`, `on_signal_added`,
`on_signal_removed`, `on_selection_changed`, `on_cursor_moved`), each
receiving that event's payload [REQ-PLUGIN-180]. Overriding one of these
methods is sufficient on its own to subscribe to that event — a plugin
does not need to call anything else to receive it [REQ-PLUGIN-181]. Every
event subscription implied by an overridden handler method is
automatically removed when the plugin is deactivated, whether or not the
plugin's own `deactivate()` does anything [REQ-PLUGIN-182].

### Error isolation

An exception raised by a plugin's `activate()`, `deactivate()`, or any of
its event handler methods is caught and logged at the point the
application invokes it, the same as any other plugin callback
[REQ-PLUGIN-190].

---

## UI Extension Points in MainWindow (#73)

This section makes #71's registration stubs (`register_menu_action`,
`register_dock_widget`) actually visible in the running application. It
is built against whatever has been registered by the time the main
window is constructed [REQ-PLUGIN-200]. **Superseded in part by #150:**
at the time this was written, no plugin could activate or deactivate
after that point, so nothing needed to react to registrations changing
while the app was already running. Once Rescan/Reload exist, that is no
longer true — see REQ-PLUGIN-390.

### The Plugins menu

Every registered menu action appears as an entry in one dedicated
"Plugins" menu, positioned between the existing Edit and Help menus
[REQ-PLUGIN-210]. **Superseded by #150:** the Plugins menu is always
present, regardless of whether any plugin action, dock widget, or
Rescan/Reload target currently exists, rather than being hidden when
empty as originally specified — see REQ-PLUGIN-391 for why.

### Docked widgets

A dock widget registered in docked mode appears as an additional titled
section in the existing Signal Info/Properties drawer, alongside the
existing Info and Properties sections, independently resizable the same
way those two already are [REQ-PLUGIN-220].

### Dialog widgets

A dock widget registered in dialog mode is not shown automatically;
instead, an entry for it is automatically added to the Plugins menu,
labeled with its title, so the user can open it on demand — the plugin
does not need to separately register a menu action just to open its own
dialog [REQ-PLUGIN-230]. Opening it shows the widget in a modal dialog,
matching how every other dialog in the application (e.g. Preferences) is
already shown [REQ-PLUGIN-231].

---

## Plugin Loader and Discovery (#74)

This is the piece that finally makes #71/#72/#73 do something: discovering
real plugin packages on disk, activating them, and deactivating them again
on shutdown.

### Discovery

The application scans one plugins directory for plugin packages
[REQ-PLUGIN-240]. Each subdirectory containing an `__init__.py` is treated
as one plugin package; anything else in the directory is ignored
[REQ-PLUGIN-241]. A plugin package declares which classes it contributes
explicitly, as a module-level list, rather than the application guessing
by inspecting the module's contents — this supports a single plugin and a
multi-plugin "toolsuite" package the same way, with no ambiguity either
way [REQ-PLUGIN-242]. A package that fails to declare that list, or
declares an empty one, is treated as broken and skipped, with the reason
logged [REQ-PLUGIN-243].

### Location

The plugins directory defaults to a location next to the running
application — the same folder the installed or portable executable lives
in — so a portable installation's plugins travel with it when the whole
folder is copied elsewhere [REQ-PLUGIN-250]. Running from source instead
uses a location relative to the source checkout, since there is no single
"next to the application" location in that case [REQ-PLUGIN-251]. The
plugins directory can be overridden to a different location
[REQ-PLUGIN-252].

### Activation

Every declared plugin class is instantiated and activated once, during
application startup, before the rest of the application's UI is
interactive [REQ-PLUGIN-260]. Two plugins that end up with the same name
are not both activated — the first one to load with a given name is
activated normally; any later one reusing that name is rejected and the
conflict is logged, rather than both silently running under an
indistinguishable identity [REQ-PLUGIN-261].

### Shutdown

Every plugin that was successfully activated is deactivated once, when
the application closes [REQ-PLUGIN-270].

### Error isolation

A failure at any point in discovering, loading, instantiating, or
activating one plugin package — an unreadable directory, a package that
fails to import, a missing or invalid declared plugin list, or a plugin
that fails to activate — is caught and logged, and does not prevent any
other plugin from loading or the application from starting normally
[REQ-PLUGIN-280].

---

## Virtual Measurement Contribution (#147)

This section extends the facade with the capability explicitly deferred in
"Out of scope for #71" above: a plugin contributing virtual signals and
virtual measurements, rather than only reading what the application already
loaded. The virtual measurement/signal concept itself — what one is and how
it behaves once it exists — is specified in
`docs/requirements/virtual-measurements.md` (`REQ-VMEAS-*`); this section
covers only the plugin-facing surface that creates and owns them.

### Creating and registering

A plugin can create a virtual signal through its context, supplying the
signal's descriptive metadata and a callback the application invokes to
resolve its sample data on demand, per REQ-VMEAS-140 [REQ-PLUGIN-290]. A
plugin can create a virtual measurement through its context and attach
previously-created virtual signals to it, per REQ-VMEAS-110/120
[REQ-PLUGIN-291]. A plugin can add a virtual measurement it has built to
the application's measurement pool, making it visible to the rest of the
application per the parity requirements in `virtual-measurements.md`
[REQ-PLUGIN-292].

### Ownership and teardown

A virtual measurement or signal contributed by a plugin is attributed to
that plugin, so the application can act on that ownership later
[REQ-PLUGIN-300]. When a plugin is deactivated, every virtual measurement
and signal it contributed is removed from the application's measurement
pool, after the plugin's own `deactivate()` has already run — giving the
plugin a chance to react (e.g. to a future serialization capability) before
its data disappears, the same ordering `stop()` already guarantees for
event subscriptions and UI registrations [REQ-PLUGIN-301]. When a user
closes a virtual measurement through the existing measurement-close UI
action, the contributing plugin is notified of the closure, separately from
and in addition to the deactivation case above [REQ-PLUGIN-302].

### Error isolation

An exception raised by a plugin-supplied virtual signal data-resolution
callback is caught at the point the application invokes it and reported to
the user the same way a real signal's read failure already is — unlike an
event handler or a registered menu action's callback (REQ-PLUGIN-150),
which are logged and swallowed silently, a failed signal resolution has an
existing, established user-facing error path this reuses rather than
duplicating [REQ-PLUGIN-310].

---

## Pluggable Tab Types (#148)

Extends #73's UI extension points: today every tab is a Plot tab (plot
stripes + Active Signals Table). This lets a plugin register a tab
*type* — a template a user can create any number of independent tabs
from — rather than only a fixed dock widget or menu action. First real
consumer tracked separately in
[#118](https://github.com/andalf-74/MDF-Viewer/issues/118) (OpenStreetMap
View), which depends on this landing first.

**Out of scope here:** a non-plot tab's own internal content survives a
save to a `.mvc` workspace file and is handed back on restore (deferred to
a future issue, matching how #147 deferred full virtual-measurement
serialization) — v1 restores a *fresh, empty* instance of the tab's type
when the owning plugin is still present, nothing more.

### Registration

A plugin can register a tab type through its context, supplying a stable
type identifier, a display name, and a factory the application invokes to
build one tab instance [REQ-PLUGIN-320]. Registration is only valid during
`activate()` [REQ-PLUGIN-321]. **Superseded in part by #150:** at the
time this was written, that meant a static snapshot with no live
add/remove while the application was already running, the same way menu
actions and dock widgets were (REQ-PLUGIN-200); Rescan/Reload now change
the registered tab type set live — see REQ-PLUGIN-390. The factory is invoked
fresh every time a new tab of that type is created, never reused across
tabs, so any number of independent tabs of the same type can be open at
once [REQ-PLUGIN-322].

### Tab creation

Creating a new tab always offers a choice between the two built-in types,
Plot and X-Axis Signal (#86 — see `docs/requirements/x-axis-signal.md`),
regardless of whether any plugin-registered tab type exists
[REQ-PLUGIN-330]. Once at least one plugin-registered tab type exists,
every entry point that creates a new tab includes it in that same choice
alongside the built-in types [REQ-PLUGIN-331]. An exception raised while building a tab's content is
caught and logged at the point the application invokes the factory, the
same as any other plugin callback (REQ-PLUGIN-150) — no tab is created for
that attempt, and the application keeps running [REQ-PLUGIN-332].

### Non-plot tab scope

A non-plot tab's content reads application state solely through the
existing read surface (active signals, measurements, cursor positions) and
event subscriptions already available through the plugin's context — no
additional read surface is added for it [REQ-PLUGIN-340]. Duplicate Tab and
Copy Signals to New Tab remain available only for Plot tabs — neither
applies to a non-plot tab [REQ-PLUGIN-341]. Closing a non-plot tab always
proceeds without the "still has active signals" confirmation Plot-tab
closing shows, since active signals are not a concept a non-plot tab has
[REQ-PLUGIN-342].

### Workspace persistence

Which tab type each tab is is included when a workspace is saved to a
`.mvc` file [REQ-PLUGIN-350]. Restoring a workspace recreates a non-plot
tab, via a fresh call to its registered type's factory, in the same
relative position among the session's other tabs, whenever a plugin is
still registered for that saved type at restore time [REQ-PLUGIN-351]. A
saved tab whose type is not registered at restore time is skipped, with
the rest of the saved session still restoring around it, consistent with
how a measurement that fails to load is already handled during restore
[REQ-PLUGIN-352].

---

## Plugin Rescan and Reload (#150)

Today (#74), `PluginLoader.load_all()` runs exactly once, at startup —
picking up a new plugin, or an edit to an existing one, requires
restarting the application. This section adds two on-demand capabilities
that don't: re-scanning the plugins directory for packages that were not
loaded at startup, and reloading one already-active plugin's code from
disk without restarting.

### Rescan

The application can re-scan the plugins directory on demand, discovering
and activating any plugin package that is not currently active — this
covers both a package added to the directory after startup and a package
that failed to load on a previous scan, treated identically and retried
every time rather than remembered as permanently broken [REQ-PLUGIN-360].
Rescanning never activates a second copy of a plugin that is already
active, keyed by plugin name across the application's entire running
session rather than only within one scan [REQ-PLUGIN-361].

A plugin folder that is removed from disk while the application is
running is not detected by Rescan, and does not, on its own, deactivate
the plugin that was loaded from it — reacting to on-disk removal is out
of scope here.

### Reload

The application can reload one specific, already-active plugin, by name,
on demand — deactivating it and reactivating a freshly re-imported copy
of its code without restarting the application [REQ-PLUGIN-370].
Reloading invalidates every cached module reachable under that plugin's
own import namespace, not only its top-level module, so that a change to
any file within a multi-file plugin package is picked up, not only a
change to its `__init__.py` [REQ-PLUGIN-371]. If the freshly reactivated
copy's `activate()` fails, the plugin ends up deactivated rather than
reverted to the copy that was running before the reload was requested
[REQ-PLUGIN-372].

This issue adds no separate way to deactivate a plugin without also
reloading it — the two bundled capabilities here are Rescan and Reload
only.

### Live UI teardown on deactivation

Deactivating an already-active plugin while the application is running
removes every currently visible trace of its contributed UI — its
docked-panel section, any dialog-mode widget it registered that is
currently open, and any open tab created from a tab type it registered —
rather than leaving that UI on screen and disconnected from a plugin that
is no longer active [REQ-PLUGIN-380].

### Live refresh of the Plugins menu

The Plugins menu, its docked-widget sections, and the set of tab types
offered when creating a new tab are all rebuilt to reflect the current
set of active plugins immediately after a Rescan or a Reload completes,
rather than only once, at startup, as originally specified in
REQ-PLUGIN-200/321 [REQ-PLUGIN-390]. The Plugins menu is always present,
regardless of whether any plugin is currently active, so that Rescan
remains reachable even from a plugins directory with nothing successfully
loaded — reversing REQ-PLUGIN-211's original "hidden when empty" rule,
which depended on registrations never changing after startup
[REQ-PLUGIN-391].

### Trigger UI

A "Rescan Plugins" action and a "Reload Plugin" submenu, listing every
currently active plugin by name, both appear at the top of the Plugins
menu, above a separator that precedes any plugin-contributed entries
[REQ-PLUGIN-400]. Completing a Rescan or a Reload reports a brief summary
of its outcome to the user through the status bar, rather than only to
the log as the equivalent startup failures already are, since both are
actions the user just initiated and expects to see the result of
[REQ-PLUGIN-401].

---

## Plugin Preferences API (#159)

Extends #71's per-plugin `PluginContext` with a settings-persistence
primitive and a matching UI surface, so a plugin has a standard place to
put user-configurable options instead of inventing its own storage and
dialog. Surfaced while scoping #76 (converting the update checker into a
first-party plugin), which becomes the first real consumer — this issue
ships the general capability with no real consumer of its own yet, the
same way #71/#147/#148 each did.

### Per-plugin setting storage

A plugin can persist a value under a key of its own choosing through its
context, and read it back later — including across application restarts
— namespaced separately per plugin so no two plugins' keys can collide
[REQ-PLUGIN-410]. A persisted value is restricted to JSON-serializable
primitives (strings, numbers, booleans, `None`, and lists/dicts of the
same); a value that is not is rejected and logged at the point it is
written, rather than surfacing later as a generic failure when the
application's settings file is saved [REQ-PLUGIN-411]. Reading a setting
that has never been written returns the caller-supplied default without
persisting it — a read never has the side effect of writing anything
[REQ-PLUGIN-412]. Both reading and writing a setting are available at any
point after a plugin has received its context — including from within
`activate()` itself, or from inside a preferences page being built —
with no narrower lifecycle restriction, unlike the UI registration
methods below [REQ-PLUGIN-413]. A plugin's persisted settings are not
automatically removed if the plugin is later renamed or is no longer
discovered — an orphaned entry is left in place indefinitely rather than
pruned [REQ-PLUGIN-414].

### Registering a preferences page

A plugin can register one preferences page through its context, supplying
a title and a factory the application invokes to build its content
[REQ-PLUGIN-420]. Registration is only valid during `activate()`, the
same as the application's other UI registration methods [REQ-PLUGIN-421].
A second registration attempt from the same plugin is rejected and
logged, rather than replacing the first or adding a second page — a
plugin registers at most one preferences page [REQ-PLUGIN-422].

### The Plugin Preferences dialog

A "Plugin Preferences…" entry in the Plugins menu opens a single dialog
listing one tab per plugin that has registered a preferences page
[REQ-PLUGIN-430]. The entry is always present, disabled when no plugin
has registered a page, and positioned alongside Rescan Plugins and Reload
Plugin rather than among plugin-contributed entries lower in the menu
[REQ-PLUGIN-431]. A plugin's preferences page is responsible for
persisting its own changes as the user edits it, through its own calls to
its context; the dialog itself provides no separate Apply/OK step and no
way to discard an in-progress edit — closing it is the only action
available [REQ-PLUGIN-432]. A plugin's preferences page content is built
once, the first time it is needed, and the same instance is reused across
every later opening of the dialog, the same way a plugin's dialog-mode
dock widget is already cached [REQ-PLUGIN-433]. An exception raised while
building a plugin's preferences page is caught and logged at the point
the application invokes the factory; that plugin's tab is omitted and
every other plugin's tab still appears, rather than the dialog failing to
open at all [REQ-PLUGIN-434].

### Interaction with Rescan and Reload

Deactivating a plugin — including as part of a Reload — removes its
preferences page registration and, if the Plugin Preferences dialog
currently has a tab open for it, removes that tab and its built content,
the same as the application already does for a deactivated plugin's other
contributed UI [REQ-PLUGIN-440].

### Out of scope here

Migrating the existing "check for updates on startup" setting, and the
core Preferences dialog it lives in today, onto this mechanism is
explicitly deferred to #76.

---

## Application Window & Version Access (#76)

Surfaced while scoping #76 (converting the update checker into a
first-party plugin): a plugin that wants to show a modal dialog of its
own — as opposed to a docked widget or a preferences page, both already
parented for it by the application — has no widget available to parent
it to; none of the existing registration methods pass one to a plugin's
callback. Separately, a plugin that needs to know the running
application's own version (e.g. to compare against a fetched release
version) has no way to obtain it without importing `mdf_viewer.__version__`
directly, outside the documented plugin-import boundary.

A plugin can obtain the application's main window through its context,
for use as the parent of a dialog the plugin constructs itself
[REQ-PLUGIN-450]. The returned object is the application's real main
window, the same way a dock widget's or preferences page's
`widget_factory` already deals in real, live `QWidget`s rather than a
wrapped projection — unlike the read-only signal/measurement views
described above, there is no narrower facade over it [REQ-PLUGIN-451]. A
plugin can obtain the application's own running version string through
its context [REQ-PLUGIN-452].

---

## Plugin Overview and Enable/Disable (#160)

Extends #74/#150's discovery and lifecycle model with per-plugin
enable/disable control, surfaced through a new "Plugin Overview" entry in
the Plugins menu. Before this, every discovered plugin package was always
imported and activated, with no way to opt one out short of removing its
folder from the plugins directory entirely.

### Discovery and identity

The application lists every plugin package found in the plugins
directory — every subdirectory containing an `__init__.py`, the same set
REQ-PLUGIN-241 already defines for startup discovery — independently of
whether each one is currently enabled, active, or has ever been imported
[REQ-PLUGIN-460]. A plugin package that is not currently enabled is
identified only by its folder name; the application does not import it
merely to discover its declared name, since doing so would defeat the
purpose of leaving it disabled [REQ-PLUGIN-461]. Enable/disable state,
and the Overview list, are both scoped to one plugin package (folder) as
a whole — a package declaring more than one plugin class in its `PLUGINS`
list enables or disables every class in it together, with no
per-class control [REQ-PLUGIN-462].

### Enable/disable semantics

A plugin package's enabled state persists across application restarts,
saved in the same application settings file as other global preferences
[REQ-PLUGIN-470]. A plugin package not previously known to the
application — a newly added folder discovered by Rescan or at the next
startup — is enabled by default, with no action required to activate it
[REQ-PLUGIN-471]. A disabled plugin package's `__init__.py` is not
imported during startup discovery or Rescan — its module code does not
execute at all while it remains disabled [REQ-PLUGIN-472].

### The Plugin Overview dialog

A "Plugin Overview" entry in the Plugins menu, positioned alongside
Rescan Plugins, Reload Plugin, and Plugin Preferences, opens a dialog
listing every discovered plugin package with a checkbox reflecting its
current enabled state [REQ-PLUGIN-480]. Unchecking a currently-active
plugin package deactivates it immediately, through the same teardown
already defined for Reload (REQ-PLUGIN-380), without requiring the
application to restart [REQ-PLUGIN-481]. Checking a currently-disabled
plugin package imports and activates it immediately, the same way
Rescan already activates a newly discovered package (REQ-PLUGIN-360),
without requiring the application to restart [REQ-PLUGIN-482]. Toggling
a checkbox persists the change immediately; the dialog provides no
separate Apply/OK step and no way to discard an in-progress change, the
same as the Plugin Preferences dialog (REQ-PLUGIN-432) [REQ-PLUGIN-483].

### Failure visibility

A plugin package that is enabled but failed to activate is shown in the
Overview list with a visible indication of that failure, distinguishable
from a package that is simply disabled [REQ-PLUGIN-490]. The application
retains the most recent failure reason for a plugin package until its
next successful activation or until it is disabled, so the Overview
dialog can display it after the scan or reload attempt that produced it
has already finished [REQ-PLUGIN-491].

### Row content

A plugin package that has never been imported is shown in the Overview
list by its folder name only [REQ-PLUGIN-500]. A plugin package that is
or has been active during the current session is additionally shown with
its declared name, version, description, and author, alongside its
folder name [REQ-PLUGIN-501].

### Stale entries

An enable/disable entry for a plugin package whose folder no longer
exists on disk is pruned silently the next time the Overview dialog is
opened, the same way a stale recent-file entry is already pruned when
the File menu opens [REQ-PLUGIN-510].

### Out of scope here

Per-individual-plugin-class control within a multi-plugin package is out
of scope — the granularity is the package as a whole (REQ-PLUGIN-462).
Disabling a currently-active plugin package with open UI state (e.g. open
tabs of its registered tab type) shows no confirmation prompt first — it
behaves identically to Reload's existing silent teardown, which already
has no such prompt.

---

## Growing a Registered Virtual Measurement (#162)

Extends the Virtual Measurement Contribution surface (#147,
REQ-PLUGIN-290-310): before this, `attach_virtual_signal` only had a
defined effect prior to `register_virtual_measurement` — a plugin that
wanted to add another signal to a measurement already visible in the
Signal Browser had no choice but to create an entirely new measurement.
This section makes attach (and a new, symmetric detach) valid for a
registered measurement's entire lifetime, not just its construction, and
adds the notification a plugin needs to react to that ongoing change. The
underlying virtual-measurement behavior this relies on is specified in
`virtual-measurements.md` (REQ-VMEAS-121–135); this section covers only
the plugin-facing methods and event.

### Attaching and detaching after registration

Attaching a virtual signal to a measurement already registered in the
application's measurement pool is reflected in the Signal Browser
immediately, without waiting for an unrelated measurement-pool change to
trigger a refresh, per REQ-VMEAS-121 [REQ-PLUGIN-520]. A plugin can detach
a previously-attached virtual signal from its measurement through its
context, per REQ-VMEAS-122/135 [REQ-PLUGIN-521]. Detaching targets the
exact virtual signal instance passed in; a measurement may contain more
than one virtual signal sharing the same name, per REQ-VMEAS-123, and the
application does not use name matching to decide which one to remove
[REQ-PLUGIN-522]. Attaching a virtual signal instance that is already
attached to the same measurement is rejected and logged rather than
creating a second, indistinguishable entry [REQ-PLUGIN-523].

### Notification

Attaching or detaching a virtual signal on an already-registered
measurement fires a `measurement_updated` event, carrying the affected
signal's name and whether it was attached or detached [REQ-PLUGIN-530]. A
plugin subscribed to this event receives it through the same per-event
handler-override mechanism as the application's other events
(REQ-PLUGIN-181) [REQ-PLUGIN-531].

### Idempotent registration

Registering a virtual measurement that is already present in the
application's measurement pool, identified as the same measurement
instance, has no further effect the second time, and is logged the same
way a rejected duplicate preferences page registration already is
(REQ-PLUGIN-422) — a plugin does not need to track for itself whether it
has already registered a given measurement [REQ-PLUGIN-540].

### Read surface

A measurement exposed to a plugin through its read surface indicates
whether it is virtual or file-backed [REQ-PLUGIN-550].

### Out of scope here

Whether an equivalent "composition changed" event could ever fire for a
file-backed measurement is not addressed — no operation exists today that
changes a file-backed measurement's channel tree after it loads, so
`measurement_updated` is only ever observed for a virtual measurement in
practice; its payload nonetheless carries the same virtual/real
distinction `measurement_closed` already does, for consistency between the
two events rather than because a real-measurement case is expected soon.
