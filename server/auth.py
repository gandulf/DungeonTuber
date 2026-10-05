"""Single-GM password login with an HMAC signed session cookie."""
import base64
import hashlib
import hmac
import json
import secrets
import time

from fastapi import HTTPException, Request, WebSocket

from core.settings import AppSettings, SettingKeys
from server.config import get_config, get_secret

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


def create_session_token() -> str:
    payload = base64.urlsafe_b64encode(json.dumps({"exp": int(time.time()) + SESSION_SECONDS}).encode()).decode()
    return payload + "." + _sign(payload.encode())


def valid_session_token(token: str | None) -> bool:
    if not token or "." not in token:
        return False
    payload, signature = token.rsplit(".", 1)
    if not hmac.compare_digest(signature, _sign(payload.encode())):
        return False
    try:
        data = json.loads(base64.urlsafe_b64decode(payload.encode()))
    except ValueError:
        return False
    return data.get("exp", 0) > time.time()


def is_loopback(host: str | None) -> bool:
    return host in _LOOPBACK


def is_authenticated(client_host: str | None, cookie: str | None) -> bool:
    if get_config().local_mode:
        return is_loopback(client_host)
    if valid_session_token(cookie):
        return True
    # Without a password only the machine itself may use the server.
    return not password_set() and is_loopback(client_host)


def require_auth(request: Request):
    host = request.client.host if request.client else None
    if not is_authenticated(host, request.cookies.get(COOKIE_NAME)):
        raise HTTPException(status_code=401, detail="Not authenticated")


def websocket_authenticated(websocket: WebSocket) -> bool:
    host = websocket.client.host if websocket.client else None
    return is_authenticated(host, websocket.cookies.get(COOKIE_NAME))
