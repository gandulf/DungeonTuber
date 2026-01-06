# Voxtube

A music player application built with Python, PySide6, and VLC.

## Build Instructions

### Using PyInstaller
```bash
pyinstaller main.py --additional-hooks-dir hooks --windowed --icon icon.ico --onefile --add-data="icon.ico;."
```

### Using Nuitka (Recommended)
The following command uses MinGW64. If you experience slow compilation, ensure your build directory is excluded from Antivirus scanning.

```bash
python -m nuitka --mingw64 --onefile --windows-console-mode=hide --enable-plugin=pyside6 --windows-icon-from-ico=icon.ico --include-data-files=icon.ico=icon.ico --follow-imports --onefile-windows-splash-screen-image=splash.png --jobs=16 main.py
```

*Note: The `--jobs` flag sets the number of parallel compilation jobs. Adjust based on your CPU cores.*
