# MDF-Viewer – Release Build

## Build Files

| File | Purpose |
|------|---------|
| `installer/mdf_viewer.spec` | PyInstaller spec — one-folder Windows bundle |
| `installer/mdf_viewer.iss` | Inno Setup 6 script — per-user installer with optional file associations |

`dist/` is in `.gitignore`; build artifacts are never committed.

## Version bump (before building)

Two files must be updated — `pyproject.toml` derives its version dynamically, so only these two need touching:

| File | What to change |
|------|---------------|
| `src/mdf_viewer/__init__.py` | `__version__ = "X.Y"` |
| `installer/mdf_viewer.iss` | `#define AppVersion "X.Y"` (line 8) |

Commit, tag (`git tag vX.Y`), and push before building so the tag lands on the correct commit.

## Plugin-author SDK sync (#151)

The separate [`mdf-viewer-plugin-sdk`](https://github.com/andalf-74/mdf-viewer-plugin-sdk) repo hand-maintains type stubs (`.pyi`) for `src/mdf_viewer/plugin_api/` (`context.py`, `plugin.py`, `registry.py`, `types.py`), `enums.py`'s `CursorMode`, and the virtual-measurement model types (`model/signal_data.py`, `model/signal_metadata.py`, `model/virtual_signal.py`, `model/virtual_measurement_loader.py`). There is no automated sync (CI push or `git subtree`) — deliberately, since stubs are hand-distilled (signatures + behavior notes, no implementation) rather than a raw copy, and `plugin_api` changes infrequently enough that automation isn't worth the cross-repo credential/tooling overhead.

**Whenever a change in this repo adds, removes, or changes the signature/behavior of anything in that surface** (not gated to version bumps — check on every PR that touches `plugin_api/`, `enums.py`'s `CursorMode`, or the virtual-measurement model types), update the matching stub(s) and docs in the SDK repo in the same spirit as this repo's own `docs/api.md`/`docs/ui.md` same-commit-update convention.

## Build steps

1. `pyinstaller installer/mdf_viewer.spec --distpath dist --workpath dist/_build -y` → produces `dist/MDF-Viewer/`
2. `Copy-Item -Recurse -Force plugins\update_checker dist\MDF-Viewer\plugins\update_checker` → ships the Update Checker plugin (#76), the first plugin required in the real build (every other plugin under `plugins/` is dev-mode-only and must **not** be copied here). PyInstaller's own `Analysis`/`COLLECT` pipeline cannot place it correctly — see `installer/mdf_viewer.spec`'s comment above `coll = COLLECT(...)` for why — so this manual copy step exists specifically to land it at `dist\MDF-Viewer\plugins\`, a sibling of `MDF-Viewer.exe`, matching `plugin_api/loader.py`'s frozen-mode default lookup. **Must run before steps 3 and 4** — both already copy the whole `dist\MDF-Viewer\` tree, so this is the only step that needs to know the plugin exists.
3. `"C:/Program Files (x86)/Inno Setup 6/ISCC.exe" installer/mdf_viewer.iss` → produces `installer/dist/MDF-Viewer-X.Y-Setup.exe`
4. `Compress-Archive -Path dist\MDF-Viewer -DestinationPath dist\MDF-Viewer-X.Y-Windows.zip -Force` → portable zip
5. Upload both to the GitHub release: `gh release upload vX.Y installer/dist/MDF-Viewer-X.Y-Setup.exe dist/MDF-Viewer-X.Y-Windows.zip`

**Latest release — v2.3.5:** https://github.com/andalf-74/MDF-Viewer/releases/tag/v2.3.5 — ships `MDF-Viewer-2.3.5-Setup.exe` (installer) and `MDF-Viewer-2.3.5-Windows.zip` (portable).
