"""MdfLoader — the only module that imports ``asammdf``.

Isolating all file I/O here means the rest of the application depends on plain
data classes (SignalData, SignalMetadata, MeasurementInfo) rather than on the
asammdf API. It is also the single place responsible for catching malformed or
unexpected MDF content and surfacing it as a clean error.
"""

from __future__ import annotations


class MdfLoadError(Exception):
    """Raised when an MDF file cannot be opened or read.

    The controller/view should catch this and present the message to the user;
    the application must never crash on malformed or incomplete MDF content.
    """


class MdfLoader:
    """Loads an MDF file and exposes its hierarchy, signals, and metadata.

    Wraps ``asammdf.MDF``. To be implemented:
      * open a file (MDF3 or MDF4), translating any failure into MdfLoadError
      * enumerate channel groups -> channels for the Signal Browser tree
      * read a single channel into a SignalData + SignalMetadata pair
      * extract file-level MeasurementInfo
    """
