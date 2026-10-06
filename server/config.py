"""Server runtime configuration (library roots, auth secrets, local mode)."""
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from core.settings import AppSettings, SettingKeys


@dataclass
class ServerConfig:
    # Local mode (desktop app): loopback clients never need to log in; other devices need the password.
    local_mode: bool = False
    # Directory with the built web frontend (default: server/static, built by `npm --prefix web run build`).
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
    from server.roots import default_library_roots as default_roots
    return default_roots()


def get_library_roots() -> list[Path]:
    """Local directories the server may expose."""
    from server.roots import get_local_roots
    return [root.storage.root for root in get_local_roots()]
