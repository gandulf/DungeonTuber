"""Voxalyzer behind an agent: the analysis runs on another machine (e.g. with a GPU) that connects out to the server.
Without an agent the on-demand cloud function (server/voxcloud.py) is used when one is configured.

For every file the server hands the agent a one-time download ticket ({"op": "analyze", "download": "/api/agents/files/<ticket>"}); the
agent fetches the mp3 with its token, analyzes it and answers with the result, which the analysis queue then stores like any other backend.
"""
import asyncio
import logging
import secrets
import threading
from os import PathLike
from pathlib import Path

from core.analyzer import AnalyzerBackend
from server import voxcloud
from server.agents import Agent, agent_hub
from server.events import hub

logger = logging.getLogger(__file__)

# Seconds to wait for one analysis (download included); analyzing a long track can take a while.
ANALYZE_TIMEOUT = 600

KIND = "voxalyzer"

_loop: asyncio.AbstractEventLoop | None = None
_tickets: dict[str, Path] = {}
_gate = threading.Semaphore(1)  # one file at a time: the agent has a single GPU session and the call timeout is per file


def ticket_path(ticket: str) -> Path | None:
    return _tickets.get(ticket)


class AgentVoxalyzerBackend(AnalyzerBackend):
    """Called from the analysis worker threads; talks to the agent on the server's event loop."""
    name = "agent"

    def analyze_mp3(self, file_path: PathLike[str]) -> dict | None:
        agent = agent_hub.get(KIND)
        if agent is None or _loop is None:
            raise ConnectionError("No Voxalyzer agent connected")
        with _gate:
            ticket = secrets.token_urlsafe(24)
            _tickets[ticket] = Path(file_path)
            try:
                call = asyncio.run_coroutine_threadsafe(
                    agent.call("analyze", timeout=ANALYZE_TIMEOUT, download=f"/api/agents/files/{ticket}"), _loop)
                return call.result(ANALYZE_TIMEOUT + 10)
            finally:
                _tickets.pop(ticket, None)


def current_backend() -> AnalyzerBackend | None:
    """The connected Voxalyzer agent, else the cloud function; None when nothing can analyze."""
    return AgentVoxalyzerBackend() if agent_hub.get(KIND) is not None else voxcloud.current_backend()


def publish_availability():
    hub.publish("analysis.available", {"active": current_backend() is not None})


async def _connected(agent: Agent):
    publish_availability()


async def _disconnected(agent: Agent):
    publish_availability()


def install():
    global _loop
    _loop = asyncio.get_running_loop()
    agent_hub.on(KIND, _connected, _disconnected)
