"""Music analysis backends (voxalyzer local/remote, mock) without any threading framework.

Callers decide how to run ``analyze_file`` (Qt thread pool, asyncio.to_thread, ...).
"""
import atexit
import json
import logging
import os
import random
import re
import subprocess
import threading
import urllib.request
from os import PathLike
from pathlib import Path
from typing import Any, Callable

import psutil

from core.i18n import _
from core.mp3 import Mp3Entry, parse_mp3, update_categories_and_tags, print_mp3_tags, list_mp3s
from core.settings import AppSettings, SettingKeys, CATEGORY_MIN, CATEGORY_MAX, MusicCategory, get_category_keys, has_local_voxalyzer, \
    has_voxalyzer
from core.utils import get_executable_path

logger = logging.getLogger(__file__)

MOCK_SUMMARY = "This is a mock summary."
# Seconds to wait for an analysis response; analyzing a long track can take a while.
ANALYZE_TIMEOUT = 600
PORT_TIMEOUT = 60

_CREATE_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class VoxalyzerService:
    """Manages the local voxalyzer child process and the port it reports."""

    def __init__(self):
        self.port: str | None = None
        self.port_found_event = threading.Event()
        self.process: subprocess.Popen[str] | None = None
        self._lock = threading.Lock()

    def start(self) -> str | None:
        with self._lock:
            executable = get_executable_path("voxalyzer.exe")

            if os.path.isfile(executable) and self.port is None and self.process is None:
                self.process = subprocess.Popen([executable, "--port", "0", "--host", "127.0.0.1"],
                                                creationflags=_CREATE_NO_WINDOW,
                                                stdout=subprocess.PIPE,
                                                stderr=subprocess.PIPE,
                                                stdin=subprocess.DEVNULL,
                                                text=True
                                                )
                atexit.register(self.stop)

                logger.info("Voxalyzer: Listening for port...")

                threading.Thread(target=self._stream_logger, args=(self.process.stdout,), daemon=True).start()
                threading.Thread(target=self._stream_logger, args=(self.process.stderr,), daemon=True).start()

            if self.process is not None and self.port is None:
                logger.info("Voxalyzer: Waiting for port...")
                if self.port_found_event.wait(timeout=PORT_TIMEOUT):
                    logger.info(f"Voxalyzer is running on port {self.port}")
                else:
                    logger.error("Voxalyzer: Timed out waiting for port!")

        return f"http://localhost:{self.port}" if self.port else None

    def _stream_logger(self, pipe):
        for line in pipe:
            logger.info(f"[Voxalyzer]: {line.strip()}")
            match = re.search(r"http://127.0.0.1:(\d+) ", line)
            if match:
                self.port = match.group(1)
                self.port_found_event.set()
                break

    # This ensures the child is killed when Python exits gracefully
    def stop(self):
        try:
            if self.process is not None:
                parent = psutil.Process(self.process.pid)
                # Find all grandchildren (Uvicorn, etc.)
                for child in parent.children(recursive=True):
                    child.terminate()
                parent.terminate()
        except psutil.NoSuchProcess:
            pass


voxalyzer = VoxalyzerService()


def start_voxalyzer() -> str | None:
    return voxalyzer.start()


def stop_voxalyzer():
    voxalyzer.stop()


def _entry(file_path: PathLike[str] | Mp3Entry) -> Mp3Entry | None:
    return file_path if isinstance(file_path, Mp3Entry) else parse_mp3(file_path)


def is_analyzed(file_path: PathLike[str] | Mp3Entry) -> bool:
    entry = _entry(file_path)
    if entry is None:
        return False

    return (set(get_category_keys()) == set(entry.categories.keys()) and entry.summary is not None
            and entry.summary != MOCK_SUMMARY and "Voxalyzer" not in entry.summary)


def is_voxalyzed(file_path: PathLike[str] | Mp3Entry) -> bool:
    entry = _entry(file_path)
    return entry is not None and entry.summary is not None and "Voxalyzer" in entry.summary


def categories_to_string(categories: list[MusicCategory]) -> str:
    return "\n\n".join(f"{cat.name}: {cat.description}\n {cat.levels}" for cat in categories)


def tags_to_string(data: dict[str, str]) -> str:
    return "\n".join(f"{key}: {value}" for key, value in data.items())


def _analyze_url(url: str | None) -> str | None:
    if not url or url == "None":
        return None
    if url.endswith("/analyze"):
        return url
    return f"{url}analyze" if url.endswith("/") else f"{url}/analyze"


def _post(url: str, data: bytes, content_type: str) -> Any:
    req = urllib.request.Request(url, data=data, method='POST')
    req.add_header('Content-Type', content_type)

    with urllib.request.urlopen(req, timeout=ANALYZE_TIMEOUT) as response:
        if response.status == 200:
            return json.loads(response.read())
        logger.error(f"Error: {response.status} - {response.reason}")
        return None


class AnalyzerBackend:
    """Turns an mp3 file into ``{"summary": str, "categories": [{"category", "scale"}], "tags": [...]}``."""

    name = "base"

    def analyze_mp3(self, file_path: PathLike[str]) -> dict | None:
        raise NotImplementedError


class MockBackend(AnalyzerBackend):
    name = "mock"

    def analyze_mp3(self, file_path: PathLike[str]) -> dict | None:
        logger.debug("--- MOCK MODE: Simulating analysis for {0} ---", file_path)

        return {
            "summary": MOCK_SUMMARY,
            "categories": [{"category": category, "scale": random.randint(CATEGORY_MIN, CATEGORY_MAX)} for category in get_category_keys()]
        }


class LocalVoxalyzerBackend(AnalyzerBackend):
    """Voxalyzer running next to the app; it reads the file from disk itself."""
    name = "local"

    def __init__(self, service: VoxalyzerService = voxalyzer):
        self.service = service

    def analyze_mp3(self, file_path: PathLike[str]) -> dict | None:
        url = _analyze_url(self.service.start())
        if not url:
            logger.error("Voxalyzer URL not set.")
            return None

        logger.debug(f"Sending request to {url} for file {file_path}")
        return _post(url, json.dumps({"file": os.path.abspath(file_path)}).encode("utf-8"), 'application/json')


class RemoteVoxalyzerBackend(AnalyzerBackend):
    """Voxalyzer on another host; the file content is uploaded."""
    name = "remote"

    def __init__(self, url: str | None = None):
        self.url = url

    def analyze_mp3(self, file_path: PathLike[str]) -> dict | None:
        url = _analyze_url(self.url if self.url is not None else AppSettings.value(SettingKeys.VOXALYZER_URL, type=str, defaultValue=''))
        if not url:
            logger.error("Voxalyzer URL not set.")
            return None

        logger.debug(f"Sending request to {url} for file {file_path}")
        with open(file_path, 'rb') as f:
            return _post(url, f.read(), 'application/octet-stream')


def get_backend() -> AnalyzerBackend:
    if has_local_voxalyzer() and AppSettings.value(SettingKeys.VOXALYZER_LOCAL, True, type=bool):
        return LocalVoxalyzerBackend()
    elif has_voxalyzer():
        return RemoteVoxalyzerBackend()
    else:
        return MockBackend()


def collect_files(path: PathLike[str]) -> list[Path]:
    """The mp3 files to analyze for a file or a directory (recursive)."""
    path = Path(path)
    if path.is_dir():
        return [path / name for name in list_mp3s(path)]
    return [path]


def analyze_file(file_path: PathLike[str], backend: AnalyzerBackend, progress: Callable[[str], None] = lambda message: None,
                 skip_analyzed: bool | None = None) -> bool:
    """Analyzes one file and writes summary/categories/tags back. Returns True if the file was updated.

    Raises on backend/network errors so callers can report them.
    """
    logger.debug("Processing {0}...", file_path)
    name = Path(file_path).name

    if skip_analyzed is None:
        skip_analyzed = AppSettings.value(SettingKeys.SKIP_ANALYZED_MUSIC, True, type=bool)

    if skip_analyzed and is_analyzed(file_path):
        progress(_("Skipping already analyzed file {0}").format(name))
        logger.debug("Skipping already analyzed file {0}", name)
        return False

    progress(_("Analyzing {0}...").format(name))

    response_data = backend.analyze_mp3(file_path)
    if not response_data:
        return False

    categories = response_data.get("categories")
    if not categories:
        logger.warning("Could not find categories for {0}.", file_path)
        return False

    update_categories_and_tags(file_path, response_data.get("summary"), categories, response_data.get("tags"))
    print_mp3_tags(file_path)

    progress(_("File {0} processed.").format(name))
    return True


__all__ = ["VoxalyzerService", "voxalyzer", "start_voxalyzer", "stop_voxalyzer", "is_analyzed", "is_voxalyzed", "categories_to_string",
           "tags_to_string", "AnalyzerBackend", "MockBackend", "LocalVoxalyzerBackend", "RemoteVoxalyzerBackend", "get_backend",
           "collect_files", "analyze_file", "MOCK_SUMMARY", "has_voxalyzer", "has_local_voxalyzer"]
