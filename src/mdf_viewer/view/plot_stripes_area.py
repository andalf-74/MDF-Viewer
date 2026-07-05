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
    # list of (group_index, channel_index), target PlotStripe — a signal drag
    # from the Signal Browser was dropped onto a specific stripe.
    signals_dropped_on_stripe = pyqtSignal(list, object)
    # Stripe lifecycle / focus.
    stripe_created = pyqtSignal(object)
    stripe_deleted = pyqtSignal(object)
    active_stripe_changed = pyqtSignal(object)
    # "Delete this Stripe" was chosen from a stripe's context menu — bubbled up
    # unhandled since a non-empty stripe needs a confirmation dialog (MainWindow's job).
    delete_stripe_requested = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)

        self._splitter = make_splitter(Qt.Orientation.Vertical)
        self._stripes: list[PlotStripe] = []
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

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._splitter)

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
        """Only the bottom-most stripe shows X-axis tick labels (REQ-PLOT-181)."""
        for i, stripe in enumerate(self._stripes):
            stripe.set_show_x_axis_ticks(i == len(self._stripes) - 1)

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
        (REQ-PLOT-057); Swimlanes and box-zoom are unaffected by it.
        """
        signals = list(self._signal_stripe)
        if not signals:
            return
        t_min = min(float(a.data.timestamps[0]) for a in signals if len(a.data.timestamps))
        t_max = max(float(a.data.timestamps[-1]) for a in signals if len(a.data.timestamps))
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

    def get_axis_grouping(self) -> tuple[list[list[str]], list[list[str]]]:
        merged: list[list[str]] = []
        synced: list[list[str]] = []
        for stripe in self._stripes:
            m, s = stripe.get_axis_grouping()
            merged.extend(m)
            synced.extend(s)
        return merged, synced

    def restore_axis_grouping(
        self,
        merged: list[list[str]],
        synced: list[list[str]],
        active_signals: list,
    ) -> None:
        # Delegates to merge_signals/sync_signals, which already validate
        # same-stripe membership (REQ-PLOT-038) and no-op otherwise — correct
        # as long as a restored session's signals all land in one stripe,
        # which holds today since stripe layout isn't part of a saved session
        # (workspace/config persistence for stripes is issue #106).
        name_map = {a.metadata.name: a for a in active_signals}
        for group_names in merged:
            actives = [name_map[n] for n in group_names if n in name_map]
            if len(actives) >= 2:
                self.merge_signals(actives)
        for group_names in synced:
            actives = [name_map[n] for n in group_names if n in name_map]
            if len(actives) >= 2:
                self.sync_signals(actives)

    def get_zoom_state(self, active_signals: list) -> ZoomState:
        # X is read from the anchor (all stripes share it); Y is read via
        # each signal's own view_box regardless of stripe — both already
        # correct without needing to know which stripe owns what.
        return self._stripes[0].get_zoom_state(active_signals)

    def set_zoom_state(self, state: ZoomState, active_signals: list) -> None:
        self._stripes[0].set_zoom_state(state, active_signals)
