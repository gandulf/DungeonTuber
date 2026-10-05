"""Server runtime configuration (library roots, auth secrets, local mode)."""
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from core.settings import AppSettings, SettingKeys


@dataclass
class ServerConfig:
    # Local mode (desktop app): only loopback clients, no login required.
    local_mode: bool = False
    # Directory with the built web frontend (index.html + assets).
    web_dir: Path | None = None
    extra_roots: list[Path] = field(default_factory=list)
    # Directory for settings.json and library.db (default: per-user app data directory).
    data_dir: Path | None = None


_config = ServerConfig()


def get_config() -> ServerConfig:
    return _config


def configure(config: ServerConfig):
    global _config
    _config = config


def get_secret() -> bytes:
    secret = AppSettings.value(SettingKeys.SERVER_SECRET, type=str)
    if not secret:
        secret = secrets.token_hex(32)
        AppSettings.setValue(SettingKeys.SERVER_SECRET, secret)
    return secret.encode("utf-8")


def default_library_roots() -> list[str]:
    root = AppSettings.value(SettingKeys.ROOT_DIRECTORY, type=str)
    if root and os.path.isdir(root):
        return [root]
    music = os.path.expanduser("~/Music")
    return [music if os.path.isdir(music) else os.path.expanduser("~")]


def get_library_roots() -> list[Path]:
    """Directories the server may expose. Everything outside is rejected."""
    roots = AppSettings.value(SettingKeys.LIBRARY_ROOTS, type=list) or default_library_roots()
    result = []
    for root in roots:
        path = Path(root).expanduser()
        if path.is_dir():
            result.append(path.resolve())
    effects_dir = AppSettings.value(SettingKeys.EFFECTS_DIRECTORY, type=str)
    if effects_dir and Path(effects_dir).is_dir():
        result.append(Path(effects_dir).resolve())
    result.extend(p.resolve() for p in _config.extra_roots if p.is_dir())
    # unique, keep order
    seen = set()
    return [p for p in result if not (str(p).lower() in seen or seen.add(str(p).lower()))]
