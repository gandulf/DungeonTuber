"""Builds the YouTube download agent into a single executable: dist/dt-youtube(.exe).

    pip install pyinstaller .
    python build.py
"""
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main() -> int:
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", str(HERE / "dist"),
               "--workpath", str(HERE / "build"), str(HERE / "dt_youtube_agent.spec")]
    result = subprocess.run(command, cwd=HERE)
    if result.returncode == 0:
        print(f"\nBuilt {HERE / 'dist'}")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
