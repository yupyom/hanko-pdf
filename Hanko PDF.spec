# -*- mode: python ; coding: utf-8 -*-
import os

from PyInstaller.utils.hooks import collect_dynamic_libs
from PyInstaller.utils.hooks import collect_all

APP_VERSION = '1.0.0'
APP_BUILD = '1'
BUNDLE_IDENTIFIER = 'io.github.yupyom.hankopdf'

datas = [('static', 'static')]
binaries = []
hiddenimports = ['appdirs', 'pydantic_core._pydantic_core', 'CoreText']
binaries += collect_dynamic_libs('pydantic_core')
tmp_ret = collect_all('fontTools')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pkg_resources', 'setuptools'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Hanko PDF',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=os.environ.get('DEVELOPER_ID_CERT') or None,
    entitlements_file=None,
    icon=['assets/hanko-icon.icns'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Hanko PDF',
)
app = BUNDLE(
    coll,
    name='Hanko PDF.app',
    icon='assets/hanko-icon.icns',
    bundle_identifier=os.environ.get('BUNDLE_ID', BUNDLE_IDENTIFIER),
    info_plist={
        'CFBundleShortVersionString': APP_VERSION,
        'CFBundleVersion': APP_BUILD,
    },
)
