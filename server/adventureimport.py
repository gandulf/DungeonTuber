"""Imports an adventure from a published adventure book (PDF) with Gemini, using the key and the model of the AI assistant (see
server/assistant.py; the default Flash model is part of the free tier).

The PDF goes to the File API of Gemini, which reads its text, layout and pictures. A first request splits the book into scenes and
the ways between them, then the notes of the scenes are written a few at a time (an answer has a limited length, and the free tier
allows only a few requests per minute). The result is a private adventure of the user with one block per scene, linked like the
scenes; music and effects stay empty (the AI cannot know the songs of the library). Imports run in a background thread, the client
polls the job (the server is a single process, see server/__main__.py).
"""
import json
import logging
import re
import threading
import time
import urllib.error
import urllib.request
import uuid
from urllib.parse import quote

from core import adventures as model
from core.i18n import _
from server import assistant

logger = logging.getLogger(__file__)

UPLOAD_URL = "https://generativelanguage.googleapis.com/upload/v1beta/files"
API_ROOT = "https://generativelanguage.googleapis.com/v1beta/"
MAX_PDF = 50 * 1024 * 1024  # the limit of the File API for PDFs
TIMEOUT = 300  # reading a whole book takes a while
SCENES_PER_REQUEST = 4
MAX_SCENES = 60
RETRIES = 3
RETRY_WAIT = 30  # seconds after "too many requests": the free tier counts requests per minute
FINISHED_JOBS_KEPT = 3600  # seconds a finished job can still be polled

OUTLINE_PROMPT = """You read a published adventure for a tabletop role playing game (for example "Das Schwarze Auge") and split it
into the scenes a game master plays through, for the notes of the game master's software.
Answer with a JSON object only:
{"title": "<the title of the adventure>", "scenes": [{"key": "s1", "title": "<short title>", "pages": "<pages of the book, e.g. 12-14>",
 "summary": "<one or two sentences>"}], "links": [{"from": "s1", "to": "s2", "label": "<how the heroes get there, or empty>"}]}
Rules:
- A scene is a place, an encounter or a situation the heroes play through. List them in the order of play, the start first, between
  5 and 40 scenes; keys are s1, s2, … in that order.
- Background chapters for the game master (the persons, the places, the secret story) become one or two scenes at the end, e.g.
  "For the game master: persons", when they matter during play. Leave out the rules summary, the credits and the advertisements.
- links say which scene can follow which: label names the choice or the condition in a few words ("they follow the tracks"), or is
  empty when the next scene simply follows.
- Write the titles and summaries in the language of the book."""

NOTES_PROMPT = """You write the notes of some scenes of a published adventure for a tabletop role playing game, from the attached
book, for the game master's software. The game master reads them during play.
Answer with a JSON object only: {"scenes": [{"key": "<key of the scene>", "markdown": "<the notes>"}]}
For each scene:
- Start with the read-aloud text of the book as a quote (lines starting with "> "), in the words of the book; without one, write two
  to four vivid sentences of what the heroes see, hear and smell.
- Then short sections with "## " headings and bullet points: who is there and what they want, secrets, what the heroes can find out
  or try (with the checks and values of the book), dangers and fights (the values of the opponents), and what happens next.
- Refer to another scene by its key in double brackets, e.g. [[s4]], where the book says where the heroes go next.
- Keep every name, place and number of the book; do not invent a different plot. Plain Markdown only: **bold**, *italic*, lists,
  "> " quotes and "## "/"### " headings; no tables and no HTML.
- Write in the language of the book, as long as the scene needs (up to about 700 words)."""

OUTLINE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "title": {"type": "STRING"},
        "scenes": {"type": "ARRAY", "items": {
            "type": "OBJECT",
            "properties": {"key": {"type": "STRING"}, "title": {"type": "STRING"}, "pages": {"type": "STRING"}, "summary": {"type": "STRING"}},
            "required": ["key", "title", "summary"],
        }},
        "links": {"type": "ARRAY", "items": {
            "type": "OBJECT",
            "properties": {"from": {"type": "STRING"}, "to": {"type": "STRING"}, "label": {"type": "STRING"}},
            "required": ["from", "to"],
        }},
    },
    "required": ["title", "scenes", "links"],
}

NOTES_SCHEMA = {
    "type": "OBJECT",
    "properties": {"scenes": {"type": "ARRAY", "items": {
        "type": "OBJECT",
        "properties": {"key": {"type": "STRING"}, "markdown": {"type": "STRING"}},
        "required": ["key", "markdown"],
    }}},
    "required": ["scenes"],
}

SCENE_LINK = re.compile(r"\[\[\s*(s\d+)\s*\]\]")


class ImportFailed(Exception):
    pass


# --- Gemini -----------------------------------------------------------------------------------------------------------------------

def _call(url: str, data: bytes | None = None, headers: dict | None = None, method: str = "POST") -> tuple[dict, dict]:
    """A request to Gemini with the key of the assistant; retries when the quota per minute is used up. Returns the JSON answer and
    the headers of the answer."""
    key = assistant.api_key()
    if not key:
        raise ImportFailed(_("The AI assistant is not configured"))
    for attempt in range(RETRIES + 1):
        request = urllib.request.Request(url, data=data, method=method, headers={**(headers or {}), "x-goog-api-key": key})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                body = response.read()
                return (json.loads(body) if body else {}), dict(response.headers)
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < RETRIES:
                logger.info("Gemini is busy (%s), waiting %s s", e.code, RETRY_WAIT)
                time.sleep(RETRY_WAIT)
                continue
            detail = assistant._detail(e)
            if e.code in (401, 403):
                raise ImportFailed(_("The AI service rejected the API key ({0})").format(detail)) from e
            raise ImportFailed(_("The AI service failed ({0}): {1}").format(e.code, detail)) from e
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            raise ImportFailed(_("The AI service is not reachable: {0}").format(e)) from e
    raise ImportFailed(_("The AI service is busy, please try again in a moment ({0})").format(""))


def upload(pdf: bytes, name: str) -> dict:
    """Uploads the PDF to the File API (resumable upload in one piece) and waits until Gemini has processed it."""
    _answer, headers = _call(UPLOAD_URL, json.dumps({"file": {"display_name": name[:120] or "adventure.pdf"}}).encode("utf-8"), {
        "X-Goog-Upload-Protocol": "resumable", "X-Goog-Upload-Command": "start", "Content-Type": "application/json",
        "X-Goog-Upload-Header-Content-Length": str(len(pdf)), "X-Goog-Upload-Header-Content-Type": "application/pdf"})
    url = next((value for header, value in headers.items() if header.lower() == "x-goog-upload-url"), None)
    if not url:
        raise ImportFailed(_("The AI service sent an unexpected answer"))
    answer, _headers = _call(url, pdf, {"X-Goog-Upload-Offset": "0", "X-Goog-Upload-Command": "upload, finalize"})
    file = answer.get("file") or {}
    for _attempt in range(60):
        if file.get("state") in (None, "ACTIVE"):
            return file
        if file.get("state") == "FAILED":
            raise ImportFailed(_("The AI service could not read the PDF"))
        time.sleep(2)
        file, _headers = _call(API_ROOT + file["name"], method="GET")
    raise ImportFailed(_("The AI service could not read the PDF"))


def remove(file: dict):
    try:
        _call(API_ROOT + file["name"], method="DELETE")
    except (ImportFailed, KeyError):
        pass  # Gemini deletes uploaded files after 48 hours anyway


def ask(file: dict, system: str, text: str, schema: dict) -> dict:
    """Asks Gemini about the uploaded book; the answer is the JSON object of the schema."""
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"fileData": {"mimeType": "application/pdf", "fileUri": file["uri"]}}, {"text": text}]}],
        "generationConfig": {"responseMimeType": "application/json", "responseSchema": schema},
    }
    data, _headers = _call(assistant.API_URL.format(model=quote(assistant.model(), safe="")), json.dumps(payload).encode("utf-8"),
                           {"Content-Type": "application/json"})
    try:
        parts = data["candidates"][0]["content"]["parts"]
        return json.loads("".join(part.get("text", "") for part in parts if not part.get("thought")))
    except (KeyError, IndexError, TypeError, ValueError) as e:
        reason = (data.get("promptFeedback") or {}).get("blockReason") if isinstance(data, dict) else None
        if reason:
            raise ImportFailed(_("The AI service refused the question ({0})").format(reason)) from e
        raise ImportFailed(_("The AI service sent an unexpected answer")) from e


# --- the adventure ----------------------------------------------------------------------------------------------------------------

def scenes_of(outline: dict) -> list[dict]:
    """The scenes of the outline with unique keys, at most MAX_SCENES."""
    scenes, seen = [], set()
    for scene in outline.get("scenes") or []:
        key = str(scene.get("key") or "").strip() if isinstance(scene, dict) else ""
        if key and key not in seen and str(scene.get("title") or "").strip():
            seen.add(key)
            scenes.append(scene)
    return scenes[:MAX_SCENES]


def outline_text(scenes: list[dict]) -> str:
    return "\n".join(f"{scene['key']}: {scene['title']} (pages {scene.get('pages') or '?'}) - {scene.get('summary') or ''}" for scene in scenes)


def build(outline: dict, notes: dict[str, str], owner: str) -> dict:
    """The adventure of the outline and the notes: one block per scene, [[key]] references become links to the blocks."""
    scenes = scenes_of(outline)
    ids = {scene["key"]: model.new_id() for scene in scenes}
    titles = {scene["key"]: str(scene["title"]).strip() for scene in scenes}

    def link(match: re.Match) -> str:
        key = match.group(1)
        return f"[{titles[key]}](block:{ids[key]})" if key in ids else match.group(0)

    blocks = []
    for scene in scenes:
        text = SCENE_LINK.sub(link, notes.get(scene["key"]) or str(scene.get("summary") or "")).strip()
        pages = str(scene.get("pages") or "").strip()
        if pages:
            text += f"\n\n*{_('Pages')}: {pages}*"
        blocks.append({"id": ids[scene["key"]], "title": titles[scene["key"]], "markdown": text, "pos": [0, 0]})
    links = [{"from": ids.get(str(item.get("from"))), "to": ids.get(str(item.get("to"))), "label": item.get("label") or None}
             for item in outline.get("links") or [] if isinstance(item, dict)]
    return model.normalize({"title": outline.get("title") or _("Imported adventure"), "blocks": blocks,
                            "links": [item for item in links if item["from"] and item["to"]]}, owner=owner)


def convert(pdf: bytes, name: str, owner: str, progress=lambda step, total: None) -> dict:
    """Reads the book and returns the adventure (not stored yet)."""
    file = upload(pdf, name)
    try:
        progress(0, 1)
        outline = ask(file, OUTLINE_PROMPT, "Split this adventure into scenes.", OUTLINE_SCHEMA)
        scenes = scenes_of(outline)
        if not scenes:
            raise ImportFailed(_("The AI found no scenes in the PDF"))
        batches = [scenes[index:index + SCENES_PER_REQUEST] for index in range(0, len(scenes), SCENES_PER_REQUEST)]
        notes: dict[str, str] = {}
        for number, batch in enumerate(batches, start=1):
            progress(number, len(batches) + 1)
            text = (f"All scenes of the adventure:\n{outline_text(scenes)}\n\n"
                    f"Write the notes of these scenes: {', '.join(scene['key'] for scene in batch)}.")
            try:
                answer = ask(file, NOTES_PROMPT, text, NOTES_SCHEMA)
            except ImportFailed as e:
                logger.warning("Notes of %s failed: %s", [scene["key"] for scene in batch], e)
                continue  # these scenes keep their summary
            for item in answer.get("scenes") or []:
                if isinstance(item, dict) and isinstance(item.get("markdown"), str):
                    notes[str(item.get("key"))] = item["markdown"]
        return build(outline, notes, owner)
    finally:
        remove(file)


# --- background jobs --------------------------------------------------------------------------------------------------------------

_jobs: dict[str, dict] = {}
_lock = threading.Lock()


def _forget_old():
    now = time.time()
    for job_id, job in list(_jobs.items()):
        if job["status"] != "running" and now - job["finished"] > FINISHED_JOBS_KEPT:
            del _jobs[job_id]


def start(pdf: bytes, name: str, user: str, store) -> dict:
    """Starts an import in the background; `store(adventure)` saves the result and returns its id. One import per user at a time."""
    with _lock:
        _forget_old()
        if any(job["user"] == user and job["status"] == "running" for job in _jobs.values()):
            raise ImportFailed(_("An import is already running"))
        job = {"id": uuid.uuid4().hex, "user": user, "name": name, "status": "running", "step": 0, "total": 1, "adventure": None,
               "error": None, "finished": 0.0}
        _jobs[job["id"]] = job

    def progress(step: int, total: int):
        job["step"], job["total"] = step, total

    def run():
        try:
            job["adventure"] = store(convert(pdf, name, user, progress))
            job["status"] = "done"
        except Exception as e:  # reported to the client
            logger.exception("Import of %s failed", name)
            job["status"], job["error"] = "error", str(e) or type(e).__name__
        finally:
            job["finished"] = time.time()

    threading.Thread(target=run, name=f"adventure-import-{job['id'][:8]}", daemon=True).start()
    return view(job)


def view(job: dict) -> dict:
    return {key: job[key] for key in ("id", "name", "status", "step", "total", "adventure", "error")}


def status(job_id: str, user: str) -> dict | None:
    job = _jobs.get(job_id)
    return view(job) if job and job["user"] == user else None
