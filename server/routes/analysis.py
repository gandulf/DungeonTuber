from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from core.i18n import _
from server.auth import require_auth
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


@router.get("/api/analysis")
def status():
    backend = current_backend()
    return {"backend": backend.name if backend else None, **analysis_queue.status()}
