"""The connection to a cloud function on Modal: its endpoint URL and the key and secret of a Modal proxy auth token.

They are kept in a file next to settings.json (mode 0600) and never sent back to the browser. Used by the cloud analysis
(server/voxcloud.py) and the music generation (server/musicgen.py); each has a file of its own.
"""
import json
import os
from pathlib import Path
from urllib.parse import urlsplit

from core.i18n import _
from core.settings import AppSettings
from core.utils import get_user_data_dir

FIELDS = ("url", "key", "secret")


class CloudError(OSError):
    pass


class CloudConfig:
    def __init__(self, file_name: str):
        self.file_name = file_name

    def file(self) -> Path:
        path = AppSettings.path
        return (path.parent if path else get_user_data_dir()) / self.file_name

    def load(self) -> dict[str, str] | None:
        try:
            data = json.loads(self.file().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if isinstance(data, dict) and all(data.get(name) for name in FIELDS):
            return {name: str(data[name]) for name in FIELDS}
        return None

    def save(self, url: str, key: str, secret: str):
        url, key, secret = url.strip(), key.strip(), secret.strip()
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise CloudError(_("The URL must start with https://"))
        if not key or not secret:
            raise CloudError(_("The key or the secret is missing"))
        path = self.file()
        path.parent.mkdir(parents=True, exist_ok=True)
        with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8", newline="\n") as out:
            json.dump({"url": url, "key": key, "secret": secret}, out)

    def delete(self):
        self.file().unlink(missing_ok=True)

    def status(self) -> dict:
        config = self.load()
        return {"configured": config is not None, "host": urlsplit(config["url"]).netloc if config else None}


def auth_headers(config: dict[str, str]) -> dict[str, str]:
    """The headers Modal's proxy auth checks before it starts a container."""
    return {"Modal-Key": config["key"], "Modal-Secret": config["secret"]}


def error_detail(error) -> str:
    """The `detail` of a FastAPI error answer (urllib.error.HTTPError), otherwise its reason."""
    try:
        return str(json.loads(error.read()).get("detail", error.reason))
    except (OSError, ValueError, AttributeError):
        return str(error.reason)
