import asyncio
import atexit

import json
import logging
import random
from dataclasses import dataclass, field
from functools import partial
from typing import List, Optional

from PySide6.QtCore import QThread, Signal, QObject
from PySide6.QtGui import QColor
from pywizlight import wizlight, PilotBuilder, PilotParser, BulbType
from pywizlight.discovery import DEFAULT_WAIT_TIME, BroadcastProtocol, PORT
from pywizlight.models import DiscoveredBulb, BulbRegistry
from pywizlight.scenes import get_id_from_scene_name, SCENES
from pywizlight.utils import create_udp_broadcast_socket

from config.settings import SettingKeys, AppSettings
from config.utils import asdict_filtered, get_broadcast_ip

logger = logging.getLogger(__file__)

_LIGHTS = set()

def set_lights(lights: list):
    if lights is None:
        AppSettings.remove(SettingKeys.LIGHTS_CONFIG)
        _LIGHTS.clear()
    else:
        AppSettings.setValue(SettingKeys.LIGHTS_CONFIG, Light.json_dump_list(lights))
        _LIGHTS.update(lights)


def get_lights():
    return _LIGHTS


def save_on_exit():
    logger.debug("Saving lights as %s" % Light.json_dump_list(get_lights()))
    AppSettings.setValue(SettingKeys.LIGHTS_CONFIG, Light.json_dump_list(get_lights()))


@dataclass
class LightSetting:

    scene: str | None = None
    brightness: int = 255  # 0..255
    temperature: int | None = None  # 1000 - 10000
    color: QColor | None = None  # 255,255,255

    def __init__(self, brightness: int = 255, temperature: int = None, color: QColor | None = None, scene: str | None = None):
        self.scene = scene
        self.brightness = brightness
        self.temperature = temperature
        if isinstance(color, str):
            self.color = QColor(color)
        else:
            self.color = color

    def is_empty(self) -> bool:
        return self.scene is None and self.color is None and (self.brightness is None or self.brightness == 255) and (self.temperature is None or self.temperature == 1000)

    @property
    def scene_id(self):
        try:
            return get_id_from_scene_name(self.scene) if self.scene is not None else None
        except ValueError as e:
            logger.warning(f"Invalid scene name '{self.scene}': {e}")
            return None

    @classmethod
    def json_dump_list(cls, lights: list):
        return json.dumps([asdict_filtered(mc) for mc in lights])

    def json_dump(self):
        logger.debug(asdict_filtered(self))
        return json.dumps(asdict_filtered(self))

    @classmethod
    def json_load(cls, json_string: str):
        data = json.loads(json_string)

        if "color" in data and isinstance(data["color"],str):
            data["color"] = QColor(data["color"])

        return LightSetting(**data)


@dataclass
class Light(LightSetting):
    name: str | None = "Light"
    mac: str | None = None
    scenable: bool = True
    state: bool = False

    control: wizlight | None = field(default=None, metadata={'export': False})
    loop: asyncio.AbstractEventLoop = field(default=None, metadata={'export': False})  # Custom flag

    temperature_min: int = field(default=1000, metadata={'export': False})
    temperature_max: int = field(default=10000, metadata={'export': False})

    scenes: list[str] = field(default=None, metadata={'export': False})

    def __init__(self, name: str = None, scenable: bool = True, mac: str | None = None, state: bool = False, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = name
        self.mac = mac
        self.scenable = scenable
        self.state = state

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
            self.color = QColor(red, green, blue)
        else:
            self.color = None

        bulb_type = await self.control.get_bulbtype()

        if bulb_type is not None and bulb_type.kelvin_range is not None:
            self.temperature_min = bulb_type.kelvin_range.min
            self.temperature_max = bulb_type.kelvin_range.max

        self.scenes = await self.control.getSupportedScenes()
        self.scene = state.get_scene()



    def set_color(self, value):
        self.color = value
        self.turn_on(PilotBuilder(rgb=(value.red(), value.green(), value.blue()) if value is not None else (255, 255, 255)))

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

    def set_scene(self, brightness: int | None = None, temperature: int | None = None, color: QColor | None = None):
        if brightness:
            self.brightness = brightness

        if temperature:
            self.temperature = temperature

        if color:
            self.color = color

        self.turn_on(self._pilot())

    def _pilot(self):
        return PilotBuilder(scene=self.scene_id, brightness=self.brightness, colortemp=self.temperature, rgb=self._rgb())

    def _rgb(self):
        return (self.color.red(), self.color.green(), self.color.blue()) if self.color is not None else None

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
        self.loop = asyncio.get_event_loop()

        if self.loop.is_running():
            return asyncio.run_coroutine_threadsafe(func(), self.loop).result(5)
        else:
            return self.loop.run_until_complete(func())  # If the loop isn't running, we run it until this task finishes

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        # Equality must match the hash logic
        if not isinstance(other, Light):
            return False
        return self.mac == other.mac

    @classmethod
    def json_dump_list(cls, lights: list):
        return json.dumps([asdict_filtered(mc) for mc in lights])

    def json_dump(self):
        return json.dumps(asdict_filtered(self))

    @classmethod
    def json_load(cls, json_string: str):
        data = json.loads(json_string)

        if "color" in data:
            data["color"] = QColor(data["color"])

        return Light(**data)


class LightManager(QObject):
    lights_found = Signal(list)
    lookup_finished = Signal()

    def __init__(self):
        super().__init__()

        atexit.register(save_on_exit)

        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

        try:
            custom_lights = AppSettings.value(SettingKeys.LIGHTS_CONFIG)
            if custom_lights:
                list_of_custom_lights = json.loads(custom_lights)
                set_lights([Light(**d) for d in list_of_custom_lights])
        except Exception as e:
            AppSettings.remove(SettingKeys.PRESETS)
            logger.error("Failed to load custom presets: {0}", e)

    def lookup(self):
        if AppSettings.value(SettingKeys.LIGHTS_WIDGET, True, type=bool):
            self.thread = DiscoveryThread(self.loop)

            # 2. Connect worker signals to UI slots
            self.thread.bulbs_found.connect(self.on_lights_found)

            # Cleanup: Ensure the thread is deleted when done
            self.thread.finished.connect(self.thread.deleteLater)

            # 3. Go!
            self.thread.start()

    def on_lights_found(self, lights: list[Light]):
        set_lights(lights)
        self.lights_found.emit(lights)


class DiscoveryThread(QThread):
    FAKE_BULBS = False
    """
    A dedicated thread to run the asyncio event loop.
    """
    bulbs_found = Signal(list)

    def __init__(self, loop):
        super().__init__()
        self.loop = loop

    def run(self):

        if self.FAKE_BULBS:
            bulbs = []
            for n in range(3):
                control = MockControl()
                control.mac = f"AA:BB:CC:DD:EE:F{n}"
                bulbs.append(control)

            lights = self.loop.run_until_complete(self.update_states(bulbs))
            self.bulbs_found.emit(lights)
        else:
            broadcast_address = AppSettings.value(SettingKeys.LIGHTS_BROADCAST_IP, get_broadcast_ip(), type=str)
            timeout = AppSettings.value(SettingKeys.LIGHTS_TIMEOUT, 5, type=float)
            # 2. Run your async tasks until complete (or forever)
            logger.info("Start lookup with broadcast address: %s for %s seconds", broadcast_address, timeout)
            # Use wait_for to ensure the thread doesn't hang forever
            bulbs = self.loop.run_until_complete(discover_lights(broadcast_space=broadcast_address, wait_time=timeout))
            # Run the discovery coroutine

            lights = self.loop.run_until_complete(self.update_states(bulbs))
            self.bulbs_found.emit(lights)

    async def update_states(self, bulbs: list[wizlight]) -> list[Light]:
        lights = []
        for bulb in bulbs:
            light: Light | None = None
            for _light in get_lights():
                if _light.mac == bulb.mac:
                    light = _light
                    break

            if light is None:
                light = Light()
                light.name = "Change me"
                light.control = bulb
                await light.refresh_state()
                get_lights().add(light)
            else:
                light.control = bulb
                await light.update_state()
                await light.refresh_state()

            lights.append(light)

        return lights


## wizlight BUGFIX BEGIN
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
    discovered_IPs = await find_wizlights(
        wait_time=wait_time, broadcast_address=broadcast_space
    )
    return [
        wizlight(ip=entry.ip_address, mac=entry.mac_address) for entry in discovered_IPs
    ]


## wizlight BUGFIX END


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

    def __init__(self, ):
        self.mac = self.generate_mac()

    def generate_mac(self):
        # Generate 6 random bytes
        mac = [random.randint(0x00, 0xff) for _ in range(6)]

        # Format as hex strings: 00:11:22:33:44:55
        return ":".join(f"{b:02x}" for b in mac)

    async def updateState(self) -> Optional[PilotParser]:
        fakeResponse = {
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
            fakeResponse["r"] = self.r
        if self.g is not None:
            fakeResponse["g"] = self.g
        if self.b is not None:
            fakeResponse["b"] = self.b

        return PilotParser(fakeResponse)

    async def get_bulbtype(self) -> BulbType:
        return BulbType.from_data(module_name="MockBulb_RGB", type_id=0, kelvin_list=[2000, 3500, 4500, 6500],
                                  fw_version="0.0.1", fan_speed_range=10, white_channels=2, white_to_color_ratio=5)

    async def getSupportedScenes(self) -> list[str]:
        return SCENES.values()

    async def turn_on(self, state: PilotBuilder):
        if "state" in state.pilot_params:
            self.state = state.pilot_params["state"]

        if "dimming" in state.pilot_params:
            self.dimming = state.pilot_params["dimming"]

        if "sceneId" in state.pilot_params:
            self.scene_id = state.pilot_params["sceneId"]

        if "r" in state.pilot_params:
            self.r = state.pilot_params["r"]
        if "g" in state.pilot_params:
            self.g = state.pilot_params["g"]

        if "b" in state.pilot_params:
            self.b = state.pilot_params["b"]

        if "temp" in state.pilot_params:
            self.temp = state.pilot_params["temp"]

        if "c" in state.pilot_params:
            self.c = state.pilot_params["c"]

        if "w" in state.pilot_params:
            self.w = state.pilot_params["w"]



        print("turn on with %s" % state.pilot_params)

    async def turn_off(self):
        self.state = False
        print("turn off")
