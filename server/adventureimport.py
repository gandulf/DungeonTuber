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
from core import i18n
from core.i18n import _
from server import assistant

logger = logging.getLogger(__file__)

UPLOAD_URL = "https://generativelanguage.googleapis.com/upload/v1beta/files"
API_ROOT = "https://generativelanguage.googleapis.com/v1beta/"
MAX_PDF = 50 * 1024 * 1024  # the limit of the File API for PDFs
TIMEOUT = 300  # reading a whole book takes a while
SCENES_PER_REQUEST = 4
MAX_SCENES = 200  # a long book at a high level of detail has many scenes
MAX_CHARACTERS = 25
MIN_OVERVIEW = 3  # the overview block "Dramatis Personae" only for at least this many persons (every person has a block of its own)
MIN_NAME = 3  # shorter names are not linked in the notes (too many false hits)
# the level of detail the user asks for: how fine the book is split into scenes (blocks) and how much the notes of a scene hold. The AI
# decides how many scenes that takes, so a long book gets more of them.
DETAILS = {
    "low": ("Few, large scenes: one per chapter or per major location; small places and encounters belong to the scene they are in.",
            "Keep the notes short: the read-aloud text and the essentials (what happens, the decisive checks and values); leave out minor details."),
    "medium": ("One scene per place, encounter or situation the heroes play through.",
               "Write what the scene needs for play: the important details, the checks and the values of the book."),
    "high": ("Fine scenes: every room, every encounter, every important conversation and every event is a scene of its own.",
             "Write complete notes: every detail, check, value, rule and hint of the book for the scene; leave nothing important out, however "
             "long that makes the notes."),
}
DEFAULT_DETAIL = "medium"
RETRIES = 3
RETRY_WAIT = 30  # seconds after "too many requests": the free tier counts requests per minute
FINISHED_JOBS_KEPT = 3600  # seconds a finished job can still be polled

OUTLINE_PROMPT = """You read a published adventure for a tabletop role playing game (for example "Das Schwarze Auge") and split it
into the scenes a game master plays through, for the notes of the game master's software.
Answer with a JSON object only:
{"title": "<the title of the adventure>", "scenes": [{"key": "s1", "title": "<short title>", "pages": "<pages of the book, e.g. 12-14>",
 "summary": "<one or two sentences>"}], "links": [{"from": "s1", "to": "s2", "label": "<how the heroes get there, or empty>"}],
 "characters": [{"key": "p1", "name": "<full name>", "aliases": ["<other ways the book names the person>"], "pages": "<pages>",
 "summary": "<one short line: the role and what the person wants>"}]}
Rules:
- A scene is a place, an encounter or a situation the heroes play through. List them in the order of play, the start first; keys are
  s1, s2, … in that order. How fine you split the book is set by the level of detail: __SPLIT__ Make as many scenes as that takes: the
  longer the book, the more scenes.
- Background chapters for the game master (the persons, the places, the secret story) become one or two scenes at the end, e.g.
  "For the game master: persons", when they matter during play. Leave out the rules summary, the credits and the advertisements.
- links say which scene can follow which: label names the choice or the condition in a few words ("they follow the tracks"), or is
  empty when the next scene simply follows.
- characters are the persons with a name who matter in play: allies, opponents, patrons, victims, the villain. Keys are p1, p2, … in
  the order of their first appearance. aliases are the short forms and titles the book uses ("Torben" and "Hauptmann Torben"); leave
  them out when there is none. Skip nameless extras and the heroes of the players. Answer an empty list when there is no such
  person.
- Page numbers (pages) are those of the PDF file, where its first page is 1, not the numbers printed on the pages.
- Write the titles and summaries in the language of the book."""

STAT_BLOCK = """Stat blocks (the master data of a person or an opponent: attributes, combat values, talents) always look like this, with the
abbreviations and values of the book's rules edition, and only the lines the book has values for:
**Attributes:** MU 13 · KL 12 · IN 14 · CH 11 · FF 12 · GE 13 · KO 12 · KK 13
**Combat:** LeP 30 · AsP 24 · INI 12 · PA 8 · RS 2 · GS 8
**Weapons:** Sword (TP 1W+4, AT 14)
**Skills:** Body control 8, Perception 10
**Special:** special abilities, spells, advantages and disadvantages, in one line
The line names above are English: write them, and the names of skills, weapons and abilities, in the language of the adventure book
(German: Eigenschaften, Kampf, Waffen, Talente, Besonderes); if you cannot tell its language, write them in __LANGUAGE__."""

NOTES_PROMPT = """You write the notes of some scenes of a published adventure for a tabletop role playing game, from the attached
book, for the game master's software. The game master reads them during play.
Answer with a JSON object only: {"scenes": [{"key": "<key of the scene>", "markdown": "<the notes>"}]}
For each scene:
- Start with the read-aloud text of the book as a quote (lines starting with "> "), in the words of the book; without one, write two
  to four vivid sentences of what the heroes see, hear and smell.
- Then short sections with "## " headings and bullet points: who is there and what they want, secrets, what the heroes can find out
  or try (with the checks and values of the book), dangers and fights (the values of the opponents), and what happens next.
- Refer to another scene by its key in double brackets, e.g. [[s4]], where the book says where the heroes go next. Name persons
  plainly, with the name the book uses; the software links them to their own pages.
- For an opponent or a person with values in the book, add the stat block in the form below.
- Where the book has a map, a floor plan, a picture or a handout for the scene, name it and link its page of the PDF: [Map of the
  tavern](pdf:12), with the page number of the PDF (the first page of the file is 1).
- A key that starts with "p" is a person, not a scene. Write the page of that person instead: first a short description (looks,
  manner, voice), then what the person wants and knows, how they treat the heroes, and the stat block if the book has one.
- Keep every name, place and number of the book; do not invent a different plot. Plain Markdown only: **bold**, *italic*, lists,
  "> " quotes and "## "/"### " headings; no tables and no HTML.
- Write in the language of the book. __NOTES_DETAIL__"""

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
        "characters": {"type": "ARRAY", "items": {
            "type": "OBJECT",
            "properties": {"key": {"type": "STRING"}, "name": {"type": "STRING"}, "aliases": {"type": "ARRAY", "items": {"type": "STRING"}},
                           "pages": {"type": "STRING"}, "summary": {"type": "STRING"}},
            "required": ["key", "name", "summary"],
        }},
    },
    "required": ["title", "scenes", "links", "characters"],
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

SCENE_LINK = re.compile(r"\[\[\s*([sp]\d+)\s*\]\]")
MARKDOWN_LINK = re.compile(r"\[[^\]]*\]\([^)]*\)")


class ImportFailed(Exception):
    pass


class Cancelled(Exception):
    """The user cancelled the import: the thread of the import ends at its next request or pause."""


# --- the log of an import: what happens (and what goes wrong) is shown in the progress popup of the app and written to the server log ------

MAX_LOG = 200
_local = threading.local()  # the import that runs in this thread


def _write(job: dict | None, message: str, level: str = "info"):
    getattr(logger, level)(message)
    if job is not None:
        job["log"].append({"time": time.time(), "level": level, "message": message})
        del job["log"][:-MAX_LOG]


def note(message: str, level: str = "info"):
    """Writes `message` to the log of the import running in this thread (level "info", "warning" or "error") and to the server log."""
    _write(getattr(_local, "job", None), message, level)


def _set_stage(job: dict, key: str, *args):
    job["stage_key"], job["stage_args"] = key, list(args)
    job["stage"] = _(key).format(*args) if args else _(key)


def check_cancelled():
    """Ends the import running in this thread when the user cancelled it."""
    event = (getattr(_local, "job", None) or {}).get("cancel")
    if event is not None and event.is_set():
        raise Cancelled()


def pause(seconds: float, checked: bool = True):
    """Waits; a cancel of the import running in this thread ends the wait at once (and the import)."""
    event = (getattr(_local, "job", None) or {}).get("cancel")
    if event is not None and checked:
        if event.wait(seconds):
            raise Cancelled()
    else:
        time.sleep(seconds)


def stage(key: str | None = None, *args) -> tuple[str, tuple]:
    """Sets what the import is doing right now (shown under the progress bar): `key` is the English text with {0}, {1} for `args`. The client
    translates it into the language of the user; the text in the language of the server is there as well. Returns the key and the
    arguments of what it was doing before (for `stage(*before)`)."""
    job = getattr(_local, "job", None)
    previous = (job["stage_key"], tuple(job["stage_args"])) if job is not None else ("", ())
    if job is not None and key is not None:
        _set_stage(job, key, *args)
    return previous


# --- Gemini -----------------------------------------------------------------------------------------------------------------------

def _call(url: str, data: bytes | None = None, headers: dict | None = None, method: str = "POST", checked: bool = True) -> tuple[dict, dict]:
    """A request to Gemini with the key of the assistant; retries when the quota per minute is used up. Returns the JSON answer and
    the headers of the answer."""
    key = assistant.api_key()
    if not key:
        raise ImportFailed(_("The AI assistant is not configured"))
    for attempt in range(RETRIES + 1):
        if checked:
            check_cancelled()
        request = urllib.request.Request(url, data=data, method=method, headers={**(headers or {}), "x-goog-api-key": key})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                body = response.read()
                return (json.loads(body) if body else {}), dict(response.headers)
        except urllib.error.HTTPError as e:
            detail = assistant._detail(e)
            if e.code in (429, 503) and attempt < RETRIES:
                note(f"The AI service is busy ({e.code}: {detail[:160]}); waiting {RETRY_WAIT} s, then trying again ({attempt + 1} of {RETRIES})", "warning")
                before = stage("The AI service is busy, waiting to try again ({0} of {1})", attempt + 1, RETRIES)
                pause(RETRY_WAIT, checked)
                stage(*before)
                continue
            note(f"The AI service answered {e.code}: {detail[:300]}", "error")
            if e.code in (401, 403):
                raise ImportFailed(_("The AI service rejected the API key ({0})").format(detail)) from e
            raise ImportFailed(_("The AI service failed ({0}): {1}").format(e.code, detail)) from e
        except (urllib.error.URLError, TimeoutError, ValueError) as e:
            note(f"The AI service is not reachable: {e}", "error")
            raise ImportFailed(_("The AI service is not reachable: {0}").format(e)) from e
    note("The AI service stayed busy; giving up", "error")
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
        pause(2)
        file, _headers = _call(API_ROOT + file["name"], method="GET")
    raise ImportFailed(_("The AI service could not read the PDF"))


def remove(file: dict):
    try:
        _call(API_ROOT + file["name"], method="DELETE", checked=False)  # also after a cancel: the file is not left at Gemini
    except (ImportFailed, KeyError, Cancelled):
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


def characters_of(outline: dict) -> list[dict]:
    """The persons of the outline with the keys p1, p2, … in their order, at most MAX_CHARACTERS."""
    people = []
    for person in outline.get("characters") or []:
        if isinstance(person, dict) and str(person.get("name") or "").strip():
            people.append({**person, "key": f"p{len(people) + 1}", "name": str(person["name"]).strip()})
    people = people[:MAX_CHARACTERS]
    return people


def names_of(person: dict) -> list[str]:
    """The names a person is called in the notes: the name and the aliases the AI found (names that are too short are left out)."""
    aliases = [alias.strip() for alias in person.get("aliases") or [] if isinstance(alias, str)]
    return sorted({name for name in [person["name"], *aliases] if len(name) >= MIN_NAME}, key=len, reverse=True)


def outline_text(scenes: list[dict], people: list[dict] = ()) -> str:
    text = "\n".join(f"{scene['key']}: {scene['title']} (pages {scene.get('pages') or '?'}) - {scene.get('summary') or ''}" for scene in scenes)
    if people:
        text += "\n\nPersons:\n" + "\n".join(f"{person['key']}: {person['name']} (pages {person.get('pages') or '?'}) - {person.get('summary') or ''}"
                                              for person in people)
    return text


def link_people(text: str, names: dict[str, str], own: str | None = None) -> str:
    """Links the first mention of each person in `text` to the block of the person (`names` maps a name to a block id; `own` is the
    block the text belongs to). Existing links and headings stay as they are."""
    names = {name: block for name, block in names.items() if block != own}
    if not names:
        return text
    pattern = re.compile(r"(?<!\w)(" + "|".join(re.escape(name) for name in sorted(names, key=len, reverse=True)) + r")(?!\w)")
    linked: set[str] = set()

    def replace(match: re.Match) -> str:
        block = names[match.group(1)]
        if block in linked:
            return match.group(0)
        linked.add(block)
        return f"[{match.group(1)}](block:{block})"

    lines = []
    for line in text.split("\n"):
        if line.lstrip().startswith("#"):
            lines.append(line)
            continue
        parts, links = MARKDOWN_LINK.split(line), MARKDOWN_LINK.findall(line)
        lines.append("".join(pattern.sub(replace, part) + (links[index] if index < len(links) else "") for index, part in enumerate(parts)))
    return "\n".join(lines)


PAGES = re.compile(r"(?<![\d.])(\d{1,4})(?:\s*[-–]\s*\d{1,4})?(?!\d)")


def page_link(pages: str) -> str:
    """Every page or range in `pages` ("7-8, 18-19") as a link to its first page in the book (PDF) of the adventure:
    [7-8](pdf:7), [18-19](pdf:18); other text stays."""
    return PAGES.sub(lambda match: f"[{match.group(0)}](pdf:{int(match.group(1))})" if int(match.group(1)) > 0 else match.group(0), pages)


def build(outline: dict, notes: dict[str, str], owner: str) -> dict:
    """The adventure of the outline and the notes: one block per scene, [[key]] references become links to the blocks. With at least
    MIN_OVERVIEW persons there is a block "Dramatis Personae"; every person has a block, their names in the notes link to it."""
    scenes, people = scenes_of(outline), characters_of(outline)
    ids = {item["key"]: model.new_id() for item in [*scenes, *people]}
    titles = {**{scene["key"]: str(scene["title"]).strip() for scene in scenes}, **{person["key"]: person["name"] for person in people}}
    names = {name: ids[person["key"]] for person in people for name in names_of(person)}

    def link(match: re.Match) -> str:
        key = match.group(1)
        return f"[{titles[key]}](block:{ids[key]})" if key in ids else match.group(0)

    def block_of(item: dict, inline: bool = False) -> dict:
        key = item["key"]
        text = link_people(SCENE_LINK.sub(link, notes.get(key) or str(item.get("summary") or "")).strip(), names, ids[key])
        pages = str(item.get("pages") or "").strip()
        if pages:
            text += f"\n\n*{_('Pages')}: {page_link(pages)}*"
        return {"id": ids[key], "title": titles[key], "markdown": text, "pos": [0, 0], "inline": inline}

    blocks = [block_of(scene) for scene in scenes]
    if len(people) >= MIN_OVERVIEW:
        overview = "\n".join(f"- [{person['name']}](block:{ids[person['key']]})" + (f" – {str(person.get('summary') or '').strip()}" if str(person.get("summary") or "").strip() else "")
                             for person in people)
        blocks.append({"id": model.new_id(), "title": _("Dramatis Personae"), "markdown": overview, "pos": [0, 0]})
    blocks.extend(block_of(person, inline=True) for person in people)  # reached through the overview and the names in the notes
    links = [{"from": ids.get(str(item.get("from"))), "to": ids.get(str(item.get("to"))), "label": item.get("label") or None}
             for item in outline.get("links") or [] if isinstance(item, dict)]
    return model.normalize({"title": outline.get("title") or _("Imported adventure"), "blocks": blocks,
                            "links": [item for item in links if item["from"] and item["to"]]}, owner=owner)


def stat_block() -> str:
    """The stat block rule; the language of the user (the language of the app) is the fallback for its line names."""
    language = i18n.language() or "en"
    return STAT_BLOCK.replace("__LANGUAGE__", assistant.LANGUAGE_NAMES.get(language, language))


def with_instructions(prompt: str) -> str:
    """The prompt with the additional instructions of the game master for the import (see the AI assistant settings), if any."""
    extra = assistant.instructions("import")
    if not extra:
        return prompt
    return "\n\n".join([prompt, "Additional instructions of the game master for this import (they come first when they differ from the rules above):", extra])


def detail_of(detail: str | None) -> str:
    return detail if detail in DETAILS else DEFAULT_DETAIL


def outline_prompt(detail: str) -> str:
    return OUTLINE_PROMPT.replace("__SPLIT__", DETAILS[detail_of(detail)][0])


def notes_prompt(detail: str) -> str:
    return NOTES_PROMPT.replace("__NOTES_DETAIL__", DETAILS[detail_of(detail)][1])


def convert(pdf: bytes, name: str, owner: str, progress=lambda step, total: None, detail: str | None = None) -> dict:
    """Reads the book and returns the adventure (not stored yet); `detail` ("low", "medium" or "high") is how fine the book is split into scenes
    and how much their notes hold."""
    detail = detail_of(detail)
    note(f"Import of \"{name}\" started ({len(pdf) // 1024} KB, level of detail: {detail})")
    stage("Uploading the PDF")
    file = upload(pdf, name)
    note("The PDF is uploaded and processed by the AI service")
    try:
        progress(0, 1)
        stage("Reading the book")
        outline = ask(file, with_instructions(outline_prompt(detail)), f"Split this adventure into scenes at the level of detail: {detail}.", OUTLINE_SCHEMA)
        scenes = scenes_of(outline)
        if not scenes:
            raise ImportFailed(_("The AI found no scenes in the PDF"))
        people = characters_of(outline)
        batches = [("scenes", scenes[index:index + SCENES_PER_REQUEST]) for index in range(0, len(scenes), SCENES_PER_REQUEST)]
        batches += [("persons", people[index:index + SCENES_PER_REQUEST]) for index in range(0, len(people), SCENES_PER_REQUEST)]
        note(f"Outline: {len(scenes)} scenes and {len(people)} persons, the notes are written in {len(batches)} steps")
        notes: dict[str, str] = {}
        for number, (kind, batch) in enumerate(batches, start=1):
            progress(number, len(batches) + 1)
            stage("Writing the notes ({0} of {1})", number, len(batches))
            note(f"Notes {number} of {len(batches)}: {kind} {', '.join(item['key'] for item in batch)}")
            text = (f"All scenes and persons of the adventure:\n{outline_text(scenes, people)}\n\n"
                    f"Write the notes of these {kind}: {', '.join(item['key'] for item in batch)}.")
            try:
                answer = ask(file, with_instructions(f"{notes_prompt(detail)}\n\n{stat_block()}"), text, NOTES_SCHEMA)
            except ImportFailed as e:
                note(f"Notes {number} of {len(batches)} failed ({e}); these keep their summary", "warning")
                continue  # these scenes and persons keep their summary
            for item in answer.get("scenes") or []:
                if isinstance(item, dict) and isinstance(item.get("markdown"), str):
                    notes[str(item.get("key"))] = item["markdown"]
        stage("Building the adventure")
        adventure = build(outline, notes, owner)
        note(f"Built the adventure with {len(adventure['blocks'])} blocks, {len(notes)} of {len(scenes) + len(people)} with notes")
        return adventure
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


def start(pdf: bytes, name: str, user: str, store, detail: str | None = None) -> dict:
    """Starts an import in the background; `store(adventure)` saves the result and returns its id. One import per user at a time."""
    with _lock:
        _forget_old()
        if any(job["user"] == user and job["status"] == "running" for job in _jobs.values()):
            raise ImportFailed(_("An import is already running"))
        job = {"id": uuid.uuid4().hex, "user": user, "name": name, "status": "running", "step": 0, "total": 1, "adventure": None,
               "error": None, "started": time.time(), "finished": 0.0, "stage": _("Starting"), "stage_key": "Starting", "stage_args": [], "log": [], "cancel": threading.Event()}
        _jobs[job["id"]] = job

    def progress(step: int, total: int):
        job["step"], job["total"] = step, total

    def run():
        _local.job = job
        try:
            adventure = convert(pdf, name, user, progress, detail)
            check_cancelled()  # nothing is stored after a cancel
            stage("Saving the adventure")
            job["adventure"] = store(adventure)
            job["status"] = "done"
            stage("Done")
            note("The adventure is stored")
        except Cancelled:
            note("The import was cancelled")  # the status and the stage were set by the cancel
        except Exception as e:  # reported to the client
            logger.exception("Import of %s failed", name)
            job["status"], job["error"] = "error", str(e) or type(e).__name__
            stage("Failed")
            note(f"The import failed: {job['error']}", "error")
        finally:
            job["finished"] = job["finished"] or time.time()
            _local.job = None

    threading.Thread(target=run, name=f"adventure-import-{job['id'][:8]}", daemon=True).start()
    return view(job)


def view(job: dict) -> dict:
    return {**{key: job[key] for key in ("id", "name", "status", "step", "total", "adventure", "error", "stage", "started", "finished")},
            "stageKey": job["stage_key"], "stageArgs": list(job["stage_args"]), "log": list(job["log"])}


def list_jobs(user: str) -> list[dict]:
    """The imports of a user, running and finished (the newest first), so a client that was closed in between finds them again."""
    with _lock:
        _forget_old()
        return [view(job) for job in sorted(_jobs.values(), key=lambda item: item["started"], reverse=True) if job["user"] == user]


def cancel(job_id: str, user: str) -> bool | None:
    """Cancels a running import: it is cancelled at once for the user (it can be dismissed and another one can be started); its thread ends at
    its next request or pause and stores nothing. None when there is no such import, False when it is not running."""
    with _lock:
        job = _jobs.get(job_id)
        if job is None or job["user"] != user:
            return None
        if job["status"] != "running":
            return False
        job["cancel"].set()
        job["status"], job["finished"] = "cancelled", time.time()
        _set_stage(job, "Cancelled")
        _write(job, "The import was cancelled by the user", "warning")
        return True


def dismiss(job_id: str, user: str) -> bool | None:
    """Removes a finished import from the list; None when there is no such import, False while it is still running."""
    with _lock:
        job = _jobs.get(job_id)
        if job is None or job["user"] != user:
            return None
        if job["status"] == "running":
            return False
        del _jobs[job_id]
        return True


def status(job_id: str, user: str) -> dict | None:
    job = _jobs.get(job_id)
    return view(job) if job and job["user"] == user else None
