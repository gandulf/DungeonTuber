"""Agent status and token management (the agents themselves connect through the /ws/agent WebSocket)."""
from fastapi import APIRouter, Depends

from server.agents import agent_hub, agent_token_set, new_agent_token
from server.auth import require_admin, require_auth

router = APIRouter()


@router.get("/api/agents", dependencies=[Depends(require_auth)])
def agents():
    return {"tokenSet": agent_token_set(), "connected": agent_hub.status()}


@router.post("/api/agents/token", dependencies=[Depends(require_admin)])
def create_token():
    """Generates a new agent token; it is shown once, only its hash is stored."""
    return {"token": new_agent_token()}
