"""Small shared enums used by both the view and the controller.

Defined here, alongside `errors.py`'s exception types, so neither layer has
to import the other just to reference a plain enum with no logic (#138).
"""

from enum import Enum, auto


class CursorMode(Enum):
    """The three states cycled by the Cursor Toggle toolbar button."""

    HIDDEN = auto()
    ONE = auto()
    TWO = auto()
