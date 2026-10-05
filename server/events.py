"""WebSocket event hub. Thread-safe publish from worker threads."""
import asyncio
import json
import logging

from fastapi import WebSocket

logger = logging.getLogger(__file__)


class EventHub:
    def __init__(self):
        self._clients: set[WebSocket] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind_loop(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self._clients.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self._clients.discard(websocket)

    async def broadcast(self, event: str, data=None):
        message = json.dumps({"event": event, "data": data}, ensure_ascii=False)
        for client in list(self._clients):
            try:
                await client.send_text(message)
            except Exception:
                self.disconnect(client)

    def publish(self, event: str, data=None):
        """Schedules a broadcast; callable from any thread."""
        if self._loop is None or self._loop.is_closed():
            return
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is self._loop:
            self._loop.create_task(self.broadcast(event, data))
        else:
            asyncio.run_coroutine_threadsafe(self.broadcast(event, data), self._loop)


hub = EventHub()
