"""CursorController — owns cursor toggle state and position memory.

Cursor behaviour is self-contained enough to isolate from AppController:
  * toggle cycle: 1 cursor -> 2 cursors -> hidden -> (repeat)
  * remembers each cursor's last position across hide/show
  * computes which cursor is nearest the mouse (for value-label display)
  * computes per-signal cursor values and the cursor-2-minus-cursor-1 delta
"""

from __future__ import annotations

from enum import Enum, auto


class CursorMode(Enum):
    """The three states cycled by the Cursor Toggle toolbar button."""

    HIDDEN = auto()
    ONE = auto()
    TWO = auto()


class CursorController:
    """Manages cursor mode, remembered positions, and value computation."""

    # To be implemented:
    #   toggle() -> advances ONE -> TWO -> HIDDEN -> ONE
    #   positions remembered between hide/show
    #   value_at(signal, cursor_index) and delta(signal)
