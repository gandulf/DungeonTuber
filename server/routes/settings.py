"""Server-side settings, categories, the presets of the users, version and locales."""
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core import i18n
from core.settings import AppSettings, MusicCategory, Preset, SettingKeys, get_music_categories, set_music_categories, settings
from core.utils import DOWNLOAD_LINK, get_broadcast_ip, get_ip, get_current_version, get_latest_version, \
    is_newer_version_available
from server.auth import current_user, require_admin, require_auth
from server.config import default_library_roots, get_config, get_library_roots
from server.events import hub
from server.index import get_index
from server.voxagent import current_backend

router = APIRouter(dependencies=[Depends(require_auth)])

# key -> (type, default)
SERVER_SETTINGS: dict[str, tuple[type, object]] = {
    SettingKeys.LOCALE: (str, ""),
    SettingKeys.SKIP_ANALYZED_MUSIC: (bool, True),
    SettingKeys.LIGHTS_ENABLED: (bool, True),
    SettingKeys.LIGHTS_BROADCAST_IP: (str, None),
    SettingKeys.LIGHTS_TIMEOUT: (float, 5.0),
    SettingKeys.EFFECTS_DIRECTORY: (str, ""),
    SettingKeys.LIBRARY_ROOTS: (list, None),
    SettingKeys.SHARE_ON_NETWORK: (bool, False),
    SettingKeys.SHARE_PORT: (int, 8765),
}


def _settings_dict() -> dict:
    result = {}
    for key, (value_type, default) in SERVER_SETTINGS.items():
        result[str(key)] = AppSettings.value(key, default, type=value_type)
    result[str(SettingKeys.LIGHTS_BROADCAST_IP)] = result[str(SettingKeys.LIGHTS_BROADCAST_IP)] or get_broadcast_ip()
    result[str(SettingKeys.LIBRARY_ROOTS)] = result[str(SettingKeys.LIBRARY_ROOTS)] or default_library_roots()
    result["networkUrl"] = f"http://{get_ip()}:{result[str(SettingKeys.SHARE_PORT)]}"
    result["voxalyzerActive"] = current_backend() is not None
    return result


def apply_locale():
    """Uses the configured language for server generated texts (category names, messages)."""
    i18n.set_language(AppSettings.value(SettingKeys.LOCALE, type=str) or None)
    settings.reload()


@router.get("/api/settings")
def get_settings():
    return _settings_dict()


@router.put("/api/settings", dependencies=[Depends(require_admin)])
def put_settings(values: dict):
    allowed = {str(key): spec for key, spec in SERVER_SETTINGS.items()}
    if str(SettingKeys.LIBRARY_ROOTS) in values and not get_config().local_mode:
        raise HTTPException(status_code=403, detail="The library folders are set when the server starts")
    for key, value in values.items():
        if key not in allowed:
            raise HTTPException(status_code=400, detail=f"Unknown setting {key}")
        value_type, _default = allowed[key]
        if value is None or value == "":
            AppSettings.remove(key)
            continue
        try:
            if value_type is float:
                value = float(value)
                if value <= 0:
                    raise ValueError
            elif value_type is bool:
                value = bool(value)
            elif value_type is int:
                value = int(value)
                if not 1024 <= value <= 65535:
                    raise ValueError
            elif value_type is list:
                if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
                    raise ValueError
            elif value_type is str:
                value = str(value)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail=f"Invalid value for {key}")
        AppSettings.setValue(key, value)

    if str(SettingKeys.LOCALE) in values:
        apply_locale()
    if str(SettingKeys.LIBRARY_ROOTS) in values:
        hub.publish("library.roots", {})  # the clients reload the folder tree and rescan the new library
    return _settings_dict()


# --- categories --------------------------------------------------------------

class CategoryModel(BaseModel):
    key: str
    name: str
    description: str = ""
    levels: dict[int, str] = {}
    group: str | None = ""


@router.get("/api/categories")
def get_categories():
    return [asdict(category) for category in get_music_categories()]


@router.put("/api/categories", dependencies=[Depends(require_admin)])
def put_categories(categories: list[CategoryModel]):
    keys = [c.key.strip() for c in categories]
    if any(not key for key in keys) or len(set(keys)) != len(keys):
        raise HTTPException(status_code=400, detail="Category keys must be unique and not empty")
    set_music_categories([MusicCategory(c.name.strip() or c.key, c.description, c.levels, group=c.group or "", key=c.key.strip())
                          for c in categories])
    return get_categories()


@router.post("/api/categories/reset", dependencies=[Depends(require_admin)])
def reset_categories():
    set_music_categories(None)
    return get_categories()


# --- presets -----------------------------------------------------------------

class PresetModel(BaseModel):
    name: str
    categories: dict[str, float | int | None] = {}
    tags: list[str] = []
    genres: list[str] = []
    bpm: int | None = None


def _presets(user: str) -> list[dict]:
    return get_index().user_state(user, "presets") or []


@router.get("/api/presets")
def get_presets_route(user: str = Depends(current_user)):
    """The presets of the signed in user."""
    return _presets(user)


@router.put("/api/presets")
def put_presets(presets: list[PresetModel], user: str = Depends(current_user)):
    kept = [asdict(Preset(p.name.strip(), {k: v for k, v in p.categories.items() if v is not None}, p.tags, p.genres, p.bpm))
            for p in presets if p.name.strip()]
    get_index().set_user_state(user, "presets", kept)
    return kept


# --- misc ------------------------------------------------------------------

@router.get("/api/version")
def version_info():
    current = get_current_version()
    return {"current": current, "latest": get_latest_version(), "newer": is_newer_version_available(current), "download": DOWNLOAD_LINK}


@router.get("/api/locales")
def locales():
    return i18n.available_locales()


@router.get("/api/library/roots")
def library_roots():
    return [root.as_posix() for root in get_library_roots()]
