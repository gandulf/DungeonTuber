"""YouTube downloads behind an agent: yt-dlp runs on another machine (e.g. a home PC that YouTube does not block) that connects out to the server.

Lookups are answered over the agent connection. For a download the server hands the agent a one-time upload address
({"op": "download", "upload": "/api/agents/uploads/<ticket>"}); the agent downloads and converts the video, uploads every mp3 with
PUT <upload>/<index> (agent token) and answers with the titles, which the download queue then stores like a local download.
"""
import asyncio
import logging
import secrets
from pathlib import Path
from typing import Callable

from core.i18n import _
from core.ytimport import DEFAULT_MAX_MINUTES, Downloaded, ImportFailed, RemoteEntry, Resolved
from server.agents import Agent, AgentError, agent_hub
from server.context import current_user_var

logger = logging.getLogger(__file__)

KIND = "youtube"

RESOLVE_TIMEOUT = 180
DOWNLOAD_TIMEOUT = 6 * 3600  # a long video is downloaded, converted, split and uploaded
MAX_UPLOAD_BYTES = 2 * 1024 * 1024 * 1024

_loop: asyncio.AbstractEventLoop | None = None
_uploads: dict[str, Path] = {}


def available() -> bool:
    return agent_hub.get(KIND) is not None


def upload_dir(ticket: str) -> Path | None:
    return _uploads.get(ticket)


def _call(op: str, timeout: float, on_progress: Callable[[dict], None] | None = None, **args):
    """Runs a request on the server's event loop (called from worker threads); agent failures become ImportFailed."""
    with agent_hub.lease(KIND, current_user_var.get()) as agent:  # the agent of the requesting user (their IP and cookies), else the least busy one
        if agent is None or _loop is None:
            raise ImportFailed(_("No YouTube agent connected"))
        try:
            return asyncio.run_coroutine_threadsafe(agent.call(op, timeout=timeout, on_progress=on_progress, **args), _loop).result(timeout + 10)
        except AgentError as e:
            raise ImportFailed(str(e))
        except (ConnectionError, TimeoutError, OSError) as e:
            raise ImportFailed(str(e) or _("The YouTube agent did not answer"))


def resolve(url: str, progress=None, whole: bool | None = None) -> Resolved:
    result = _call("resolve", RESOLVE_TIMEOUT, url=url, whole=whole)
    entries = [RemoteEntry(**entry) for entry in result.get("entries") or []]
    return Resolved(result.get("title") or "", bool(result.get("is_playlist")), entries, bool(result.get("has_video")))


def download(url: str, directory: Path, progress: Callable[[str], None] | None = None, max_minutes: int = DEFAULT_MAX_MINUTES,
             album: str | None = None, percent: Callable[[int], None] | None = None, split: bool = False) -> Downloaded:
    """Same contract as core.ytimport.download; the files arrive in `directory` as <index>.mp3."""
    ticket = secrets.token_urlsafe(24)
    _uploads[ticket] = directory

    def on_progress(message: dict):
        if percent and message.get("percent") is not None:
            percent(int(message["percent"]))
        if progress and message.get("message"):
            progress(str(message["message"]))

    try:
        result = _call("download", DOWNLOAD_TIMEOUT, on_progress, url=url, upload=f"/api/agents/uploads/{ticket}", max_minutes=max_minutes,
                       album=album, split=split)
    finally:
        _uploads.pop(ticket, None)
    files = result.get("files") or []
    if not files:
        raise ImportFailed(_("The download produced no mp3 file"))
    songs = []
    for index, file in enumerate(files):
        path = directory / f"{index}.mp3"
        if not path.is_file():
            raise ImportFailed(_("The agent did not upload {0}").format(file.get("name")))
        songs.append(Downloaded(path, file["name"], file.get("title") or file["name"]))
    if result.get("split"):
        return Downloaded(songs[0].path, result.get("name") or songs[0].name, result.get("title") or "", songs)
    return Downloaded(songs[0].path, songs[0].name, songs[0].title)


async def _changed(agent: Agent):
    from server.events import hub
    hub.publish("import.agent", {"active": available()})


def install():
    global _loop
    _loop = asyncio.get_running_loop()
    agent_hub.on(KIND, _changed, _changed)

