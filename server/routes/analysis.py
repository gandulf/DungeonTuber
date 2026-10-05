from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.analyzer import get_backend
from server.auth import require_auth
from server.jobs import analysis_queue
from server.paths import safe_path

router = APIRouter(dependencies=[Depends(require_auth)])


class AnalysisRequest(BaseModel):
    paths: list[str]


@router.post("/api/analysis")
def analyze(body: AnalysisRequest):
    paths = [safe_path(path) for path in body.paths]
    count = analysis_queue.submit(paths)
    return {"queued": count, **analysis_queue.status()}


@router.get("/api/analysis")
def status():
    return {"backend": get_backend().name, **analysis_queue.status()}
