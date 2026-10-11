"""The AI assistant (Google Gemini): song suggestions for a scene, a general chat for the game master, and its configuration."""
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.i18n import _
from server import assistant, songcheck
from server.auth import require_admin, require_auth

router = APIRouter(dependencies=[Depends(require_auth)])


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20000)


class SearchContext(BaseModel):
    """The tags and genres the smart search may choose from (those of the songs the filter is applied to)."""
    tags: list[str] = Field(default=[], max_length=1000)
    genres: list[str] = Field(default=[], max_length=1000)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=200)
    mode: Literal["music", "general", "smart"] = "music"
    context: SearchContext | None = None


class SongModel(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    artist: str = Field(default="", max_length=300)


class VerifyRequest(BaseModel):
    songs: list[SongModel] = Field(min_length=1, max_length=20)


class AssistantConfig(BaseModel):
    key: str | None = None  # None keeps the stored key
    model: str | None = None
    instructions: str | None = Field(default=None, max_length=assistant.MAX_INSTRUCTIONS_LENGTH)
    generalInstructions: str | None = Field(default=None, max_length=assistant.MAX_INSTRUCTIONS_LENGTH)


@router.post("/api/assistant/chat")
def chat(body: ChatRequest):
    if not assistant.configured():
        raise HTTPException(status_code=409, detail=_("The AI assistant is not configured"))
    if body.messages[-1].role != "user":
        raise HTTPException(status_code=400, detail="The last message must come from the user")
    try:
        return assistant.chat([m.model_dump() for m in body.messages], body.mode, body.context.model_dump() if body.context else None)
    except assistant.AssistantError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.post("/api/assistant/verify")
def verify(body: VerifyRequest):
    """Looks the suggested songs up on YouTube (through a YouTube agent when one is connected) and returns the matching videos."""
    return {"results": songcheck.verify([song.model_dump() for song in body.songs])}


@router.get("/api/assistant/config", dependencies=[Depends(require_admin)])
def get_config():
    return assistant.status()


@router.get("/api/assistant/models", dependencies=[Depends(require_admin)])
def get_models():
    """The models to choose from: loaded from Google with the stored key, a built-in list without one."""
    return assistant.models()


@router.put("/api/assistant/config", dependencies=[Depends(require_admin)])
def put_config(body: AssistantConfig):
    assistant.configure(body.key, body.model, body.instructions, body.generalInstructions)
    return assistant.status()


@router.delete("/api/assistant/config", dependencies=[Depends(require_admin)])
def delete_config():
    assistant.remove()
    return assistant.status()
