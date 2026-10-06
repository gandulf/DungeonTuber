"""JSON file backed key/value store (settings.json)."""
import json
import logging
import os
import threading
from pathlib import Path
from typing import Any

logger = logging.getLogger(__file__)

_TRUE_STRINGS = {"true", "1", "yes", "on"}


def _coerce(value: Any, value_type: type | None) -> Any:
    if value_type is None:
        return value
    if value_type is bool:
        if isinstance(value, str):
            return value.strip().lower() in _TRUE_STRINGS
        return bool(value)
    if value_type is int:
        if isinstance(value, bool):
            return int(value)
        return int(float(value))
    if value_type is float:
        return float(value)
    if value_type is str:
        return value if isinstance(value, str) else str(value)
    if value_type is list:
        if isinstance(value, list):
            return value
        if isinstance(value, (tuple, set)):
            return list(value)
        return [value]
    if value_type is dict:
        return value if isinstance(value, dict) else dict(value)
    return value


class JsonSettings:
    """Thread-safe settings store persisted as a single JSON document."""

    def __init__(self, path: str | os.PathLike | None = None):
        self._lock = threading.RLock()
        self._data: dict[str, Any] = {}
        self._path: Path | None = None
        if path is not None:
            self.set_path(path)

    # --- storage -------------------------------------------------------
    @property
    def path(self) -> Path | None:
        return self._path

    def set_path(self, path: str | os.PathLike):
        """Points the store at a file and (re)loads it."""
        with self._lock:
            self._path = Path(path)
            self._data = self._read()

    def exists(self) -> bool:
        return self._path is not None and self._path.is_file()

    def _read(self) -> dict[str, Any]:
        if self._path is None or not self._path.is_file():
            return {}
        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError) as e:
            logger.error("Unable to read settings {0}: {1}", self._path, e)
            return {}

    def sync(self):
        if self._path is None:
            return
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(self._path.suffix + ".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self._path)

    # --- key/value API -------------------------------------------------
    def value(self, key: str, defaultValue: Any = None, type: type | None = None) -> Any:  # noqa: A002 - typed lookup
        with self._lock:
            raw = self._data.get(str(key))
        if raw is None:
            return defaultValue
        try:
            return _coerce(raw, type)
        except (TypeError, ValueError):
            logger.warning("Setting {0} has an invalid value of type {1}", key, raw.__class__.__name__)  # never log the value: it may be a secret
            return defaultValue

    def setValue(self, key: str, value: Any):
        with self._lock:
            self._data[str(key)] = value
            self.sync()

    def remove(self, key: str):
        with self._lock:
            if self._data.pop(str(key), None) is not None:
                self.sync()

    def contains(self, key: str) -> bool:
        with self._lock:
            return str(key) in self._data

    def allKeys(self) -> list[str]:
        with self._lock:
            return list(self._data.keys())

    def clear(self):
        with self._lock:
            self._data.clear()
            self.sync()
