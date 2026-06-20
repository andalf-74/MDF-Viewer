"""Application-level exception types.

Defined here so both the model and the view can import a shared error class
without either layer depending on the other.
"""


class MdfLoadError(Exception):
    """Raised when an MDF file cannot be opened or read.

    The controller/view should catch this and present the message to the user;
    the application must never crash on malformed or incomplete MDF content.
    """
