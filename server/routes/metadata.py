"""Metadata lookup: candidates for title, artist, album and track number of a song from AcoustID and MusicBrainz
(core/musiclookup.py), and the AcoustID key. The user picks a candidate in the song editor and saves it as usual."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core import musiclookup
from core.settings import AppSettings, SettingKeys
from server.auth import require_admin, require_auth
from server.config import setting_or_env
from server.index import get_index
from server.paths import safe_id

router = APIRouter(dependencies=[Depends(require_auth)])


ACOUSTID_KEY_ENV = "DT_ACOUSTID_API_KEY"


def _acoustid_key() -> str:
    return setting_or_env(SettingKeys.ACOUSTID_API_KEY, ACOUSTID_KEY_ENV)[0]


def _status() -> dict:
    key, source = setting_or_env(SettingKeys.ACOUSTID_API_KEY, ACOUSTID_KEY_ENV)
    return {"configured": bool(key), "keyHint": key[-4:] if len(key) > 8 else "", "keySource": source,
            "fpcalc": musiclookup.fpcalc_available()}


@router.get("/api/tracks/{track_id}/lookup")
def lookup(track_id: str):
    location = safe_id(track_id)
    track = get_index().get(location)
    if track is None:
        raise HTTPException(status_code=404, detail="Not found")
    path = str(location.local_path) if location.root.is_local else None  # the fingerprint needs the file itself
    return musiclookup.lookup(path, track.get("title"), track.get("artist"), location.name, track.get("length"), _acoustid_key())


class MetadataConfig(BaseModel):
    key: str = Field(max_length=200)


@router.get("/api/metadata/config", dependencies=[Depends(require_admin)])
def get_config():
    return _status()


@router.put("/api/metadata/config", dependencies=[Depends(require_admin)])
def put_config(config: MetadataConfig):
    if config.key.strip():
        AppSettings.setValue(SettingKeys.ACOUSTID_API_KEY, config.key.strip())
    else:
        AppSettings.remove(SettingKeys.ACOUSTID_API_KEY)
    return _status()


@router.delete("/api/metadata/config", dependencies=[Depends(require_admin)])
def delete_config():
    AppSettings.remove(SettingKeys.ACOUSTID_API_KEY)
    return _status()
