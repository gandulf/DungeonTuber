"""Adventures: blocks of notes with music, effects and lights, linked into a path. Private ones belong to their owner, public ones are
visible to everybody; only the owner (and the SuperAdmin) changes them."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core import adventures as model
from core.storage import StorageError
from server import adventures
from server.auth import current_user, require_auth
from server.events import hub
from server.routes.library import hidden
from server.users import ADMIN

router = APIRouter(dependencies=[Depends(require_auth)])


def _can_view(adventure: dict, user: str) -> bool:
    return adventure["visibility"] == "public" or adventure["owner"] == user or user == ADMIN


def _can_edit(adventure: dict, user: str) -> bool:
    return adventure["owner"] == user or user == ADMIN


def _load(adventure_id: str, user: str, edit: bool = False):
    try:
        found = adventures.find(adventure_id)
    except StorageError as e:
        raise HTTPException(status_code=502, detail=str(e))
    if found is None or not _can_view(found[1], user):
        raise HTTPException(status_code=404, detail="Adventure not found")
    if edit and not _can_edit(found[1], user):
        raise HTTPException(status_code=403, detail="Only the owner can change this adventure")
    return found


def _save(location, adventure: dict):
    try:
        adventures.save(location, adventure)
    except StorageError as e:
        raise HTTPException(status_code=502, detail=str(e))


def _view(adventure: dict, user: str) -> dict:
    adventure = adventures.mark_unavailable(adventure, user, hidden)
    return {**adventure, "editable": _can_edit(adventure, user)}


class AdventureCreate(BaseModel):
    title: str = "New adventure"


class AdventureVisibility(BaseModel):
    visibility: str
    confirm: bool = False


@router.get("/api/adventures")
def list_adventures(user: str = Depends(current_user)):
    items = [model.summary(adventure) | {"editable": _can_edit(adventure, user)}
             for _, adventure in adventures.list_all() if _can_view(adventure, user)]
    return {"adventures": sorted(items, key=lambda item: item["updated"], reverse=True)}


@router.post("/api/adventures")
def create_adventure(body: AdventureCreate, user: str = Depends(current_user)):
    try:
        _, adventure = adventures.create(body.title, user)
    except adventures.NoLibrary:
        raise HTTPException(status_code=400, detail="No library configured")
    except StorageError as e:
        raise HTTPException(status_code=502, detail=str(e))
    hub.publish("adventures.changed", {})
    return _view(adventure, user)


@router.get("/api/adventures/{adventure_id}")
def get_adventure(adventure_id: str, user: str = Depends(current_user)):
    return _view(_load(adventure_id, user)[1], user)


@router.put("/api/adventures/{adventure_id}")
def put_adventure(adventure_id: str, body: dict, user: str = Depends(current_user)):
    """Replaces the title, blocks and links; id, owner and visibility stay as they are."""
    location, stored = _load(adventure_id, user, edit=True)
    adventure = model.normalize({**body, "visibility": stored["visibility"]}, previous=stored)
    _save(location, adventure)
    if adventure["title"] != stored["title"] or len(adventure["blocks"]) != len(stored["blocks"]):
        hub.publish("adventures.changed", {})
    return _view(adventure, user)


@router.post("/api/adventures/{adventure_id}/visibility")
def set_visibility(adventure_id: str, body: AdventureVisibility, user: str = Depends(current_user)):
    """Makes an adventure public or private again. Publishing an adventure that refers to private playlists is only done with `confirm`;
    until then the names of those playlists come back (others would see them as unavailable)."""
    if body.visibility not in model.VISIBILITIES:
        raise HTTPException(status_code=400, detail="Invalid visibility")
    location, stored = _load(adventure_id, user, edit=True)
    private = adventures.private_playlists(stored) if body.visibility == "public" else []
    if private and not body.confirm:
        return {"changed": False, "visibility": stored["visibility"], "private_playlists": private}
    stored["visibility"] = body.visibility
    _save(location, model.normalize(stored, previous=stored))
    hub.publish("adventures.changed", {})
    return {"changed": True, "visibility": body.visibility, "private_playlists": private}


@router.delete("/api/adventures/{adventure_id}")
def delete_adventure(adventure_id: str, user: str = Depends(current_user)):
    location, _ = _load(adventure_id, user, edit=True)
    try:
        adventures.delete(location)
    except StorageError as e:
        raise HTTPException(status_code=502, detail=str(e))
    hub.publish("adventures.changed", {})
    return {"deleted": True}
