"""Speech to text for dictation (the microphone button of the AI assistant and the notes): Groq Whisper when a Groq key is stored, otherwise
Gemini, with the keys of the AI assistant (see server/assistant.py). The audio is recorded by the browser and not stored."""
import json
import urllib.request
import uuid
from base64 import b64encode
from urllib.parse import quote

from core.i18n import _
from server import assistant

GROQ_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_MODEL = "whisper-large-v3-turbo"
MAX_AUDIO_BYTES = 10 * 1024 * 1024  # a few minutes of speech; Groq accepts 25 MB
# what the browsers record (MediaRecorder): the extension Groq needs to recognize the format
_EXTENSIONS = {"webm": "webm", "ogg": "ogg", "mp4": "mp4", "mpeg": "mp3", "mp3": "mp3", "wav": "wav", "x-wav": "wav", "flac": "flac", "aac": "m4a"}
GEMINI_PROMPT = "Transcribe the speech of this audio exactly as spoken. Answer with the transcript only, without comments. Empty if nothing is said."


def configured() -> bool:
    return assistant.groq_configured() or assistant.configured()


def _kind(content_type: str) -> str:
    return content_type.split(";")[0].strip().lower().rpartition("/")[2]


def _multipart(fields: dict[str, str], filename: str, content_type: str, audio: bytes) -> tuple[bytes, str]:
    boundary = uuid.uuid4().hex
    body = b"".join(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode() for name, value in fields.items())
    body += (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\nContent-Type: {content_type}\r\n\r\n').encode()
    return body + audio + f"\r\n--{boundary}--\r\n".encode(), f"multipart/form-data; boundary={boundary}"


def _groq(audio: bytes, content_type: str, language: str) -> str:
    fields = {"model": GROQ_MODEL, "response_format": "json", "temperature": "0"}
    if language:
        fields["language"] = language
    body, header = _multipart(fields, f"dictation.{_EXTENSIONS.get(_kind(content_type), 'webm')}", content_type or "audio/webm", audio)
    request = urllib.request.Request(GROQ_URL, data=body, method="POST", headers={"Content-Type": header})
    return str(assistant._send(request, "groq").get("text") or "")


def _gemini(audio: bytes, content_type: str) -> str:
    payload = {"contents": [{"parts": [{"text": GEMINI_PROMPT},
                                       {"inline_data": {"mime_type": (content_type or "audio/webm").split(";")[0], "data": b64encode(audio).decode()}}]}]}
    request = urllib.request.Request(assistant.API_URL.format(model=quote(assistant.model(), safe="")), data=json.dumps(payload).encode("utf-8"),
                                     method="POST", headers={"Content-Type": "application/json"})
    answer = assistant._send(request)
    parts = ((answer.get("candidates") or [{}])[0].get("content") or {}).get("parts") or []
    return "".join(str(part.get("text") or "") for part in parts if not part.get("thought"))


def transcribe(audio: bytes, content_type: str = "", language: str = "") -> str:
    """The text of the speech in `audio`; `language` (e.g. "de") is a hint, empty to let the service detect it."""
    if not audio:
        raise assistant.AssistantError(_("No audio was recorded"))
    if len(audio) > MAX_AUDIO_BYTES:
        raise assistant.AssistantError(_("The recording is too long"))
    if assistant.groq_configured():
        return _groq(audio, content_type, language).strip()
    return _gemini(audio, content_type).strip()
