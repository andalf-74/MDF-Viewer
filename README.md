# MDF-Viewer

Desktop application for visualizing ASAM MDF (MDF3 and MDF4) measurement data
files. Built with PyQt6, PyQtGraph, and asammdf.

## Status

Greenfield — project scaffold and architecture are in place; feature
implementation is in progress.

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
