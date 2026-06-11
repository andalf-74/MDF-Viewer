"""Ad-hoc profiling script: load a real MDF, add signals, simulate pan/zoom.

Run with: python tools/profile_plot.py (from the repo root).
"""
from __future__ import annotations

import cProfile
import os
import pstats
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtWidgets import QApplication

from mdf_viewer.controller.app_controller import AppController
from mdf_viewer.controller.cursor_controller import CursorController
from mdf_viewer.model.mdf_loader import MdfLoader
from mdf_viewer.view.cursors import CursorView
from mdf_viewer.view.main_window import MainWindow

FILE = "data/test.mf4"

# (group_index, channel_index) picks — high sample-count groups.
SIGNALS = [
    (90, 1), (90, 2), (90, 3),
    (97, 1), (97, 2),
    (100, 1),
]


def main() -> None:
    app = QApplication(sys.argv)
    window = MainWindow()
    loader = MdfLoader()
    controller = AppController(
        loader=loader,
        signal_browser=window.signal_browser,
        plot_area=window.plot_area,
        active_signals_table=window.active_signals_table,
        measurement_info_box=window.measurement_info_box,
        signal_info_box=window.signal_info_box,
    )
    cursor_view = CursorView(window.plot_area.plot_item)
    cursor_ctrl = CursorController(
        cursor_view=cursor_view,
        get_x_range=lambda: tuple(window.plot_area.plot_item.vb.viewRange()[0]),
        active_signals_table=window.active_signals_table,
    )
    controller.set_cursor_controller(cursor_ctrl)
    window.set_controller(controller, cursor_ctrl)
    window.resize(1600, 900)
    window.show()

    t0 = time.perf_counter()
    controller.load_file(FILE)
    print(f"load_file: {time.perf_counter() - t0:.4f}s")

    t0 = time.perf_counter()
    for gi, ci in SIGNALS:
        ok = controller.add_signal(gi, ci)
        print(f"  add_signal({gi},{ci}) -> {ok}, "
              f"n={controller.active_signals[-1].data.sample_count if ok else '-'}")
    print(f"add 6 signals: {time.perf_counter() - t0:.4f}s")

    app.processEvents()

    t0 = time.perf_counter()
    window.plot_area.zoom_to_fit()
    app.processEvents()
    print(f"zoom_to_fit: {time.perf_counter() - t0:.4f}s")

    # Simulate panning/zooming: repeatedly change the X range and force a repaint.
    vb = window.plot_area.plot_item.vb
    x_min, x_max = vb.viewRange()[0]
    span = x_max - x_min

    def pan_zoom_loop():
        for i in range(60):
            frac = (i % 20) / 20.0
            new_min = x_min + frac * span * 0.3
            new_max = new_min + span * (0.5 + 0.5 * frac)
            vb.setXRange(new_min, new_max, padding=0)
            app.processEvents()

    t0 = time.perf_counter()
    pan_zoom_loop()
    print(f"60x pan/zoom: {time.perf_counter() - t0:.4f}s")

    # Profile the pan/zoom loop in detail.
    profiler = cProfile.Profile()
    profiler.enable()
    pan_zoom_loop()
    profiler.disable()

    stats = pstats.Stats(profiler).sort_stats("cumulative")
    stats.print_stats(25)

    # Cursor drag simulation
    cursor_ctrl.toggle()  # ONE
    cursor_ctrl.toggle()  # TWO
    app.processEvents()

    profiler2 = cProfile.Profile()
    profiler2.enable()
    for i in range(60):
        x = x_min + (i / 60.0) * span
        cursor_view.cursor_moved.emit(0, x)
        app.processEvents()
    profiler2.disable()

    print("\n--- cursor drag profile ---")
    stats2 = pstats.Stats(profiler2).sort_stats("cumulative")
    stats2.print_stats(20)


if __name__ == "__main__":
    main()
