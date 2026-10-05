"""Library browsing, tracks, media streaming, covers, playlists and file operations."""
import io
import logging
import os
import shutil
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from core.lights import LightSetting
from core.mp3 import (append_m3u, create_m3u, get_m3u_paths, list_mp3s, parse_mp3, remove_m3u, update_mp3_album, update_mp3_artist,
                      update_mp3_bpm, update_mp3_categories, update_mp3_chapters, update_mp3_cover_data, update_mp3_favorite, update_mp3_genre,
                      update_mp3_light, update_mp3_summary, update_mp3_tags, update_mp3_title)
from server.auth import require_auth
from server.config import get_library_roots
from server.events import hub
from server.index import entry_from_dict, get_index
from server.paths import path_to_id, safe_id, safe_name, safe_path

logger = logging.getLogger(__file__)

router = APIRouter(dependencies=[Depends(require_auth)])

MAX_UPLOAD_BYTES = 200 * 1024 * 1024
COVER_SIZES = (64, 128, 256, 512)


# --- browsing --------------------------------------------------------------

def _dir_has_music(path: str, depth: int = 0) -> bool:
    try:
        mtime = os.stat(path).st_mtime
    except OSError:
        return False
    return _dir_has_music_cached(path, mtime, depth)


@lru_cache(maxsize=4096)
def _dir_has_music_cached(path: str, mtime: float, depth: int) -> bool:
    if depth > 12:
        return False
    try:
        with os.scandir(path) as it:
            subdirs = []
            for entry in it:
                if entry.name.startswith("."):
                    continue
                if entry.is_file() and entry.name.lower().endswith((".mp3", ".m3u")):
                    return True
                if entry.is_dir():
                    subdirs.append(entry.path)
    except OSError:
        return False
    return any(_dir_has_music(sub, depth + 1) for sub in subdirs)


def _item(path: Path, kind: str) -> dict:
    return {"name": path.name if kind == "dir" else path.stem, "file": path.name, "path": path.as_posix(), "id": path_to_id(path), "type": kind}


@router.get("/api/roots")
def roots():
    return [{"name": root.name or root.as_posix(), "path": root.as_posix(), "id": path_to_id(root), "type": "dir"} for root in get_library_roots()]


@router.get("/api/browse")
def browse(path: str, smart: bool = False):
    directory = safe_path(path, kind="dir")
    dirs, files = [], []
    try:
        with os.scandir(directory) as it:
            for entry in it:
                if entry.name.startswith(".") or entry.name.startswith("$"):
                    continue
                try:
                    if entry.is_dir():
                        if not smart or _dir_has_music(entry.path):
                            dirs.append(_item(Path(entry.path), "dir"))
                    elif entry.is_file():
                        lower = entry.name.lower()
                        if lower.endswith(".mp3"):
                            files.append(_item(Path(entry.path), "mp3"))
                        elif lower.endswith(".m3u"):
                            files.append(_item(Path(entry.path), "m3u"))
                except OSError:
                    continue
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")

    dirs.sort(key=lambda item: item["name"].lower())
    files.sort(key=lambda item: item["name"].lower())
    parent = directory.parent
    return {"path": directory.as_posix(), "name": directory.name, "id": path_to_id(directory),
            "parent": parent.as_posix() if parent != directory and safe_parent(parent) else None,
            "items": dirs + files}


def safe_parent(parent: Path) -> bool:
    try:
        safe_path(parent, kind="dir")
        return True
    except HTTPException:
        return False


# --- tracks ----------------------------------------------------------------

@router.get("/api/tracks")
def tracks(dir: str | None = None, playlist: str | None = None, recursive: bool = True):
    if playlist:
        playlist_path = safe_path(playlist, kind="file")
        paths = get_m3u_paths(playlist_path)
        if paths is None:
            raise HTTPException(status_code=400, detail="Not an extended M3U playlist")
        paths = [p for p in paths if p.is_file() and safe_parent(p.parent)]
        return {"type": "playlist", "path": playlist_path.as_posix(), "name": playlist_path.stem, "tracks": get_index().get_many(paths)}
    if dir:
        directory = safe_path(dir, kind="dir")
        paths = [directory / name for name in list_mp3s(directory, recursive=recursive)]
        data = get_index().get_many(paths)
        for item in data:
            item["index"] = None
        return {"type": "dir", "path": directory.as_posix(), "name": directory.name, "tracks": data}
    raise HTTPException(status_code=400, detail="dir or playlist required")


@router.get("/api/tracks/{track_id}")
def track(track_id: str):
    data = get_index().get(safe_id(track_id))
    if data is None:
        raise HTTPException(status_code=422, detail="Unreadable mp3 file")
    return data


class LightModel(BaseModel):
    scene: str | None = None
    brightness: int | None = 255
    temperature: int | None = None
    color: str | None = None

    def to_setting(self) -> LightSetting:
        return LightSetting(brightness=self.brightness if self.brightness is not None else 255, temperature=self.temperature,
                            color=self.color, scene=self.scene)


class TrackPatch(BaseModel):
    title: str | None = None
    artist: str | None = None
    album: str | None = None
    summary: str | None = None
    genres: list[str] | None = None
    tags: list[str] | None = None
    bpm: int | None = None
    favorite: bool | None = None
    categories: dict[str, float | int | None] | None = None
    light: LightModel | None = None
    name: str | None = None


def _clean_list(values: list[str]) -> list[str]:
    return [value.strip() for value in values if value and value.strip()]


@router.patch("/api/tracks/{track_id}")
def patch_track(track_id: str, patch: TrackPatch):
    path = safe_id(track_id)
    fields = patch.model_fields_set

    if "title" in fields:
        update_mp3_title(path, patch.title or None)
    if "artist" in fields:
        update_mp3_artist(path, patch.artist or None)
    if "album" in fields:
        update_mp3_album(path, patch.album or None)
    if "summary" in fields:
        update_mp3_summary(path, patch.summary or "")
    if "genres" in fields:
        update_mp3_genre(path, _clean_list(patch.genres or []))
    if "tags" in fields:
        update_mp3_tags(path, _clean_list(patch.tags or []))
    if "bpm" in fields:
        update_mp3_bpm(path, patch.bpm if patch.bpm else None)
    if "favorite" in fields:
        update_mp3_favorite(path, bool(patch.favorite))
    if "categories" in fields:
        entry = parse_mp3(path)
        categories = dict(entry.categories if entry else {})
        for key, value in (patch.categories or {}).items():
            if value is None:
                categories.pop(key, None)
            else:
                categories[key] = min(max(0, value), 10)
        update_mp3_categories(path, categories)
    if "light" in fields:
        setting = patch.light.to_setting() if patch.light else None
        update_mp3_light(path, None if setting is None or setting.is_empty() else setting)

    if "name" in fields and patch.name:
        new_name = safe_name(patch.name)
        if not new_name.lower().endswith(".mp3"):
            new_name += ".mp3"
        target = path.with_name(new_name)
        if target != path:
            if target.exists():
                raise HTTPException(status_code=409, detail="A file with this name already exists")
            get_index().invalidate(path)
            path.rename(target)
            path = target

    get_index().invalidate(path)
    data = get_index().get(path)
    data["previous_id"] = track_id
    hub.publish("track.updated", data)
    return data


class ChapterModel(BaseModel):
    title: str
    time: int
    light: LightModel | None = None


@router.put("/api/tracks/{track_id}/chapters")
def put_chapters(track_id: str, chapters: list[ChapterModel]):
    path = safe_id(track_id)
    update_mp3_chapters(path, [{"title": c.title, "time": max(0, c.time), "light": c.light.to_setting() if c.light else None}
                               for c in chapters])
    get_index().invalidate(path)
    data = get_index().get(path)
    hub.publish("track.updated", data)
    return data


@router.put("/api/tracks/{track_id}/cover")
async def put_cover(track_id: str, file: UploadFile = File(...)):
    path = safe_id(track_id)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty image")
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as image:
            mime = Image.MIME.get(image.format, "image/jpeg")
    except Exception:
        raise HTTPException(status_code=400, detail="Unsupported image")
    update_mp3_cover_data(path, data, mime)
    _thumbnail.cache_clear()
    get_index().invalidate(path)
    track_data = get_index().get(path)
    hub.publish("track.updated", track_data)
    return track_data


# --- media -----------------------------------------------------------------

@router.get("/media/tracks/{track_id}")
def media_track(track_id: str):
    path = safe_id(track_id)
    return FileResponse(path, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=3600"})


@lru_cache(maxsize=2048)
def _thumbnail(path: str, mtime: float, size: int) -> tuple[bytes, str] | None:
    from PIL import Image

    entry = parse_mp3(path)
    cover = entry.cover_data() if entry else None
    if cover is None:
        return None
    data, mime = cover
    if size <= 0:
        return data, mime
    try:
        with Image.open(io.BytesIO(data)) as image:
            image = image.convert("RGB")
            image.thumbnail((size, size))
            out = io.BytesIO()
            image.save(out, format="JPEG", quality=85)
            return out.getvalue(), "image/jpeg"
    except Exception:
        return data, mime


@router.get("/media/covers/{track_id}")
def media_cover(track_id: str, size: int = Query(128, ge=0, le=2048)):
    path = safe_id(track_id)
    if size:
        size = min(COVER_SIZES, key=lambda s: abs(s - size)) if size < 1024 else 0
    result = _thumbnail(str(path), path.stat().st_mtime, size)
    if result is None:
        raise HTTPException(status_code=404, detail="No cover")
    return Response(content=result[0], media_type=result[1], headers={"Cache-Control": "private, max-age=86400"})


@router.get("/media/files/{file_id}")
def media_file(file_id: str):
    """Plain image files inside the library (e.g. effect folder covers)."""
    path = safe_id(file_id)
    if path.suffix.lower() not in (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"):
        raise HTTPException(status_code=403, detail="Not an image")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=86400"})


# --- playlists -------------------------------------------------------------

class PlaylistCreate(BaseModel):
    path: str
    ids: list[str] = []


class PlaylistEntries(BaseModel):
    playlist: str
    ids: list[str]
    index: int = -1


def _entries(ids: list[str]):
    entries = []
    for track_id in ids:
        data = get_index().get(safe_id(track_id))
        if data is not None:
            entries.append(entry_from_dict(data))
    return entries


def _playlist_path(path: str, must_exist: bool = True) -> Path:
    playlist = safe_path(path, must_exist=must_exist, kind="file" if must_exist else None)
    if playlist.suffix.lower() != ".m3u":
        raise HTTPException(status_code=400, detail="Playlists must be .m3u files")
    return playlist


@router.post("/api/playlists")
def create_playlist(body: PlaylistCreate):
    playlist = Path(body.path)
    if playlist.suffix.lower() != ".m3u":
        playlist = playlist.with_name(playlist.name + ".m3u")
    playlist = _playlist_path(str(playlist), must_exist=False)
    safe_path(playlist.parent, kind="dir")
    if playlist.exists():
        raise HTTPException(status_code=409, detail="Playlist already exists")
    create_m3u(_entries(body.ids), playlist, allow_empty=True)
    hub.publish("library.changed", {"path": playlist.parent.as_posix()})
    return {"path": playlist.as_posix(), "id": path_to_id(playlist), "name": playlist.stem}


@router.post("/api/playlists/entries")
def add_to_playlist(body: PlaylistEntries):
    playlist = _playlist_path(body.playlist)
    append_m3u(_entries(body.ids), playlist, body.index)
    hub.publish("playlist.changed", {"path": playlist.as_posix()})
    return {"ok": True}


@router.post("/api/playlists/remove")
def remove_from_playlist(body: PlaylistEntries):
    playlist = _playlist_path(body.playlist)
    remove_m3u(_entries(body.ids), playlist)
    hub.publish("playlist.changed", {"path": playlist.as_posix()})
    return {"ok": True}


@router.put("/api/playlists/order")
def reorder_playlist(body: PlaylistEntries):
    playlist = _playlist_path(body.playlist)
    create_m3u(_entries(body.ids), playlist, allow_empty=True)
    hub.publish("playlist.changed", {"path": playlist.as_posix()})
    return {"ok": True}


# --- files -----------------------------------------------------------------

class MoveRequest(BaseModel):
    source: str
    target_dir: str


@router.post("/api/files/move")
def move_file(body: MoveRequest):
    source = safe_path(body.source)
    target_dir = safe_path(body.target_dir, kind="dir")
    target = target_dir / source.name
    if target.exists():
        raise HTTPException(status_code=409, detail="Target already exists")
    if source.is_dir() and target_dir.is_relative_to(source):
        raise HTTPException(status_code=400, detail="Cannot move a folder into itself")
    shutil.move(str(source), str(target))
    get_index().invalidate(source)
    hub.publish("library.changed", {"path": source.parent.as_posix()})
    hub.publish("library.changed", {"path": target_dir.as_posix()})
    return {"path": target.as_posix(), "id": path_to_id(target)}


@router.post("/api/files/folder")
def create_folder(parent: str = Form(...), name: str = Form(...)):
    directory = safe_path(parent, kind="dir") / safe_name(name)
    directory.mkdir(exist_ok=False)
    hub.publish("library.changed", {"path": directory.parent.as_posix()})
    return {"path": directory.as_posix(), "id": path_to_id(directory)}


@router.post("/api/upload")
async def upload(dir: str = Form(...), files: list[UploadFile] = File(...)):
    directory = safe_path(dir, kind="dir")
    saved = []
    for upload_file in files:
        name = safe_name(Path(upload_file.filename or "").name)
        if not name.lower().endswith(".mp3"):
            raise HTTPException(status_code=400, detail=f"Only mp3 files can be uploaded: {name}")
        target = directory / name
        if target.exists():
            raise HTTPException(status_code=409, detail=f"File already exists: {name}")
        size = 0
        with open(target, "wb") as out:
            while chunk := await upload_file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    out.close()
                    target.unlink(missing_ok=True)
                    raise HTTPException(status_code=413, detail=f"File too large: {name}")
                out.write(chunk)
        if parse_mp3(target) is None:
            target.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=f"Not a valid mp3 file: {name}")
        saved.append(get_index().get(target))
    hub.publish("library.changed", {"path": directory.as_posix()})
    return {"tracks": saved}
