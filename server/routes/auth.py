from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from core.settings import AppSettings, SettingKeys
from server.index import get_index

from server.auth import COOKIE_NAME, SESSION_SECONDS, authenticate, create_session_token, current_user, hash_password, password_set, \
    require_admin, set_password, user_of
from server.config import get_config
from server.users import ADMIN, MIN_PASSWORD, add_user, all_users, find_user, public, remove_user, set_user_hash

router = APIRouter()


class LoginRequest(BaseModel):
    username: str | None = None
    password: str


class PasswordRequest(BaseModel):
    password: str | None = None


class OpenTab(BaseModel):
    type: Literal["dir", "playlist"]
    path: str


class TabsState(BaseModel):
    open: list[OpenTab] = []
    active: str | None = None


ACCENTS = ("violet", "blue", "teal", "green", "amber", "orange", "red", "pink")  # the colours of web/src/lib/accent.ts


class UserStateRequest(BaseModel):
    favorites: list[str] | None = None
    tabs: TabsState | None = None
    accent: str | None = None  # one of ACCENTS, "" for the default


class NewUserRequest(BaseModel):
    name: str
    password: str


def _client(request: Request) -> str | None:
    return request.client.host if request.client else None


def _set_session(request: Request, response: Response, user: str):
    response.set_cookie(COOKIE_NAME, create_session_token(user), max_age=SESSION_SECONDS, httponly=True, samesite="strict",
                        secure=request.url.scheme == "https")


def _checked(password: str | None) -> str:
    if not password or len(password) < MIN_PASSWORD:
        raise HTTPException(status_code=400, detail=f"The password needs at least {MIN_PASSWORD} characters")
    return password


@router.get("/api/auth/me")
def me(request: Request):
    user = user_of(_client(request), request.cookies.get(COOKIE_NAME))
    return {"authenticated": user is not None, "local": get_config().local_mode, "password_set": password_set(),
            "user": user, "is_admin": user == ADMIN}


@router.post("/api/auth/login")
def login(body: LoginRequest, request: Request, response: Response):
    user = authenticate(body.username, body.password)
    if user is None:
        raise HTTPException(status_code=401, detail="Wrong user name or password")
    _set_session(request, response, user)
    return {"authenticated": True, "user": user, "is_admin": user == ADMIN}


@router.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"authenticated": False}


@router.put("/api/auth/password", dependencies=[Depends(require_admin)])
def change_password(body: PasswordRequest, request: Request, response: Response):
    if not body.password and all_users():
        raise HTTPException(status_code=400, detail="Remove all users before removing the SuperAdmin password")
    set_password(body.password or None)
    if body.password:
        # the secret was rotated: issue a fresh session for the current user
        _set_session(request, response, ADMIN)
    return {"password_set": password_set()}


@router.put("/api/auth/me/password")
def change_own_password(body: PasswordRequest, request: Request, response: Response, user: str = Depends(current_user)):
    if user == ADMIN:
        raise HTTPException(status_code=400, detail="Use the SuperAdmin password setting")
    set_user_hash(user, hash_password(_checked(body.password)))
    return {"changed": True}


# --- user management (SuperAdmin only) ----------------------------------------

@router.get("/api/users", dependencies=[Depends(require_admin)])
def list_users():
    return [{"name": ADMIN, "admin": True, "created": None}] + [{**public(u), "admin": False} for u in all_users()]


@router.post("/api/users", dependencies=[Depends(require_admin)])
def create_user(body: NewUserRequest):
    if not password_set():
        raise HTTPException(status_code=400, detail="Set the SuperAdmin password first")
    return {**public(add_user(body.name, hash_password(_checked(body.password)))), "admin": False}


@router.put("/api/users/{name}/password", dependencies=[Depends(require_admin)])
def reset_user_password(name: str, body: PasswordRequest):
    set_user_hash(name, hash_password(_checked(body.password)))
    return {"changed": True}


@router.delete("/api/users/{name}", dependencies=[Depends(require_admin)])
def delete_user(name: str):
    user = find_user(name)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    remove_user(name)
    get_index().forget_user(user["name"])
    return {"deleted": True}


# --- what every user keeps for themselves ---------------------------------------

@router.get("/api/user/state")
def get_user_state(user: str = Depends(current_user)):
    """Favorite folders, open tabs (folders and playlists) and accent color of the signed in user."""
    index = get_index()
    favorites = index.user_state(user, "favorites")
    if favorites is None and user == ADMIN:  # the favorites from before they were per user
        favorites = AppSettings.value(SettingKeys.FAVORITES, [], type=list)
    return {"favorites": favorites or [], "tabs": index.user_state(user, "tabs"), "accent": index.user_state(user, "accent") or ""}


@router.put("/api/user/state")
def put_user_state(body: UserStateRequest, user: str = Depends(current_user)):
    index = get_index()
    if body.favorites is not None:
        index.set_user_state(user, "favorites", list(dict.fromkeys(body.favorites)))
    if body.tabs is not None:
        index.set_user_state(user, "tabs", body.tabs.model_dump())
    if body.accent is not None:
        if body.accent and body.accent not in ACCENTS:
            raise HTTPException(status_code=400, detail="Unknown accent color")
        index.set_user_state(user, "accent", body.accent)
    return get_user_state(user)
