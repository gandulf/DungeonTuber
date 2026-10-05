import logging
from pathlib import Path

import pytest

from core.log import StrFormatLogRecord
from core.settings import AppSettings, settings

# Core code logs with str.format placeholders, like the app does.
logging.setLogRecordFactory(StrFormatLogRecord)

# One silent MPEG-1 Layer III frame: 128 kbit/s, 44.1 kHz -> 417 bytes.
_FRAME = b"\xff\xfb\x90\x64" + b"\x00" * 413


def write_mp3(path: Path, frames: int = 80) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_FRAME * frames)
    return path


@pytest.fixture(autouse=True)
def isolated_settings(tmp_path):
    """Every test gets its own empty settings file."""
    previous = AppSettings.path
    AppSettings.set_path(tmp_path / "settings.json")
    settings.reload()
    yield AppSettings
    if previous is not None:
        AppSettings.set_path(previous)
    settings.reload()


@pytest.fixture
def mp3_file(tmp_path) -> Path:
    return write_mp3(tmp_path / "music" / "song.mp3")
