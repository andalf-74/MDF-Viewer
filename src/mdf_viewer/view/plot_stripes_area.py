"""PlotStripesArea — composes one or more PlotStripes into the full plot area.

This is what MainWindow builds as ``self.plot_area`` and what AppController
receives as its ``plot_area`` dependency (see ``PlotAreaProtocol``). It owns
stripe lifecycle (create/delete), signal-to-stripe routing, active-stripe
tracking, and the cross-stripe scoping rules for actions that used to be
unambiguous when there was only one plot (zoom, swimlanes, Merge/Sync axis
groups, selection).

Cursors are handled entirely outside this class — see cursors.CursorStripesView,
wired directly against this class's stripe_created/stripe_deleted/
active_stripe_changed signals in app.py.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import QVBoxLayout, QWidget

from mdf_viewer.view.plot_stripe import PlotStripe
from mdf_viewer.view.widgets import make_splitter

if TYPE_CHECKING:
    from PyQt6.QtGui import QColor

    from mdf_viewer.view_model.active_signal import ActiveSignal
    from mdf_viewer.view_model.zoom_state import ZoomState

# Debounce for range-driven axis realignment (see _range_realign_timer):
# integer-valued signals' tick labels can gain/lose digits while panning or
# zooming (e.g. "5" -> "12"), changing a stripe's axis width without any
# structural change (add/remove/move signal) to trigger a recompute. Mirrors
# ZoomController's own gesture-settle debounce rather than recomputing on
# every frame of a drag.
_RANGE_REALIGN_DEBOUNCE_MS = 300


class PlotStripesArea(QWidget):
    """Container for one or more PlotStripes, sharing one X-axis and cursors."""

    # Re-emitted from the wrapped PlotStripe(s) — see PlotStripe for meaning.
    y_grid_toggled = pyqtSignal(bool)
    file_dropped = pyqtSignal(object)
    range_changed = pyqtSignal()
    signal_clicked = pyqtSignal(object)
    # list of (measurement_index, group_index, channel_index) triples (#103)
    # and the target PlotStripe — a signal drag from the Signal Browser was
    # dropped onto a specific stripe; a single drag can span rows from
    # different loaded measurements, so each item carries its own index.
    signals_dropped_on_stripe = pyqtSignal(list, object)
    # set of id(ActiveSignal), and target PlotStripe — an already-active
    # signal was dragged from the Active Signals Table and dropped onto a
    # stripe's plot area (#116).
    active_signals_dropped_on_stripe = pyqtSignal(object, object)
    # Stripe lifecycle / focus.
    stripe_created = pyqtSignal(object)
    stripe_deleted = pyqtSignal(object)
    active_stripe_changed = pyqtSignal(object)
    # "Delete this Stripe" was chosen from a stripe's context menu — bubbled up
    # unhandled since a non-empty stripe needs a confirmation dialog (MainWindow's job).
    delete_stripe_requested = pyqtSignal(object)
    # list[int] — the stripe splitter's sizes after an interactive drag, so
    # MainWindow can mirror them onto the Active Signals Table's own segment
    # splitter (REQ-PLOT-274).
    stripe_sizes_changed = pyqtSignal(list)
    # The LoadedMeasurement whose offset_s just changed via dragging one of
    # the bottom-most stripe's per-measurement axis rows (#101) — AppController
    # listens to refresh that measurement's curves across every tab/stripe.
    measurement_offset_changed = pyqtSignal(object)
    # The bottom-most stripe's Synchronize/Un-sync button was clicked (#102)
    # — AppController owns the actual synchronized flag, so this just asks
    # it to flip and push the new state back down to every tab.
    synchronize_toggled = pyqtSignal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._splitter = make_splitter(Qt.Orientation.Vertical)
        self._stripes: list[PlotStripe] = []
        # Current global measurement pool (#101), pushed here by AppController
        # via refresh_measurement_axes() — applied to whichever stripe is
        # currently bottom-most (REQ-PLOT-301); re-applied whenever the
        # bottom-most stripe changes (create/delete).
        self._measurements: list = []
        # Whether the measurement pool's per-measurement axis rows are
        # collapsed into one shared ruler (#102) — pushed here alongside
        # self._measurements by refresh_measurement_axes(); same lifetime
        # and re-apply-on-bottom-stripe-change rules as the pool itself.
        self._synchronized: bool = False
        # Creation-order counter for default stripe names (REQ-PLOT-291),
        # scoped to this tab's PlotStripesArea — mirrors MainWindow's own
        # _tab_counter, never reused or renumbered as stripes are deleted.
        self._stripe_counter = 0
        self._active_stripe: PlotStripe | None = None
        self._signal_stripe: dict[ActiveSignal, PlotStripe] = {}
        # The stripe whose last signal_clicked hit is the current selection —
        # a miss-click in a different stripe must not clear it (REQ-PLOT-047).
        self._stripe_of_last_click: PlotStripe | None = None
        # Guards X-range broadcast below against feedback loops — same pattern
        # as PlotStripe's own _syncing_y for Synced Y-axis groups.
        self._syncing_x = False
        # Coalesces repeated axis-alignment recompute requests within the same
        # event-loop tick into a single deferred pass (see _schedule_realign).
        self._realign_pending = False
        # Guards against re-entrant stripe_sizes_changed emission from
        # set_stripe_sizes() — belt-and-suspenders, since QSplitter.setSizes()
        # does not itself re-emit splitterMoved (only an interactive drag
        # does), matching the _syncing_x/_syncing_y pattern used elsewhere.
        self._syncing_sizes = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._splitter)
        self._splitter.splitterMoved.connect(self._on_splitter_moved)

        # Re-checks axis-width alignment shortly after panning/zooming settles,
        # since tick-label digit count (and therefore axis width) can change
        # with no structural signal/stripe change at all.
        self._range_realign_timer = QTimer(self)
        self._range_realign_timer.setSingleShot(True)
        self._range_realign_timer.setInterval(_RANGE_REALIGN_DEBOUNCE_MS)
        self._range_realign_timer.timeout.connect(self._realign_axis_widths)
        self.range_changed.connect(self._range_realign_timer.start)

        self.create_stripe()

    # ------------------------------------------------------------------
    # Stripe lifecycle
    # ------------------------------------------------------------------

    def create_stripe(self) -> PlotStripe:
        """Create a new stripe, redistributing height equally (REQ-PLOT-190/192)."""
        stripe = PlotStripe()
        self._stripe_counter += 1
        stripe.name = f"Stripe {self._stripe_counter}"
        self._wire_stripe(stripe)
        self._stripes.append(stripe)
        self._splitter.addWidget(stripe)
        self._splitter.setSizes([1] * len(self._stripes))
        self._update_x_axis_tick_visibility()
        if self._active_stripe is None:
            self.set_active_stripe(stripe)
        elif len(self._stripes) > 1:
            # Bring the new stripe's X range in line with the others immediately.
            x_min, x_max = self._stripes[0].plot_item.vb.viewRange()[0]
            stripe.sync_x_range(x_min, x_max)
        self._schedule_realign()
        self.stripe_created.emit(stripe)
        # Push the post-equalization sizes so the new AST segment (just
        # created by stripe_created's connected slot, synchronously, above)
        # starts matching its stripe immediately — without this, a freshly
        # created segment keeps whatever arbitrary initial size Qt's
        # QSplitter.addWidget() gave it until a drag happens to touch that
        # specific divider (#100 postmortem: this, not rounding, was the
        # real source of the "outer segments drift" symptom).
        self.stripe_sizes_changed.emit(self._splitter.sizes())
        return stripe

    def delete_stripe(self, stripe: PlotStripe) -> bool:
        """Delete *stripe*. Refuses if it's the last one, or if it still has signals.

        Force-removing a non-empty stripe's signals first (REQ-PLOT-194) is an
        AppController-level concern, not this view's — removing a signal
        properly also means clearing its Active Signals Table row and cursor
        labels, which this class has no knowledge of. AppController.delete_stripe
        removes each signal via its own full removal pipeline before calling
        this method with an already-empty stripe.
        """
        if len(self._stripes) <= 1:
            return False
        if self.get_signals_in_stripe(stripe):
            return False

        self._stripes.remove(stripe)
        stripe.setParent(None)
        stripe.deleteLater()

        if self._active_stripe is stripe:
            self.set_active_stripe(self._stripes[0])

        self._update_x_axis_tick_visibility()
        self._schedule_realign()
        self.stripe_deleted.emit(stripe)
        # Push post-removal sizes for the same reason create_stripe() does —
        # Qt auto-redistributes the removed stripe's space on its own, and
        # the AST's segment splitter needs to match that redistribution.
        self.stripe_sizes_changed.emit(self._splitter.sizes())
        return True

    def set_active_stripe(self, stripe: PlotStripe) -> None:
        if stripe is self._active_stripe:
            return
        self._active_stripe = stripe
        for s in self._stripes:
            s.set_active(s is stripe)
        self.active_stripe_changed.emit(stripe)

    def get_active_stripe(self) -> PlotStripe:
        return self._active_stripe

    def get_stripes(self) -> list[PlotStripe]:
        return list(self._stripes)

    def get_stripe_sizes(self) -> list[int]:
        """Current absolute stripe heights, for MainWindow to push into a
        freshly bootstrapped Active Signals Table (REQ-PLOT-274) — the tab's
        first stripe (and its stripe_sizes_changed emission) already existed
        before any wiring could connect to it."""
        return self._splitter.sizes()

    def set_stripe_sizes(self, sizes: list[int]) -> None:
        """Apply stripe heights (absolute pixels) from the Active Signals
        Table's own segment splitter (REQ-PLOT-274) — each stripe's height
        matches its segment's height 1:1, which is what makes the divider
        between two stripes land at the same screen position as the divider
        between the corresponding two AST segments."""
        self._syncing_sizes = True
        try:
            self._splitter.setSizes(sizes)
        finally:
            self._syncing_sizes = False

    def _on_splitter_moved(self, pos: int, index: int) -> None:
        if self._syncing_sizes:
            return
        self.stripe_sizes_changed.emit(self._splitter.sizes())

    def get_signals_in_stripe(self, stripe: PlotStripe) -> list[ActiveSignal]:
        return [a for a, s in self._signal_stripe.items() if s is stripe]

    def get_stripe_for_signal(self, active: ActiveSignal) -> PlotStripe | None:
        return self._signal_stripe.get(active)

    def move_signal_to_stripe(self, active: ActiveSignal, target: PlotStripe) -> None:
        """Move a signal from its current stripe to *target*. No-op if already there."""
        source = self._signal_stripe.get(active)
        if source is None or source is target:
            return
        if source.get_group_type(active) is not None:
            source.ungroup_signal(active)
        source.remove_signal(active)
        target.add_signal(active)
        self._signal_stripe[active] = target
        self._schedule_realign()

    def _update_x_axis_tick_visibility(self) -> None:
        """Only the bottom-most stripe shows X-axis info (REQ-PLOT-181): either
        the plain 'Time' axis (no measurements loaded — matches pre-#101
        behavior exactly) or the per-measurement axis rows (#101,
        REQ-PLOT-301), never both. Once at least one measurement is loaded,
        the per-measurement row(s) replace the plain 'Time' axis rather than
        stacking alongside it, since they cover the same information (the
        shared display-time ruler) plus each measurement's own offset.

        When synchronized (#102), the bottom stripe shows exactly one row —
        the reference measurement's (always self._measurements[0], the
        first-loaded one) — instead of one row per measurement, and that
        row is not draggable (REQ-PLOT-311/312/314). set_show_x_axis_ticks
        still gates on the full pool, not the collapsed row list: row count
        changes, but per-measurement rows never fall back to the plain
        'Time' axis just because they collapsed to one.
        """
        for i, stripe in enumerate(self._stripes):
            is_bottom = i == len(self._stripes) - 1
            measurements_for_stripe = self._measurements if is_bottom else []
            synchronized_here = is_bottom and self._synchronized and self._measurements
            axes_to_show = [self._measurements[0]] if synchronized_here else measurements_for_stripe
            stripe.set_show_x_axis_ticks(is_bottom and not measurements_for_stripe)
            stripe.set_measurement_axes(
                axes_to_show,
                on_offset_changed=self.measurement_offset_changed.emit,
                draggable=not synchronized_here,
            )
            stripe.set_measurement_sync_control(
                visible=is_bottom and len(self._measurements) >= 2,
                synchronized=self._synchronized,
                on_toggle=self.synchronize_toggled.emit,
            )

    def refresh_measurement_axes(self, measurements: list, synchronized: bool = False) -> None:
        """Push the current measurement pool (#101) and sync state (#102) to
        the bottom-most stripe.

        Called by AppController whenever the pool or synchronized flag
        changes; _update_x_axis_tick_visibility() re-applies both on its own
        whenever the bottom-most stripe itself changes (stripe create/
        delete), so the axis rows always follow whichever stripe
        REQ-PLOT-301 currently designates without this needing to be called
        again for that case.
        """
        self._measurements = measurements
        self._synchronized = synchronized
        self._update_x_axis_tick_visibility()

    def _schedule_realign(self) -> None:
        """Defer axis-width realignment to let Qt finish laying out the new axis first.

        A freshly added/resized AxisItem's width() isn't accurate until Qt has
        run a layout pass; deferring via singleShot(0) also coalesces several
        structural changes in the same event-loop tick (e.g. adding several
        signals at once) into a single recompute.
        """
        if self._realign_pending:
            return
        self._realign_pending = True
        QTimer.singleShot(0, self._realign_axis_widths)

    def _realign_axis_widths(self) -> None:
        """Pad every stripe's axis area so all stripes' viewports share one pixel width.

        Each stripe is a separate PlotWidget whose Y-axis columns auto-size
        independently — with a different number (or tick-label width) of
        signals per stripe, the same X value would otherwise land at a
        different screen position in each stripe.
        """
        self._realign_pending = False
        if not self._stripes:
            return
        if len(self._stripes) == 1:
            self._stripes[0].set_axis_padding(0)
            return
        widths = {s: s.content_axis_width() for s in self._stripes}
        max_width = max(widths.values())
        for s in self._stripes:
            s.set_axis_padding(max_width - widths[s])

    def _wire_stripe(self, stripe: PlotStripe) -> None:
        stripe.y_grid_toggled.connect(self.y_grid_toggled)
        stripe.file_dropped.connect(self.file_dropped)
        stripe.range_changed.connect(self.range_changed)
        stripe.signal_clicked.connect(lambda active, s=stripe: self._on_signal_clicked(s, active))
        stripe.signals_dropped.connect(
            lambda locs, s=stripe: self.signals_dropped_on_stripe.emit(locs, s)
        )
        stripe.active_signals_dropped.connect(
            lambda ids, s=stripe: self.active_signals_dropped_on_stripe.emit(ids, s)
        )
        stripe.activated.connect(self.set_active_stripe)
        stripe.create_stripe_requested.connect(lambda _s: self.create_stripe())
        stripe.delete_stripe_requested.connect(self.delete_stripe_requested)
        stripe.plot_item.vb.sigXRangeChanged.connect(
            lambda vb, rng, s=stripe: self._on_stripe_x_changed(s, rng)
        )

    def _on_stripe_x_changed(self, source: PlotStripe, x_range: tuple[float, float]) -> None:
        """Broadcast one stripe's X range to every other stripe (X is shared/global).

        Guarded against feedback loops the same way PlotStripe guards Synced
        Y-axis groups (_syncing_y): pyqtgraph's setXLink only lets a view
        listen to a single other view, which can't express "any stripe may
        drive all the others," so this is done manually instead.
        """
        if self._syncing_x:
            return
        self._syncing_x = True
        try:
            for stripe in self._stripes:
                if stripe is not source:
                    stripe.sync_x_range(x_range[0], x_range[1])
        finally:
            self._syncing_x = False

    def _on_signal_clicked(self, source: PlotStripe, active: ActiveSignal | None) -> None:
        if active is not None:
            self._stripe_of_last_click = source
            self.signal_clicked.emit(active)
            return
        # Miss-click: only clears the selection if it happened in the stripe
        # that owns it — a miss elsewhere must not clear a different stripe's
        # selection (REQ-PLOT-047).
        if self._stripe_of_last_click is None or source is self._stripe_of_last_click:
            self.signal_clicked.emit(None)

    # ------------------------------------------------------------------
    # plot_item passthrough — X is shared, so any one stripe's is representative.
    # ------------------------------------------------------------------

    @property
    def plot_item(self):
        return self._stripes[0].plot_item

    # ------------------------------------------------------------------
    # PlotAreaProtocol — per-signal delegation
    # ------------------------------------------------------------------

    def add_signal(self, active: ActiveSignal, stripe: PlotStripe | None = None) -> None:
        target = stripe or self._active_stripe
        target.add_signal(active)
        self._signal_stripe[active] = target
        self._schedule_realign()

    def remove_signal(self, active: ActiveSignal) -> None:
        stripe = self._signal_stripe.pop(active, None)
        if stripe is not None:
            stripe.remove_signal(active)
            self._schedule_realign()

    def recolor_signal(self, active: ActiveSignal, color: QColor) -> None:
        stripe = self._signal_stripe.get(active)
        if stripe is not None:
            stripe.recolor_signal(active, color)

    def set_step_mode(self, active: ActiveSignal, step_mode: bool) -> None:
        stripe = self._signal_stripe.get(active)
        if stripe is not None:
            stripe.set_step_mode(active, step_mode)

    def set_signal_visible(self, active: ActiveSignal, visible: bool) -> None:
        stripe = self._signal_stripe.get(active)
        if stripe is not None:
            stripe.set_signal_visible(active, visible)

    def refresh_signal_data(self, active: ActiveSignal) -> None:
        stripe = self._signal_stripe.get(active)
        if stripe is not None:
            stripe.refresh_signal_data(active)

    def set_display_mode(self, active: ActiveSignal, mode: str, shape: str) -> None:
        stripe = self._signal_stripe.get(active)
        if stripe is not None:
            stripe.set_display_mode(active, mode, shape)

    def set_line_width(self, active: ActiveSignal, width: int) -> None:
        stripe = self._signal_stripe.get(active)
        if stripe is not None:
            stripe.set_line_width(active, width)

    def set_line_style(self, active: ActiveSignal, style: str) -> None:
        stripe = self._signal_stripe.get(active)
        if stripe is not None:
            stripe.set_line_style(active, style)

    def set_enum_display_yaxis(self, active: ActiveSignal, enabled: bool) -> None:
        stripe = self._signal_stripe.get(active)
        if stripe is not None:
            stripe.set_enum_display_yaxis(active, enabled)

    def set_y_grid(self, active: ActiveSignal, enabled: bool) -> None:
        stripe = self._signal_stripe.get(active)
        if stripe is not None:
            stripe.set_y_grid(active, enabled)

    def set_selected_signals(
        self,
        selected: list[ActiveSignal],
        all_signals: list[ActiveSignal] | None = None,
        top_first: bool = True,
    ) -> None:
        # Fanned out unmodified: each stripe's own Z-order math only ever
        # touches signals it actually owns, so passing the full global list
        # to every stripe is correct (cross-stripe Z comparisons are moot —
        # stripes never visually overlap).
        for stripe in self._stripes:
            stripe.set_selected_signals(selected, all_signals=all_signals, top_first=top_first)
        self._schedule_realign()

    def set_selected_line_boost(self, value: int) -> None:
        for stripe in self._stripes:
            stripe.set_selected_line_boost(value)

    def set_show_only_selected_y_axis(self, enabled: bool) -> None:
        for stripe in self._stripes:
            stripe.set_show_only_selected_y_axis(enabled)
        self._schedule_realign()

    def swimlanes(self, signals: list[ActiveSignal]) -> bool:
        # Always scoped to the active stripe (REQ-PLOT-057), unaffected by
        # the All Stripes/Active Stripe zoom-scope toggle.
        active_stripe = self._active_stripe
        own = [s for s in signals if self._signal_stripe.get(s) is active_stripe]
        return active_stripe.swimlanes(own)

    def zoom_to_fit(self, all_stripes: bool = True) -> None:
        """Reset X to the full data range across every stripe (always global).

        Y-autorange is scoped by *all_stripes* — every stripe, or only the
        active one — per the "All Stripes / Active Stripe" toggle
        (REQ-PLOT-057); Swimlanes and box-zoom are unaffected by it. A
        hidden signal's data range is excluded (#133, REQ-PLOT-337).
        """
        signals = [a for a in self._signal_stripe if a.visible]
        if not signals:
            return
        t_min = min(float(a.display_timestamps[0]) for a in signals if len(a.data.timestamps))
        t_max = max(float(a.display_timestamps[-1]) for a in signals if len(a.data.timestamps))
        self.zoom_to_x_range(t_min, t_max)
        for stripe in (self._stripes if all_stripes else [self._active_stripe]):
            stripe.autorange_y()

    def zoom_y_to_view(self, all_stripes: bool = True) -> bool:
        """Rescale Y to the currently visible X range, scoped by *all_stripes*
        the same way as zoom_to_fit() (REQ-PLOT-057)."""
        if not self._signal_stripe:
            return False
        for stripe in (self._stripes if all_stripes else [self._active_stripe]):
            stripe.zoom_y_to_view()
        return True

    def zoom_to_x_range(self, x_min: float, x_max: float) -> None:
        # X is shared/linked across all stripes — setting it on any one
        # (here, the anchor) propagates to every other stripe.
        self._stripes[0].zoom_to_x_range(x_min, x_max)

    def merge_signals(self, signals: list[ActiveSignal]) -> None:
        stripe = self._same_stripe_or_none(signals)
        if stripe is not None:
            stripe.merge_signals(signals)
            self._schedule_realign()

    def sync_signals(self, signals: list[ActiveSignal]) -> None:
        stripe = self._same_stripe_or_none(signals)
        if stripe is not None:
            stripe.sync_signals(signals)
            self._schedule_realign()

    def _same_stripe_or_none(self, signals: list[ActiveSignal]) -> PlotStripe | None:
        """Return the common owning stripe of *signals*, or None if they span stripes.

        Merged/Synced groups must be confined to one stripe (REQ-PLOT-038).
        """
        stripes = {self._signal_stripe.get(s) for s in signals}
        if len(stripes) != 1:
            return None
        return next(iter(stripes))

    def ungroup_signal(self, active: ActiveSignal) -> None:
        stripe = self._signal_stripe.get(active)
        if stripe is not None:
            stripe.ungroup_signal(active)
            self._schedule_realign()

    def get_grouped_signals(self) -> set:
        result: set = set()
        for stripe in self._stripes:
            result |= stripe.get_grouped_signals()
        return result

    def get_merged_signals(self) -> set:
        result: set = set()
        for stripe in self._stripes:
            result |= stripe.get_merged_signals()
        return result

    def get_synced_signals(self) -> set:
        result: set = set()
        for stripe in self._stripes:
            result |= stripe.get_synced_signals()
        return result

    def get_group_type(self, active: ActiveSignal) -> str | None:
        stripe = self._signal_stripe.get(active)
        return stripe.get_group_type(active) if stripe is not None else None

    def get_axis_grouping(self) -> tuple[list[list[tuple]], list[list[tuple]]]:
        merged: list[list[tuple]] = []
        synced: list[list[tuple]] = []
        for stripe in self._stripes:
            m, s = stripe.get_axis_grouping()
            merged.extend(m)
            synced.extend(s)
        return merged, synced

    def restore_axis_grouping(
        self,
        merged: list[list[tuple]],
        synced: list[list[tuple]],
        active_signals: list,
    ) -> None:
        """Restore merged/synced groups from (name, measurement) pairs (#106).

        Delegates to merge_signals/sync_signals, which already validate
        same-stripe membership (REQ-PLOT-038) and no-op otherwise. Matching
        by (name, measurement) rather than bare name is required once more
        than one loaded measurement can share a channel name in the same
        tab — a bare-name match would silently resolve to whichever
        same-named signal happens to win a dict-key collision, potentially
        grouping the wrong measurement's signal (found via live-testing,
        #106 M6). Keyed by id(measurement), not the measurement object
        itself — LoadedMeasurement is a plain, unhashable @dataclass
        (mutable, field-equality __eq__); id() also gives identity rather
        than value-equality matching, avoiding a second bug class where two
        distinct measurements sharing the same path/label/offset would
        otherwise spuriously match.
        """
        key_map = {(a.metadata.name, id(a.measurement)): a for a in active_signals}
        for group_refs in merged:
            keys = [(name, id(m)) for name, m in group_refs]
            actives = [key_map[k] for k in keys if k in key_map]
            if len(actives) >= 2:
                self.merge_signals(actives)
        for group_refs in synced:
            keys = [(name, id(m)) for name, m in group_refs]
            actives = [key_map[k] for k in keys if k in key_map]
            if len(actives) >= 2:
                self.sync_signals(actives)

    def get_zoom_state(self, active_signals: list) -> ZoomState:
        # X is read from the anchor (all stripes share it); Y is read via
        # each signal's own view_box regardless of stripe — both already
        # correct without needing to know which stripe owns what.
        return self._stripes[0].get_zoom_state(active_signals)

    def set_zoom_state(self, state: ZoomState, active_signals: list) -> None:
        self._stripes[0].set_zoom_state(state, active_signals)
