"""Agent status and token management (the agents themselves connect through the /ws/agent WebSocket)."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from server.agents import agent_hub, agent_token_set, bearer_token, new_agent_token, valid_agent_token
from server.auth import require_admin, require_auth
from server.voxagent import ticket_path

router = APIRouter()


@router.get("/api/agents", dependencies=[Depends(require_auth)])
def agents():
    return {"tokenSet": agent_token_set(), "connected": agent_hub.status()}


@router.post("/api/agents/token", dependencies=[Depends(require_admin)])
def create_token():
    """Generates a new agent token; it is shown once, only its hash is stored."""
    return {"token": new_agent_token()}


@router.get("/api/agents/files/{ticket}")
def agent_file(ticket: str, request: Request):
    """Download of a file the server asked an agent to process; the ticket is valid for the duration of that request only."""
    if not valid_agent_token(bearer_token(request)):
        raise HTTPException(401, "Invalid agent token")
    path = ticket_path(ticket)
    if path is None or not path.is_file():
        raise HTTPException(404, "Unknown ticket")
    return FileResponse(path, media_type="audio/mpeg")
