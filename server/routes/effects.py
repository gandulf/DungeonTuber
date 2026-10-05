import os
from pathlib import Path

from fastapi import APIRouter, Depends

from core.mp3 import EffectEntry
from core.settings import AppSettings, SettingKeys
from server.auth import require_auth
from server.index import get_index
from server.paths import path_to_id

router = APIRouter(dependencies=[Depends(require_auth)])


def effect_dict(path: Path, effect: EffectEntry) -> dict:
    intensities = [get_index().get(entry.path) for entry in effect.intensities]
    intensities = [data for data in intensities if data is not None]
    first = intensities[0] if intensities else None
    if first and first.get("has_cover"):
        cover_url = f"/media/covers/{first['id']}"
    elif effect.cover_path is not None:
        cover_url = f"/media/files/{path_to_id(effect.cover_path)}"
    else:
        cover_url = None
    return {
        "id": path_to_id(path),
        "path": path.as_posix(),
        "name": effect.name,
        "title": effect.title,
        "cover_url": cover_url,
        "intensities": intensities,
    }


@router.get("/api/effects")
def effects():
    directory = AppSettings.value(SettingKeys.EFFECTS_DIRECTORY, type=str)
    if not directory or not os.path.isdir(directory):
        return {"directory": directory or None, "effects": []}

    result = []
    for name in sorted(os.listdir(directory), key=str.lower):
        if name.startswith("."):
            continue
        path = Path(directory) / name
        if path.is_file() and path.suffix.lower() != ".mp3":
            continue
        effect = EffectEntry.from_file(path)
        if effect is not None and effect.intensities:
            result.append(effect_dict(path, effect))
    return {"directory": Path(directory).as_posix(), "effects": result}
