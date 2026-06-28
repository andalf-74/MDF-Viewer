# MDF-Viewer – Release Build

## Build Files

| File | Purpose |
|------|---------|
| `installer/mdf_viewer.spec` | PyInstaller spec — one-folder Windows bundle |
| `installer/mdf_viewer.iss` | Inno Setup 6 script — per-user installer with optional file associations |

`dist/` is in `.gitignore`; build artifacts are never committed.

## Steps

1. `pyinstaller installer/mdf_viewer.spec --distpath dist --workpath dist/_build -y` → produces `dist/MDF-Viewer/`
2. `"C:/Program Files (x86)/Inno Setup 6/ISCC.exe" installer/mdf_viewer.iss` → produces `installer/dist/MDF-Viewer-X.Y-Setup.exe`
3. `Compress-Archive -Path dist\MDF-Viewer -DestinationPath dist\MDF-Viewer-X.Y-Windows.zip -Force` → portable zip
4. Upload both to the GitHub release: `gh release upload vX.Y installer/dist/MDF-Viewer-X.Y-Setup.exe dist/MDF-Viewer-X.Y-Windows.zip`

**Latest release — v2.1:** https://github.com/andalf-74/MDF-Viewer/releases/tag/v2.1 — ships `MDF-Viewer-2.1-Setup.exe` (installer) and `MDF-Viewer-2.1-Windows.zip` (portable).
