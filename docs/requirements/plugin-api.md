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

**Open question for #71:** event payloads that carry a signal (`signal_added`,
`signal_removed`) pass the live, mutable `ActiveSignal` instance itself — the
same object `AppController` and the plot use internally, including its
PyQtGraph `curve`/`view_box` handles and every mutable display field. #71
("read access to active signals") must decide whether plugins keep that
level of access, or receive a narrower, read-only projection instead. Not
decided here — #70 only needs the raw object flowing internally.
