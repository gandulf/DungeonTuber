"""WiZ light model, persistence and discovery (Qt-free)."""
import asyncio
import json
import logging
import random
from dataclasses import dataclass, field
from functools import partial
from typing import List, Optional

from pywizlight import wizlight, PilotBuilder, PilotParser, BulbType
from pywizlight.discovery import DEFAULT_WAIT_TIME, BroadcastProtocol, PORT
from pywizlight.models import DiscoveredBulb, BulbRegistry
from pywizlight.scenes import get_id_from_scene_name, SCENES
from pywizlight.utils import create_udp_broadcast_socket

from core.settings import SettingKeys, AppSettings
from core.utils import asdict_filtered, to_hex_color, hex_to_rgb, get_broadcast_ip

logger = logging.getLogger(__file__)


@dataclass
class LightSetting:
    scene: str | None = None
    brightness: int = 255  # 0..255
    temperature: int | None = None  # 1000 - 10000
    color: str | None = None  # '#rrggbb'

    def __init__(self, brightness: int = 255, temperature: int = None, color=None, scene: str | None = None):
        self.scene = scene
        self.brightness = brightness
        self.temperature = temperature
        self.color = to_hex_color(color)

    def is_empty(self) -> bool:
        return (self.scene is None and self.color is None and (self.brightness is None or self.brightness == 255)
                and (self.temperature is None or self.temperature == 1000))

    @property
    def scene_id(self):
        try:
            return get_id_from_scene_name(self.scene) if self.scene is not None else None
        except ValueError as e:
            logger.warning(f"Invalid scene name '{self.scene}': {e}")
            return None

    @property
    def rgb(self) -> tuple[int, int, int] | None:
        return hex_to_rgb(self.color)

    def to_dict(self) -> dict:
        return {"scene": self.scene, "brightness": self.brightness, "temperature": self.temperature, "color": self.color}

    @classmethod
    def json_dump_list(cls, lights: list):
        return json.dumps([asdict_filtered(mc) for mc in lights])

    def json_dump(self):
        return json.dumps(self.to_dict())

    @classmethod
    def json_load(cls, json_string: str):
        data = json.loads(json_string)
        return LightSetting(**{k: v for k, v in data.items() if k in ("scene", "brightness", "temperature", "color")})


@dataclass(eq=False)
class Light(LightSetting):
    name: str | None = "Light"
    mac: str | None = None
    scenable: bool = True
    state: bool = False

    control: wizlight | None = field(default=None, metadata={'export': False})
    loop: asyncio.AbstractEventLoop = field(default=None, metadata={'export': False})

    temperature_min: int = field(default=1000, metadata={'export': False})
    temperature_max: int = field(default=10000, metadata={'export': False})

    scenes: list[str] = field(default=None, metadata={'export': False})

    def __init__(self, name: str = None, scenable: bool = True, mac: str | None = None, state: bool = False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = name
        self.mac = mac
        self.scenable = scenable
        self.state = state
        self.control = None
        self.loop = None
        self.temperature_min = 1000
        self.temperature_max = 10000
        self.scenes = None

    def apply_settings(self, settings: LightSetting):
        self.temperature = settings.temperature
        self.brightness = settings.brightness
        self.color = settings.color
        self.scene = settings.scene

        self.turn_on(self._pilot())

    def get_settings(self):
        return self

    async def update_state(self):
        if self.state:
            await self._turn_on(self._pilot())
        else:
            await self._turn_off()

    async def refresh_state(self):
        state = await self.control.updateState()

        self.mac = state.get_mac()

        if state.get_state() is not None:
            self.state = state.get_state()
        if state.get_colortemp() is not None:
            self.temperature = state.get_colortemp()
        if state.get_brightness() is not None:
            self.brightness = state.get_brightness()

        red, green, blue = state.get_rgb()
        if red is not None and green is not None and blue is not None:
            self.color = to_hex_color((red, green, blue))
        else:
            self.color = None

        bulb_type = await self.control.get_bulbtype()

        if bulb_type is not None and bulb_type.kelvin_range is not None:
            self.temperature_min = bulb_type.kelvin_range.min
            self.temperature_max = bulb_type.kelvin_range.max

        self.scenes = await self.control.getSupportedScenes()
        self.scene = state.get_scene()

    def set_color(self, value):
        self.color = to_hex_color(value)
        self.turn_on(PilotBuilder(rgb=self.rgb if self.color is not None else (255, 255, 255)))

    def set_brightness(self, value):
        self.brightness = value
        self.turn_on(PilotBuilder(brightness=value))

    def set_temperature(self, value):
        self.temperature = value
        self.turn_on(PilotBuilder(colortemp=value))

    def set_state(self, value):
        self.state = value
        if self.state:
            self.turn_on(self._pilot())
        else:
            self.turn_off()

    def set_scene_id(self, value: str | None):
        self.scene = value
        if self.scene_id is not None:
            self.turn_on(PilotBuilder(scene=self.scene_id))

    def set_scene(self, brightness: int | None = None, temperature: int | None = None, color=None):
        if brightness:
            self.brightness = brightness

        if temperature:
            self.temperature = temperature

        if color:
            self.color = to_hex_color(color)

        self.turn_on(self._pilot())

    def _pilot(self):
        return PilotBuilder(scene=self.scene_id, brightness=self.brightness, colortemp=self.temperature, rgb=self.rgb)

    def turn_on(self, pilot_builder: PilotBuilder = PilotBuilder()):
        if self.state:
            self._execute(partial(self._turn_on, pilot_builder))

    def turn_off(self):
        self._execute(self._turn_off)

    async def _turn_on(self, pilot_builder: PilotBuilder):
        await self.control.turn_on(pilot_builder)

    async def _turn_off(self):
        await self.control.turn_off()

    def _execute(self, func):
        if self.control is None:
            return None

        self.loop = asyncio.get_event_loop()

        if self.loop.is_running():
            return asyncio.run_coroutine_threadsafe(func(), self.loop).result(5)
        else:
            return self.loop.run_until_complete(func())  # If the loop isn't running, we run it until this task finishes

    # --- async API (for callers that already run an event loop, e.g. the server) ---
    async def apply_settings_async(self, settings: LightSetting):
        self.temperature = settings.temperature
        self.brightness = settings.brightness
        self.color = settings.color
        self.scene = settings.scene
        if self.state and self.control is not None:
            await self._turn_on(self._pilot())

    async def set_state_async(self, value: bool):
        self.state = value
        if self.control is None:
            return
        if value:
            await self._turn_on(self._pilot())
        else:
            await self._turn_off()

    async def update_async(self, brightness: int | None = None, temperature: int | None = None, color=None, scene: str | None = None,
                           clear_color: bool = False):
        """Changes values like the UI does: color, temperature and scene are mutually exclusive."""
        if brightness is not None:
            self.brightness = brightness
        if clear_color:
            self.color = None
        if color is not None:
            self.color, self.temperature, self.scene = to_hex_color(color), None, None
        elif temperature is not None:
            self.color, self.temperature, self.scene = None, temperature, None
        elif scene is not None:
            self.color, self.temperature, self.scene = None, None, scene or None

        if self.state and self.control is not None:
            await self._turn_on(self._pilot())

    def to_dict(self) -> dict:
        data = super().to_dict()
        data.update({"name": self.name, "mac": self.mac, "scenable": self.scenable, "state": self.state, "online": self.control is not None,
                     "temperature_min": self.temperature_min, "temperature_max": self.temperature_max,
                     "scenes": list(self.scenes) if self.scenes else list(SCENES.values())})
        return data

    def _identity(self):
        return self.mac if self.mac else self.name

    def __hash__(self):
        return hash(self._identity())

    def __eq__(self, other):
        if not isinstance(other, Light):
            return False
        return self._identity() == other._identity()

    @classmethod
    def json_dump_list(cls, lights: list):
        return json.dumps([asdict_filtered(mc) for mc in lights])

    def json_dump(self):
        return json.dumps(asdict_filtered(self))

    @classmethod
    def json_load(cls, json_string: str):
        return Light(**json.loads(json_string))


class LightRegistry:
    """Known lights and the fake-bulb switch used for development without real hardware."""

    def __init__(self):
        self.fake_bulbs = False
        self.lights: set[Light] = set()

    def load(self):
        """Loads the persisted light names/settings."""
        try:
            raw = AppSettings.value(SettingKeys.LIGHTS_CONFIG)
            if raw:
                data = json.loads(raw) if isinstance(raw, str) else raw
                self.lights.update(Light(**d) for d in data)
        except Exception as e:
            AppSettings.remove(SettingKeys.LIGHTS_CONFIG)
            logger.error("Failed to load lights config: {0}", e)

    def save(self):
        AppSettings.setValue(SettingKeys.LIGHTS_CONFIG, Light.json_dump_list(self.lights))

    def set_lights(self, lights: list | None):
        if lights is None:
            AppSettings.remove(SettingKeys.LIGHTS_CONFIG)
            self.lights.clear()
        else:
            AppSettings.setValue(SettingKeys.LIGHTS_CONFIG, Light.json_dump_list(lights))
            self.lights.update(lights)

    def find(self, mac: str) -> Light | None:
        for light in self.lights:
            if light.mac == mac:
                return light
        return None

    async def discover(self) -> list[Light]:
        """Discovers bulbs on the LAN (or creates mock bulbs in fake mode) and merges them with known lights."""
        if self.fake_bulbs:
            bulbs = []
            for n in range(3):
                control = MockControl()
                control.mac = f"AA:BB:CC:DD:EE:F{n}"
                bulbs.append(control)
        else:
            broadcast_address = AppSettings.value(SettingKeys.LIGHTS_BROADCAST_IP, get_broadcast_ip(), type=str)
            timeout = AppSettings.value(SettingKeys.LIGHTS_TIMEOUT, 5, type=float)
            logger.info("Start lookup with broadcast address: %s for %s seconds", broadcast_address, timeout)
            bulbs = await discover_lights(broadcast_space=broadcast_address, wait_time=timeout)

        return await self.update_states(bulbs)

    async def update_states(self, bulbs: list) -> list[Light]:
        lights = []
        for bulb in bulbs:
            light = self.find(bulb.mac)

            if light is None:
                light = Light()
                light.name = "Change me"
                light.control = bulb
                await light.refresh_state()
                self.lights.add(light)
            else:
                light.control = bulb
                await light.update_state()
                await light.refresh_state()

            lights.append(light)

        return lights


light_registry = LightRegistry()


def fake_lights_mode():
    light_registry.fake_bulbs = True


def set_lights(lights: list):
    light_registry.set_lights(lights)


def get_lights():
    return light_registry.lights


def save_on_exit():
    logger.debug("Saving lights as %s" % Light.json_dump_list(get_lights()))
    light_registry.save()


# wizlight BUGFIX BEGIN
async def find_wizlights(
        wait_time: float = DEFAULT_WAIT_TIME, broadcast_address: str = "255.255.255.255"
) -> List[DiscoveredBulb]:
    """Start discovery and return list of IPs of the bulbs."""
    registry = BulbRegistry()
    loop = asyncio.get_event_loop()
    future = loop.create_future()
    transport, protocol = await loop.create_datagram_endpoint(
        lambda: BroadcastProtocol(loop, registry, broadcast_address, future),
        sock=create_udp_broadcast_socket(PORT),
    )
    await asyncio.sleep(wait_time)
    transport.close()

    bulbs = registry.bulbs()

    logger.debug(f"Discovered {len(bulbs)} bulbs.")

    return bulbs


async def discover_lights(
        broadcast_space: str = "255.255.255.255", wait_time: float = DEFAULT_WAIT_TIME
) -> List[wizlight]:
    """Find lights and return list with wizlight objects."""
    discovered = await find_wizlights(wait_time=wait_time, broadcast_address=broadcast_space)
    return [wizlight(ip=entry.ip_address, mac=entry.mac_address) for entry in discovered]
# wizlight BUGFIX END


class MockControl:
    mac: str = "AA:BB:CC:DD:EE"

    state: bool = True
    r: int = 250
    g: int = 0
    b: int = 0
    temp: int = 4000
    c: int = 128
    w: int = 128
    scene_id: int = None
    dimming: int = 100

    def __init__(self):
        self.mac = self.generate_mac()

    def generate_mac(self):
        mac = [random.randint(0x00, 0xff) for _ in range(6)]
        return ":".join(f"{b:02x}" for b in mac)

    async def updateState(self) -> Optional[PilotParser]:
        fake_response = {
            "state": self.state,
            "src": "127.0.0.1",
            "mac": self.mac,
            "pc": 1000,
            "w": self.w,
            "whiteRange": [1000, 3000],
            "extRange": [2200, 2700, 6500, 6500],
            "speed": 100,
            "ratio": 10,
            "sceneId": self.scene_id,
            "c": self.c,
            "dimming": self.dimming,
            "temp": self.temp
        }

        if self.r is not None:
            fake_response["r"] = self.r
        if self.g is not None:
            fake_response["g"] = self.g
        if self.b is not None:
            fake_response["b"] = self.b

        return PilotParser(fake_response)

    async def get_bulbtype(self) -> BulbType:
        return BulbType.from_data(module_name="MockBulb_RGB", type_id=0, kelvin_list=[2000, 3500, 4500, 6500],
                                  fw_version="0.0.1", fan_speed_range=10, white_channels=2, white_to_color_ratio=5)

    async def getSupportedScenes(self) -> list[str]:
        return list(SCENES.values())

    async def turn_on(self, state: PilotBuilder):
        params = state.pilot_params
        if "state" in params:
            self.state = params["state"]
        if "dimming" in params:
            self.dimming = params["dimming"]
        if "sceneId" in params:
            self.scene_id = params["sceneId"]
        for key in ("r", "g", "b", "temp", "c", "w"):
            if key in params:
                setattr(self, key, params[key])

        logger.debug("%s: Turn on with %s" % (self.mac, params))

    async def turn_off(self):
        self.state = False
        logger.debug("%s: Turn off" % self.mac)
