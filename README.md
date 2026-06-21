# MDF-Viewer

Desktop application for visualizing ASAM MDF (MDF3 and MDF4) measurement data
files. Built with PyQt6, PyQtGraph, and asammdf.

## Status

v2.0 released. See the [Releases](https://github.com/andalf-74/MDF-Viewer/releases)
page for downloads.

## Requirements

- Python 3.10+
- Windows or Linux

## Setup

```sh
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux
source .venv/bin/activate

pip install -e ".[dev]"   # or: pip install -r requirements-dev.txt
```

## Run

```sh
python -m mdf_viewer
```

## Test

```sh
pytest
```

## Architecture

Strict Model–View–Controller separation. See
[`docs/architecture.md`](docs/architecture.md) for the layer rules and module
map.

```
src/mdf_viewer/
├── model/        pure data + MDF file I/O (asammdf isolated here)
├── view_model/   Model<->View bridge objects (ActiveSignal)
├── controller/   coordination + cross-widget state
└── view/         PyQt6 / PyQtGraph UI
```

## License

MDF-Viewer is free, open-source software licensed under the
[GNU General Public License v3.0](LICENSE).

There is no paywall — the application works fully without a license key.
That said, if MDF-Viewer saves you time, purchasing a license as a form
of recognition would be very much appreciated.
