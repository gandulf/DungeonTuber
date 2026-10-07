"""YouTube download agent: runs yt-dlp on this machine and uploads the mp3s to a DungeonTuber server.

    dt-youtube-agent --token <agent token> [--server https://dungeontuber.duckdns.org]

Useful when the server cannot download from YouTube itself (YouTube blocks most data centers): run the agent on a PC at home. The server
sends {"op": "resolve", "url": ...} to look up links and {"op": "download", "url": ..., "upload": "/api/agents/uploads/<ticket>"}; the agent
downloads and converts the video, uploads every mp3 with PUT <upload>/<index> (agent token) and answers with the titles. Progress is sent as
{"type": "progress", "id": <request id>, "message": ..., "percent": ...}. The protocol is the one of the other agents (see server/agents.py).
"""
import argparse
import asyncio
import json
import logging
import os
import platform
import sys
import tempfile
import urllib.request
from dataclasses import asdict
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, InvalidStatus, WebSocketException

try:
    import core  # noqa: F401  (the download code of the server: installed next to the agent, or the checkout this file lives in)
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from core import ytimport  # noqa: E402
from core.agentconfig import agent_config  # noqa: E402
from core.i18n import _  # noqa: E402
from core.ytimport import DEFAULT_MAX_MINUTES, ImportFailed  # noqa: E402

logger = logging.getLogger(__name__)

KIND = "youtube"
DEFAULT_SERVER = "https://dungeontuber.duckdns.org"
MAX_RETRY_DELAY = 30
CLOSE_REMOVED = 4403  # the server's administrator removed this agent
UPLOAD_TIMEOUT = 3600


def _parts(server: str):
    return urlsplit(server if "://" in server else "http://" + server)


def agent_url(server: str) -> str:
    """http(s)://host[:port][/prefix] -> ws(s)://host[:port][/prefix]/ws/agent"""
    parts = _parts(server)
    scheme = {"http": "ws", "https": "wss"}.get(parts.scheme, parts.scheme)
    return urlunsplit((scheme, parts.netloc, parts.path.rstrip("/") + "/ws/agent", "", ""))


def http_url(server: str, path: str) -> str:
    parts = _parts(server)
    return urlunsplit((parts.scheme, parts.netloc, parts.path.rstrip("/") + path, "", ""))


class Worker:
    """Carries out the requests of the server; downloads run one at a time (one conversion keeps a small machine usable)."""

    def __init__(self, server: str, token: str):
        self.server = server
        self.token = token
        self._lock = asyncio.Lock()

    def _upload(self, upload: str, index: int, path: Path):
        size = path.stat().st_size
        with open(path, "rb") as source:
            request = urllib.request.Request(http_url(self.server, f"{upload}/{index}"), data=source, method="PUT",
                                             headers={"Authorization": f"Bearer {self.token}", "Content-Type": "audio/mpeg",
                                                      "Content-Length": str(size)})
            with urllib.request.urlopen(request, timeout=UPLOAD_TIMEOUT):
                pass

    def _download(self, request: dict, progress) -> dict:
        album = request.get("album") or None
        with tempfile.TemporaryDirectory(prefix="dt-youtube-") as tmp:
            result = ytimport.download(str(request["url"]), Path(tmp), lambda message: progress(message=message),
                                       int(request.get("max_minutes") or DEFAULT_MAX_MINUTES), album,
                                       lambda value: progress(percent=value), bool(request.get("split")))
            songs = result.parts or [result]
            progress(message=_("Uploading {0}...").format(result.title))
            for index, song in enumerate(songs):
                self._upload(str(request["upload"]), index, song.path)
            return {"title": result.title, "name": result.name, "split": bool(result.parts),
                    "files": [{"name": song.name, "title": song.title} for song in songs]}

    async def handle(self, request: dict, progress):
        op = request.get("op")
        if op == "resolve":
            resolved = await asyncio.to_thread(ytimport.resolve, str(request["url"]), None, request.get("whole"))
            return asdict(resolved)
        if op == "download":
            async with self._lock:
                return await asyncio.to_thread(self._download, request, progress)
        if op == "version":
            return _yt_dlp_version()
        raise ValueError(f"Unknown operation {op}")


def _yt_dlp_version() -> str:
    from yt_dlp.version import __version__
    return __version__


async def answer(websocket, worker: Worker, raw: str):
    request = json.loads(raw)
    loop = asyncio.get_running_loop()

    def progress(message: str | None = None, percent: int | None = None):  # called from the download thread
        report = {"type": "progress", "id": request.get("id"), "message": message, "percent": percent}
        asyncio.run_coroutine_threadsafe(websocket.send(json.dumps(report)), loop)

    try:
        reply = {"id": request.get("id"), "ok": True, "result": await worker.handle(request, progress)}
    except ImportFailed as e:
        reply = {"id": request.get("id"), "ok": False, "error": str(e)}
    except Exception as e:  # reported to the server, the agent keeps running
        logger.warning("{0} failed: {1}", request.get("op"), e)
        reply = {"id": request.get("id"), "ok": False, "error": str(e) or type(e).__name__}
    await websocket.send(json.dumps(reply))


async def run(server: str, token: str, name: str, worker: Worker | None = None, once: bool = False) -> int:
    """Stays connected to the server (reconnecting with a growing delay); returns an exit code when the token is rejected."""
    worker = worker or Worker(server, token)
    url = agent_url(server)
    delay = 1
    while True:
        try:
            async with connect(url, additional_headers={"Authorization": f"Bearer {token}"}, ping_timeout=None) as websocket:
                await websocket.send(json.dumps({"type": "hello", "kind": KIND, "name": name}))
                if json.loads(await websocket.recv()).get("type") != "welcome":
                    raise WebSocketException("Unexpected answer of the server")
                logger.info("Connected to {0}", url)
                delay = 1
                tasks: set[asyncio.Task] = set()
                async for raw in websocket:
                    task = asyncio.create_task(answer(websocket, worker, raw))
                    tasks.add(task)
                    task.add_done_callback(tasks.discard)
        except ConnectionClosed as e:
            if e.rcvd is not None and e.rcvd.code == CLOSE_REMOVED:
                logger.error("The agent was removed on the server")
                return 3
            logger.warning("Connection lost: {0}", e)
        except InvalidStatus as e:
            if e.response.status_code in (401, 403):
                logger.error("The server rejected the agent token")
                return 2
            logger.warning("Connection failed: {0}", e)
        except (OSError, WebSocketException) as e:
            logger.warning("Connection lost: {0}", e)
        if once:
            return 1
        logger.info("Reconnecting in {0} s", delay)
        await asyncio.sleep(delay)
        delay = min(delay * 2, MAX_RETRY_DELAY)


def build_parser() -> argparse.ArgumentParser:
    env = os.environ.get
    config = agent_config()
    parser = argparse.ArgumentParser(prog="dt-youtube-agent", description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--server", default=env("DT_SERVER") or config.get("server") or DEFAULT_SERVER, help="URL of the DungeonTuber server (default: %(default)s)")
    parser.add_argument("--token", default=env("DT_AGENT_TOKEN") or config.get("token"), help="agent token created in the DungeonTuber settings")
    parser.add_argument("--name", default=env("DT_AGENT_NAME") or config.get("name") or platform.node() or "youtube", help="name shown in the server log")
    parser.add_argument("--cookies", default=env("DT_COOKIES"), help="cookies.txt of a signed-in YouTube session")
    parser.add_argument("--cookies-from-browser", default=env("DT_COOKIES_FROM_BROWSER"), metavar="BROWSER",
                        help="take the YouTube cookies from a browser profile (firefox, chrome, edge, ...)")
    parser.add_argument("--verbose", action="store_true", help="log debug output")
    return parser


def main(argv: list[str] | None = None):
    from core.log import StrFormatLogRecord

    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.token:
        parser.error("--token is required (or DT_AGENT_TOKEN, or the token in agents.json)")
    logging.setLogRecordFactory(StrFormatLogRecord)
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ytimport.use_cookies(args.cookies, args.cookies_from_browser)
    try:
        sys.exit(asyncio.run(run(args.server, args.token, args.name)))
    except KeyboardInterrupt:
        sys.exit(0)


if __name__ == "__main__":
    main()
