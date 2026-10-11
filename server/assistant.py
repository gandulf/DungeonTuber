"""AI assistant through the Gemini API of Google (aistudio.google.com), in two modes: "music" suggests songs for a scene of a
role playing session, "general" answers questions of the game master (rules like those of DSA, the setting, ideas).

The SuperAdmin stores the API key in the settings; it is never sent back to the browser. The client keeps the conversation
and sends it with every request, so the server stays stateless.
"""
import json
import logging
import urllib.error
import urllib.request
from urllib.parse import quote

from core.i18n import _
from core.settings import AppSettings, SettingKeys

logger = logging.getLogger(__file__)

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
# a Flash model: the free tier of Google AI Studio covers it
DEFAULT_MODEL = "gemini-3.8-flash"
MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models?pageSize=1000"
# Only Flash and Flash-Lite models are part of the free tier of the Gemini API (ai.google.dev/gemini-api/docs/pricing);
# the model list of Google does not say so, the name does.
_FREE_FAMILY = "flash"
# offered while the list of Google cannot be loaded (no key yet, offline); see ai.google.dev/gemini-api/docs/models
KNOWN_MODELS = [
    {"id": "gemini-3.8-flash", "name": "Gemini 3.8 Flash"},
    {"id": "gemini-3.6-flash", "name": "Gemini 3.6 Flash"},
    {"id": "gemini-3.5-flash-lite", "name": "Gemini 3.5 Flash-Lite"},
    {"id": "gemini-3.1-flash-lite", "name": "Gemini 3.1 Flash-Lite"},
]
# models for images, speech, embeddings or live audio cannot answer with a song list
_UNSUITED = ("image", "tts", "audio", "live", "embedding", "robotics", "computer-use")
# keys of the former Groq connection, removed once the assistant is configured again
_LEGACY_KEYS = ("assistantApiKey", "assistantModel")
SONG_COUNT = 10
TIMEOUT = 60
MAX_MESSAGES = 30
MAX_MESSAGE_LENGTH = 4000
MAX_INSTRUCTIONS_LENGTH = 4000

SYSTEM_PROMPT = """Answer with a JSON object only:
{"message": "<one or two short sentences for the user>", "songs": [{"title": "<song title>", "artist": "<artist or composer>"}]}
Write the message in the language the user writes in."""

GENERAL_PROMPT = """You are the assistant of the game master of a tabletop role playing session, for example Das Schwarze Auge (DSA).
Answer questions about the rules, the world and its lore, and help with ideas for the session: names, descriptions, plot hooks.
Answer concisely and to the point, so the answer can be read during the session; use Markdown for lists and emphasis.
When you are not sure about a rule or a fact, say so instead of inventing one.
Write in the language the user writes in."""

# the answer Gemini has to give in the music mode (structured output)
RESPONSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "message": {"type": "STRING"},
        "songs": {"type": "ARRAY", "items": {
            "type": "OBJECT",
            "properties": {"title": {"type": "STRING"}, "artist": {"type": "STRING"}},
            "required": ["title", "artist"],
        }},
    },
    "required": ["message", "songs"],
}


class AssistantError(OSError):
    pass


def api_key() -> str:
    return (AppSettings.value(SettingKeys.ASSISTANT_API_KEY, "", type=str) or "").strip()


def model() -> str:
    return (AppSettings.value(SettingKeys.ASSISTANT_MODEL, "", type=str) or "").strip() or DEFAULT_MODEL


def instructions(mode: str = "music") -> str:
    key = SettingKeys.ASSISTANT_GENERAL_INSTRUCTIONS if mode == "general" else SettingKeys.ASSISTANT_INSTRUCTIONS
    return (AppSettings.value(key, "", type=str) or "").strip()


def system_prompt(mode: str = "music") -> str:
    extra = instructions(mode)
    base = GENERAL_PROMPT if mode == "general" else SYSTEM_PROMPT
    return base + (f"\n\nAdditional instructions of the game master:\n{extra}" if extra else "")


def configured() -> bool:
    return bool(api_key())


def status() -> dict:
    key = api_key()
    return {"configured": bool(key), "model": model(), "defaultModel": DEFAULT_MODEL, "keyHint": key[-4:] if len(key) > 8 else "",
            "instructions": instructions(), "generalInstructions": instructions("general")}


def configure(key: str | None, model_name: str | None, extra_instructions: str | None = None, general_instructions: str | None = None):
    """Stores a new key, the model ('' for the default) and the additional instructions of both modes; None keeps the stored value."""
    for legacy in _LEGACY_KEYS:
        AppSettings.remove(legacy)
    if key is not None:
        if key.strip():
            AppSettings.setValue(SettingKeys.ASSISTANT_API_KEY, key.strip())
        else:
            AppSettings.remove(SettingKeys.ASSISTANT_API_KEY)
    if model_name is not None:
        if model_name.strip() and model_name.strip() != DEFAULT_MODEL:
            AppSettings.setValue(SettingKeys.ASSISTANT_MODEL, model_name.strip())
        else:
            AppSettings.remove(SettingKeys.ASSISTANT_MODEL)
    for setting, value in ((SettingKeys.ASSISTANT_INSTRUCTIONS, extra_instructions),
                           (SettingKeys.ASSISTANT_GENERAL_INSTRUCTIONS, general_instructions)):
        if value is None:
            continue
        if value.strip():
            AppSettings.setValue(setting, value.strip()[:MAX_INSTRUCTIONS_LENGTH])
        else:
            AppSettings.remove(setting)


def remove():
    AppSettings.remove(SettingKeys.ASSISTANT_API_KEY)
    AppSettings.remove(SettingKeys.ASSISTANT_MODEL)


def _post(payload: dict) -> dict:
    request = urllib.request.Request(API_URL.format(model=quote(model(), safe="")), data=json.dumps(payload).encode("utf-8"),
                                     method="POST", headers={"Content-Type": "application/json"})
    return _send(request)


def _send(request: urllib.request.Request) -> dict:
    key = api_key()
    if not key:
        raise AssistantError(_("The AI assistant is not configured"))
    request.add_header("x-goog-api-key", key)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as e:
        detail = _detail(e)
        if e.code in (401, 403) or (e.code == 400 and "API key" in detail):
            raise AssistantError(_("The AI service rejected the API key ({0})").format(detail)) from e
        if e.code == 429:
            raise AssistantError(_("The AI service is busy, please try again in a moment ({0})").format(detail)) from e
        raise AssistantError(_("The AI service failed ({0}): {1}").format(e.code, detail)) from e
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise AssistantError(_("The AI service is not reachable: {0}").format(e)) from e


def _detail(error: urllib.error.HTTPError) -> str:
    try:
        data = json.loads(error.read())
        return str(data.get("error", {}).get("message") or error.reason)
    except (OSError, ValueError, AttributeError):
        return str(error.reason)


def models() -> dict:
    """The Gemini models of the free tier that can chat: the list of Google for the stored key, otherwise KNOWN_MODELS."""
    if configured():
        try:
            data = _send(urllib.request.Request(MODELS_URL))
            found = []
            for entry in data.get("models") or []:
                model_id = str(entry.get("name") or "").removeprefix("models/")
                if (model_id.startswith("gemini") and _FREE_FAMILY in model_id and "generateContent" in (entry.get("supportedGenerationMethods") or [])
                        and not any(word in model_id for word in _UNSUITED)):
                    found.append({"id": model_id, "name": str(entry.get("displayName") or model_id)})
            if found:
                return {"models": sorted(found, key=lambda m: m["id"], reverse=True), "live": True}
        except (AssistantError, AttributeError, TypeError) as e:
            logger.warning("Unable to load the Gemini models: {0}", e)
    return {"models": KNOWN_MODELS, "live": False}


def _songs(raw: object) -> list[dict[str, str]]:
    songs, seen = [], set()
    for entry in raw if isinstance(raw, list) else []:
        if isinstance(entry, str):
            entry = {"title": entry}
        if not isinstance(entry, dict):
            continue
        title = str(entry.get("title") or "").strip()
        artist = str(entry.get("artist") or "").strip()
        if title and (title.lower(), artist.lower()) not in seen:
            seen.add((title.lower(), artist.lower()))
            songs.append({"title": title, "artist": artist})
    return songs[:SONG_COUNT]


def chat(messages: list[dict[str, str]], mode: str = "music") -> dict:
    """Sends the conversation (role user or assistant) and returns the message, the suggested songs and the raw answer.

    The raw answer goes back into the conversation as the assistant turn, so the model knows what it already suggested.
    The general mode answers in Markdown and suggests no songs.
    """
    history = [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"][:MAX_MESSAGE_LENGTH]}]}
               for m in messages[-MAX_MESSAGES:]]
    payload = {"systemInstruction": {"parts": [{"text": system_prompt(mode)}]}, "contents": history}
    if mode != "general":
        payload["generationConfig"] = {"responseMimeType": "application/json", "responseSchema": RESPONSE_SCHEMA}
    data = _post(payload)
    try:
        candidate = data["candidates"][0]
        # thoughts of thinking models are not part of the answer
        content = "".join(part.get("text", "") for part in candidate["content"]["parts"] if not part.get("thought")).strip()
    except (KeyError, IndexError, TypeError, AttributeError) as e:
        reason = (data.get("promptFeedback") or {}).get("blockReason") if isinstance(data, dict) else None
        if reason:
            raise AssistantError(_("The AI service refused the question ({0})").format(reason)) from e
        raise AssistantError(_("The AI service sent an unexpected answer")) from e
    if mode == "general":
        return {"message": content, "songs": [], "content": content}
    try:
        parsed = json.loads(content)
    except ValueError:
        logger.warning("The assistant answered without JSON: {0}", content[:200])
        parsed = {"message": content, "songs": []}
    if not isinstance(parsed, dict):
        parsed = {"songs": parsed}
    return {"message": str(parsed.get("message") or "").strip(), "songs": _songs(parsed.get("songs")), "content": content}
