# Requirements: Preferences Dialog

Part of the `docs/requirements/` collection — the single source of truth for
*what* the application does. This file covers the Preferences dialog's own
behavior as a dialog (tab layout, navigation memory) — see #169. It does not
cover the individual settings the dialog exposes; those are documented
alongside the feature they belong to (e.g. cursor colors in `plotting.md`,
logging level in `logging.md`, plugin-specific settings in `plugin-api.md`).

**Out of scope here:** the content of any individual Preferences tab, and
whether a given setting applies immediately or needs a restart (both
documented per-setting in their own domain file); persisting the
last-viewed tab across an application restart — explicitly session-only,
see REQ-PREFS-011.

**Conventions:** requirements are numbered `REQ-PREFS-NNN`, grouped by
sub-topic with gaps left for insertion. Each testable statement is tagged
inline so it can be cited from an issue or a test via
`@pytest.mark.requirement("REQ-PREFS-NNN")`.

---

## Tab-Position Memory

The Preferences dialog opens on whichever tab was showing the last time it
was closed, rather than always starting on the first tab [REQ-PREFS-010].
This memory is held only for the current application session — it is not
persisted to `settings.json`, so the dialog reopens on the first tab again
after an application restart [REQ-PREFS-011]. The remembered tab updates
regardless of whether the dialog was closed via OK or Cancel, since it
reflects where the user was looking, not a setting they chose to keep
[REQ-PREFS-012].
