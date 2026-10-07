"""Agent status and token management (the agents themselves connect through the /ws/agent WebSocket)."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse

from server.agents import agent_hub, agent_token_set, bearer_token, new_agent_token, valid_agent_token
from server.auth import require_admin, require_auth
from server import ytagent
from server.voxagent import ticket_path

router = APIRouter()


@router.get("/api/agents", dependencies=[Depends(require_auth)])
def agents():
    return {"tokenSet": agent_token_set(), "connected": agent_hub.status()}


@router.post("/api/agents/token", dependencies=[Depends(require_admin)])
def create_token():
    """Generates a new agent token; it is shown once, only its hash is stored."""
    return {"token": new_agent_token()}


@router.delete("/api/agents/{kind}", dependencies=[Depends(require_admin)])
async def remove_agent(kind: str):
    """Disconnects an agent; it is told not to reconnect (a new token locks out agents for good)."""
    if not await agent_hub.remove(kind):
        raise HTTPException(404, "No such agent connected")
    return {"connected": agent_hub.status()}


@router.get("/api/agents/files/{ticket}")
def agent_file(ticket: str, request: Request):
    """Download of a file the server asked an agent to process; the ticket is valid for the duration of that request only."""
    if not valid_agent_token(bearer_token(request)):
        raise HTTPException(401, "Invalid agent token")
    path = ticket_path(ticket)
    if path is None or not path.is_file():
        raise HTTPException(404, "Unknown ticket")
    return FileResponse(path, media_type="audio/mpeg")


@router.put("/api/agents/uploads/{ticket}/{index}")
async def agent_upload(ticket: str, index: int, request: Request):
    """The mp3 of a YouTube download the agent did for the server (raw request body); the ticket is valid for the duration of that request."""
    if not valid_agent_token(bearer_token(request)):
        raise HTTPException(401, "Invalid agent token")
    directory = ytagent.upload_dir(ticket)
    if directory is None or not 0 <= index < 1000:
        raise HTTPException(404, "Unknown ticket")
    size = 0
    with open(directory / f"{index}.mp3", "wb") as out:
        async for chunk in request.stream():
            size += len(chunk)
            if size > ytagent.MAX_UPLOAD_BYTES:
                raise HTTPException(413, "File too large")
            out.write(chunk)
    return {"size": size}
