# -*- mode: python ; coding: utf-8 -*-
# Desktop app: web frontend in a pywebview window with the embedded server.
# Build the frontend first (writes server/static): npm --prefix web ci && npm --prefix web run build
from PyInstaller.utils.hooks import collect_submodules


a = Analysis(
    ['DungeonTuber.py'],
    pathex=[],
    binaries=[],
    datas=[('docs/icon.ico', 'docs'), ('core/locales', 'core/locales'), ('server/static', 'server/static')],
    hiddenimports=collect_submodules('uvicorn') + collect_submodules('server') + ['webview.platforms.edgechromium'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='DungeonTuber',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['docs\\icon.ico'],
    version='version.rc'
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='DungeonTuber',
)
