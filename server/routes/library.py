"""Library browsing, tracks, media streaming, covers, playlists and file operations (local folders and remote storages)."""
import contextlib
import io
import logging
import mimetypes
import os
import tempfile
from functools import lru_cache
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel

from core.lights import LightSetting
from core.mp3 import parse_mp3
from core.storage import AlreadyExists, InvalidPath, NotFound
from server import playlists
from server.auth import current_user, require_auth
from server.users import ADMIN
from server.events import hub
from server.index import get_index
from server.paths import Location, safe_id, safe_name, safe_path
from server.rescan import rescan
from server.roots import get_roots

logger = logging.getLogger(__file__)

router = APIRouter(dependencies=[Depends(require_auth)])

MAX_UPLOAD_BYTES = 200 * 1024 * 1024
COVER_SIZES = (64, 128, 256, 512)
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp")


@contextlib.contextmanager
def storage_errors():
    """Maps storage failures to HTTP errors."""
    try:
        yield
    except NotFound:
        raise HTTPException(status_code=404, detail="Not found")
    except AlreadyExists:
        raise HTTPException(status_code=409, detail="Target already exists")
    except InvalidPath as e:
        raise HTTPException(status_code=400, detail=str(e))


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


def has_music(location: Location) -> bool:
    if location.root.is_local:
        return _dir_has_music(str(location.local_path))
    return any(e.name.lower().endswith((".mp3", ".m3u")) and not e.name.startswith(".") for e in location.storage.walk(location.rel))


def _item(location: Location, kind: str) -> dict:
    return {"name": location.name if kind == "dir" else location.stem, "file": location.name, "path": location.client_path,
            "id": location.id, "type": kind}


def _visible(name: str) -> bool:
    return not name.startswith((".", "$"))


@router.get("/api/roots")
def roots():
    return [{"name": root.name, "path": root.client_path(""), "id": Location(root).id, "type": "dir", "storage": root.storage.type}
            for root in get_roots()]


@router.get("/api/browse")
def browse(path: str, smart: bool = False):
    directory = safe_path(path, kind="dir")
    dirs, files = [], []
    with storage_errors():
        entries = directory.storage.list(directory.rel)
    for entry in entries:
        if not _visible(entry.name):
            continue
        location = Location(directory.root, entry.path)
        if entry.is_dir:
            if not smart or has_music(location):
                dirs.append(_item(location, "dir"))
        else:
            lower = entry.name.lower()
            if lower.endswith(".mp3"):
                files.append(_item(location, "mp3"))
            elif lower.endswith(".m3u"):
                files.append(_item(location, "m3u"))

    dirs.sort(key=lambda item: item["name"].lower())
    files.sort(key=lambda item: item["name"].lower())
    owners = get_index().uploads_under(directory)
    for item in dirs + files:
        if item["path"] in owners:
            item["uploaded_by"] = owners[item["path"]]
    parent = directory.parent
    return {"path": directory.client_path, "name": directory.name, "id": directory.id,
            "parent": parent.client_path if parent else None, "items": dirs + files}


class RescanRequest(BaseModel):
    path: str | None = None


@router.post("/api/library/rescan")
def rescan_library(body: RescanRequest | None = None):
    """Syncs the metadata database with the storage; without a path every library root is rescanned."""
    path = body.path if body else None
    targets = [safe_path(path)] if path else [Location(root) for root in get_roots()]
    total = {"added": 0, "changed": 0, "removed": 0, "total": 0}
    with storage_errors():
        for target in targets:
            for key, value in rescan(target).items():
                total[key] += value
            hub.publish("library.changed", {"path": target.client_path})
    return total


# --- tracks ----------------------------------------------------------------

def _mp3s(directory: Location, recursive: bool) -> list[Location]:
    with storage_errors():
        entries = directory.storage.walk(directory.rel) if recursive else (e for e in directory.storage.list(directory.rel) if not e.is_dir)
        found = [Location(directory.root, e.path) for e in entries if e.name.lower().endswith(".mp3")]
    prefix = len(directory.rel) + 1 if directory.rel else 0
    found = [loc for loc in found if all(_visible(part) or part.startswith("$") for part in loc.rel[prefix:].split("/"))]
    return sorted(found, key=lambda loc: loc.rel)


@router.get("/api/tracks")
def tracks(dir: str | None = None, playlist: str | None = None, recursive: bool = True):
    if playlist:
        playlist_loc = safe_path(playlist, kind="file")
        with storage_errors():
            locations = playlists.read(playlist_loc)
        if locations is None:
            raise HTTPException(status_code=400, detail="Not an extended M3U playlist")
        locations = [loc for loc in locations if not loc.root.is_local or loc.storage.exists(loc.rel)]
        return {"type": "playlist", "path": playlist_loc.client_path, "name": playlist_loc.stem, "tracks": get_index().get_many(locations)}
    if dir:
        directory = safe_path(dir, kind="dir")
        data = get_index().get_many(_mp3s(directory, recursive))
        for item in data:
            item["index"] = None
        return {"type": "dir", "path": directory.client_path, "name": directory.name, "tracks": data}
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
    location = safe_id(track_id)
    fields = patch.model_fields_set
    index = get_index()

    changes: dict = {}
    if "title" in fields:
        changes["title"] = patch.title or None
    if "artist" in fields:
        changes["artist"] = patch.artist or None
    if "album" in fields:
        changes["album"] = patch.album or None
    if "summary" in fields:
        changes["summary"] = patch.summary or ""
    if "genres" in fields:
        changes["genres"] = _clean_list(patch.genres or [])
    if "tags" in fields:
        changes["tags"] = _clean_list(patch.tags or [])
    if "bpm" in fields:
        changes["bpm"] = patch.bpm if patch.bpm else None
    if "favorite" in fields:
        changes["favorite"] = bool(patch.favorite)
    if "categories" in fields:
        current = index.get(location)
        categories = dict(current["categories"] if current else {})
        for key, value in (patch.categories or {}).items():
            if value is None:
                categories.pop(key, None)
            else:
                categories[key] = min(max(0, value), 10)
        changes["categories"] = categories
    if "light" in fields:
        setting = patch.light.to_setting() if patch.light else None
        changes["light"] = None if setting is None or setting.is_empty() else setting

    with storage_errors():
        if changes:
            index.update(location, changes)

        if "name" in fields and patch.name:
            new_name = safe_name(patch.name)
            if not new_name.lower().endswith(".mp3"):
                new_name += ".mp3"
            target = location.sibling(new_name)
            if target != location:
                if location.storage.exists(target.rel):
                    raise HTTPException(status_code=409, detail="A file with this name already exists")
                location.storage.move(location.rel, target.rel)
                index.relocate(location, target)
                location = target

    data = index.get(location)
    if data is None:
        raise HTTPException(status_code=422, detail="Unreadable mp3 file")
    data["previous_id"] = track_id
    hub.publish("track.updated", data)
    return data


class ChapterModel(BaseModel):
    title: str
    time: int
    light: LightModel | None = None


@router.put("/api/tracks/{track_id}/chapters")
def put_chapters(track_id: str, chapters: list[ChapterModel]):
    location = safe_id(track_id)
    data = get_index().set_chapters(location, [{"title": c.title, "time": max(0, c.time), "light": c.light.to_setting() if c.light else None}
                                               for c in chapters])
    if data is None:
        raise HTTPException(status_code=422, detail="Unreadable mp3 file")
    hub.publish("track.updated", data)
    return data


@router.put("/api/tracks/{track_id}/cover")
async def put_cover(track_id: str, file: UploadFile = File(...)):
    location = safe_id(track_id)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty image")
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as image:
            mime = Image.MIME.get(image.format, "image/jpeg")
    except Exception:
        raise HTTPException(status_code=400, detail="Unsupported image")
    track_data = get_index().set_cover(location, data, mime)
    _thumbnail.cache_clear()
    if track_data is None:
        raise HTTPException(status_code=422, detail="Unreadable mp3 file")
    hub.publish("track.updated", track_data)
    return track_data


# --- media -----------------------------------------------------------------

def _parse_range(header: str, size: int) -> tuple[int, int] | None:
    """The first range of ``bytes=a-b`` / ``bytes=a-`` / ``bytes=-n`` clamped to the file, None if unsatisfiable."""
    try:
        unit, _, spec = header.partition("=")
        first, _, last = spec.split(",")[0].strip().partition("-")
        if unit.strip().lower() != "bytes":
            return None
        if first == "":
            start, end = max(0, size - int(last)), size - 1
        else:
            start, end = int(first), int(last) if last else size - 1
        end = min(end, size - 1)
        return (start, end) if 0 <= start <= end else None
    except ValueError:
        return None


@router.get("/media/tracks/{track_id}")
def media_track(track_id: str, request: Request):
    location = safe_id(track_id)
    if location.root.is_local:
        return FileResponse(location.local_path, media_type="audio/mpeg", headers={"Cache-Control": "private, max-age=3600"})
    if location.root.direct:
        return RedirectResponse(location.storage.url(location.rel, 3600), status_code=307, headers={"Cache-Control": "private, max-age=600"})

    # remote storage without direct access: proxy with range support so seeking works
    with storage_errors():
        size = location.storage.stat(location.rel).size
        headers = {"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600"}
        requested = request.headers.get("range")
        if requested:
            span = _parse_range(requested, size)
            if span is None:
                return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
            start, end = span
            headers.update({"Content-Range": f"bytes {start}-{end}/{size}", "Content-Length": str(end - start + 1)})
            return StreamingResponse(location.storage.read(location.rel, start, end), status_code=206, media_type="audio/mpeg", headers=headers)
        headers["Content-Length"] = str(size)
        return StreamingResponse(location.storage.read(location.rel), media_type="audio/mpeg", headers=headers)


@lru_cache(maxsize=2048)
def _thumbnail(location: Location, mtime: float, size: int) -> tuple[bytes, str] | None:
    from PIL import Image

    cover = get_index().cover(location)
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
    location = safe_id(track_id)
    if size:
        size = min(COVER_SIZES, key=lambda s: abs(s - size)) if size < 1024 else 0
    mtime = location.storage.stat(location.rel).mtime if location.root.is_local else 0.0
    result = _thumbnail(location, mtime, size)
    if result is None:
        raise HTTPException(status_code=404, detail="No cover")
    return Response(content=result[0], media_type=result[1], headers={"Cache-Control": "private, max-age=86400"})


@router.get("/media/files/{file_id}")
def media_file(file_id: str):
    """Plain image files inside the library (e.g. effect folder covers)."""
    location = safe_id(file_id)
    if location.suffix not in IMAGE_SUFFIXES:
        raise HTTPException(status_code=403, detail="Not an image")
    headers = {"Cache-Control": "private, max-age=86400"}
    if location.root.is_local:
        return FileResponse(location.local_path, headers=headers)
    with storage_errors():
        return Response(content=location.storage.read_bytes(location.rel), media_type=mimetypes.guess_type(location.name)[0], headers=headers)


# --- playlists -------------------------------------------------------------

class PlaylistCreate(BaseModel):
    path: str
    ids: list[str] = []


class PlaylistEntries(BaseModel):
    playlist: str
    ids: list[str]
    index: int = -1


def _locations(ids: list[str]) -> list[Location]:
    return [safe_id(track_id) for track_id in ids]


def _playlist_location(path: str, must_exist: bool = True) -> Location:
    playlist = safe_path(path, must_exist=must_exist, kind="file" if must_exist else None)
    if playlist.suffix != ".m3u":
        raise HTTPException(status_code=400, detail="Playlists must be .m3u files")
    return playlist


@router.post("/api/playlists")
def create_playlist(body: PlaylistCreate):
    path = body.path if body.path.lower().endswith(".m3u") else body.path + ".m3u"
    playlist = _playlist_location(path, must_exist=False)
    parent = playlist.parent
    if parent is None:
        raise HTTPException(status_code=400, detail="Invalid playlist path")
    safe_path(parent.client_path, kind="dir")
    if playlist.storage.exists(playlist.rel):
        raise HTTPException(status_code=409, detail="Playlist already exists")
    with storage_errors():
        playlists.write(playlist, _locations(body.ids))
    hub.publish("library.changed", {"path": parent.client_path})
    return {"path": playlist.client_path, "id": playlist.id, "name": playlist.stem}


@router.post("/api/playlists/entries")
def add_to_playlist(body: PlaylistEntries):
    playlist = _playlist_location(body.playlist)
    with storage_errors():
        added = playlists.append(playlist, _locations(body.ids), body.index)
    if added:
        hub.publish("playlist.changed", {"path": playlist.client_path})
    return {"ok": True, "added": added}


@router.post("/api/playlists/remove")
def remove_from_playlist(body: PlaylistEntries):
    playlist = _playlist_location(body.playlist)
    with storage_errors():
        playlists.remove(playlist, _locations(body.ids))
    hub.publish("playlist.changed", {"path": playlist.client_path})
    return {"ok": True}


@router.put("/api/playlists/order")
def reorder_playlist(body: PlaylistEntries):
    playlist = _playlist_location(body.playlist)
    with storage_errors():
        playlists.write(playlist, _locations(body.ids))
    hub.publish("playlist.changed", {"path": playlist.client_path})
    return {"ok": True}


# --- files -----------------------------------------------------------------

class MoveRequest(BaseModel):
    source: str
    target_dir: str


@router.post("/api/files/move")
def move_file(body: MoveRequest):
    source = safe_path(body.source)
    target_dir = safe_path(body.target_dir, kind="dir")
    if source.root != target_dir.root:
        raise HTTPException(status_code=400, detail="Files cannot be moved between different libraries")
    target = target_dir.child(source.name)
    if source.is_root:
        raise HTTPException(status_code=400, detail="Cannot move a library root")
    if target_dir.is_relative_to(source):
        raise HTTPException(status_code=400, detail="Cannot move a folder into itself")
    with storage_errors():
        source.storage.move(source.rel, target.rel)
    get_index().relocate(source, target)
    hub.publish("library.changed", {"path": source.parent.client_path})
    hub.publish("library.changed", {"path": target_dir.client_path})
    return {"path": target.client_path, "id": target.id}


@router.post("/api/files/folder")
def create_folder(parent: str = Form(...), name: str = Form(...), user: str = Depends(current_user)):
    directory = safe_path(parent, kind="dir").child(safe_name(name))
    with storage_errors():
        directory.storage.mkdir(directory.rel)
    get_index().set_uploader(directory, user)
    hub.publish("library.changed", {"path": directory.parent.client_path})
    return {"path": directory.client_path, "id": directory.id}


def _ensure_dirs(base: Location, folder: Location, user: str):
    """Creates `folder` and every missing directory between it and `base`; the new directories belong to `user`."""
    missing = []
    while folder != base and not folder.storage.exists(folder.rel):
        missing.append(folder)
        folder = folder.parent
    for directory in reversed(missing):
        with storage_errors(), contextlib.suppress(AlreadyExists):
            directory.storage.mkdir(directory.rel)
        get_index().set_uploader(directory, user)


@router.post("/api/upload")
async def upload(dir: str = Form(...), files: list[UploadFile] = File(...), paths: list[str] = Form(default=[]),
                 user: str = Depends(current_user)):
    """Stores mp3 files in `dir`. `paths` optionally holds one relative path per file (e.g. `Album/Disc 1/song.mp3`)
    whose folders are created below `dir`, so whole directory trees keep their structure."""
    directory = safe_path(dir, kind="dir")
    if paths and len(paths) != len(files):
        raise HTTPException(status_code=400, detail="paths and files do not match")
    saved = []
    for index, upload_file in enumerate(files):
        parts = [part for part in (paths[index] if paths else "").replace("\\", "/").split("/") if part]
        name = safe_name(parts.pop() if parts else Path(upload_file.filename or "").name)
        if not name.lower().endswith(".mp3"):
            raise HTTPException(status_code=400, detail=f"Only mp3 files can be uploaded: {name}")
        folder = directory
        for part in parts:
            folder = folder.child(safe_name(part))
        target = folder.child(name)
        if target.storage.exists(target.rel):
            raise HTTPException(status_code=409, detail=f"File already exists: {name}")
        with tempfile.TemporaryDirectory(prefix="dt-upload-") as tmp:
            temp_file = Path(tmp) / "upload.mp3"
            size = 0
            with open(temp_file, "wb") as out:
                while chunk := await upload_file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise HTTPException(status_code=413, detail=f"File too large: {name}")
                    out.write(chunk)
            entry = parse_mp3(temp_file)
            if entry is None:
                raise HTTPException(status_code=400, detail=f"Not a valid mp3 file: {name}")
            cover = entry.cover_data()
            _ensure_dirs(directory, folder, user)
            with open(temp_file, "rb") as source, storage_errors():
                target.storage.write(target.rel, source)
        if target.root.is_local:
            get_index().get(target)
        else:
            get_index().import_entry(target, entry, cover)
        get_index().set_uploader(target, user)
        saved.append(get_index().known(target))
    hub.publish("library.changed", {"path": directory.client_path})
    return {"tracks": saved}


def _owned_by(location: Location, user: str, owners: dict[str, str]) -> bool:
    """True if the folder and every folder and song in it was uploaded or created by `user` (other files do not matter)."""
    pending = [location]
    while pending:
        folder = pending.pop()
        for entry in folder.storage.list(folder.rel):
            child = Location(folder.root, entry.path)
            if entry.is_dir:
                if owners.get(child.client_path) != user:
                    return False
                pending.append(child)
            elif entry.name.lower().endswith(".mp3") and owners.get(child.client_path) != user:
                return False
    return True


def may_delete(location: Location, user: str) -> bool:
    """The SuperAdmin may delete everything, other users only what they uploaded or created themselves."""
    if user == ADMIN:
        return True
    owners = get_index().uploads_under(location)
    if owners.get(location.client_path) != user:
        return False
    with storage_errors():
        return not location.storage.stat(location.rel).is_dir or _owned_by(location, user, owners)


@router.delete("/api/files")
def delete_file(path: str = Query(...), user: str = Depends(current_user)):
    location = safe_path(path)
    if location.is_root:
        raise HTTPException(status_code=400, detail="Cannot delete a library root")
    if not may_delete(location, user):
        raise HTTPException(status_code=403, detail="You can only delete what you uploaded yourself")
    with storage_errors():
        location.storage.delete(location.rel)
    get_index().forget(location)
    hub.publish("library.changed", {"path": location.parent.client_path})
    return {"deleted": True}
