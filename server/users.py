"""Accounts besides the SuperAdmin. The SuperAdmin is the server password itself (user name "admin"); everyone else is stored here."""
import re
import time

from fastapi import HTTPException

from core.settings import AppSettings, SettingKeys

ADMIN = "admin"
NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{1,31}$")
MIN_PASSWORD = 4


def all_users() -> list[dict]:
    """Stored accounts: dicts with name, hash and created."""
    return [u for u in (AppSettings.value(SettingKeys.USERS, type=list) or []) if isinstance(u, dict) and u.get("name")]


def _save(users: list[dict]):
    if users:
        AppSettings.setValue(SettingKeys.USERS, users)
    else:
        AppSettings.remove(SettingKeys.USERS)


def find_user(name: str | None) -> dict | None:
    wanted = (name or "").strip().lower()
    return next((u for u in all_users() if u["name"].lower() == wanted), None) if wanted else None


def is_admin_name(name: str | None) -> bool:
    return (name or "").strip().lower() == ADMIN


def add_user(name: str, password_hash: str) -> dict:
    name = (name or "").strip()
    if not NAME_PATTERN.match(name):
        raise HTTPException(status_code=400, detail="Invalid user name")
    if is_admin_name(name) or find_user(name):
        raise HTTPException(status_code=409, detail="User already exists")
    user = {"name": name, "hash": password_hash, "created": int(time.time())}
    _save([*all_users(), user])
    return user


def remove_user(name: str):
    user = find_user(name)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    _save([u for u in all_users() if u["name"] != user["name"]])


def set_user_hash(name: str, password_hash: str):
    user = find_user(name)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    _save([{**u, "hash": password_hash} if u["name"] == user["name"] else u for u in all_users()])


def public(user: dict) -> dict:
    return {"name": user["name"], "created": user.get("created")}
