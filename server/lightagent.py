"""WiZ bulbs behind a light agent: RemoteControl mimics the pywizlight bulb API and forwards it to the agent in the home network."""
import logging
from types import SimpleNamespace

from pywizlight import PilotBuilder, PilotParser

from core.lights import light_registry
from server.agents import Agent, agent_hub
from server.events import hub

logger = logging.getLogger(__file__)

KIND = "lights"


class RemoteControl:
    """Stands in for `pywizlight.wizlight` / `MockControl` in `core.lights.Light.control`."""

    def __init__(self, mac: str, ip: str | None = None):
        self.mac = mac
        self.ip = ip
        self._kelvin: list[int] | None = None
        self._scenes: list[str] = []

    @staticmethod
    async def _call(op: str, **args):
        agent = agent_hub.get(KIND)
        if agent is None:
            raise ConnectionError("No light agent connected")
        return await agent.call(op, **args)

    async def updateState(self) -> PilotParser:
        result = await self._call("state", mac=self.mac)
        self._kelvin = result.get("kelvin")
        self._scenes = result.get("scenes") or []
        return PilotParser(result["pilot"])

    async def get_bulbtype(self):
        if not self._kelvin:
            return None
        low, high = self._kelvin
        return SimpleNamespace(kelvin_range=SimpleNamespace(min=low, max=high))

    async def getSupportedScenes(self) -> list[str]:
        return self._scenes

    async def turn_on(self, pilot: PilotBuilder):
        await self._call("pilot", mac=self.mac, params=pilot.set_pilot_message(state=True)["params"])

    async def turn_off(self):
        await self._call("off", mac=self.mac)


async def remote_bulbs() -> list[RemoteControl] | None:
    """The bulbs the connected light agent can reach; None when there is no agent."""
    agent = agent_hub.get(KIND)
    if agent is None:
        return None
    found = await agent.call("discover", timeout=60)
    return [RemoteControl(entry["mac"], entry.get("ip")) for entry in found]


async def _connected(agent: Agent):
    await light_registry.discover()
    light_registry.save()
    hub.publish("lights.state", [light.to_dict() for light in light_registry.lights])


async def _disconnected(agent: Agent):
    for light in light_registry.lights:
        if isinstance(light.control, RemoteControl):
            light.control = None
    hub.publish("lights.state", [light.to_dict() for light in light_registry.lights])


def install():
    """Routes the light registry through the agent while one is connected."""
    light_registry.remote_bulbs = remote_bulbs
    agent_hub.on(KIND, _connected, _disconnected)
