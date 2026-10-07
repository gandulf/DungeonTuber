from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.i18n import _
from server import voxagent, voxcloud
from server.auth import require_admin, require_auth
from server.jobs import analysis_queue
from server.paths import safe_path
from server.voxagent import current_backend

router = APIRouter(dependencies=[Depends(require_auth)])


class AnalysisRequest(BaseModel):
    paths: list[str]


@router.post("/api/analysis")
def analyze(body: AnalysisRequest):
    if current_backend() is None:
        raise HTTPException(status_code=409, detail=_("No analysis agent connected"))
    locations = [safe_path(path) for path in body.paths]
    count = analysis_queue.submit(locations)
    return {"queued": count, **analysis_queue.status()}


class CloudRequest(BaseModel):
    url: str
    key: str
    secret: str


@router.get("/api/analysis/cloud", dependencies=[Depends(require_admin)])
def cloud_status():
    """Whether the cloud analysis is configured (the key and the secret are never sent back)."""
    return voxcloud.status()


@router.put("/api/analysis/cloud", dependencies=[Depends(require_admin)])
def put_cloud(body: CloudRequest):
    try:
        voxcloud.save_config(body.url, body.key, body.secret)
    except voxcloud.CloudError as e:
        raise HTTPException(status_code=400, detail=str(e))
    voxagent.publish_availability()
    return voxcloud.status()


@router.delete("/api/analysis/cloud", dependencies=[Depends(require_admin)])
def remove_cloud():
    voxcloud.delete_config()
    voxagent.publish_availability()
    return voxcloud.status()


@router.get("/api/analysis")
def status():
    backend = current_backend()
    return {"backend": backend.name if backend else None, **analysis_queue.status()}
