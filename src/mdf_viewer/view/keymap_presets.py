"""keymap_presets.py — the 20 rebindable actions and the three built-in
keyboard-shortcut presets (Default, MDA, CANape) for #111.

Pure data: `DEFAULT_PRESET`/`MDA_PRESET`/`CANAPE_PRESET` are transcribed
from what `main_window.py`/`active_signals_table.py` hardcoded before
#111 (see `docs/requirements/keyboard-shortcuts.md` REQ-KEYS-010–023).
`MainWindow.apply_keymap()` is what actually pushes a resolved mapping
onto the real `QAction`/`QShortcut` objects and the AST's
`keyPressEvent`-based dispatch — nothing in this module touches a live
Qt widget.

A binding's primary slot may be the empty `QKeySequence()` (REQ-KEYS-010's
"Cursors toggle" and "Move to new Stripe" both start unbound); the
secondary slot is `None` when unused.

Copy Name(s) (Ctrl+C, both the Active Signals Table and Signal Browser)
is deliberately excluded from rebindable scope entirely — live-testing
surfaced real friction rebinding it (a stray already-bound Ctrl+C on one
widget blocking a rebind attempt on the other), and direct user feedback
settled that a copy/paste-style shortcut isn't something a user should
be able to reassign in the first place. Both widgets keep a hardcoded
Ctrl+C check in their own `keyPressEvent`, exactly as before #111.
"""

from __future__ import annotations

import json
from pathlib import Path

from PyQt6.QtGui import QKeySequence

Keybinding = tuple[QKeySequence, "QKeySequence | None"]

# Order here is also the row order in the Preferences "Shortcuts" tab.
ACTION_LABELS: dict[str, str] = {
    "open_file": "Open…",
    "zoom_to_fit": "Zoom to Fit",
    "zoom_y_to_view": "Zoom Y to View",
    "swimlanes": "Swimlanes",
    "zoom_to_cursors": "Zoom to Cursors",
    "cursor_toggle": "Cycle Cursors",
    "undo": "Undo",
    "redo": "Redo",
    "save_workspace": "Save Workspace",
    "exit": "Exit",
    "cursor1_toggle": "Toggle one Cursor",
    "cursor2_toggle": "Toggle both Cursors",
    "cursor_step_left": "Step Active Cursor Left",
    "cursor_step_right": "Step Active Cursor Right",
    "next_tab": "Next Tab",
    "prev_tab": "Previous Tab",
    "ast_remove_signal": "Remove Signal",
    "ast_toggle_visibility": "Toggle Signal Visibility",
    "ast_y_autozoom": "Y Autozoom",
    "ast_move_to_new_stripe": "Move Signal to New Stripe",
    # Copy Name(s) (Ctrl+C, both Active Signals Table and Signal Browser)
    # is deliberately NOT rebindable — a copy/paste-style shortcut isn't
    # something a user should be able to reassign (#111, direct user
    # feedback after live-testing).
}

ACTION_IDS: list[str] = list(ACTION_LABELS)


def _preset(pairs: dict[str, tuple[str, "str | None"]]) -> dict[str, Keybinding]:
    """Build a full preset from {action_id: (primary_str, secondary_str_or_None)}."""
    return {
        action_id: (QKeySequence(primary), QKeySequence(secondary) if secondary else None)
        for action_id, (primary, secondary) in pairs.items()
    }


DEFAULT_PRESET: dict[str, Keybinding] = _preset({
    "open_file": ("Ctrl+O", None),
    "zoom_to_fit": ("Ctrl+0", "F"),
    "zoom_y_to_view": ("Y", None),
    "swimlanes": ("B", None),
    "zoom_to_cursors": ("C", None),
    "cursor_toggle": ("", None),
    "undo": ("Ctrl+Z", None),
    "redo": ("Ctrl+Shift+Z", None),
    "save_workspace": ("Ctrl+S", None),
    "exit": ("Ctrl+Q", None),
    "cursor1_toggle": (".", None),
    "cursor2_toggle": (",", None),
    "cursor_step_left": ("Left", None),
    "cursor_step_right": ("Right", None),
    "next_tab": ("Ctrl+Tab", None),
    "prev_tab": ("Ctrl+Shift+Tab", None),
    "ast_remove_signal": ("Del", "Backspace"),
    "ast_toggle_visibility": ("Ctrl+W", None),
    "ast_y_autozoom": ("Ctrl+D", None),
    "ast_move_to_new_stripe": ("", None),
})

# REQ-KEYS-022 — every other action keeps DEFAULT_PRESET's value.
MDA_PRESET: dict[str, Keybinding] = {
    **DEFAULT_PRESET,
    **_preset({
        "zoom_to_fit": ("Ctrl+F12", None),
        "ast_y_autozoom": ("Ctrl+D", None),
        "cursor_toggle": ("Ctrl+R", None),
        "ast_toggle_visibility": ("Ctrl+W", None),
        "ast_move_to_new_stripe": ("Ctrl+T", None),
    }),
}

# REQ-KEYS-023 — every other action keeps DEFAULT_PRESET's value.
CANAPE_PRESET: dict[str, Keybinding] = {
    **DEFAULT_PRESET,
    **_preset({
        "zoom_to_fit": ("F", None),
        "swimlanes": ("Ctrl+B", None),
        "save_workspace": ("F2", None),
        "exit": ("Alt+X", None),
        "cursor1_toggle": (".", None),
        "cursor2_toggle": (",", None),
        "cursor_step_left": ("Ctrl+Left", None),
        "cursor_step_right": ("Ctrl+Right", None),
    }),
}

BUILTIN_PRESETS: dict[str, dict[str, Keybinding]] = {
    "Default": DEFAULT_PRESET,
    "MDA": MDA_PRESET,
    "CANape": CANAPE_PRESET,
}


class KeymapValidationError(Exception):
    """Raised by load_mvck() when a .mvck file's content is malformed."""


def keymap_to_dict(keymap: dict[str, Keybinding]) -> dict[str, dict[str, "str | None"]]:
    """The plain-data shape stored in Settings.keymap and .mvck files."""
    return {
        action_id: {
            "primary": primary.toString(),
            "secondary": secondary.toString() if secondary is not None else None,
        }
        for action_id, (primary, secondary) in keymap.items()
    }


def keymap_from_dict(data: dict[str, dict[str, "str | None"]]) -> dict[str, Keybinding]:
    """Inverse of keymap_to_dict(). Any action id missing from *data* falls
    back to DEFAULT_PRESET's value (forward-compatible with a future
    action added after a preset file was saved)."""
    keymap = dict(DEFAULT_PRESET)
    for action_id, value in data.items():
        if action_id not in ACTION_IDS:
            continue
        primary = QKeySequence(value.get("primary") or "")
        secondary_str = value.get("secondary")
        secondary = QKeySequence(secondary_str) if secondary_str else None
        keymap[action_id] = (primary, secondary)
    return keymap


def save_mvck(path: "Path | str", keymap: dict[str, Keybinding], label: str) -> None:
    """Write *keymap* to *path* as a named .mvck preset file (REQ-KEYS-031)."""
    payload = {"label": label, "keymap": keymap_to_dict(keymap)}
    Path(path).write_text(json.dumps(payload, indent=2), encoding="utf-8")


def load_mvck(path: "Path | str") -> tuple[dict[str, Keybinding], str]:
    """Read a .mvck file, returning (keymap, label). Raises
    KeymapValidationError if the content isn't a valid keymap file
    (REQ-KEYS-032)."""
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise KeymapValidationError(f"Could not read '{path}': {exc}") from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("keymap"), dict):
        raise KeymapValidationError(f"'{path}' is not a valid keyboard shortcut preset file.")
    label = payload.get("label")
    if not isinstance(label, str) or not label:
        label = Path(path).stem
    try:
        keymap = keymap_from_dict(payload["keymap"])
    except (AttributeError, TypeError) as exc:
        raise KeymapValidationError(f"'{path}' is not a valid keyboard shortcut preset file.") from exc
    return keymap, label
