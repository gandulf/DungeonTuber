"""Sound effects: every entry of the effects folder is a single mp3 or a folder of up to 5 intensities (any library root, local or remote)."""
from fastapi import APIRouter, Depends

from core.settings import AppSettings, SettingKeys
from core.storage import StorageError
from server.auth import require_auth
from server.index import get_index
from server.paths import Location, locate

router = APIRouter(dependencies=[Depends(require_auth)])

MAX_INTENSITIES = 5
COVER_NAME = "cover.jpg"


def _mp3s(directory: Location, entries) -> list[Location]:
    return sorted((Location(directory.root, e.path) for e in entries if not e.is_dir and e.name.lower().endswith(".mp3")), key=lambda loc: loc.name)


def effect_dict(location: Location, name: str, files: list[Location], cover: Location | None) -> dict | None:
    intensities = get_index().get_many(files)
    if not intensities:
        return None
    first = intensities[0]
    if first.get("has_cover"):
        cover_url = f"/media/covers/{first['id']}"
    elif cover is not None:
        cover_url = f"/media/files/{cover.id}"
    else:
        cover_url = None
    return {
        "id": location.id,
        "path": location.client_path,
        "name": name,
        "title": name if len(intensities) > 1 else first.get("title"),
        "cover_url": cover_url,
        "intensities": intensities,
    }


@router.get("/api/effects")
def effects():
    setting = AppSettings.value(SettingKeys.EFFECTS_DIRECTORY, type=str)
    directory = locate(setting) if setting else None
    if directory is None:
        return {"directory": setting or None, "effects": []}
    try:
        children = directory.storage.list(directory.rel)
    except StorageError:
        return {"directory": setting, "effects": []}

    result = []
    for child in sorted(children, key=lambda e: e.name.lower()):
        if child.name.startswith("."):
            continue
        location = Location(directory.root, child.path)
        if child.is_dir:
            try:
                inner = location.storage.list(location.rel)
            except StorageError:
                continue
            files = _mp3s(location, inner)
            if not files or len(files) > MAX_INTENSITIES:
                continue
            cover = location.child(COVER_NAME) if any(e.name == COVER_NAME for e in inner) else None
            effect = effect_dict(location, location.name, files, cover)
        elif child.name.lower().endswith(".mp3"):
            effect = effect_dict(location, location.stem, [location], None)
        else:
            continue
        if effect is not None:
            result.append(effect)
    return {"directory": directory.client_path, "effects": result}
