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
import threading
import time
from collections.abc import Awaitable, Callable
from contextlib import contextmanager

from fastapi import WebSocket, WebSocketDisconnect
from starlette.requests import HTTPConnection

from core.settings import AppSettings, SettingKeys
from server.users import ADMIN

logger = logging.getLogger(__file__)

HELLO_TIMEOUT = 10
CALL_TIMEOUT = 15
CLOSE_UNAUTHORIZED = 4401
CLOSE_REMOVED = 4403  # the agent was removed: it must not reconnect
SINGLE_KINDS = {"lights"}  # one agent for the whole server (the bulbs of one network); the other kinds may run in several instances


class AgentError(OSError):
    """The agent could not carry out a request."""


def _digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _stored_tokens() -> list[dict]:
    return list(AppSettings.value(SettingKeys.AGENT_TOKENS, [], type=list) or [])


def create_agent_token(user: str, name: str, token: str | None = None) -> tuple[str, dict]:
    """A new token for `user` (random unless given, e.g. DT_AGENT_TOKEN); the plain token is only available here, the server keeps its hash."""
    token = token or secrets.token_urlsafe(32)
    entry = {"id": secrets.token_hex(6), "name": name.strip()[:60], "user": user, "hash": _digest(token), "created": time.time(), "used": None}
    AppSettings.setValue(SettingKeys.AGENT_TOKENS, [*_stored_tokens(), entry])
    return token, entry


def set_agent_token(token: str):
    """Makes `token` (e.g. DT_AGENT_TOKEN) a token of the SuperAdmin."""
    if not valid_agent_token(token):
        create_agent_token(ADMIN, "DT_AGENT_TOKEN", token)


def agent_tokens(user: str | None = None) -> list[dict]:
    """The tokens without their hashes, of one user or (None) of everybody."""
    return [{key: value for key, value in entry.items() if key != "hash"} for entry in _stored_tokens() if user is None or entry["user"] == user]


def delete_agent_token(token_id: str, user: str | None) -> bool:
    """Revokes a token (of `user` only, unless None); False when there is no such token."""
    stored = _stored_tokens()
    remaining = [entry for entry in stored if entry["id"] != token_id or (user is not None and entry["user"] != user)]
    if len(remaining) == len(stored):
        return False
    AppSettings.setValue(SettingKeys.AGENT_TOKENS, remaining)
    return True


def agent_token_id(token: str | None) -> str | None:
    """The id of the token, None when it is not valid."""
    if not token:
        return None
    digest = _digest(token)
    return next((entry["id"] for entry in _stored_tokens() if hmac.compare_digest(digest, entry["hash"])), None)


def valid_agent_token(token: str | None) -> bool:
    return agent_token_id(token) is not None


def touch_agent_token(token_id: str):
    """Remembers that the token has just been used (an agent connected with it)."""
    AppSettings.setValue(SettingKeys.AGENT_TOKENS, [{**entry, "used": time.time()} if entry["id"] == token_id else entry for entry in _stored_tokens()])


def bearer_token(connection: HTTPConnection) -> str | None:
    header = connection.headers.get("authorization", "")
    return header[7:].strip() if header.lower().startswith("bearer ") else None


_agent_ids = itertools.count(1)


class Agent:
    def __init__(self, websocket: WebSocket, kind: str, name: str, token_id: str | None = None):
        self.id = next(_agent_ids)
        self.websocket = websocket
        self.token_id = token_id
        self.leases = 0  # requests that were handed to this agent and are not finished yet
        self.gate = threading.Semaphore(1)  # for kinds that work on one request at a time
        self.kind = kind
        self.name = name
        self._ids = itertools.count(1)
        self._pending: dict[int, asyncio.Future] = {}
        self._progress: dict[int, Callable[[dict], None]] = {}

    async def call(self, op: str, timeout: float = CALL_TIMEOUT, on_progress: Callable[[dict], None] | None = None, **args):
        """Sends a request and waits for the answer; raises TimeoutError, AgentError or ConnectionError (both OSError).
        A long running agent may report on the way: {"type": "progress", "id": 1, ...} messages are passed to `on_progress`."""
        request_id = next(self._ids)
        future = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        if on_progress is not None:
            self._progress[request_id] = on_progress
        try:
            await self.websocket.send_text(json.dumps({"id": request_id, "op": op, **args}))
            return await asyncio.wait_for(future, timeout)
        except (WebSocketDisconnect, RuntimeError) as e:
            raise ConnectionError(f"Agent {self.name} is not connected") from e
        finally:
            self._pending.pop(request_id, None)
            self._progress.pop(request_id, None)

    def resolve(self, message: dict):
        if message.get("type") == "progress":
            handler = self._progress.get(message.get("id"))
            if handler is not None:
                try:
                    handler(message)
                except Exception as e:  # a faulty handler must not end the connection
                    logger.warning("Progress handler failed: %s", e)
            return
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
    """The connected agents. Most kinds ("voxalyzer", "youtube") may have several instances, the kinds in SINGLE_KINDS ("lights") one:
    a new connection replaces the previous one. Requests go to the agent of the requesting user, otherwise to the least busy one."""

    def __init__(self):
        self._agents: dict[str, list[Agent]] = {}
        self._on_connect: dict[str, Hook] = {}
        self._on_disconnect: dict[str, Hook] = {}
        self._lock = threading.Lock()
        self.on_change: Callable[[], None] | None = None  # the list of connected agents changed

    def _pick(self, kind: str, user: str | None) -> Agent | None:
        candidates = self._agents.get(kind) or []
        own = [agent for agent in candidates if user and self.owner(agent) == user]
        return min(own or candidates, key=lambda agent: agent.leases, default=None)

    def get(self, kind: str, user: str | None = None) -> Agent | None:
        return self._pick(kind, user)

    @contextmanager
    def lease(self, kind: str, user: str | None = None):
        """The agent for one request (None when no agent of the kind is connected); counts as busy until the block ends."""
        with self._lock:
            agent = self._pick(kind, user)
            if agent is not None:
                agent.leases += 1
        try:
            yield agent
        finally:
            if agent is not None:
                with self._lock:
                    agent.leases -= 1

    def status(self) -> list[dict]:
        return [{"id": agent.id, "kind": agent.kind, "name": agent.name, "user": self.owner(agent)}
                for agents in self._agents.values() for agent in agents]

    @staticmethod
    def owner(agent: "Agent") -> str | None:
        return next((entry["user"] for entry in agent_tokens() if entry["id"] == agent.token_id), None)

    async def revoke(self, token_id: str):
        """Disconnects the agents that connected with a token that was just revoked."""
        for agents in list(self._agents.values()):
            for agent in [agent for agent in agents if agent.token_id == token_id]:
                await agent.websocket.close(code=CLOSE_REMOVED)

    async def remove(self, agent_id: int, user: str | None = None) -> bool:
        """Disconnects an agent and tells it to stay away (only one of `user`, unless None); False when there is no such agent."""
        for agents in self._agents.values():
            for agent in agents:
                if agent.id == agent_id and (user is None or self.owner(agent) == user):
                    await agent.websocket.close(code=CLOSE_REMOVED)
                    return True
        return False

    def _changed(self):
        if self.on_change is not None:
            self.on_change()

    def on(self, kind: str, connect: Hook | None = None, disconnect: Hook | None = None):
        if connect:
            self._on_connect[kind] = connect
        if disconnect:
            self._on_disconnect[kind] = disconnect

    async def serve(self, websocket: WebSocket):
        """Handles one agent connection until it closes."""
        token_id = agent_token_id(bearer_token(websocket))
        if token_id is None:
            await websocket.close(code=CLOSE_UNAUTHORIZED)
            return
        touch_agent_token(token_id)
        await websocket.accept()
        agent = None
        try:
            hello = json.loads(await asyncio.wait_for(websocket.receive_text(), HELLO_TIMEOUT))
            kind = str(hello.get("kind") or "")
            if hello.get("type") != "hello" or not kind:
                await websocket.close(code=1008)
                return
            agent = Agent(websocket, kind, str(hello.get("name") or kind), token_id)
            agents = self._agents.setdefault(kind, [])
            # a reconnecting agent (same token and name) replaces its stale connection
            previous = [other for other in agents if kind in SINGLE_KINDS or (other.token_id == token_id and other.name == agent.name)]
            agents[:] = [other for other in agents if other not in previous]
            agents.append(agent)
            self._changed()
            for other in previous:
                other.fail_all()
                await other.websocket.close(code=1000)
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
                if agent in self._agents.get(agent.kind, []):
                    self._agents[agent.kind].remove(agent)
                    self._changed()
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
