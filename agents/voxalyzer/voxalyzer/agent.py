"""Voxalyzer agent: runs on a machine with the analysis models (e.g. a GPU) and connects *out* to a DungeonTuber server.

    voxalyzer --token <agent token> [--server https://dungeontuber.duckdns.org]

The server sends {"op": "analyze", "download": "/api/agents/files/<ticket>"}; the agent downloads that mp3 with its token, analyzes it and
answers with the result, which the server stores. The protocol is the one of the WiZ light agent (see server/agents.py).
"""
import asyncio
import json
import logging
import os
import random
import urllib.request
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit, urlunsplit

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus, WebSocketException

from voxalyzer import MODEL_VERSION
from voxalyzer.mp3 import CATEGORIES

logger = logging.getLogger(__name__)

KIND = "voxalyzer"
DEFAULT_SERVER = "https://dungeontuber.duckdns.org"
MAX_RETRY_DELAY = 30
CLOSE_REMOVED = 4403  # the server's administrator removed this agent
DOWNLOAD_TIMEOUT = 120


def _parts(server: str):
    return urlsplit(server if "://" in server else "http://" + server)


def agent_url(server: str) -> str:
    """http(s)://host[:port][/prefix] -> ws(s)://host[:port][/prefix]/ws/agent"""
    parts = _parts(server)
    scheme = {"http": "ws", "https": "wss"}.get(parts.scheme, parts.scheme)
    return urlunsplit((scheme, parts.netloc, parts.path.rstrip("/") + "/ws/agent", "", ""))


def http_url(server: str, path: str) -> str:
    """The URL of a server path (as sent in a download request)."""
    parts = _parts(server)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/") + path, "", ""))


def to_response(analysis: dict) -> dict:
    """The part of an analysis the server stores, as plain JSON types (numpy scalars -> python)."""
    result = {key: analysis.get(key) for key in ("categories", "tags", "genres", "bpm")}
    return json.loads(json.dumps(result, default=lambda value: value.item() if hasattr(value, "item") else str(value)))


def fake_analysis() -> dict:
    """Mock values for testing without models: the shape of a real result."""
    return {"categories": {category: random.randint(0, 10) for category in CATEGORIES}, "tags": ["Mock"],
            "genres": [random.choice(["Rock", "Ambient", "Orchestral", "Folk"])], "bpm": random.randint(70, 160)}


class Analyzer:
    """Downloads and analyzes the files of the server, one at a time (one GPU session); fake=True only returns mock values."""

    def __init__(self, server: str, token: str, fake: bool = False):
        self.server = server
        self.token = token
        self.fake = fake
        self._lock = asyncio.Lock()
        self._session = None

    def _download(self, path: str) -> str:
        request = urllib.request.Request(http_url(self.server, path), headers={"Authorization": f"Bearer {self.token}"})
        with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT) as response, NamedTemporaryFile(delete=False, suffix=".mp3") as tmp:
            while chunk := response.read(1 << 20):
                tmp.write(chunk)
            return tmp.name

    def _analyze(self, download: str) -> dict:
        if self.fake:
            return fake_analysis()
        from voxalyzer.analyzer import analyze_file, begin_session  # models and onnxruntime are only needed for real work

        if self._session is None:
            self._session = begin_session()
        path = self._download(download)
        try:
            analysis = analyze_file(path, session_handler=self._session, force=True)
        finally:
            os.remove(path)
        if analysis is None:
            raise OSError("The analysis produced no result")
        return to_response(analysis)

    async def handle(self, request: dict):
        op = request.get("op")
        if op == "analyze":
            async with self._lock:
                return await asyncio.to_thread(self._analyze, str(request["download"]))
        if op == "version":
            return MODEL_VERSION
        raise ValueError(f"Unknown operation {op}")

    def close(self):
        if self._session is not None:
            from voxalyzer.analyzer import end_session
            end_session(self._session)


async def answer(websocket, analyzer: Analyzer, raw: str):
    request = json.loads(raw)
    try:
        reply = {"id": request.get("id"), "ok": True, "result": await analyzer.handle(request)}
    except Exception as e:  # reported to the server, the agent keeps running
        logger.warning("%s failed: %s", request.get("op"), e)
        reply = {"id": request.get("id"), "ok": False, "error": str(e) or type(e).__name__}
    await websocket.send(json.dumps(reply))


async def run(server: str, token: str, name: str, analyzer: Analyzer | None = None, once: bool = False) -> int:
    """Stays connected to the server (reconnecting with a growing delay); returns an exit code when the token is rejected."""
    analyzer = analyzer or Analyzer(server, token)
    url = agent_url(server)
    delay = 1
    while True:
        try:
            async with connect(url, additional_headers={"Authorization": f"Bearer {token}"}, ping_timeout=None) as websocket:
                await websocket.send(json.dumps({"type": "hello", "kind": KIND, "name": name}))
                if json.loads(await websocket.recv()).get("type") != "welcome":
                    raise WebSocketException("Unexpected answer of the server")
                logger.info("Connected to %s", url)
                delay = 1
                tasks: set[asyncio.Task] = set()
                async for raw in websocket:
                    task = asyncio.create_task(answer(websocket, analyzer, raw))
                    tasks.add(task)
                    task.add_done_callback(tasks.discard)
        except ConnectionClosed as e:
            if e.rcvd is not None and e.rcvd.code == CLOSE_REMOVED:
                logger.error("The agent was removed on the server")
                return 3
            logger.warning("Connection lost: %s", e)
        except InvalidStatus as e:
            if e.response.status_code in (401, 403):
                logger.error("The server rejected the agent token")
                return 2
            logger.warning("Connection failed: %s", e)
        except (OSError, WebSocketException) as e:
            logger.warning("Connection lost: %s", e)
        if once:
            return 1
        logger.info("Reconnecting in %d s", delay)
        await asyncio.sleep(delay)
        delay = min(delay * 2, MAX_RETRY_DELAY)
