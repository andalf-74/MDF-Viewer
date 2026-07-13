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

**Resolved for #71:** event payloads that carry a signal (`signal_added`,
`signal_removed`) still pass the live, mutable `ActiveSignal` internally —
#70's event bus is unchanged. `PluginContext` (below) exposes a narrower,
read-only projection instead of that raw object; a plugin never receives
the live `ActiveSignal` (or its PyQtGraph `curve`/`view_box` handles)
through either the event bus or the context.

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
Events) through its own context [REQ-PLUGIN-140].

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
