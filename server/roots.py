"""Library roots: local folders and remote storages (S3 compatible), and the client facing paths that address them.

A client path is the absolute posix path for local roots (as it always was) and ``s3://<root id>/<relative path>`` for remote roots.
"""
import hashlib
import json
import logging
import re
import threading
from pathlib import Path

from core.settings import AppSettings, SettingKeys
from core.storage import LocalStorage, Storage, create_storage

logger = logging.getLogger(__file__)

REMOTE_PREFIX = "s3://"
_SECRET_KEYS = ("secret_key", "access_key")


class Root:
    def __init__(self, id: str, storage: Storage, direct: bool = False):
        self.id = id
        self.storage = storage
        # remote roots: let the browser stream from presigned URLs instead of proxying through the server
        self.direct = direct

    @property
    def name(self) -> str:
        return self.storage.name

    @property
    def is_local(self) -> bool:
        return isinstance(self.storage, LocalStorage)

    def client_path(self, rel: str) -> str:
        if self.is_local:
            base = self.storage.root.as_posix()
            return f"{base.rstrip('/')}/{rel}" if rel else base
        return f"{REMOTE_PREFIX}{self.id}/{rel}" if rel else f"{REMOTE_PREFIX}{self.id}"

    def __eq__(self, other):
        return isinstance(other, Root) and other.id == self.id

    def __hash__(self):
        return hash(self.id)


_lock = threading.Lock()
_remote_cache: dict[str, Root] = {}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "storage"


def default_library_roots() -> list[str]:
    import os
    music = os.path.expanduser("~/Music")
    return [music if os.path.isdir(music) else os.path.expanduser("~")]


def _local_root(path: Path) -> Root:
    storage = LocalStorage(path)
    return Root("local-" + hashlib.sha1(storage.root.as_posix().lower().encode()).hexdigest()[:10], storage)


def _remote_root(config: dict) -> Root | None:
    """Remote roots are cached so the (expensive) client is reused between requests."""
    key = json.dumps(config, sort_keys=True)
    with _lock:
        root = _remote_cache.get(key)
        if root is None:
            try:
                storage = create_storage({**config, "type": config.get("type", "s3")})
            except Exception as e:
                logger.error("Unable to open storage {0}: {1}", config.get("name") or config.get("bucket"), e)
                return None
            root = Root(_slug(str(config.get("id") or storage.name)), storage, direct=bool(config.get("direct", False)))
            _remote_cache[key] = root
    return root


def _contains(parent: Path, child: Path) -> bool:
    try:
        return child.resolve().is_relative_to(parent.resolve())
    except OSError:
        return False


def get_roots() -> list[Root]:
    """Everything the server may expose; paths outside of these are rejected."""
    roots: list[Root] = []
    configured = AppSettings.value(SettingKeys.LIBRARY_ROOTS, type=list) or []
    remote = [c for c in (AppSettings.value(SettingKeys.STORAGE_ROOTS, type=list) or []) if isinstance(c, dict)]
    if not configured and not remote:
        configured = default_library_roots()

    paths = [Path(p).expanduser() for p in configured]
    from server.config import get_config
    paths.extend(get_config().extra_roots)
    effects_dir = AppSettings.value(SettingKeys.EFFECTS_DIRECTORY, type=str)
    if effects_dir and not effects_dir.startswith(REMOTE_PREFIX):  # remote effects folders live inside a configured storage root
        effects_path = Path(effects_dir).expanduser()
        if not any(_contains(path, effects_path) for path in paths):  # no extra root if it is part of a library already
            paths.append(effects_path)

    seen = set()
    for path in paths:
        if not path.is_dir():
            continue
        root = _local_root(path)
        if root.id not in seen:
            seen.add(root.id)
            roots.append(root)
    for config in remote:
        root = _remote_root(config)
        if root is not None and root.id not in seen:
            seen.add(root.id)
            roots.append(root)
    return roots


def get_local_roots() -> list[Root]:
    return [root for root in get_roots() if root.is_local]


def public_config(config: dict) -> dict:
    """A storage description without credentials."""
    return {key: value for key, value in config.items() if key not in _SECRET_KEYS}


def reset_remote_cache():
    """Drops the cached storage clients, e.g. after the storage configuration changed."""
    with _lock:
        _remote_cache.clear()


def slugify(text: str) -> str:
    return _slug(text)
