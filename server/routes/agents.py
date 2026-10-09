"""Agent status and token management (the agents themselves connect through the /ws/agent WebSocket)."""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from fastapi.responses import FileResponse

from server.agents import agent_hub, agent_tokens, bearer_token, create_agent_token, delete_agent_token, valid_agent_token
from server.auth import current_user
from server.users import ADMIN
from server import ytagent
from server.voxagent import ticket_path

router = APIRouter()


@router.get("/api/agents")
def agents(user: str = Depends(current_user)):
    """The connected agents and the tokens: everybody sees their own, the SuperAdmin all of them."""
    return {"tokens": agent_tokens(None if user == ADMIN else user), "connected": agent_hub.status()}


class TokenRequest(BaseModel):
    name: str = ""


@router.post("/api/agents/tokens")
def create_token(body: TokenRequest, user: str = Depends(current_user)):
    """Creates a token for the signed-in user; it is shown once, only its hash is stored."""
    token, entry = create_agent_token(user, body.name)
    return {"token": token, "id": entry["id"]}


@router.delete("/api/agents/tokens/{token_id}")
async def remove_token(token_id: str, user: str = Depends(current_user)):
    """Revokes a token (the SuperAdmin any, everybody else their own) and disconnects the agents that use it."""
    if not delete_agent_token(token_id, None if user == ADMIN else user):
        raise HTTPException(404, "No such token")
    await agent_hub.revoke(token_id)
    return {"tokens": agent_tokens(None if user == ADMIN else user), "connected": agent_hub.status()}


@router.delete("/api/agents/{agent_id}")
async def remove_agent(agent_id: int, user: str = Depends(current_user)):
    """Disconnects an agent (the SuperAdmin any, everybody else their own); it is told not to reconnect."""
    if not await agent_hub.remove(agent_id, None if user == ADMIN else user):
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
