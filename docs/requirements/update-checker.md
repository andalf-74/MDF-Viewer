# Requirements: Update Checker

Part of the `docs/requirements/` collection — the single source of truth for
*what* the application does. This covers checking whether a newer released
version of MDF-Viewer is available, both on demand and automatically at
startup. Tracked by
[#76](https://github.com/andalf-74/MDF-Viewer/issues/76), which also
converts this capability from a built-in feature into the application's
first first-party plugin — see `docs/requirements/plugin-api.md`'s
"Application Window Access (#76)" section for the one new `PluginContext`
capability that conversion required, and `docs/architecture.md` for the
plugin-conversion decision itself.

**Out of scope here:** cross-cutting behavior already covered by
`docs/requirements/non-functional.md`'s "Network Resilience (Update
Checking)" section — that checking is optional and defaults to on
(REQ-NFR-030), that an automatic check runs in the background without
blocking the UI (REQ-NFR-031), the silent-automatic-vs-reported-manual
failure distinction (REQ-NFR-032), and that a network failure never
crashes the application (REQ-NFR-033). Those requirements are
cross-referenced below, not restated. Also out of scope: that this
capability happens to be implemented as a plugin rather than built in
(see `docs/architecture.md`), and how it is presented on screen beyond
the specific dialogs/menu entry described below (see `docs/ui.md`).

**Conventions:** requirements are numbered `REQ-UPDATE-NNN`, grouped by
sub-topic with gaps left for insertion. Each testable statement is tagged
inline so it can be cited from an issue or a test via
`@pytest.mark.requirement("REQ-UPDATE-NNN")`.

---

## Checking for Updates

The application can check whether a newer released version exists by
querying the project's GitHub releases API for the latest published
release [REQ-UPDATE-010]. A user can trigger a check at any time via a
"Check for Update…" menu action, independently of whatever the automatic
startup check setting (see "User Preference" below, REQ-NFR-030) is
currently set to [REQ-UPDATE-020]. When a manually triggered check finds
a newer version, the application shows a dialog naming the newer version
and offering to open its release page in the user's browser
[REQ-UPDATE-030]. When a manually triggered check finds no newer version,
the application shows a dialog confirming the running version is already
the latest — distinct from a failed check, which is reported per
REQ-NFR-032 [REQ-UPDATE-040].

## Automatic Startup Check

The automatic startup check (REQ-NFR-030/031) shows the same "newer
version available" dialog as a manual check when it finds one, but shows
no dialog at all when it finds none — unlike a manual check, which always
confirms up-to-dateness either way [REQ-UPDATE-110].

## User Preference

Whether the automatic startup check is enabled (REQ-NFR-030) has no
effect on the manually triggered check, which remains available
regardless of the setting's value [REQ-UPDATE-210]. The setting is
presented to the user as a checkbox on a dedicated preferences page,
reachable independently of the application's own core Preferences dialog
[REQ-UPDATE-220].

## Availability

Both the manual menu action and the automatic startup check are present
only when this capability's plugin has successfully loaded; the
application places no other requirement on either being available, and
provides no separate fallback if the plugin fails to load
[REQ-UPDATE-310]. Upgrading from a version where the startup-check
setting was stored elsewhere preserves whatever value the user had
already chosen, rather than reverting to the default on the first startup
after upgrade — determined by whether the old setting's key is still
present in the settings file, not by any separate version marker
[REQ-UPDATE-320].
