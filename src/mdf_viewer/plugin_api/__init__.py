"""Plugin API — the programmatic surface exposed to plugins (#71).

``PluginContext`` (``plugin_api.context``) is the only object a plugin is
ever allowed to import from the application. Everything here is a
read-only facade or a registration surface — no plugin ever receives a
live, mutable application object (``ActiveSignal``, ``LoadedMeasurement``,
``AppController``) directly.
"""

from __future__ import annotations
