"""Library storage backends (local directory, S3 compatible object stores)."""
from core.storage.base import AlreadyExists, InvalidPath, NotFound, Storage, StorageEntry, StorageError, join, normalize, parent_of
from core.storage.local import LocalStorage


def create_storage(config: dict) -> Storage:
    """Builds a storage from a root description, e.g. ``{"type": "local", "path": "~/Music"}`` or
    ``{"type": "s3", "bucket": "music", "prefix": "rpg", "endpoint_url": "...", "access_key": "...", "secret_key": "..."}``."""
    kind = config.get("type", "local")
    name = config.get("name", "")
    if kind == "local":
        return LocalStorage(config["path"], name=name)
    if kind == "s3":
        from core.storage.s3 import S3Storage
        return S3Storage(config["bucket"], prefix=config.get("prefix", ""), endpoint_url=config.get("endpoint_url"), region=config.get("region"),
                         access_key=config.get("access_key"), secret_key=config.get("secret_key"), name=name,
                         public_endpoint_url=config.get("public_endpoint_url"))
    raise ValueError(f"Unknown storage type: {kind}")


__all__ = ["AlreadyExists", "InvalidPath", "LocalStorage", "NotFound", "Storage", "StorageEntry", "StorageError", "create_storage", "join",
           "normalize", "parent_of"]
