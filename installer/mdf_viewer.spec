# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for MDF-Viewer.
# Run from the project root:
#   pyinstaller installer/mdf_viewer.spec
#
# Output: dist/MDF-Viewer/MDF-Viewer.exe  (one-folder bundle)

import os
from PyInstaller.utils.hooks import collect_all

# All source paths are relative to the project root, one level up from installer/.
ROOT = os.path.dirname(SPECPATH)

# Collect asammdf's data files, binaries, and hidden imports in one shot.
asammdf_datas, asammdf_binaries, asammdf_hiddenimports = collect_all("asammdf")

a = Analysis(
    [os.path.join(ROOT, "src/mdf_viewer/__main__.py")],
    pathex=[os.path.join(ROOT, "src")],
    binaries=asammdf_binaries,
    datas=[
        # Icons must land at  mdf_viewer/resources/icons/  inside the bundle
        # so that  Path(__file__).parent.parent / "resources" / "icons"
        # resolves correctly at runtime (mirrors the src-layout structure).
        (os.path.join(ROOT, "src/mdf_viewer/resources"), "mdf_viewer/resources"),
        *asammdf_datas,
    ],
    hiddenimports=asammdf_hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "IPython", "jupyter"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MDF-Viewer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=os.path.join(ROOT, "src/mdf_viewer/resources/icons/app_icon.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MDF-Viewer",
)
