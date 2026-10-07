"""Settings shared by all DungeonTuber agents (WiZ lights, Voxalyzer, YouTube), so a machine that runs several of them is configured once.

This file exists three times, byte for byte (core/, agents/wiz/ and agents/voxalyzer/voxalyzer/): the agents are standalone programs. A test
keeps the copies equal.

The settings come from `agents.json`, searched in this order: the path in DT_AGENT_CONFIG, next to the program (the exe or script), the
DungeonTuber data folder (%APPDATA%/DungeonTuber, ~/.config/DungeonTuber). It holds the keys `server`, `token` and `name`:

    {"server": "https://music.example.com", "token": "...", "name": "my-pc"}

A command line option beats the environment variable (DT_SERVER, DT_AGENT_TOKEN, DT_AGENT_NAME), which beats this file.
"""
import json
import os
import sys
from pathlib import Path

FILE_NAME = "agents.json"
KEYS = ("server", "token", "name")


def data_dir() -> Path:
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return Path(base) / "DungeonTuber"


def config_paths() -> list[Path]:
    program = Path(sys.executable if getattr(sys, "frozen", False) else sys.argv[0] or ".").resolve().parent
    explicit = os.environ.get("DT_AGENT_CONFIG")
    return ([Path(explicit)] if explicit else []) + [program / FILE_NAME, data_dir() / FILE_NAME]


def agent_config() -> dict[str, str]:
    """The shared settings (server, token, name) of the first agents.json that can be read; empty when there is none."""
    for path in config_paths():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict):
            return {key: str(data[key]).strip() for key in KEYS if data.get(key)}
    return {}
