import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_core_imports_without_pyside():
    code = (
        "import sys\n"
        "import core.analyzer, core.lights, core.log, core.mp3, core.scoring, core.settings, core.utils\n"
        "qt = sorted(m for m in sys.modules if m.startswith('PySide6') or m.startswith('shiboken'))\n"
        "print(','.join(qt))\n"
    )
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, check=True)

    assert result.stdout.strip() == ""
