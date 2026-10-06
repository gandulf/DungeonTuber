"""Configuration of remote library storages (S3 compatible buckets). Credentials are write-only: they are never sent to the client."""
import importlib.util

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.settings import AppSettings, SettingKeys
from core.storage import create_storage
from server.auth import require_admin
from server.events import hub
from server.roots import reset_remote_cache, slugify

router = APIRouter(dependencies=[Depends(require_admin)])

CREDENTIALS = ("access_key", "secret_key")


class StorageModel(BaseModel):
    id: str | None = None
    name: str = ""
    bucket: str
    prefix: str = ""
    endpoint_url: str = ""
    public_endpoint_url: str = ""
    region: str = ""
    # None keeps the stored value of an existing storage, an empty string clears it
    access_key: str | None = None
    secret_key: str | None = None
    direct: bool = False


def _stored() -> list[dict]:
    """Configured storages; entries written by hand or from the environment without an id get the one the library roots use."""
    return [{**c, "id": c.get("id") or slugify(c.get("name") or c.get("bucket", ""))}
            for c in (AppSettings.value(SettingKeys.STORAGE_ROOTS, type=list) or []) if isinstance(c, dict)]


def _public(config: dict) -> dict:
    return {"id": config.get("id") or slugify(config.get("name") or config.get("bucket", "")), "name": config.get("name", ""),
            "bucket": config.get("bucket", ""), "prefix": config.get("prefix", ""), "endpoint_url": config.get("endpoint_url", ""),
            "public_endpoint_url": config.get("public_endpoint_url", ""), "region": config.get("region", ""), "direct": bool(config.get("direct", False)),
            "has_credentials": bool(config.get("access_key") and config.get("secret_key"))}


def _response() -> dict:
    return {"available": importlib.util.find_spec("boto3") is not None, "storages": [_public(c) for c in _stored()]}


def _clean(model: StorageModel, existing: dict | None, taken: set[str]) -> dict:
    bucket = model.bucket.strip()
    if not bucket:
        raise HTTPException(status_code=400, detail="A bucket name is required")
    config = {"type": "s3", "bucket": bucket, "name": model.name.strip() or bucket, "prefix": model.prefix.strip().strip("/"),
              "endpoint_url": model.endpoint_url.strip(),
              "public_endpoint_url": model.public_endpoint_url.strip(), "region": model.region.strip(), "direct": model.direct}
    for key in CREDENTIALS:
        value = getattr(model, key)
        config[key] = value.strip() if value is not None else (existing or {}).get(key, "")
    if existing:
        config["id"] = existing["id"]
    else:
        base = slugify(model.id or config["name"])
        config["id"], n = base, 2
        while config["id"] in taken:
            config["id"], n = f"{base}-{n}", n + 1
    return {key: value for key, value in config.items() if value not in ("", None, False) or key == "bucket"}


@router.get("/api/storages")
def get_storages():
    return _response()


@router.put("/api/storages")
def put_storages(models: list[StorageModel]):
    stored = {c.get("id"): c for c in _stored()}
    result: list[dict] = []
    taken: set[str] = set()
    for model in models:
        existing = stored.get(model.id) if model.id else None
        if existing and existing["id"] in taken:
            raise HTTPException(status_code=400, detail="Duplicate storage id")
        config = _clean(model, existing, taken)
        taken.add(config["id"])
        result.append(config)
    if result:
        AppSettings.setValue(SettingKeys.STORAGE_ROOTS, result)
    else:
        AppSettings.remove(SettingKeys.STORAGE_ROOTS)
    reset_remote_cache()
    hub.publish("storages.changed", {})
    return _response()


@router.post("/api/storages/test")
def test_storage(model: StorageModel):
    existing = next((c for c in _stored() if model.id and c.get("id") == model.id), None)
    config = _clean(model, existing, set())
    try:
        entries = create_storage(config).list("")
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e) or type(e).__name__)
    return {"ok": True, "entries": len(entries)}
