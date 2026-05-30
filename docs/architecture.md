# MDF-Viewer Architecture

Strict MVC separation is mandatory. The prototype this project replaces failed
because data, UI, and plotting were tightly coupled; every decision here exists
to keep those concerns apart.

## Layers

| Layer | Package | May import | Must NOT import |
|-------|---------|------------|-----------------|
| Model | `mdf_viewer.model` | numpy, asammdf | PyQt6, pyqtgraph, view, controller |
| View | `mdf_viewer.view` | PyQt6, pyqtgraph | model-loading logic, asammdf |
| Controller | `mdf_viewer.controller` | model, view_model | — |
| View-model | `mdf_viewer.view_model` | model, PyQt6, pyqtgraph | — |

The **model** is pure data and never imports Qt. The **view** is pure UI and
holds no business logic. The **controller** coordinates the two and owns
cross-widget state. The **view-model** holds the few bridge objects that must
reference both a model object and its on-screen representation.

## Signal classes

- **`model.signal_data.SignalData`** — raw timestamps + sample arrays. Pure data.
- **`model.signal_metadata.SignalMetadata`** — name, unit, min/max, sample
  count, comment, and other MDF fields. Pure data, no samples.
- **`view_model.active_signal.ActiveSignal`** — a signal placed on the plot.
  Pairs `SignalData` + `SignalMetadata` with its PyQtGraph curve, ViewBox, and
  color. This is the Model↔View bridge, which is why it lives in `view_model`
  rather than `model` (it references Qt/PyQtGraph types).

## File I/O isolation

`model.mdf_loader.MdfLoader` is the **only** module that imports `asammdf`. It
translates a file on disk into the plain data classes above and raises
`MdfLoadError` on malformed or unreadable content, so the rest of the app never
touches the asammdf API and never crashes on bad input.

## Assembly

`app.run()` is the single place that constructs and wires the three layers
together. No layer constructs another's object graph.

## Module map

```
model/        signal_data, signal_metadata, measurement, mdf_loader
view_model/   active_signal
controller/   app_controller, cursor_controller
view/         main_window, signal_browser, active_signals_table, plot_area,
              cursors, measurement_info_box, signal_info_box, widgets/
```
