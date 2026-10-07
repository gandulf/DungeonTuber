"""Import of YouTube links (single videos and playlists) into the library."""
from dataclasses import asdict

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.i18n import _
from core.ytimport import ImportFailed, check_url, resolve
from server.auth import current_user, require_auth
from server.downloads import Batch, download_queue, make_folder, max_minutes
from server.paths import safe_path
from server.routes.library import storage_errors
from server.voxagent import current_backend

router = APIRouter(dependencies=[Depends(require_auth)])


class ResolveRequest(BaseModel):
    url: str
    whole: bool | None = None  # video link of a playlist: True the playlist, False only the video


class ImportEntry(BaseModel):
    url: str
    title: str = ""


class ImportRequest(BaseModel):
    dir: str
    entries: list[ImportEntry]
    album: str | None = None
    playlist: str | None = None  # create a playlist with this name
    folder: str | None = None  # download into a new subfolder with this name
    analyze: bool = False  # analyze the songs with the analysis agent once they are stored
    split: bool = False  # videos with chapters become one song per chapter


@router.post("/api/import/resolve")
def resolve_link(body: ResolveRequest):
    """The videos behind a link (a playlist link lists all of them), without downloading anything."""
    try:
        result = resolve(body.url, whole=body.whole)
    except ImportFailed as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"title": result.title, "playlist": result.is_playlist, "hasVideo": result.has_video, "maxMinutes": max_minutes(),
            "entries": [asdict(entry) for entry in result.entries]}


@router.post("/api/import")
def start_import(body: ImportRequest, user: str = Depends(current_user)):
    directory = safe_path(body.dir, kind="dir")
    try:
        entries = [(check_url(entry.url), entry.title) for entry in body.entries]
    except ImportFailed as e:
        raise HTTPException(status_code=400, detail=str(e))
    if not entries:
        raise HTTPException(status_code=400, detail="No links")
    if body.analyze and current_backend() is None:
        raise HTTPException(status_code=409, detail=_("No analysis agent connected"))
    if body.folder and body.folder.strip():
        with storage_errors():
            directory = make_folder(directory, body.folder, user)
    queued = download_queue.submit(Batch(directory, entries, user, body.album or None, body.playlist or None, body.analyze, body.split))
    return {"queued": queued, **download_queue.status()}


@router.get("/api/import")
def status():
    return download_queue.status()
