# -*- mode: python ; coding: utf-8 -*-
"""Windows one-folder build for Hanko PDF."""

import os

from PyInstaller.utils.hooks import collect_all, collect_dynamic_libs


PROJECT_ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir, os.pardir))

datas = [(os.path.join(PROJECT_ROOT, "static"), "static")]
binaries = collect_dynamic_libs("pydantic_core")
hiddenimports = ["appdirs", "pydantic_core._pydantic_core"]

fonttools = collect_all("fontTools")
datas += fonttools[0]
binaries += fonttools[1]
hiddenimports += fonttools[2]

a = Analysis(
    [os.path.join(PROJECT_ROOT, "launcher.py")],
    pathex=[PROJECT_ROOT],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pkg_resources", "setuptools"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Hanko PDF",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    icon=[os.path.join(PROJECT_ROOT, "assets", "hanko-icon.ico")],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="Hanko PDF",
)
