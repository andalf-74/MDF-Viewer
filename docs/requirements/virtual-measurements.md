# Requirements: Virtual Measurements & Virtual Signals

Part of the `docs/requirements/` collection — the single source of truth for
*what* the application does. This covers a capability distinct from the
`PluginContext` facade (`docs/requirements/plugin-api.md`): a **virtual
measurement** is an entry in the application's measurement pool that behaves
like any file-backed measurement to the rest of the app (Signal Browser,
plotting, offset/Primary/Sync) without necessarily being backed by a real
file on disk. A **virtual signal** is the individual channel-level building
block a virtual measurement is made of. Tracked by
[#147](https://github.com/andalf-74/MDF-Viewer/issues/147), filed as a
follow-up out of #71's scope (see plugin-api.md's "Out of scope for #71").

Two use cases motivate this, both converging on the same mechanism rather
than needing separate designs: artificial/computed signals as a plugin
(epic [#58](https://github.com/andalf-74/MDF-Viewer/issues/58)) instead of
a built-in feature, and custom file-format support, where a plugin converts
a foreign file into a virtual measurement the app understands without the
core app ever needing to know the foreign format exists.

**Out of scope here:** how any of this is implemented across Model/View/
Controller (see `docs/architecture.md`), and *who* is allowed to create a
virtual measurement or signal — today that is exclusively a plugin, through
the `PluginContext` surface described in `docs/requirements/plugin-api.md`'s
"Virtual Measurement Contribution (#147)" section, but the capability
described here is not inherently plugin-specific.

**Explicitly deferred to future issues, not covered by #147:**
downsampling and windowed/lazy loading of large real-measurement signals
through this same mechanism (a virtual signal's lazy data resolution is
designed so this can be added later without redesigning the interface, but
no such loading is implemented yet), and full serialization of a virtual
measurement's state into a `.mvc` workspace file (see the Workspace
Persistence section below for #147's actual v1 behavior).

**Conventions:** requirements are numbered `REQ-VMEAS-NNN`, grouped by
sub-topic with gaps left for insertion. Each testable statement is tagged
inline so it can be cited from an issue or a test via
`@pytest.mark.requirement("REQ-VMEAS-NNN")`.

---

## Parity with file-backed measurements

A virtual measurement appears in the Signal Browser alongside file-backed
measurements [REQ-VMEAS-010]. A virtual measurement's signals can be added
to a plot the same way a file-backed measurement's signals can
[REQ-VMEAS-020]. A virtual measurement supports a time offset applied to
its signals' displayed timestamps, identically to a file-backed measurement
[REQ-VMEAS-030]. A virtual measurement can be designated the Primary
measurement [REQ-VMEAS-040]. A virtual measurement participates in the
application's cross-measurement Sync state identically to a file-backed
measurement [REQ-VMEAS-050]. A virtual measurement is excluded from the
Recently Opened Files list, since it has no file path to reopen
[REQ-VMEAS-060].

## Composition

A virtual signal can be created independently of any virtual measurement
[REQ-VMEAS-110]. A virtual signal can be attached to a virtual
measurement's channel tree after having been created independently
[REQ-VMEAS-120]. A virtual measurement's channel tree contains only virtual
signals, never real MDF channels — a virtual signal is never attached
directly onto a file-backed measurement's own channel tree [REQ-VMEAS-130].

## Data resolution

A virtual signal's sample data is obtained by the application only when the
signal is actually needed for display, rather than eagerly at the time the
signal is created [REQ-VMEAS-140]. An exception raised while resolving a
virtual signal's sample data is caught at the point the application invokes
the resolution and reported to the user the same way a real signal's read
failure already is, without crashing the application or affecting any other
already-plotted signal [REQ-VMEAS-150].

## Visual distinction

A virtual measurement with no persistent file or serialized backing is
visually distinguished from file-backed measurements in the Signal Browser
and Measurement Info Box, so a user is not confused about why it has no
file path [REQ-VMEAS-210].

## Workspace persistence

A virtual measurement is not included when a workspace is saved to a `.mvc`
file [REQ-VMEAS-410]. Restoring a workspace does not recreate virtual
measurements that existed in the session at save time — a plugin that wants
its contributed measurement back must recreate it itself, e.g. on its own
next activation [REQ-VMEAS-420]. A signal plotted from a virtual
measurement is likewise not included in a saved workspace's tab/stripe
layout, consistent with the measurement itself being excluded — a saved
session never references a virtual measurement or its signals by position
[REQ-VMEAS-430].

## Editing restrictions

The action that lets a user pick a new file for an already-loaded
measurement is not available for a virtual measurement — it has no file
path for the user to browse to in the first place [REQ-VMEAS-440].
