# Requirements: Non-Functional

Part of the `docs/requirements/` collection (see CLAUDE.md's "Requirements
Workflow" for conventions and ID scheme). Cross-cutting qualities that
don't belong to one feature domain: crash resilience, persistence
resilience, network resilience, platform support, and rendering
performance.

**Out of scope here:** domain-specific instances of these qualities,
which live in their owning domain file and are cross-referenced below
rather than restated. Licensing/entitlement (`src/mdf_viewer/license/`,
`docs/architecture.md`) is also out of scope — it's tracked separately
and doesn't have a requirements file yet. Noted here only because it's
easy to assume it belongs under "non-functional": today it is purely
informational (license status is shown in the About box and Help menu)
and is not a hard blocker — no feature is gated or disabled based on
license state.

---

## Crash Resilience

The application must never crash due to malformed, incomplete, or
unexpected input — whether that input is a measurement file, a saved
session file, or the local settings file [REQ-NFR-010]. Errors are caught
at the boundary where the untrusted data is parsed and surfaced to the
user as a clear, non-fatal message rather than allowed to propagate into
a crash [REQ-NFR-011]. Domain-specific instances of this contract:
malformed MDF content (`mdf-support.md` REQ-MDF-070 through 072), a bad
`.mvc` session file (`file-handling.md` REQ-FILE-068), and a load failure
for an individual channel (`mdf-support.md` REQ-MDF-033,
`signal-browser.md` REQ-BROWSER-041) [REQ-NFR-012].

## Settings Persistence Resilience

A missing, unreadable, or corrupted local settings file does not prevent
the application from starting — it falls back to built-in defaults for
every preference rather than failing to launch [REQ-NFR-020]. Each
individual preference change is persisted immediately as it's made,
rather than batched, so a later abnormal exit doesn't lose changes made
earlier in the session [REQ-NFR-021].

## Network Resilience (Update Checking)

Checking for a new release is optional, governed by a user preference,
and defaults to on [REQ-NFR-030]. When performed automatically at
startup, the check runs in the background and never blocks the UI or
interrupts the user [REQ-NFR-031]. A failed automatic startup check (e.g.
no network access) fails silently, since it wasn't something the user
explicitly asked for; a failed manually-requested check is reported to
the user with a clear message, since that one was explicitly requested
[REQ-NFR-032]. Either way, a network failure while checking for updates
never crashes or otherwise disrupts the application [REQ-NFR-033].

## Platform Support

The application runs on Windows and Linux [REQ-NFR-040]. Where the
operating system defines a convention for per-user application data
(e.g. `%APPDATA%` on Windows, the XDG-style config directory on Linux),
the application follows it for storing its local settings rather than
using a hardcoded or non-idiomatic location [REQ-NFR-041].

## Rendering Performance on Large Recordings

A signal's rendered curve is progressively simplified as it is zoomed
out, so recordings with very large sample counts stay smooth and
responsive to pan/zoom rather than rendering every individual sample
regardless of screen resolution [REQ-NFR-050]. This simplification
affects only the drawn curve line — cursor value readout, interpolation,
min/max statistics, and delta-time calculations always operate on the
full-resolution underlying data, never the simplified rendering
[REQ-NFR-051].
