"""The AI assistant (Google Gemini): song suggestions for a scene, a general chat for the game master, new pieces composed by the
music generation (ACE-Step on Modal), sounds of the sound generation (Stable Audio 3 on Modal), and their configuration."""
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from core.i18n import _
from server import assistant, imagegen, musicgen, songcheck, soundgen
from server.auth import current_user, require_admin, require_auth
from server.paths import safe_path

router = APIRouter(dependencies=[Depends(require_auth)])


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=20000)


class SearchContext(BaseModel):
    """The tags and genres the smart search may choose from (those of the songs the filter is applied to)."""
    tags: list[str] = Field(default=[], max_length=1000)
    genres: list[str] = Field(default=[], max_length=1000)
    instrumental: bool = True  # compose mode: a piece without vocals
    duration: int | None = Field(default=None, ge=10, le=600)  # compose mode: the length of the piece in seconds (for the lyrics)
    language: str | None = Field(default=None, pattern=r"^[a-z]{2,3}$")  # compose mode: the language of the lyrics
    kind: Literal["sfx", "ambience", "music"] | None = None  # effects mode: the kind of sound


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=200)
    mode: Literal["music", "general", "smart", "compose", "effects", "story", "image"] = "music"
    context: SearchContext | None = None


class SongModel(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    artist: str = Field(default="", max_length=300)


class VerifyRequest(BaseModel):
    songs: list[SongModel] = Field(min_length=1, max_length=20)


class ComposeRequest(BaseModel):
    dir: str  # the library folder the piece is stored in
    title: str = Field(default="", max_length=200)
    caption: str = Field(min_length=1, max_length=assistant.MAX_CAPTION_LENGTH)
    lyrics: str = Field(default="", max_length=assistant.MAX_LYRICS_LENGTH)
    language: str = Field(default="", pattern=r"^([a-z]{2,3})?$")  # of the lyrics; empty: ACE-Step finds it
    instrumental: bool = True
    duration: int = Field(default=120, ge=musicgen.MIN_SECONDS, le=musicgen.MAX_SECONDS)
    bpm: int | None = Field(default=None, ge=30, le=300)
    seed: int | None = Field(default=None, ge=0, le=2 ** 31 - 1)
    analyze: bool = True


class SoundRequest(BaseModel):
    dir: str  # the folder the sound is stored in, usually the effects folder
    title: str = Field(default="", max_length=200)
    caption: str = Field(min_length=1, max_length=assistant.MAX_CAPTION_LENGTH)
    kind: Literal["sfx", "ambience", "music"] = "sfx"
    duration: int | None = Field(default=None, ge=soundgen.MIN_SECONDS, le=soundgen.MAX_SECONDS)  # None: the default of the kind
    seed: int | None = Field(default=None, ge=0, le=2 ** 31 - 1)


class CloudRequest(BaseModel):
    url: str
    key: str
    secret: str


class AssistantConfig(BaseModel):
    key: str | None = None  # None keeps the stored key
    model: str | None = None
    instructions: str | None = Field(default=None, max_length=assistant.MAX_INSTRUCTIONS_LENGTH)
    generalInstructions: str | None = Field(default=None, max_length=assistant.MAX_INSTRUCTIONS_LENGTH)
    composeInstructions: str | None = Field(default=None, max_length=assistant.MAX_INSTRUCTIONS_LENGTH)
    smartInstructions: str | None = Field(default=None, max_length=assistant.MAX_INSTRUCTIONS_LENGTH)
    effectsInstructions: str | None = Field(default=None, max_length=assistant.MAX_INSTRUCTIONS_LENGTH)
    imageInstructions: str | None = Field(default=None, max_length=assistant.MAX_INSTRUCTIONS_LENGTH)
    # the built-in prompts by name (see assistant.PROMPTS); empty or the default restores the built-in one
    prompts: dict[str, Annotated[str, Field(max_length=assistant.MAX_PROMPT_LENGTH)]] | None = Field(default=None, max_length=20)
    groqKey: str | None = None  # None keeps the stored key
    groqModel: str | None = None


@router.post("/api/assistant/chat")
def chat(body: ChatRequest):
    if not assistant.configured(body.mode):
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
    assistant.configure(body.key, body.model, body.instructions, body.generalInstructions, body.groqKey, body.groqModel,
                         body.composeInstructions, body.smartInstructions, body.prompts, body.effectsInstructions,
                         body.imageInstructions)
    return assistant.status()


@router.delete("/api/assistant/config", dependencies=[Depends(require_admin)])
def delete_config(service: Literal["gemini", "groq"] = "gemini"):
    assistant.remove(service)
    return assistant.status()


@router.post("/api/assistant/compose")
def compose(body: ComposeRequest, user: str = Depends(current_user)):
    """Composes the piece in the cloud function and stores it in `dir`; takes from a few seconds to some minutes (cold start)."""
    if not musicgen.configured():
        raise HTTPException(status_code=409, detail=_("The music generation is not configured"))
    directory = safe_path(body.dir, kind="dir")
    try:
        return musicgen.compose(body.model_dump(exclude={"dir", "analyze"}), directory, user, body.analyze)
    except musicgen.MusicGenError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/api/assistant/musicgen", dependencies=[Depends(require_admin)])
def musicgen_status():
    """Whether the music generation is configured (the key and the secret are never sent back)."""
    return musicgen.status()


@router.put("/api/assistant/musicgen", dependencies=[Depends(require_admin)])
def put_musicgen(body: CloudRequest):
    try:
        musicgen.save_config(body.url, body.key, body.secret)
    except musicgen.CloudError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return musicgen.status()


@router.delete("/api/assistant/musicgen", dependencies=[Depends(require_admin)])
def delete_musicgen():
    musicgen.delete_config()
    return musicgen.status()


@router.post("/api/assistant/sound")
def sound(body: SoundRequest, user: str = Depends(current_user)):
    """Generates the sound in the cloud function and stores it in `dir`; takes from a few seconds to some minutes (cold start)."""
    if not soundgen.configured():
        raise HTTPException(status_code=409, detail=_("The sound generation is not configured"))
    directory = safe_path(body.dir, kind="dir")
    try:
        return soundgen.create(body.model_dump(exclude={"dir"}), directory, user)
    except soundgen.SoundGenError as e:
        raise HTTPException(status_code=502, detail=str(e))


@router.get("/api/assistant/soundgen", dependencies=[Depends(require_admin)])
def soundgen_status():
    """Whether the sound generation is configured (the key and the secret are never sent back)."""
    return soundgen.status()


@router.put("/api/assistant/soundgen", dependencies=[Depends(require_admin)])
def put_soundgen(body: CloudRequest):
    try:
        soundgen.save_config(body.url, body.key, body.secret)
    except soundgen.CloudError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return soundgen.status()


@router.delete("/api/assistant/soundgen", dependencies=[Depends(require_admin)])
def delete_soundgen():
    soundgen.delete_config()
    return soundgen.status()


@router.get("/api/assistant/imagegen", dependencies=[Depends(require_admin)])
def imagegen_status():
    """Whether the image generation is configured (the key and the secret are never sent back)."""
    return imagegen.status()


@router.put("/api/assistant/imagegen", dependencies=[Depends(require_admin)])
def put_imagegen(body: CloudRequest):
    try:
        imagegen.save_config(body.url, body.key, body.secret)
    except imagegen.CloudError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return imagegen.status()


@router.delete("/api/assistant/imagegen", dependencies=[Depends(require_admin)])
def delete_imagegen():
    imagegen.delete_config()
    return imagegen.status()
