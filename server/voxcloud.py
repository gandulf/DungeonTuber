"""Voxalyzer on demand: the analysis runs in a cloud function (agents/voxalyzer/modal_app.py on Modal) that starts when an mp3 is posted.

The endpoint URL and the key and secret of its Modal proxy auth token are kept next to settings.json (mode 0600) and never sent back
to the browser; an agent that is connected is preferred (see server/voxagent.py). Modal checks the key and secret before it starts a
container, so a request without them costs nothing.
"""
import json
import logging
import os
import threading
import urllib.error
import urllib.request
from os import PathLike
from pathlib import Path
from urllib.parse import urlsplit

from core.analyzer import AnalyzerBackend
from core.i18n import _
from core.settings import AppSettings
from core.utils import get_user_data_dir

logger = logging.getLogger(__file__)

CONFIG_NAME = "voxalyzer-cloud.json"

# Seconds for one analysis: the upload, a cold start of the container (GPU + models) and the analysis itself.
ANALYZE_TIMEOUT = 600

_gate = threading.Semaphore(4)  # parallel analyses; the cloud side caps its containers as well


class CloudError(OSError):
    pass


def config_file() -> Path:
    path = AppSettings.path
    return (path.parent if path else get_user_data_dir()) / CONFIG_NAME


def load_config() -> dict[str, str] | None:
    try:
        data = json.loads(config_file().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(data, dict) and all(data.get(name) for name in ("url", "key", "secret")):
        return {name: str(data[name]) for name in ("url", "key", "secret")}
    return None


def save_config(url: str, key: str, secret: str):
    url, key, secret = url.strip(), key.strip(), secret.strip()
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise CloudError(_("The URL must start with https://"))
    if not key or not secret:
        raise CloudError(_("The key or the secret is missing"))
    path = config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with os.fdopen(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), "w", encoding="utf-8", newline="\n") as out:
        json.dump({"url": url, "key": key, "secret": secret}, out)


def delete_config():
    config_file().unlink(missing_ok=True)


def status() -> dict:
    config = load_config()
    return {"configured": config is not None, "host": urlsplit(config["url"]).netloc if config else None}


class CloudVoxalyzerBackend(AnalyzerBackend):
    """Called from the analysis worker threads."""
    name = "cloud"

    def __init__(self, config: dict[str, str]):
        self.config = config

    def analyze_mp3(self, file_path: PathLike[str]) -> dict | None:
        with _gate, open(file_path, "rb") as file:
            size = os.fstat(file.fileno()).st_size
            request = urllib.request.Request(self.config["url"], data=file, method="POST", headers={
                "Modal-Key": self.config["key"], "Modal-Secret": self.config["secret"], "Content-Type": "audio/mpeg", "Content-Length": str(size)})
            try:
                with urllib.request.urlopen(request, timeout=ANALYZE_TIMEOUT) as response:
                    return json.loads(response.read())
            except urllib.error.HTTPError as e:
                detail = _detail(e)
                if e.code in (401, 403):
                    raise CloudError(_("The cloud analysis rejected the key or the secret ({0})").format(detail)) from e
                raise CloudError(_("The cloud analysis failed ({0}): {1}").format(e.code, detail)) from e
            except (urllib.error.URLError, TimeoutError, ValueError) as e:
                raise CloudError(_("The cloud analysis is not reachable: {0}").format(e)) from e


def _detail(error: urllib.error.HTTPError) -> str:
    try:
        return str(json.loads(error.read()).get("detail", error.reason))
    except (OSError, ValueError, AttributeError):
        return str(error.reason)


def current_backend() -> AnalyzerBackend | None:
    """The configured cloud function; None when there is none."""
    config = load_config()
    return CloudVoxalyzerBackend(config) if config else None
