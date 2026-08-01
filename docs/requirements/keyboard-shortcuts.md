# Requirements: Keyboard Shortcut Configuration

Part of the `docs/requirements/` collection — the single source of truth for
*what* the application does. This file covers the mechanism to rebind the
application's existing keyboard shortcuts and to switch between, save, and
load named presets of those bindings — see #111.

**Out of scope here:** adding a keyboard shortcut to an action that has none
today (tracked separately as #167), and adding any new application
functionality suggested by MDA's or CANape's own keyboard-shortcut
references that this app doesn't already have (tracked separately as
#168) — #111 only makes *existing* bindings reconfigurable. Also out of
scope: how any of this is presented on screen beyond the requirements below
(see `docs/ui.md`) and how it is implemented across Model/View/Controller
(see `docs/architecture.md`). Also explicitly out of scope: Copy Name(s)
(Ctrl+C, both the Active Signals Table and the Signal Browser) — a
copy/paste-style shortcut is deliberately never rebindable, and stays a
fixed, hardcoded Ctrl+C exactly as it was before #111.

**Conventions:** requirements are numbered `REQ-KEYS-NNN`, grouped by
sub-topic with gaps left for insertion. Each testable statement is tagged
inline so it can be cited from an issue or a test via
`@pytest.mark.requirement("REQ-KEYS-NNN")`.

---

## Rebindable Actions

Twenty actions are rebindable: the 9 existing toolbar/menu `QAction`
shortcuts (Open, Zoom to Fit, Zoom Y to View, Swimlanes, Zoom to Cursors,
Undo, Redo, Save Workspace, Exit), the 6 existing global shortcuts (Cursor 1
toggle, Cursor 2 toggle, cursor step left, cursor step right, next tab,
previous tab), 3 existing Active Signals Table shortcuts (remove signal,
toggle visibility, Y autozoom), the Cursors toolbar button's cycle action
(hidden → 1 → 2 → hidden), and Move to new Stripe [REQ-KEYS-010]. Each
rebindable action has a primary key binding and an optional secondary key
binding [REQ-KEYS-011]. Zoom to Fit's shipped default keeps both of its
existing bindings (Ctrl+0 as primary, F as secondary) [REQ-KEYS-012].

## Built-in Presets

A preset is a complete set of primary/secondary bindings for every
rebindable action [REQ-KEYS-020]. Three built-in presets ship with the
application: Default (today's shipped bindings), MDA, and CANape
[REQ-KEYS-021]. The MDA preset binds Ctrl+F12 to Zoom to Fit, Ctrl+D to Y
Autozoom, Ctrl+R to the Cursors toggle cycle, Ctrl+W to Toggle Visibility,
and Ctrl+T to Move to new Stripe; every other action keeps the Default
preset's binding [REQ-KEYS-022]. The CANape preset binds F to Zoom to Fit,
Ctrl+B to Swimlanes, F2 to Save Workspace, Alt+X to Exit, "." to Cursor 1
toggle, "," to Cursor 2 toggle, Ctrl+Left to cursor step left, and
Ctrl+Right to cursor step right; every other action keeps the Default
preset's binding [REQ-KEYS-023].

## Custom Presets

The current keymap can be saved as a named custom preset file
[REQ-KEYS-030]. A custom preset is saved as a JSON file with the `.mvck`
extension [REQ-KEYS-031]. A previously saved `.mvck` file can be loaded,
replacing the current keymap in full [REQ-KEYS-032].

## Conflict Handling

Attempting to bind a key sequence already assigned to a different action is
rejected, and the action that already owns it is named to the user
[REQ-KEYS-040].

## Preferences UI

The Preferences dialog gains a "Shortcuts" tab [REQ-KEYS-050]. Each
rebindable action is shown as a row with its label, primary key field, and
secondary key field [REQ-KEYS-051]. Clicking a key field, then pressing a
key combination, captures that combination as the field's binding
[REQ-KEYS-052]. A preset selector lists Default, MDA, CANape, and offers
actions to load or save a custom `.mvck` file [REQ-KEYS-053]. Each row has a
control resetting that action's bindings to the Default preset's values
[REQ-KEYS-054]. A "Reset All to Defaults" control resets every action to
the Default preset's values [REQ-KEYS-055].

## Persistence & Apply

The full resolved keymap is persisted directly in `Settings`, not as a
reference to a preset file [REQ-KEYS-060]. A label identifying which preset
the current keymap was last loaded from, or that it has been customized
since, is shown in the Shortcuts tab [REQ-KEYS-061]. A rebind, preset
switch, or reset takes effect immediately, without requiring an application
restart [REQ-KEYS-062].
