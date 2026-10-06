"""Password login with an HMAC signed session cookie: the SuperAdmin (the server password) and additional users."""
import base64
import hashlib
import hmac
import json
import secrets
import time

from fastapi import HTTPException, Request, WebSocket

from core.settings import AppSettings, SettingKeys
from server.config import get_config, get_secret
from server.context import current_user_var
from server.users import ADMIN, find_user, is_admin_name

COOKIE_NAME = "dt_session"
SESSION_SECONDS = 30 * 24 * 3600
_LOOPBACK = {"127.0.0.1", "::1", "localhost", "testclient"}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2 ** 14, r=8, p=1)
    return "scrypt$" + base64.b64encode(salt).decode() + "$" + base64.b64encode(digest).decode()


def verify_password(password: str, stored: str | None) -> bool:
    if not stored or not stored.startswith("scrypt$"):
        return False
    _, salt_b64, digest_b64 = stored.split("$", 2)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=base64.b64decode(salt_b64), n=2 ** 14, r=8, p=1)
    return hmac.compare_digest(digest, base64.b64decode(digest_b64))


def set_password(password: str | None):
    if password:
        AppSettings.setValue(SettingKeys.SERVER_PASSWORD_HASH, hash_password(password))
    else:
        AppSettings.remove(SettingKeys.SERVER_PASSWORD_HASH)
    # invalidate existing sessions
    AppSettings.remove(SettingKeys.SERVER_SECRET)


def password_set() -> bool:
    return bool(AppSettings.value(SettingKeys.SERVER_PASSWORD_HASH, type=str))


def _sign(payload: bytes) -> str:
    return hmac.new(get_secret(), payload, hashlib.sha256).hexdigest()


def create_session_token(user: str = ADMIN) -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"exp": int(time.time()) + SESSION_SECONDS, "u": user}).encode()).decode()
    return payload + "." + _sign(payload.encode())


def session_user(token: str | None) -> str | None:
    """The user a valid session token belongs to (tokens without a user are SuperAdmin sessions); None if invalid or the user is gone."""
    if not token or "." not in token:
        return None
    payload, signature = token.rsplit(".", 1)
    if not hmac.compare_digest(signature, _sign(payload.encode())):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(payload.encode()))
    except ValueError:
        return None
    if data.get("exp", 0) <= time.time():
        return None
    name = data.get("u") or ADMIN
    if is_admin_name(name):
        return ADMIN
    user = find_user(name)
    return user["name"] if user else None


def valid_session_token(token: str | None) -> bool:
    return session_user(token) is not None


def authenticate(username: str | None, password: str) -> str | None:
    """The user name for valid credentials. An empty user name means the SuperAdmin."""
    if not (username or "").strip() or is_admin_name(username):
        return ADMIN if verify_password(password, AppSettings.value(SettingKeys.SERVER_PASSWORD_HASH, type=str)) else None
    user = find_user(username)
    return user["name"] if user and verify_password(password, user["hash"]) else None


def is_loopback(host: str | None) -> bool:
    return host in _LOOPBACK


def user_of(client_host: str | None, cookie: str | None) -> str | None:
    """The signed in user, or None when not authenticated."""
    # Desktop app: its own window (this computer) never needs to log in, even when shared on the network.
    if get_config().local_mode and is_loopback(client_host):
        return ADMIN
    user = session_user(cookie)
    if user:
        return user
    # Without a password only the machine itself may use the server.
    return ADMIN if not password_set() and is_loopback(client_host) else None


def is_authenticated(client_host: str | None, cookie: str | None) -> bool:
    return user_of(client_host, cookie) is not None


async def current_user(request: Request) -> str:
    """Dependency: the signed in user (401 otherwise). Async on purpose: the context variable must reach the endpoint's thread."""
    user = user_of(request.client.host if request.client else None, request.cookies.get(COOKIE_NAME))
    if user is None:
        raise HTTPException(status_code=401, detail="Not authenticated")
    current_user_var.set(user)
    return user


async def require_auth(request: Request):
    await current_user(request)


async def require_admin(request: Request) -> str:
    user = await current_user(request)
    if user != ADMIN:
        raise HTTPException(status_code=403, detail="Only the SuperAdmin may do this")
    return user


def websocket_authenticated(websocket: WebSocket) -> bool:
    host = websocket.client.host if websocket.client else None
    return is_authenticated(host, websocket.cookies.get(COOKIE_NAME))
