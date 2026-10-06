"""DungeonTuber WiZ light agent.

Runs on a machine in the same network as the WiZ bulbs, connects *out* to the DungeonTuber server and carries out its light commands:

    python dt_wiz_agent.py --token <agent token> [--server https://dungeontuber.duckdns.org]

Settings can also be given as environment variables: DT_SERVER, DT_AGENT_TOKEN, DT_AGENT_NAME, DT_BROADCAST, DT_FAKE_LIGHTS=1.
"""
import argparse
import asyncio
import json
import logging
import os
import platform
import sys
from urllib.parse import urlsplit, urlunsplit

from pywizlight import PilotParser, wizlight
from pywizlight.discovery import BroadcastProtocol, DEFAULT_WAIT_TIME, PORT
from pywizlight.models import BulbRegistry
from pywizlight.scenes import SCENES
from pywizlight.utils import create_udp_broadcast_socket
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus, WebSocketException

logger = logging.getLogger("dt-wiz-agent")

MAX_RETRY_DELAY = 30
DEFAULT_SERVER = "https://dungeontuber.duckdns.org"


def agent_url(server: str) -> str:
    """http(s)://host[:port][/prefix] -> ws(s)://host[:port][/prefix]/ws/agent"""
    parts = urlsplit(server if "://" in server else "http://" + server)
    scheme = {"http": "ws", "https": "wss"}.get(parts.scheme, parts.scheme)
    return urlunsplit((scheme, parts.netloc, parts.path.rstrip("/") + "/ws/agent", "", ""))


async def find_bulbs(broadcast: str, wait: float) -> list[wizlight]:
    """Broadcast discovery (pywizlight's own helper does not take the broadcast address of the network)."""
    registry = BulbRegistry()
    loop = asyncio.get_running_loop()
    future = loop.create_future()
    transport, _ = await loop.create_datagram_endpoint(lambda: BroadcastProtocol(loop, registry, broadcast, future),
                                                       sock=create_udp_broadcast_socket(PORT))
    await asyncio.sleep(wait)
    transport.close()
    return [wizlight(ip=entry.ip_address, mac=entry.mac_address) for entry in registry.bulbs()]


class FakeBulb:
    """Simulated bulb for testing without hardware."""

    def __init__(self, mac: str):
        self.mac = mac
        self.pilot = {"state": True, "mac": mac, "dimming": 100, "temp": 4000, "r": 250, "g": 0, "b": 0, "c": 128, "w": 128, "sceneId": None}

    async def state(self) -> dict:
        return {"pilot": dict(self.pilot), "kelvin": [2200, 6500], "scenes": list(SCENES.values())}

    async def pilot_set(self, params: dict):
        self.pilot.update(params)

    async def off(self):
        self.pilot["state"] = False


class RealBulb:
    def __init__(self, bulb: wizlight):
        self.bulb = bulb
        self.mac = bulb.mac

    async def state(self) -> dict:
        states = await self.bulb.updateState()
        if isinstance(states, list):  # newer pywizlight versions return one state per bulb head
            states = next((s for s in states if s is not None), None)
        if not isinstance(states, PilotParser):
            raise OSError("Bulb did not answer")
        bulb_type = await self.bulb.get_bulbtype()
        kelvin = bulb_type.kelvin_range if bulb_type is not None else None
        return {"pilot": states.pilotResult, "kelvin": [kelvin.min, kelvin.max] if kelvin else None,
                "scenes": list(await self.bulb.getSupportedScenes() or [])}

    async def pilot_set(self, params: dict):
        await self.bulb.send({"method": "setPilot", "params": params})

    async def off(self):
        await self.bulb.turn_off()


class Bulbs:
    """The bulbs found by the last discovery, by MAC address."""

    def __init__(self, broadcast: str, wait: float, fake: bool):
        self.broadcast = broadcast
        self.wait = wait
        self.fake = fake
        self._bulbs: dict[str, FakeBulb | RealBulb] = {}

    async def discover(self) -> list[dict]:
        if self.fake:
            found = self._bulbs or {mac: FakeBulb(mac) for mac in (f"aa:bb:cc:dd:ee:f{n}" for n in range(3))}
            self._bulbs = found
            return [{"mac": mac, "ip": "127.0.0.1"} for mac in found]
        bulbs = await find_bulbs(self.broadcast, self.wait)
        self._bulbs = {bulb.mac: RealBulb(bulb) for bulb in bulbs}
        logger.info("Discovered %d bulbs", len(bulbs))
        return [{"mac": bulb.mac, "ip": bulb.ip} for bulb in bulbs]

    def _bulb(self, mac: str):
        try:
            return self._bulbs[mac]
        except KeyError:
            raise OSError(f"Unknown bulb {mac}") from None

    async def handle(self, request: dict):
        op = request.get("op")
        if op == "discover":
            return await self.discover()
        bulb = self._bulb(request.get("mac"))
        if op == "state":
            return await bulb.state()
        if op == "pilot":
            return await bulb.pilot_set(request.get("params") or {})
        if op == "off":
            return await bulb.off()
        raise ValueError(f"Unknown operation {op}")


async def answer(websocket, bulbs: Bulbs, raw: str):
    request = json.loads(raw)
    try:
        reply = {"id": request.get("id"), "ok": True, "result": await bulbs.handle(request)}
    except Exception as e:  # reported to the server, the agent keeps running
        logger.warning("%s failed: %s", request.get("op"), e)
        reply = {"id": request.get("id"), "ok": False, "error": str(e) or type(e).__name__}
    await websocket.send(json.dumps(reply))


async def run(url: str, token: str, name: str, bulbs: Bulbs, once: bool = False) -> int:
    """Stays connected to the server (reconnecting with a growing delay); returns an exit code when the token is rejected."""
    delay = 1
    while True:
        try:
            async with connect(url, additional_headers={"Authorization": f"Bearer {token}"}) as websocket:
                await websocket.send(json.dumps({"type": "hello", "kind": "lights", "name": name}))
                if json.loads(await websocket.recv()).get("type") != "welcome":
                    raise WebSocketException("Unexpected answer of the server")
                logger.info("Connected to %s", url)
                delay = 1
                tasks: set[asyncio.Task] = set()
                async for raw in websocket:
                    task = asyncio.create_task(answer(websocket, bulbs, raw))
                    tasks.add(task)
                    task.add_done_callback(tasks.discard)
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


def main(argv: list[str] | None = None) -> int:
    env = os.environ.get
    parser = argparse.ArgumentParser(prog="dt-wiz-agent", description="WiZ light agent for a DungeonTuber server")
    parser.add_argument("--server", default=env("DT_SERVER", DEFAULT_SERVER), help="URL of the DungeonTuber server (default: %(default)s)")
    parser.add_argument("--token", default=env("DT_AGENT_TOKEN"), help="Agent token (Settings > Lights in DungeonTuber)")
    parser.add_argument("--name", default=env("DT_AGENT_NAME", platform.node() or "wiz-agent"), help="Name shown in the server log")
    parser.add_argument("--broadcast", default=env("DT_BROADCAST", "255.255.255.255"), help="Broadcast address of the bulb network")
    parser.add_argument("--wait", type=float, default=DEFAULT_WAIT_TIME, help="Seconds to wait for bulbs to answer a discovery")
    parser.add_argument("--fake", action="store_true", default=env("DT_FAKE_LIGHTS") == "1", help="Simulate three bulbs")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args(argv)
    if not args.token:
        parser.error("--token is required (or DT_AGENT_TOKEN)")

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        return asyncio.run(run(agent_url(args.server), args.token, args.name, Bulbs(args.broadcast, args.wait, args.fake)))
    except KeyboardInterrupt:
        return 0


if __name__ == "__main__":
    sys.exit(main())
