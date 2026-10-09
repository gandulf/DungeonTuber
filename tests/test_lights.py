import asyncio
import json

from core.lights import Light, LightRegistry, LightSetting
from core.settings import AppSettings, SettingKeys
from core.utils import kelvin_to_rgb, to_hex_color


class _FakeQColor:
    def name(self):
        return "#ABCDEF"


def test_color_normalization():
    assert to_hex_color("FF0000") == "#ff0000"
    assert to_hex_color("#80ff0000") == "#ff0000"
    assert to_hex_color((1, 2, 300)) == "#0102ff"
    assert to_hex_color(_FakeQColor()) == "#abcdef"
    assert to_hex_color(None) is None
    assert kelvin_to_rgb(6600).startswith("#")


def test_light_setting_json_roundtrip():
    setting = LightSetting(brightness=100, temperature=3000, color=_FakeQColor(), scene="Ocean")

    loaded = LightSetting.json_load(setting.json_dump())

    assert loaded.color == "#abcdef"
    assert loaded.rgb == (0xab, 0xcd, 0xef)
    assert loaded.brightness == 100
    assert loaded.temperature == 3000
    assert loaded.scene == "Ocean"
    assert loaded.scene_id is not None


def test_light_setting_is_empty():
    assert LightSetting().is_empty()
    assert not LightSetting(color="#000001").is_empty()


def test_light_identity_uses_mac():
    a = Light(name="Lamp", mac="aa")
    b = Light(name="Renamed", mac="aa")

    assert a == b
    assert hash(a) == hash(b)
    assert len({a, b}) == 1


def test_light_without_control_does_nothing():
    light = Light(name="Offline", mac="bb", state=True)
    light.set_color("#123456")

    assert light.color == "#123456"


def test_registry_load_and_save():
    AppSettings.setValue(SettingKeys.LIGHTS_CONFIG, json.dumps([{"name": "Desk", "mac": "cc", "color": "#ff0000"}]))
    registry = LightRegistry()
    registry.load()

    light = registry.find("cc")
    assert light.name == "Desk"
    assert light.color == "#ff0000"

    light.name = "Table"
    registry.save()
    saved = json.loads(AppSettings.value(SettingKeys.LIGHTS_CONFIG))
    assert saved[0]["name"] == "Table"
    assert "control" not in saved[0]


def test_registry_invalid_config_only_removes_lights():
    AppSettings.setValue(SettingKeys.LOCALE, "de")
    AppSettings.setValue(SettingKeys.LIGHTS_CONFIG, "{broken")

    LightRegistry().load()

    assert not AppSettings.contains(SettingKeys.LIGHTS_CONFIG)
    assert AppSettings.contains(SettingKeys.LOCALE)


def test_fake_discovery():
    registry = LightRegistry()
    registry.fake_bulbs = True

    lights = asyncio.run(registry.discover())

    assert len(lights) == 3
    assert all(light.mac.startswith("AA:BB:CC:DD:EE:F") for light in lights)
    assert lights[0].color == "#fa0000"
    assert lights[0].temperature_min == 2000
    assert len(registry.lights) == 3
