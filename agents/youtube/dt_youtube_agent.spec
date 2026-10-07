# PyInstaller spec for the YouTube download agent: a single console executable.  Build with `python build.py`.
from PyInstaller.utils.hooks import collect_all, collect_submodules

yt_dlp_ejs = collect_all('yt_dlp_ejs')  # the JavaScript yt-dlp runs for YouTube

a = Analysis(
    ['dt_youtube_agent.py'],
    pathex=['../..'],  # core/ of the repository
    binaries=yt_dlp_ejs[1],
    datas=[('../../core/locales', 'core/locales')] + yt_dlp_ejs[0],
    hiddenimports=collect_submodules('yt_dlp') + yt_dlp_ejs[2],
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
    name='dt-youtube',
    debug=False,
    strip=False,
    upx=False,
    console=True,
)
