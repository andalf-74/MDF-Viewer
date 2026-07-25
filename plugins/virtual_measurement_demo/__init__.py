"""Virtual Measurement Demo — proof-of-concept plugin exercising the
virtual measurement/signal pipeline end-to-end (#152, follow-up to #147).

Registers a "Create Virtual Measurement" menu action that builds a
two-signal virtual measurement (a sine wave and a monotonic counter) and
adds it to the pool, the same way #75 (Signal Statistics) was the first
real end-to-end validation of #71-#74's plugin groundwork rather than a
built-in feature of its own. Exercises create_virtual_signal(),
create_virtual_measurement(), attach_virtual_signal(), and
register_virtual_measurement() together for the first time outside a
test — proving the Signal Browser's "(virtual)" badge, the Measurement
Info Box's disabled Replace…, and offset/Primary/Sync all behave
correctly for a real (if synthetic) virtual measurement.

Not shipped in the packaged app (installer/portable) — lives in the
repo's plugins/ directory, matching signal_statistics/tab_type_fixture/
preferences_fixture's precedent exactly.

Live-test notes:
- "User-initiated close" (File → Close Measurement) is observable
  directly: this plugin's on_measurement_closed logs any virtual
  measurement close while it's still active to confirm the event
  reaches it normally.
- "Plugin-deactivation teardown" (Reload this plugin) is NOT observable
  the same way: PluginContext._teardown() deliberately unsubscribes a
  plugin from measurement_closed before removing its own virtual
  measurements (REQ-PLUGIN-301), so a plugin never receives its own
  teardown's closure event. Confirm this path instead by watching the
  measurement disappear from the Signal Browser after Reload.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.plugin_api.plugin import Plugin

if TYPE_CHECKING:
    from mdf_viewer.plugin_api.context import PluginContext
    from mdf_viewer.plugin_api.types import PluginMeasurementClosedEvent

_DURATION_S = 10.0
_SAMPLE_COUNT = 1000


def _sine_wave_resolver() -> tuple[SignalData, SignalMetadata]:
    timestamps = np.linspace(0.0, _DURATION_S, _SAMPLE_COUNT)
    samples = np.sin(2 * np.pi * 0.5 * timestamps)
    return SignalData(timestamps=timestamps, samples=samples), SignalMetadata(name="Sine Wave", unit="V")


def _counter_resolver() -> tuple[SignalData, SignalMetadata]:
    timestamps = np.linspace(0.0, _DURATION_S, _SAMPLE_COUNT)
    samples = np.arange(_SAMPLE_COUNT, dtype=np.float64)
    return SignalData(timestamps=timestamps, samples=samples), SignalMetadata(name="Counter", unit="count")


class VirtualMeasurementDemoPlugin(Plugin):
    """Creates a two-signal virtual measurement on demand."""

    name = "Virtual Measurement Demo"
    version = "1.0"
    description = "Proof-of-concept plugin exercising virtual measurements (#147)."
    author = "MDF-Viewer"

    def activate(self, context: "PluginContext") -> None:
        self._context = context
        context.register_menu_action("Create Virtual Measurement", self._on_create)

    def _on_create(self) -> None:
        context = self._context
        sine = context.create_virtual_signal("Sine Wave", _sine_wave_resolver, unit="V")
        counter = context.create_virtual_signal("Counter", _counter_resolver, unit="count")
        measurement = context.create_virtual_measurement()
        context.attach_virtual_signal(measurement, sine)
        context.attach_virtual_signal(measurement, counter)
        context.register_virtual_measurement(measurement, "Virtual Measurement Demo")

    def on_measurement_closed(self, event: "PluginMeasurementClosedEvent") -> None:
        if event.is_virtual:
            print(f"[Virtual Measurement Demo] measurement_closed: label={event.label!r}")


PLUGINS = [VirtualMeasurementDemoPlugin]
