"""Voxalyzer on demand: the analysis runs in a cloud function (agents/voxalyzer/modal_app.py on Modal) that starts when an mp3 is posted.

The endpoint URL and the key and secret of its Modal proxy auth token are kept next to settings.json (see server/cloudconfig.py) and
never sent back to the browser; an agent that is connected is preferred (see server/voxagent.py). Modal checks the key and secret
before it starts a container, so a request without them costs nothing.
"""
import json
import logging
import os
import threading
import urllib.error
import urllib.request
from os import PathLike
from pathlib import Path

from core.analyzer import AnalyzerBackend
from core.i18n import _
from server.cloudconfig import CloudConfig, CloudError, auth_headers, error_detail

logger = logging.getLogger(__file__)

__all__ = ["CloudError", "CloudVoxalyzerBackend", "config_file", "current_backend", "delete_config", "load_config", "save_config", "status"]

CONFIG = CloudConfig("voxalyzer-cloud.json", "DT_VOXALYZER_CLOUD")

# Seconds for one analysis: the upload, a cold start of the container (GPU + models) and the analysis itself.
ANALYZE_TIMEOUT = 600

_gate = threading.Semaphore(4)  # parallel analyses; the cloud side caps its containers as well


def config_file() -> Path:
    return CONFIG.file()


def load_config() -> dict[str, str] | None:
    return CONFIG.load()


def save_config(url: str, key: str, secret: str):
    CONFIG.save(url, key, secret)


def delete_config():
    CONFIG.delete()


def status() -> dict:
    return CONFIG.status()


class CloudVoxalyzerBackend(AnalyzerBackend):
    """Called from the analysis worker threads."""
    name = "cloud"

    def __init__(self, config: dict[str, str]):
        self.config = config

    def analyze_mp3(self, file_path: PathLike[str]) -> dict | None:
        with _gate, open(file_path, "rb") as file:
            size = os.fstat(file.fileno()).st_size
            request = urllib.request.Request(self.config["url"], data=file, method="POST", headers={
                **auth_headers(self.config), "Content-Type": "audio/mpeg", "Content-Length": str(size)})
            try:
                with urllib.request.urlopen(request, timeout=ANALYZE_TIMEOUT) as response:
                    return json.loads(response.read())
            except urllib.error.HTTPError as e:
                detail = error_detail(e)
                if e.code in (401, 403):
                    raise CloudError(_("The cloud analysis rejected the key or the secret ({0})").format(detail)) from e
                raise CloudError(_("The cloud analysis failed ({0}): {1}").format(e.code, detail)) from e
            except (urllib.error.URLError, TimeoutError, ValueError) as e:
                raise CloudError(_("The cloud analysis is not reachable: {0}").format(e)) from e


def current_backend() -> AnalyzerBackend | None:
    """The configured cloud function; None when there is none."""
    config = load_config()
    return CloudVoxalyzerBackend(config) if config else None
