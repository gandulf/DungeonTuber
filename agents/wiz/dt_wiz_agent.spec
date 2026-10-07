# PyInstaller spec for the WiZ light agent: a single console executable.  Build with `python build.py`.
a = Analysis(
    ['dt_wiz_agent.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'unittest', 'pydoc'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='dt-wiz-light',
    debug=False,
    strip=False,
    upx=False,
    console=True,
)
