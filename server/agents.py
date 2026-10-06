"""Agents: helper programs on other machines (WiZ lights in the home network, GPU analysis, ...) that connect *out* to the server.

An agent opens a WebSocket to /ws/agent, authenticates with the agent token (not a user password) and then answers requests of the
server: {"id": 1, "op": "discover", ...} -> {"id": 1, "ok": true, "result": ...} or {"id": 1, "ok": false, "error": "..."}.
"""
import asyncio
import hashlib
import hmac
import itertools
import json
import logging
import secrets
from collections.abc import Awaitable, Callable

from fastapi import WebSocket, WebSocketDisconnect

from core.settings import AppSettings, SettingKeys

logger = logging.getLogger(__file__)

HELLO_TIMEOUT = 10
CALL_TIMEOUT = 15
CLOSE_UNAUTHORIZED = 4401


class AgentError(OSError):
    """The agent could not carry out a request."""


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def set_agent_token(token: str | None):
    if token:
        AppSettings.setValue(SettingKeys.AGENT_TOKEN_HASH, _digest(token))
    else:
        AppSettings.remove(SettingKeys.AGENT_TOKEN_HASH)


def new_agent_token() -> str:
    """Replaces the agent token (agents using the old one are locked out); the plain token is only available here."""
    token = secrets.token_urlsafe(32)
    set_agent_token(token)
    return token


def agent_token_set() -> bool:
    return bool(AppSettings.value(SettingKeys.AGENT_TOKEN_HASH, type=str))


def valid_agent_token(token: str | None) -> bool:
    stored = AppSettings.value(SettingKeys.AGENT_TOKEN_HASH, type=str)
    return bool(token and stored and hmac.compare_digest(_digest(token), stored))


def bearer_token(websocket: WebSocket) -> str | None:
    header = websocket.headers.get("authorization", "")
    return header[7:].strip() if header.lower().startswith("bearer ") else None


class Agent:
    def __init__(self, websocket: WebSocket, kind: str, name: str):
        self.websocket = websocket
        self.kind = kind
        self.name = name
        self._ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future] = {}

    async def call(self, op: str, timeout: float = CALL_TIMEOUT, **args):
        """Sends a request and waits for the answer; raises TimeoutError, AgentError or ConnectionError (both OSError)."""
        request_id = next(self._ids)
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            await self.websocket.send_text(json.dumps({"id": request_id, "op": op, **args}))
            return await asyncio.wait_for(future, timeout)
        except (WebSocketDisconnect, RuntimeError) as e:
            raise ConnectionError(f"Agent {self.name} is not connected") from e
        finally:
            self._pending.pop(request_id, None)

    def resolve(self, message: dict):
        future = self._pending.get(message.get("id"))
        if future is None or future.done():
            return
        if message.get("ok"):
            future.set_result(message.get("result"))
        else:
            future.set_exception(AgentError(str(message.get("error") or "Agent error")))

    def fail_all(self):
        for future in self._pending.values():
            if not future.done():
                future.set_exception(ConnectionError(f"Agent {self.name} disconnected"))


Hook = Callable[[Agent], Awaitable[None]]


class AgentHub:
    """The connected agents, one per kind ("lights", ...); a new connection replaces the previous one of its kind."""

    def __init__(self):
        self._agents: dict[str, Agent] = {}
        self._on_connect: dict[str, Hook] = {}
        self._on_disconnect: dict[str, Hook] = {}

    def get(self, kind: str) -> Agent | None:
        return self._agents.get(kind)

    def status(self) -> list[dict]:
        return [{"kind": agent.kind, "name": agent.name} for agent in self._agents.values()]

    def on(self, kind: str, connect: Hook | None = None, disconnect: Hook | None = None):
        if connect:
            self._on_connect[kind] = connect
        if disconnect:
            self._on_disconnect[kind] = disconnect

    async def serve(self, websocket: WebSocket):
        """Handles one agent connection until it closes."""
        if not valid_agent_token(bearer_token(websocket)):
            await websocket.close(code=CLOSE_UNAUTHORIZED)
            return
        await websocket.accept()
        agent = None
        try:
            hello = json.loads(await asyncio.wait_for(websocket.receive_text(), HELLO_TIMEOUT))
            kind = str(hello.get("kind") or "")
            if hello.get("type") != "hello" or not kind:
                await websocket.close(code=1008)
                return
            agent = Agent(websocket, kind, str(hello.get("name") or kind))
            previous = self._agents.get(kind)
            self._agents[kind] = agent
            if previous is not None:
                previous.fail_all()
                await previous.websocket.close(code=1000)
            await websocket.send_text(json.dumps({"type": "welcome"}))
            logger.info("Agent %s (%s) connected", agent.name, kind)
            # runs next to the receive loop: the hook itself talks to the agent
            hook = asyncio.create_task(self._run(self._on_connect.get(kind), agent))
            try:
                while True:
                    agent.resolve(json.loads(await websocket.receive_text()))
            finally:
                hook.cancel()
        except (WebSocketDisconnect, asyncio.TimeoutError, ValueError):
            pass
        finally:
            if agent is not None:
                agent.fail_all()
                if self._agents.get(agent.kind) is agent:
                    del self._agents[agent.kind]
                    await self._run(self._on_disconnect.get(agent.kind), agent)
                logger.info("Agent %s (%s) disconnected", agent.name, agent.kind)

    @staticmethod
    async def _run(hook: Hook | None, agent: Agent):
        if hook is None:
            return
        try:
            await hook(agent)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.warning("Agent hook for %s failed: %s", agent.kind, e)


agent_hub = AgentHub()
