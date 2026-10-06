import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from pywizlight.scenes import SCENES

from core.lights import LightSetting, light_registry
from core.settings import AppSettings, SettingKeys
from server.agents import agent_hub
from server.auth import require_auth
from server.events import hub

logger = logging.getLogger(__file__)

router = APIRouter(dependencies=[Depends(require_auth)])

_TIMEOUT_ERRORS = (TimeoutError, OSError)


def _lights() -> list[dict]:
    return sorted((light.to_dict() for light in light_registry.lights), key=lambda d: (d["name"] or "", d["mac"] or ""))


def _broadcast():
    hub.publish("lights.state", _lights())


@router.get("/api/lights")
def lights():
    return {"enabled": AppSettings.value(SettingKeys.LIGHTS_ENABLED, True, type=bool), "lights": _lights(),
            "scenes": list(SCENES.values()), "agent": agent_hub.get("lights") is not None}


@router.post("/api/lights/discover")
async def discover():
    if not AppSettings.value(SettingKeys.LIGHTS_ENABLED, True, type=bool):
        raise HTTPException(status_code=409, detail="Lights are disabled")
    try:
        await light_registry.discover()
    except _TIMEOUT_ERRORS as e:
        raise HTTPException(status_code=502, detail=f"Discovery failed: {e}")
    light_registry.save()
    _broadcast()
    return lights()


class LightPatch(BaseModel):
    name: str | None = None
    state: bool | None = None
    scenable: bool | None = None
    brightness: int | None = None
    temperature: int | None = None
    color: str | None = None
    scene: str | None = None
    clear_color: bool = False


@router.patch("/api/lights/{mac}")
async def patch_light(mac: str, patch: LightPatch):
    light = light_registry.find(mac)
    if light is None:
        raise HTTPException(status_code=404, detail="Unknown light")
    try:
        if patch.name is not None:
            light.name = patch.name.strip() or light.name
        if patch.scenable is not None:
            light.scenable = patch.scenable
        if patch.state is not None:
            await light.set_state_async(patch.state)
        if any(v is not None for v in (patch.brightness, patch.temperature, patch.color, patch.scene)) or patch.clear_color:
            await light.update_async(brightness=patch.brightness, temperature=patch.temperature, color=patch.color, scene=patch.scene,
                                     clear_color=patch.clear_color)
    except _TIMEOUT_ERRORS as e:
        raise HTTPException(status_code=502, detail=f"Light did not respond: {e}")
    light_registry.save()
    _broadcast()
    return light.to_dict()


class CueRequest(BaseModel):
    scene: str | None = None
    brightness: int | None = 255
    temperature: int | None = None
    color: str | None = None


@router.post("/api/lights/cue")
async def cue(body: CueRequest):
    """Applies a song/chapter/effect light setting to all lights that are 'controlled by songs'."""
    setting = LightSetting(brightness=body.brightness if body.brightness is not None else 255, temperature=body.temperature,
                           color=body.color, scene=body.scene)
    applied = 0
    for light in list(light_registry.lights):
        if light.scenable:
            try:
                await light.apply_settings_async(setting)
                applied += 1
            except _TIMEOUT_ERRORS as e:
                logger.warning("Light {0} did not respond: {1}", light.name, e)
    _broadcast()
    return {"applied": applied}
