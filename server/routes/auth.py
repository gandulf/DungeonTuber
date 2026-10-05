from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel

from server.auth import COOKIE_NAME, SESSION_SECONDS, create_session_token, is_authenticated, password_set, require_auth, set_password, \
    verify_password
from server.config import get_config
from core.settings import AppSettings, SettingKeys

router = APIRouter()


class LoginRequest(BaseModel):
    password: str


class PasswordRequest(BaseModel):
    password: str | None = None


@router.get("/api/auth/me")
def me(request: Request):
    host = request.client.host if request.client else None
    return {"authenticated": is_authenticated(host, request.cookies.get(COOKIE_NAME)), "local": get_config().local_mode,
            "password_set": password_set()}


@router.post("/api/auth/login")
def login(body: LoginRequest, request: Request, response: Response):
    if not verify_password(body.password, AppSettings.value(SettingKeys.SERVER_PASSWORD_HASH, type=str)):
        raise HTTPException(status_code=401, detail="Wrong password")
    response.set_cookie(COOKIE_NAME, create_session_token(), max_age=SESSION_SECONDS, httponly=True, samesite="strict",
                        secure=request.url.scheme == "https")
    return {"authenticated": True}


@router.post("/api/auth/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE_NAME)
    return {"authenticated": False}


@router.put("/api/auth/password", dependencies=[Depends(require_auth)])
def change_password(body: PasswordRequest, request: Request, response: Response):
    set_password(body.password or None)
    if body.password:
        # the secret was rotated: issue a fresh session for the current user
        response.set_cookie(COOKIE_NAME, create_session_token(), max_age=SESSION_SECONDS, httponly=True, samesite="strict",
                            secure=request.url.scheme == "https")
    return {"password_set": password_set()}
