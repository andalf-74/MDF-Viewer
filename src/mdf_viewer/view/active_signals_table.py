"""ActiveSignalsTable — per-stripe segments of signals currently on the plot.

A facade over: one shared header row (never given rows, the only visible/
interactive header — REQ-PLOT-272), a vertical splitter of per-stripe
"segments" (one `_ActiveTable` QTableWidget per stripe, own scrollbar, own
hidden header — REQ-PLOT-270/275), and one Remove Signal/Remove All button
row spanning the whole area (REQ-PLOT-280).

Columns: color swatch | name | cursor 1 value | cursor 2 value | delta.
Cursor-value columns are hidden until cursors are activated.
Selection in this table drives the Signal Info Box via selection_changed.
Multi-select is supported (ExtendedSelection). Right-clicking a row that is
already part of the selection does not change the selection.

Segments are created/destroyed reactively via add_stripe_segment()/
remove_stripe_segment(), driven by PlotStripesArea's stripe_created/
stripe_deleted signals (wired in MainWindow._wire_tab_view, which also
bootstraps the stripe(s) that already existed before wiring connected).

Data model: there is ONE ordered list of active signals for the whole tab
(`self._signals`, mirroring AppController's own `TabWorkspace.active`) plus
one external mapping of signal -> stripe (`self._stripe_for_signal`,
mirroring `PlotStripesArea._signal_stripe`). A segment's rows are never
independently tracked — they are always a pure rendering of "the signals
whose stripe is this segment's stripe, in list order" (see
_segment_signals). This is deliberate: an earlier version gave each segment
its own independent signal list that had to be kept in sync by hand, and a
gap in that sync (moving a signal to a different stripe never told the view)
is what orphaned a row's AST entry when its old stripe was deleted (#100
postmortem). Deriving segment contents from one shared list instead of
tracking N parallel copies makes that class of bug structurally impossible.
"""

from __future__ import annotations

from typing import Callable

from PyQt6.QtCore import QByteArray, QEvent, QMimeData, QPoint, Qt, pyqtSignal
from PyQt6.QtGui import QAction, QColor, QDrag, QKeyEvent, QMouseEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QColorDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMenu,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from mdf_viewer.view._mime import (
    ROW_MIME_TYPE,
    SIGNAL_MIME_TYPE,
    decode_row_payload,
    decode_signal_payload,
    encode_row_payload,
)
from mdf_viewer.view.widgets import ColorSwatch, make_splitter
from mdf_viewer.view_model.active_signal import ActiveSignal

_COL_COLOR = 0
_COL_NAME = 1
_COL_C1 = 2
_COL_C2 = 3
_COL_DELTA = 4
_NUM_COLS = 5

_CURSOR_COLS = (_COL_C1, _COL_C2, _COL_DELTA)
_HEADERS = ("", "Signal", "Cursor 1", "Cursor 2", "Δ")


def _ro_item(text: str) -> QTableWidgetItem:
    """A non-editable QTableWidgetItem."""
    item = QTableWidgetItem(text)
    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
    return item


def _configure_columns(table: QTableWidget) -> None:
    """Column layout shared by the header widget and every per-stripe segment.

    Keeping this in one place is what lets the header's column widths and
    every segment's column widths line up pixel-for-pixel (REQ-PLOT-271).
    """
    table.setColumnCount(_NUM_COLS)
    table.setHorizontalHeaderLabels(_HEADERS)
    hdr = table.horizontalHeader()
    hdr.setSectionResizeMode(_COL_COLOR, QHeaderView.ResizeMode.Fixed)
    table.setColumnWidth(_COL_COLOR, 28)
    hdr.setSectionResizeMode(_COL_NAME, QHeaderView.ResizeMode.Interactive)
    table.setColumnWidth(_COL_NAME, 120)
    for col in _CURSOR_COLS:
        hdr.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        table.setColumnWidth(col, 80)
    hdr.setStretchLastSection(False)
    for col in _CURSOR_COLS:
        table.setColumnHidden(col, True)


class _ActiveTable(QTableWidget):
    """One stripe's segment: a QTableWidget rendering that stripe's rows.

    Holds no signal data of its own — ActiveSignalsTable derives its rows
    from the facade's single shared signal list on every structural change.
    Only transient drag state lives here.
    """

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(0, _NUM_COLS, parent)
        self._drag_start_pos: QPoint | None = None
        # True once a drag has actually started during the current press
        # (i.e. mouseMoveEvent crossed the drag-distance threshold) — lets
        # mouseReleaseEvent tell a genuine click-release apart from the end
        # of a drag gesture.
        self._drag_happened: bool = False
        # All three set by ActiveSignalsTable._add_segment() after
        # construction (need a reference to this instance, which doesn't
        # exist yet mid-__init__).
        # on_mouse_press: called at the top of every press so the facade can
        # activate this segment's stripe (REQ-PLOT-278) and clear sibling
        # segments' selection (REQ-PLOT-276) before Qt's own native click
        # handling runs — except when the press landed on an already-
        # selected row, where clearing is deferred to on_click_release (see
        # there for why).
        self.on_mouse_press: Callable[[QMouseEvent], None] | None = None
        # on_drag_start: called once the mouse has moved far enough past a
        # press on a row to count as a drag gesture (REQ-PLOT-279).
        self.on_drag_start: Callable[["_ActiveTable"], None] | None = None
        # on_click_release: called on mouse release only when no drag
        # happened this press (REQ-PLOT-276/279 — see on_mouse_press).
        self.on_click_release: Callable[[QMouseEvent], None] | None = None
        # Both set by ActiveSignalsTable._add_segment() right after
        # construction (REQ-PLOT-290): name_label is this segment's stripe-
        # name row; container is the small wrapper widget stacking
        # [name_label, self] that actually goes into the segments splitter
        # (self itself does not — see _add_segment).
        self.name_label: "_SegmentLabel | None" = None
        self.container: "QWidget | None" = None

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._drag_happened = False
        if self.on_mouse_press is not None:
            self.on_mouse_press(event)
        if event.button() == Qt.MouseButton.LeftButton:
            idx = self.indexAt(event.position().toPoint())
            self._drag_start_pos = event.position().toPoint() if idx.isValid() else None
        if event.button() == Qt.MouseButton.RightButton:
            idx = self.indexAt(event.position().toPoint())
            if idx.isValid():
                selected = {r.row() for r in self.selectionModel().selectedRows()}
                if idx.row() in selected:
                    return  # keep current selection; context menu fires separately
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            self._drag_start_pos is not None
            and event.buttons() & Qt.MouseButton.LeftButton
            and (event.position().toPoint() - self._drag_start_pos).manhattanLength()
            >= QApplication.startDragDistance()
        ):
            self._drag_start_pos = None
            self._drag_happened = True
            if self.on_drag_start is not None:
                self.on_drag_start(self)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_start_pos = None
        if not self._drag_happened and self.on_click_release is not None:
            self.on_click_release(event)
        super().mouseReleaseEvent(event)


class _SegmentLabel(QLabel):
    """Stripe-name label occupying its own row above a segment's data rows
    (REQ-PLOT-290) — a dedicated layout row, not an overlay: an early
    version floated it over the segment's top-left corner to avoid touching
    the divider-alignment math, but that covered part of the first row's
    content. Living inside the segment's own container widget (see
    _add_segment) instead doesn't need any alignment-math change either:
    REQ-PLOT-273/274 only constrains each *container's* total height to
    match its stripe's, not how that container subdivides itself
    internally — the label is simply less space left over for data rows,
    the same way it already is for the shared header/button chrome
    (#100 postmortem). Double-click renames the stripe (REQ-PLOT-292)."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.on_double_click: Callable[[], None] | None = None
        self.setStyleSheet(
            "font-weight: 600; padding: 1px 5px; background: palette(alternate-base);"
        )

    def mouseDoubleClickEvent(self, event) -> None:
        if self.on_double_click is not None:
            self.on_double_click()
        event.accept()


class ActiveSignalsTable(QWidget):
    """Per-stripe segments of active signals, sharing one header and column layout."""

    # active_signal (or None) — emitted when row selection changes to 0 or 1 rows
    selection_changed = pyqtSignal(object)
    # True when >1 rows are selected; False otherwise
    multi_selection_active = pyqtSignal(bool)
    # list[ActiveSignal] — emitted alongside multi_selection_active(True) with the full selection
    multi_selection_changed = pyqtSignal(list)
    # list[ActiveSignal] — emitted when Remove Signal is clicked / Del pressed / context menu
    remove_requested = pyqtSignal(list)
    # emitted when Remove All is clicked
    remove_all_requested = pyqtSignal()
    # list[ActiveSignal], new QColor — emitted when user picks a new color
    color_change_requested = pyqtSignal(list, QColor)
    # list[ActiveSignal], bool enabled — emitted from context menu step-mode actions
    step_mode_set_requested = pyqtSignal(list, bool)
    # list of (group_index, channel_index), target stripe, and which loaded
    # measurement (#101) they belong to — emitted when signals are dropped
    # from the Signal Browser onto a specific segment; they're added to
    # that segment's stripe (REQ-PLOT-277), the same way
    # PlotStripesArea.signals_dropped_on_stripe works for drops onto a
    # stripe directly in the plot area.
    signals_dropped_on_stripe = pyqtSignal(list, object, int)
    # list[ActiveSignal] in new order — emitted after a row drag-and-drop reorder
    order_changed = pyqtSignal(list)
    # str (selected signal name) — emitted when "Display Name Rule…" is chosen from context menu
    configure_display_names_requested = pyqtSignal(str)
    # bool — emitted when the "Shorten Signal Names" toggle is clicked in the context menu
    shorten_names_toggled = pyqtSignal(bool)
    # list[ActiveSignal] — emitted when "Merge Y-Axis" is chosen from the context menu
    merge_y_axis_requested = pyqtSignal(list)
    # list[ActiveSignal] — emitted when "Sync Y-Axis" is chosen from the context menu
    sync_y_axis_requested = pyqtSignal(list)
    # list[ActiveSignal] — emitted when "Remove from merged/synced axis" is chosen
    ungroup_y_axis_requested = pyqtSignal(list)
    # list[ActiveSignal], target stripe — emitted when a specific stripe is chosen
    # from the "Move to Stripe" submenu
    move_to_stripe_requested = pyqtSignal(list, object)
    # list[ActiveSignal] — emitted when "Move to new Stripe" is chosen
    move_to_new_stripe_requested = pyqtSignal(list)
    # list[int] — the segment splitter's sizes after an interactive drag, so
    # MainWindow can mirror them onto PlotStripesArea's own stripe splitter
    # (REQ-PLOT-274).
    segment_sizes_changed = pyqtSignal(list)
    # stripe — emitted on any mouse press inside a segment, so MainWindow can
    # make that segment's stripe the active one (REQ-PLOT-278), mirroring
    # PlotStripe's own "click anywhere inside activates it" (REQ-PLOT-211).
    segment_activated = pyqtSignal(object)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        # Single source of truth for this tab's active signals (see module
        # docstring) — order is list position; stripe membership is external.
        self._signals: list[ActiveSignal] = []
        self._stripe_for_signal: dict = {}

        self._segments: list[_ActiveTable] = []
        self._segment_for_stripe: dict = {}
        self._stripe_for_segment: dict = {}

        self._name_formatter: Callable[[ActiveSignal], str] = lambda a: a.metadata.name
        self._shorten_names_enabled: bool = False
        self._merged_signals: set = set()
        self._synced_signals: set = set()
        self._get_stripes: Callable[[], list] | None = None
        self._get_stripe_for_signal: Callable[[ActiveSignal], object] | None = None
        # Guards against re-entrant segment_sizes_changed emission from
        # set_segment_sizes() — see PlotStripesArea._syncing_sizes for why
        # this is belt-and-suspenders rather than strictly required.
        self._syncing_segment_sizes = False
        self._build_ui()
        # No segment is created eagerly — in production, segments are created
        # reactively from PlotStripesArea.stripe_created (wired, with a
        # bootstrap for the already-existing first stripe, in
        # MainWindow._wire_tab_view). add_row()'s stripe=None default below
        # covers tests that exercise this widget without a real stripe.

    # ------------------------------------------------------------------
    # Public API (called by AppController)
    # ------------------------------------------------------------------

    def add_stripe_segment(self, stripe: object) -> "_ActiveTable":
        """Create (or return the existing) segment for *stripe* (REQ-PLOT-270)."""
        existing = self._segment_for_stripe.get(stripe)
        if existing is not None:
            return existing
        seg = self._add_segment()
        self._segment_for_stripe[stripe] = seg
        self._stripe_for_segment[seg] = stripe
        seg.name_label.setText(getattr(stripe, "name", ""))
        seg.name_label.adjustSize()
        return seg

    def remove_stripe_segment(self, stripe: object) -> None:
        """Destroy the segment for *stripe*. No-op if unknown.

        Assumes *stripe* is already empty — AppController.delete_stripe
        always removes every signal (via remove_row, which updates
        self._signals/_stripe_for_signal) before this is called
        (REQ-PLOT-193/194), so there is nothing left to reassign here.
        """
        seg = self._segment_for_stripe.pop(stripe, None)
        if seg is None:
            return
        self._stripe_for_segment.pop(seg, None)
        self._segments.remove(seg)
        # The splitter holds seg.container (label + seg stacked), not seg
        # itself — deleting the container takes seg with it.
        seg.container.setParent(None)
        seg.container.deleteLater()

    def add_row(self, active: ActiveSignal, stripe: object | None = None) -> None:
        """Append a row for the given ActiveSignal to the segment for *stripe*.

        In production every stripe's segment already exists by the time this
        is called (created reactively from PlotStripesArea.stripe_created via
        add_stripe_segment) — *stripe* is resolved by AppController before
        calling. Tests exercising this widget in isolation can omit *stripe*
        entirely and get one implicit default segment, matching the
        single-table behavior this replaces.
        """
        seg = self._segment_for_stripe.get(stripe)
        if seg is None:
            seg = self.add_stripe_segment(stripe)
        self._signals.append(active)
        self._stripe_for_signal[active] = stripe
        # Appending to the shared list always puts *active* last within its
        # own segment's filtered view too, so a single native insert (not a
        # full _render_segment rebuild) is correct and keeps existing rows'
        # selection state untouched, same as before this data-model change.
        self._add_row_to_segment(seg, active)

    def move_to_stripe(self, actives: list[ActiveSignal], target_stripe: object) -> None:
        """Reassign each of *actives* to *target_stripe* (REQ-PLOT-202/203).

        List position is left as-is — a moved signal lands wherever it
        naturally falls in the target stripe's filtered view given the
        shared list's existing order, the same "no explicit position" rule
        REQ-PLOT-202/203 already specified before #100. No-op per-signal if
        already in *target_stripe* or not a currently active signal.
        """
        target_seg = self._segment_for_stripe.get(target_stripe)
        if target_seg is None:
            target_seg = self.add_stripe_segment(target_stripe)
        affected = set()
        for active in actives:
            old_stripe = self._stripe_for_signal.get(active)
            if old_stripe is None or old_stripe == target_stripe:
                continue
            old_seg = self._segment_for_stripe.get(old_stripe)
            if old_seg is not None:
                affected.add(old_seg)
            self._stripe_for_signal[active] = target_stripe
            affected.add(target_seg)
        for seg in affected:
            self._render_segment(seg)

    def select_signal(self, active: "ActiveSignal | None") -> None:
        """Programmatically select (and scroll to) the row for *active*, or clear selection."""
        if active is None:
            for seg in self._segments:
                seg.clearSelection()
            return
        seg, row = self._find(active)
        if seg is None:
            return
        seg.setCurrentCell(row, 0)
        seg.scrollTo(seg.model().index(row, 0))

    def set_shorten_names_enabled(self, enabled: bool) -> None:
        """Keep the context menu checkbox in sync with the current rule state."""
        self._shorten_names_enabled = enabled

    def set_group_membership(self, merged: set, synced: set) -> None:
        """Update which signals are currently in a Merged or Synced Y-axis group."""
        self._merged_signals = set(merged)
        self._synced_signals = set(synced)

    def set_stripe_providers(
        self,
        get_stripes: Callable[[], list],
        get_stripe_for_signal: Callable[[ActiveSignal], object],
    ) -> None:
        """Wire the callables used to build the "Move to Stripe" context-menu submenu."""
        self._get_stripes = get_stripes
        self._get_stripe_for_signal = get_stripe_for_signal

    def set_row_color(self, active: ActiveSignal, color: QColor) -> None:
        """Update the color swatch for *active*. No-op if the signal is not in the table."""
        seg, row = self._find(active)
        if seg is None:
            return
        swatch = seg.cellWidget(row, _COL_COLOR)
        if isinstance(swatch, ColorSwatch):
            swatch.set_color(color)

    def set_name_formatter(self, formatter: Callable[[ActiveSignal], str]) -> None:
        """Set a function that maps an active signal to its display name, then refresh all rows.

        Takes the whole ActiveSignal (not just its raw name) so the
        formatter can factor in measurement identity (#101, REQ-PLOT-306)
        alongside the existing display-name-shortening rule.
        """
        self._name_formatter = formatter
        for seg in self._segments:
            for row, active in enumerate(self._segment_signals(seg)):
                item = seg.item(row, _COL_NAME)
                if item is not None:
                    item.setText(formatter(active))

    def remove_row(self, active: ActiveSignal) -> None:
        """Remove the row for the given ActiveSignal. No-op if not present."""
        seg, row = self._find(active)
        if seg is None:
            return
        seg.removeRow(row)
        self._signals.remove(active)
        self._stripe_for_signal.pop(active, None)

    def clear(self) -> None:
        """Remove all rows from every segment."""
        self._signals.clear()
        self._stripe_for_signal.clear()
        for seg in self._segments:
            seg.setRowCount(0)

    def set_segment_sizes(self, sizes: list[int]) -> None:
        """Apply segment heights from PlotStripesArea's own stripe sizes
        (REQ-PLOT-274) — subtracting this widget's known header/button
        chrome from the first/last entry only, so every interior segment
        (and therefore every interior divider) matches its stripe exactly.
        See the offset comment in _build_ui for why a straight 1:1 copy
        can't do this."""
        if not sizes:
            return
        adjusted = list(sizes)
        adjusted[0] = max(0, adjusted[0] - self._top_size_offset)
        adjusted[-1] = max(0, adjusted[-1] - self._bottom_size_offset)
        self._syncing_segment_sizes = True
        try:
            self._segments_splitter.setSizes(adjusted)
        finally:
            self._syncing_segment_sizes = False

    def _on_segment_splitter_moved(self, pos: int, index: int) -> None:
        if self._syncing_segment_sizes:
            return
        sizes = list(self._segments_splitter.sizes())
        if sizes:
            sizes[0] += self._top_size_offset
            sizes[-1] += self._bottom_size_offset
        self.segment_sizes_changed.emit(sizes)

    def show_cursor_columns(self, visible: bool) -> None:
        """Show or hide the three cursor-value columns on the header and every segment."""
        for col in _CURSOR_COLS:
            self._header.setColumnHidden(col, not visible)
            for seg in self._segments:
                seg.setColumnHidden(col, not visible)

    def set_cursor_column_headers(self, c3_label: str, c4_label: str) -> None:
        """Update the header text for the two cursor value columns."""
        self._header.setHorizontalHeaderItem(_COL_C1, QTableWidgetItem(c3_label))
        self._header.setHorizontalHeaderItem(_COL_C2, QTableWidgetItem(c4_label))

    def set_delta_column_header(self, text: str) -> None:
        """Update the header text for the delta column."""
        self._header.setHorizontalHeaderItem(_COL_DELTA, QTableWidgetItem(text))

    def update_cursor_values(
        self,
        active: ActiveSignal,
        c1_text: str,
        c2_text: str,
        delta_text: str,
    ) -> None:
        """Update cursor value cells for one signal (called by CursorController)."""
        seg, row = self._find(active)
        if seg is None:
            return
        for col, text in zip(_CURSOR_COLS, (c1_text, c2_text, delta_text)):
            item = seg.item(row, col)
            if item is not None:
                item.setText(text)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._header = QTableWidget(0, _NUM_COLS)
        _configure_columns(self._header)
        self._header.verticalHeader().setVisible(False)
        self._header.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self._header.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._header.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self._header.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._header.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self._header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        header_height = (
            self._header.horizontalHeader().sizeHint().height()
            + 2 * self._header.frameWidth()
        )
        self._header.setFixedHeight(header_height)
        self._header.horizontalHeader().sectionResized.connect(self._on_header_column_resized)
        layout.addWidget(self._header)

        self._segments_splitter = make_splitter(Qt.Orientation.Vertical)
        self._segments_splitter.splitterMoved.connect(self._on_segment_splitter_moved)
        layout.addWidget(self._segments_splitter, 1)

        btn_layout = QHBoxLayout()
        btn_layout.setContentsMargins(0, 0, 0, 0)
        self._remove_btn = QPushButton("Remove Signal")
        self._remove_btn.setEnabled(False)
        self._remove_all_btn = QPushButton("Remove All")
        btn_layout.addWidget(self._remove_btn)
        btn_layout.addWidget(self._remove_all_btn)
        layout.addLayout(btn_layout)

        self._remove_btn.clicked.connect(self._on_remove_clicked)
        self._remove_all_btn.clicked.connect(self.remove_all_requested)

        # Fixed, known chrome above/below the segments splitter within this
        # widget's own column (header row; button row + its layout spacing)
        # — subtracted from/added back to only the first/last segment during
        # size sync (REQ-PLOT-274), so every *interior* divider lands at
        # exactly the same pixel position as its stripe's divider. Forwarding
        # PlotStripesArea's absolute sizes unadjusted can't achieve that: its
        # splitter has no equivalent chrome, so its total height is always
        # larger than this splitter's by exactly this amount, and Qt's own
        # setSizes() squash-to-fit only preserves *ratios* — not equal
        # absolute segment/stripe heights (#100 postmortem).
        self._top_size_offset = header_height + layout.spacing()
        self._bottom_size_offset = self._remove_btn.sizeHint().height() + layout.spacing()

    def _add_segment(self) -> _ActiveTable:
        """Create, configure, and register one new per-stripe segment table."""
        seg = _ActiveTable()
        _configure_columns(seg)
        seg.horizontalHeader().hide()
        seg.verticalHeader().setVisible(False)
        seg.verticalHeader().setDefaultSectionSize(24)
        seg.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        seg.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        seg.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        seg.setShowGrid(True)
        seg.setStyleSheet(
            "QTableWidget { gridline-color: #d0d0d0; outline: 0; }"
            "QTableWidget::item:selected { background-color: #e0e0e0; color: black; }"
        )
        # Every segment (and the header, above) always reserves the same
        # vertical-scrollbar gutter width, whether or not it actually needs
        # to scroll — this is what keeps columns pixel-aligned across
        # independently-scrolling segments (REQ-PLOT-275).
        seg.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        seg.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        # QTableWidget's default minimumSizeHint reserves more vertical space
        # than a bare PlotStripe needs — left alone, a middle segment in a
        # 3+ way split can't shrink to match its stripe's actual (smaller)
        # share, and the deficit silently gets redistributed to its sibling
        # segments instead (visible drift, worse the further a divider is
        # dragged — see #100 postmortem).
        seg.setMinimumHeight(0)

        # Row dragging (reorder/move-to-stripe) is driven entirely manually
        # via _ActiveTable.mouseMoveEvent + our own QDrag (REQ-PLOT-279) —
        # setDragEnabled(True) would additionally let Qt try to start its own
        # native drag using its default item MIME encoding, which would
        # fight with that. DropOnly still accepts both SIGNAL_MIME_TYPE
        # (Signal Browser) and ROW_MIME_TYPE (row move) drops, handled by
        # the eventFilter installed on the viewport below.
        seg.setDragEnabled(False)
        seg.setAcceptDrops(True)
        seg.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly)

        seg.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        seg.customContextMenuRequested.connect(
            lambda pos, s=seg: self._on_context_menu(s, pos)
        )
        seg.itemSelectionChanged.connect(lambda s=seg: self._on_selection_changed(s))
        seg.on_mouse_press = lambda event, s=seg: self._on_segment_mouse_press(s, event)
        seg.on_drag_start = lambda s=seg: self._start_segment_drag(s)
        seg.on_click_release = lambda event, s=seg: self._on_segment_click_release(s, event)

        seg.viewport().setAcceptDrops(True)
        seg.viewport().installEventFilter(self)

        # seg itself does NOT go into the splitter — it's wrapped in a small
        # container stacking [name_label, seg] so the label gets its own
        # dedicated row rather than overlapping seg's first data row (#100
        # postmortem; see _SegmentLabel's docstring for why this needs no
        # change to the divider-alignment size-sync math).
        seg.name_label = _SegmentLabel()
        seg.name_label.on_double_click = lambda s=seg: self._rename_segment(s)
        container = QWidget()
        container_layout = QVBoxLayout(container)
        container_layout.setContentsMargins(0, 0, 0, 0)
        container_layout.setSpacing(0)
        container_layout.addWidget(seg.name_label)
        container_layout.addWidget(seg, 1)
        seg.container = container

        self._segments.append(seg)
        self._segments_splitter.addWidget(container)
        return seg

    def _rename_segment(self, seg: _ActiveTable) -> None:
        """Rename seg's stripe (REQ-PLOT-292), mirroring MainWindow's own
        tab-rename pattern exactly: a direct QInputDialog, no controller
        round-trip — stripe names, like tab names, aren't persisted/model
        state (REQ-PLOT-294)."""
        stripe = self._stripe_for_segment.get(seg)
        if stripe is None:
            return
        from PyQt6.QtWidgets import QInputDialog
        current_name = getattr(stripe, "name", "")
        name, ok = QInputDialog.getText(self, "Rename Stripe", "Stripe name:", text=current_name)
        if ok and name.strip():
            stripe.name = name.strip()
            seg.name_label.setText(stripe.name)
            seg.name_label.adjustSize()

    def _add_row_to_segment(self, seg: _ActiveTable, active: ActiveSignal) -> None:
        row = seg.rowCount()
        seg.insertRow(row)

        swatch = ColorSwatch(active.color)
        swatch.clicked.connect(
            lambda checked=False, a=active: self._on_color_swatch_clicked(a)
        )
        seg.setCellWidget(row, _COL_COLOR, swatch)
        seg.setItem(row, _COL_NAME, _ro_item(self._name_formatter(active)))
        for col in _CURSOR_COLS:
            seg.setItem(row, col, _ro_item(""))

    def _on_header_column_resized(self, index: int, old_size: int, new_size: int) -> None:
        for seg in self._segments:
            seg.setColumnWidth(index, new_size)

    # ------------------------------------------------------------------
    # Slots (private)
    # ------------------------------------------------------------------

    def _on_segment_mouse_press(self, seg: _ActiveTable, event: QMouseEvent) -> None:
        """Called at the top of every mouse press inside a segment."""
        stripe = self._stripe_for_segment.get(seg)
        if stripe is not None:
            # Any button activates the segment's stripe (REQ-PLOT-278),
            # mirroring PlotStripe's own "any press activates it" rule.
            self.segment_activated.emit(stripe)
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return  # Ctrl(+Shift)-click is the only way to build a
            # cross-segment selection (REQ-PLOT-276) — leave every segment's
            # selection, including this one's, untouched here.
        idx = seg.indexAt(event.position().toPoint())
        already_selected = idx.isValid() and idx.row() in {
            r.row() for r in seg.selectionModel().selectedRows()
        }
        if already_selected:
            # Pressing an already-selected row might be the start of
            # dragging the current (possibly cross-segment) selection as a
            # group (REQ-PLOT-279) — Qt's own selection model already knows
            # not to collapse a multi-selection on such a press, deferring
            # that to release if no drag happens; clearing sibling segments
            # here would pre-empt that and break dragging an existing
            # cross-segment selection. Deferred to on_click_release instead.
            return
        self._clear_other_segments_selection(seg)

    def _on_segment_click_release(self, seg: _ActiveTable, event: QMouseEvent) -> None:
        """Called on release, only when the press didn't turn into a drag."""
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            return
        self._clear_other_segments_selection(seg)

    def _clear_other_segments_selection(self, seg: _ActiveTable) -> None:
        """Clear every segment's selection except *seg*'s own (REQ-PLOT-276).

        blockSignals avoids a spurious itemSelectionChanged (and therefore a
        redundant _on_selection_changed) for segments whose selection is
        simply being reset to empty.
        """
        for other in self._segments:
            if other is not seg and other.selectionModel().hasSelection():
                other.blockSignals(True)
                other.clearSelection()
                other.blockSignals(False)

    def _on_selection_changed(self, seg: _ActiveTable) -> None:
        selected = self._selected_signals()
        count = len(selected)
        self._remove_btn.setEnabled(count > 0)
        if count == 0:
            self.selection_changed.emit(None)
            self.multi_selection_active.emit(False)
        elif count == 1:
            self.selection_changed.emit(selected[0])
            self.multi_selection_active.emit(False)
        else:
            self.selection_changed.emit(None)
            self.multi_selection_active.emit(True)
            self.multi_selection_changed.emit(selected)

    def _on_remove_clicked(self) -> None:
        signals = self._selected_signals()
        if signals:
            self.remove_requested.emit(signals)

    def _on_color_swatch_clicked(self, active: ActiveSignal) -> None:
        QColorDialog.setCustomColor(0, active.color)
        new_color = QColorDialog.getColor(active.color, self, "Choose Signal Color")
        if not new_color.isValid():
            return
        selected = self._selected_signals()
        targets = selected if len(selected) > 1 and active in selected else [active]
        for sig in targets:
            seg, row = self._find(sig)
            if seg is not None:
                swatch = seg.cellWidget(row, _COL_COLOR)
                if isinstance(swatch, ColorSwatch):
                    swatch.set_color(new_color)
        self.color_change_requested.emit(targets, new_color)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self._on_remove_clicked()
        else:
            super().keyPressEvent(event)

    def _on_context_menu(self, seg: _ActiveTable, pos) -> None:
        index = seg.indexAt(pos)
        segment_signals = self._segment_signals(seg)
        if not index.isValid() or index.row() >= len(segment_signals):
            return
        selected = self._selected_signals()
        if not selected:
            selected = [segment_signals[index.row()]]
        n = len(selected)
        menu = QMenu(self)

        remove_label = f"Remove {n} Signals" if n > 1 else "Remove Signal"
        remove_action = QAction(remove_label, self)
        remove_action.triggered.connect(lambda: self.remove_requested.emit(selected))
        menu.addAction(remove_action)

        menu.addSeparator()

        enable_label = "Enable Step Mode for all" if n > 1 else "Enable Step Mode"
        enable_action = QAction(enable_label, self)
        enable_action.triggered.connect(
            lambda: self.step_mode_set_requested.emit(selected, True)
        )
        menu.addAction(enable_action)

        disable_label = "Disable Step Mode for all" if n > 1 else "Disable Step Mode"
        disable_action = QAction(disable_label, self)
        disable_action.triggered.connect(
            lambda: self.step_mode_set_requested.emit(selected, False)
        )
        menu.addAction(disable_action)

        menu.addSeparator()

        shorten_action = QAction("Shorten Signal Names", self)
        shorten_action.setCheckable(True)
        shorten_action.setChecked(self._shorten_names_enabled)
        shorten_action.triggered.connect(
            lambda checked: self.shorten_names_toggled.emit(checked)
        )
        menu.addAction(shorten_action)

        display_name_action = QAction("Display Name Rule…", self)
        preview_name = selected[0].metadata.name if selected else ""
        display_name_action.triggered.connect(
            lambda: self.configure_display_names_requested.emit(preview_name)
        )
        menu.addAction(display_name_action)

        menu.addSeparator()

        # A signal already in one group type can't join the other (#84) — hide
        # the action rather than let it silently no-op in the controller.
        any_synced = any(s in self._synced_signals for s in selected)
        any_merged = any(s in self._merged_signals for s in selected)

        if n >= 2 and not any_synced:
            merge_action = QAction("Merge Y-Axis", self)
            merge_action.setToolTip(
                "All selected signals share one ViewBox and one Y-axis — same Y scale, zoomed together."
            )
            merge_action.triggered.connect(lambda: self.merge_y_axis_requested.emit(selected))
            menu.addAction(merge_action)

        if n >= 2 and not any_merged:
            sync_action = QAction("Sync Y-Axis", self)
            sync_action.setToolTip(
                "Selected signals keep separate Y-axes but pan/zoom together to the same absolute Y range."
            )
            sync_action.triggered.connect(lambda: self.sync_y_axis_requested.emit(selected))
            menu.addAction(sync_action)

        grouped_selected = [s for s in selected if s in self._merged_signals or s in self._synced_signals]
        if grouped_selected:
            ungroup_action = QAction("Remove from merged/synced axis", self)
            ungroup_action.triggered.connect(
                lambda: self.ungroup_y_axis_requested.emit(grouped_selected)
            )
            menu.addAction(ungroup_action)

        if self._get_stripes is not None and self._get_stripe_for_signal is not None:
            menu.addSeparator()
            stripes = self._get_stripes()
            current_stripes = {self._get_stripe_for_signal(s) for s in selected}
            other_stripes = [s for s in stripes if s not in current_stripes]
            if other_stripes:
                move_menu = menu.addMenu("Move to Stripe")
                for stripe in stripes:
                    if stripe in current_stripes:
                        continue
                    action = move_menu.addAction(stripe.name)
                    action.triggered.connect(
                        lambda checked=False, s=stripe: self.move_to_stripe_requested.emit(selected, s)
                    )

            move_new_action = QAction("Move to new Stripe", self)
            move_new_action.triggered.connect(
                lambda: self.move_to_new_stripe_requested.emit(selected)
            )
            menu.addAction(move_new_action)

        menu.exec(seg.viewport().mapToGlobal(pos))

    def eventFilter(self, watched, event):
        seg = self._segment_for_viewport(watched)
        if seg is None:
            return super().eventFilter(watched, event)

        t = event.type()
        if t == QEvent.Type.DragEnter:
            mime = event.mimeData()
            if mime.hasFormat(SIGNAL_MIME_TYPE) or mime.hasFormat(ROW_MIME_TYPE):
                event.acceptProposedAction()
                return True
            event.ignore()
            return True
        elif t == QEvent.Type.DragMove:
            mime = event.mimeData()
            if mime.hasFormat(SIGNAL_MIME_TYPE) or mime.hasFormat(ROW_MIME_TYPE):
                event.acceptProposedAction()
                return True
            event.ignore()
            return True
        elif t == QEvent.Type.Drop:
            mime = event.mimeData()
            if mime.hasFormat(SIGNAL_MIME_TYPE):
                data = bytes(mime.data(SIGNAL_MIME_TYPE))
                measurement_index, locs = decode_signal_payload(data)
                stripe = self._stripe_for_segment.get(seg)
                self.signals_dropped_on_stripe.emit(locs, stripe, measurement_index)
                event.acceptProposedAction()
                return True
            if mime.hasFormat(ROW_MIME_TYPE):
                self._on_row_move_drop(seg, event)
                return True
            return True
        return super().eventFilter(watched, event)

    def _segment_for_viewport(self, watched) -> "_ActiveTable | None":
        for seg in self._segments:
            if watched is seg.viewport():
                return seg
        return None

    def _start_segment_drag(self, seg: _ActiveTable) -> None:
        """Begin dragging the current selection (REQ-PLOT-279).

        Always drags the full cross-segment selection (_selected_signals),
        not just this segment's own rows: in the common case (no
        Ctrl-built cross-segment selection active) that's identical to this
        segment's own selection, since a plain press elsewhere already
        cleared every other segment (REQ-PLOT-276) before this can fire —
        but if a Ctrl-built multi-segment selection survived to this press,
        dragging any one of its rows moves the whole group together
        (REQ-PLOT-279 M8).
        """
        moving = self._selected_signals()
        if not moving:
            return
        mime = QMimeData()
        mime.setData(ROW_MIME_TYPE, QByteArray(encode_row_payload(moving)))
        drag = QDrag(seg)
        drag.setMimeData(mime)
        drag.exec(Qt.DropAction.MoveAction)

    def _on_row_move_drop(self, seg: _ActiveTable, event) -> None:
        data = bytes(event.mimeData().data(ROW_MIME_TYPE))
        ids = decode_row_payload(data)
        # Iterate self._signals (not the JSON-decoded set, whose order is
        # arbitrary) so a multi-signal drag preserves its existing relative
        # order in the drop, whether the signals came from one segment or
        # several (REQ-PLOT-279 M8).
        moving = [a for a in self._signals if id(a) in ids]
        if not moving:
            event.ignore()
            return
        target = seg.indexAt(event.position().toPoint())
        local = self._segment_signals(seg)
        dst_row = target.row() if target.isValid() else len(local)
        self._apply_row_move(moving, seg, dst_row)
        event.acceptProposedAction()

    def _apply_row_move(
        self, moving: list[ActiveSignal], target_seg: _ActiveTable, dst_row: int
    ) -> None:
        """Move *moving* to local row *dst_row* within *target_seg*'s stripe.

        Handles both a same-segment reorder (every dragged signal already in
        target_seg's stripe) and a cross-segment move (some arriving from a
        different stripe's segment, REQ-PLOT-279) uniformly — reusing
        move_to_stripe's stripe-membership reassignment, then splicing every
        affected segment's rendering back to reflect it. Segments that lose
        members are re-rendered too, not just the target.

        A cross-segment move also emits move_to_stripe_requested for the
        signals that actually changed stripe, so the controller relocates
        them in the plot too (#116) — this method used to only update its
        own _stripe_for_signal bookkeeping, leaving the AST row moved but
        the curve behind in its old stripe.
        """
        target_stripe = self._stripe_for_segment.get(target_seg)
        local_before = self._segment_signals(target_seg)
        dst_row = max(0, min(dst_row, len(local_before)))

        affected_segments = {target_seg}
        cross_stripe_moves: list[ActiveSignal] = []
        for m in moving:
            old_stripe = self._stripe_for_signal.get(m)
            if old_stripe != target_stripe:
                cross_stripe_moves.append(m)
                old_seg = self._segment_for_stripe.get(old_stripe)
                if old_seg is not None:
                    affected_segments.add(old_seg)

        # "Everyone else" already in target_seg, i.e. local_before minus any
        # of *moving* that were already there (the same-segment case) — the
        # baseline the dragged signals get spliced back into.
        remaining = [a for a in local_before if a not in moving]
        # For a same-segment reorder, dst_row must shift left by however
        # many dragged rows sat *before* it in the pre-move layout, so the
        # drop lands where the user visually pointed rather than where
        # removing them shifts it to. Cross-segment arrivals were never in
        # local_before, so they never contribute to this adjustment.
        items_before = sum(
            1 for i, a in enumerate(local_before) if a in moving and i < dst_row
        )
        adjusted_dst = max(0, min(len(remaining), dst_row - items_before))

        for m in moving:
            self._stripe_for_signal[m] = target_stripe

        new_local = list(remaining)
        new_local[adjusted_dst:adjusted_dst] = moving
        self._reorder_segment_in_place(target_seg, new_local)

        for seg in affected_segments:
            select_rows = (
                list(range(adjusted_dst, adjusted_dst + len(moving)))
                if seg is target_seg else None
            )
            self._render_segment(seg, select_rows=select_rows)
        self.order_changed.emit(list(self._signals))
        if cross_stripe_moves:
            # _stripe_for_signal is already updated above, so the
            # controller's own table.move_to_stripe() call (inside its
            # move_signals_to_stripe handler) is a safe no-op here — this
            # emit exists purely to reach the plot side (#116).
            self.move_to_stripe_requested.emit(cross_stripe_moves, target_stripe)

    def _reorder_segment_in_place(self, seg: _ActiveTable, new_local: list[ActiveSignal]) -> None:
        """Rewrite the shared list's slots for *seg*'s stripe to *new_local*'s
        order, leaving every other stripe's signals at their existing global
        positions untouched (a same-segment reorder only changes relative
        order within that one stripe)."""
        stripe = self._stripe_for_segment.get(seg)
        positions = [
            i for i, a in enumerate(self._signals)
            if self._stripe_for_signal.get(a) is stripe
        ]
        for pos, active in zip(positions, new_local):
            self._signals[pos] = active

    def _render_segment(self, seg: _ActiveTable, select_rows: list[int] | None = None) -> None:
        """Rebuild one segment's rows from the shared signal list, optionally
        selecting the given local row indices afterward (used by reorder)."""
        signals = self._segment_signals(seg)
        seg.blockSignals(True)
        seg.setRowCount(0)
        for active in signals:
            self._add_row_to_segment(seg, active)
        seg.blockSignals(False)
        if select_rows:
            sm = seg.selectionModel()
            sm.clearSelection()
            for row in select_rows:
                sm.select(
                    seg.model().index(row, 0),
                    sm.SelectionFlag.Select | sm.SelectionFlag.Rows,
                )
        seg.viewport().update()

    def _segment_signals(self, seg: _ActiveTable) -> list[ActiveSignal]:
        """The signals currently assigned to *seg*'s stripe, in list order."""
        stripe = self._stripe_for_segment.get(seg)
        return [a for a in self._signals if self._stripe_for_signal.get(a) is stripe]

    def _selected_signals(self) -> list[ActiveSignal]:
        """Return all currently selected ActiveSignals, segment order then row order."""
        result: list[ActiveSignal] = []
        for seg in self._segments:
            local = self._segment_signals(seg)
            rows = sorted(r.row() for r in seg.selectionModel().selectedRows())
            result.extend(local[r] for r in rows if r < len(local))
        return result

    def _find(self, active: ActiveSignal) -> "tuple[_ActiveTable, int] | tuple[None, None]":
        """Return the (segment, row index) of *active* using identity, or (None, None)."""
        stripe = self._stripe_for_signal.get(active)
        seg = self._segment_for_stripe.get(stripe)
        if seg is None:
            return None, None
        local = self._segment_signals(seg)
        for i, s in enumerate(local):
            if s is active:
                return seg, i
        return None, None
