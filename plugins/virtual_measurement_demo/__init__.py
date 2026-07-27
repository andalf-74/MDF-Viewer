"""Virtual Measurement Demo — proof-of-concept plugin exercising the
virtual measurement/signal pipeline end-to-end (#152/#162, follow-up to #147).

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

"Attach Extra Signal to Demo Measurement" and "Detach Counter Signal from
Demo Measurement" (#162) exercise growing/shrinking that same measurement
after it's already registered and visible — attach-after-registration,
the measurement_updated event, and detaching a signal that may currently
be plotted (the real-world Signal Calculator use case #162 was filed for).

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
- "Attach Extra Signal" appears in the Signal Browser immediately, with
  no other measurement-pool action needed first (#162, REQ-PLUGIN-520).
  "Detach Counter Signal" removes it from the plot immediately if it was
  plotted (REQ-VMEAS-135) — try this with the Counter signal plotted in
  a background (non-active) tab too, the highest-risk path the #162
  architecture review flagged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from mdf_viewer.model.signal_data import SignalData
from mdf_viewer.model.signal_metadata import SignalMetadata
from mdf_viewer.plugin_api.plugin import Plugin

if TYPE_CHECKING:
    from mdf_viewer.model.virtual_measurement_loader import VirtualMeasurementLoader
    from mdf_viewer.model.virtual_signal import VirtualSignal
    from mdf_viewer.plugin_api.context import PluginContext
    from mdf_viewer.plugin_api.types import PluginMeasurementClosedEvent, PluginMeasurementUpdatedEvent

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


def _ramp_resolver(slope: float) -> tuple[SignalData, SignalMetadata]:
    timestamps = np.linspace(0.0, _DURATION_S, _SAMPLE_COUNT)
    samples = slope * timestamps
    return SignalData(timestamps=timestamps, samples=samples), SignalMetadata(name="Ramp", unit="")


class VirtualMeasurementDemoPlugin(Plugin):
    """Creates a two-signal virtual measurement on demand, and can grow or
    shrink it afterward (#162)."""

    name = "Virtual Measurement Demo"
    version = "1.0"
    description = "Proof-of-concept plugin exercising virtual measurements (#147/#162)."
    author = "MDF-Viewer"

    def activate(self, context: "PluginContext") -> None:
        self._context = context
        self._measurement: "VirtualMeasurementLoader | None" = None
        self._counter_signal: "VirtualSignal | None" = None
        self._extra_count = 0
        context.register_menu_action("Create Virtual Measurement", self._on_create)
        context.register_menu_action("Attach Extra Signal to Demo Measurement", self._on_attach_extra)
        context.register_menu_action("Detach Counter Signal from Demo Measurement", self._on_detach_counter)

    def _on_create(self) -> None:
        context = self._context
        sine = context.create_virtual_signal("Sine Wave", _sine_wave_resolver, unit="V")
        counter = context.create_virtual_signal("Counter", _counter_resolver, unit="count")
        measurement = context.create_virtual_measurement()
        context.attach_virtual_signal(measurement, sine)
        context.attach_virtual_signal(measurement, counter)
        context.register_virtual_measurement(measurement, "Virtual Measurement Demo")
        self._measurement = measurement
        self._counter_signal = counter

    def _on_attach_extra(self) -> None:
        if self._measurement is None:
            print("[Virtual Measurement Demo] no measurement created yet — click 'Create Virtual Measurement' first")
            return
        self._extra_count += 1
        slope = float(self._extra_count)
        extra = self._context.create_virtual_signal(f"Ramp {self._extra_count}", lambda: _ramp_resolver(slope))
        self._context.attach_virtual_signal(self._measurement, extra)

    def _on_detach_counter(self) -> None:
        if self._measurement is None or self._counter_signal is None:
            print("[Virtual Measurement Demo] no measurement created yet — click 'Create Virtual Measurement' first")
            return
        self._context.detach_virtual_signal(self._measurement, self._counter_signal)
        self._counter_signal = None

    def on_measurement_closed(self, event: "PluginMeasurementClosedEvent") -> None:
        if event.is_virtual:
            print(f"[Virtual Measurement Demo] measurement_closed: label={event.label!r}")

    def on_measurement_updated(self, event: "PluginMeasurementUpdatedEvent") -> None:
        print(
            f"[Virtual Measurement Demo] measurement_updated: label={event.label!r} "
            f"signal_name={event.signal_name!r} change={event.change!r}"
        )


PLUGINS = [VirtualMeasurementDemoPlugin]
