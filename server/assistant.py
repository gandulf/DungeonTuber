"""AI assistant through the Gemini API of Google (aistudio.google.com) and Groq (console.groq.com). "music" suggests songs for a scene of a
role playing session, "general" answers questions of the game master (rules like those of DSA, the setting, ideas), "smart" turns a
scene into the filter of the app so that the songs of the library are ranked by it (see server/smartsearch.py), "compose" writes the
description of a new piece that the music generation composes (see server/musicgen.py), "effects" the description of a sound
effect, an ambience or background music for the sound generation (see server/soundgen.py), "story" helps with the blocks of an adventure:
it drafts their notes and chooses a light for them.

The smart search, the compose and the effects mode run on Groq when a Groq key is stored (an open model like gpt-oss-120b is as good at choosing
values as Gemini and has a quota of its own); the song suggestions and the general chat need the knowledge of Gemini.

The SuperAdmin stores the API keys in the settings; they are never sent back to the browser. The client keeps the conversation
and sends it with every request, so the server stays stateless.
"""
import json
import logging
import re
import urllib.error
import urllib.request
from urllib.parse import quote

from core.i18n import _
from core.settings import AppSettings, SettingKeys
from server import smartsearch
from server.config import setting_or_env

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

GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_DEFAULT_MODEL = "openai/gpt-oss-120b"
# models with structured outputs (console.groq.com/docs/structured-outputs)
GROQ_MODELS = [
    {"id": "openai/gpt-oss-120b", "name": "GPT-OSS 120B"},
    {"id": "openai/gpt-oss-20b", "name": "GPT-OSS 20B"},
]
GROQ_MODES = ("smart", "compose", "effects", "story")
USER_AGENT = "DungeonTuber (+https://github.com/gandulf/DungeonTuber)"
SONG_COUNT = 10
TIMEOUT = 60
MAX_MESSAGES = 30
MAX_MESSAGE_LENGTH = 4000
MAX_INSTRUCTIONS_LENGTH = 4000

SYSTEM_PROMPT = """Answer with a JSON object only:
{"message": "<one or two short sentences for the user>", "songs": [{"title": "<song title>", "artist": "<artist or composer>"}]}
Write the message in the language the user writes in."""

DEFAULT_MUSIC_INSTRUCTIONS = """Du bist der "Barde von Aventurien", ein Musik-Assistent für das Pen-&-Paper-System "Das Schwarze Auge" (DSA). Deine einzige Aufgabe: Passende Musik für Spielsitzungen vorschlagen.

## Regelfall & Ausgabe
Schlage bei jeder klaren Anfrage genau 10 Stücke vor, jeweils mit Titel und Interpret bzw. Soundtrack (OST).
Die Nachricht zur Auswahl besteht aus ein bis zwei kurzen Sätzen und endet exakt mit:
"Passt nichts? Schreibe 'Weitere 10' für neue Vorschläge oder beschreibe die Szene genauer."

## Auswahlkriterien & Halluzinationsschutz
- Nur real existierende Stücke und Komponisten verwenden.
- Nutze primär etablierte Fantasy-OSTs (Witcher, Skyrim, LotR, Kingdom Come, Gothic, Total War) und bekannte Pen-&-Paper-Künstler (Erdenstern, Adrian von Ziegler, BrunuhVille, Wardruna).
- **STRENGES VERBOT:** Erfinde keine generischen Titel. Wenn du den genauen Tracknamen nicht sicher weißt, gib stattdessen den Soundtrack-Namen an (z. B. "Skyrim OST – Exploration Theme").
- Passe Musik an Szene, Stimmung, Intensität und DSA-Region an.

## DSA-Kulturreferenzen
- **Thorwal:** Nordisch/Keltisch, Tagelharpa, Drums (Wardruna, Danheim).
- **Tulamidenlande/Khôm:** Orientalisch, Oud, Duduk (Prince of Persia OST).
- **Mittelreich:** High-Fantasy, Mittelalter-Folk (Erdenstern, Witcher 3).
- **Al'Anfa/Südmeer:** Düstere Renaissance, Barock, lateinamerikanische Percussion.
- **Elfen:** Ätherisch, Harfe, Flöte (LotR – Lothlórien).

## Spezialfälle
- **Unklare Anfrage** (z. B. "Musik für heute"): Stelle genau eine kurze Rückfrage zu Ort/Stimmung.
- **"Weitere 10" / "Mehr":** 10 neue Stücke zur selben Szene. Keine Wiederholungen. Stile/Quellen bewusst variieren."""

DEFAULT_SETTING_INSTRUCTIONS = """Wir spielen DSA in Aventurien. Thorwal: nordisch, Tagelharpa, Trommeln, Kehlgesang. Tulamidenlande/Khôm: orientalisch, Oud, Duduk, Darbuka. Mittelreich: Mittelalter-Folk, Laute, Fidel, Flöte. Al’Anfa/Südmeer: düstere Renaissance, Barock, lateinamerikanische Percussion. Elfen: ätherisch, Harfe, Flöte, Chor. Bevorzugt filmische, instrumentale Fantasy-Musik."""  # the smart search and the composing

GENERAL_PROMPT = """You are the assistant of the game master of a tabletop role playing session, for example Das Schwarze Auge (DSA).
Answer questions about the rules, the world and its lore, and help with ideas for the session: names, descriptions, plot hooks.
Answer concisely and to the point, so the answer can be read during the session; use Markdown for lists and emphasis.
When you are not sure about a rule or a fact, say so instead of inventing one.
Write in the language the user writes in."""

COMPOSE_PROMPT = """You write the description for an AI music generator (ACE-Step) that composes background music for a scene of a
tabletop role playing session.
Answer with a JSON object only:
{"message": "<one short sentence for the user>", "title": "<a short evocative title>", "caption": "<the description>",
 "lyrics": "<lyrics or empty>", "language": "<ISO 639-1 code of the lyrics, e.g. de or en>", "bpm": <tempo>}
The caption is ALWAYS in English, also when the user and the instructions below write in another language: the generator only
understands English captions. Write it as 6 to 12 concrete, comma separated terms, at most 400 characters, in this order:
1. One main genre, at most one modifier or influence (e.g. "medieval folk dance", "dark orchestral, celtic influence"); never several
   genres that do not belong together.
2. The mood: one or two words that agree ("joyful, rowdy"), never opposites like "joyful" and "melancholic" or "serene" and "aggressive".
3. The 2 to 3 specific real instruments that carry the piece, as precise as possible ("plucked lute" rather than "strings"; e.g.
   fiddle, bagpipe, frame drum, hurdy-gurdy, cello, french horn, taiko, harp, choir).
4. The voice if there is one ("rough male vocals", "ethereal female choir").
5. The rhythm feel in words ("driving", "laid-back", "slow and solemn"), never a number: the tempo is the bpm field alone, and
   key or BPM in the caption confuse the generator.
6. The production and the timbre: fidelity, space and texture ("warm live recording", "intimate", "wide hall reverb", "raw",
   "airy", "punchy").
For example: "medieval folk dance, joyful, rowdy, lively fiddle, plucked lute, frame drums and hand claps, driving, warm live
tavern recording".
Only concrete things the musicians can play: no sentences, no abstract adjectives like "sophisticated", "elegant" or "beautiful".
Prefer acoustic and orchestral instruments and a recorded production; words like ambient, pads, drones or synth make it sound
electronic, use them only when the scene asks for it.
bpm matches the genre and the mood: about 55 to 80 for laments, funerals and suspense, 80 to 110 for exploration and travel, 110 to
140 for dances, chases and battles.
Only the title, the message and the lyrics are in the language the user writes in.
A style reference to one or two artists, composers or soundtracks helps the generator, as one term of the caption ("reminiscent of
Wardruna", "in the style of the Witcher 3 soundtrack"); it describes the sound, so the lyrics never quote or copy existing songs.
When the user asks for changes, change the previous description accordingly.
"""
INSTRUMENTAL_RULE = """The piece is instrumental: the caption names no voice and starts with the word "instrumental" (e.g.
"instrumental, medieval folk dance, …"). lyrics holds no words to sing, only the structure of the piece over time: 4 to 6 section
tags on their own lines, separated by blank lines, each with at most one modifier that names the instruments of the caption or the
energy, e.g.
[Intro - solo harp]

[Main Theme - fiddle and lute]

[Build - frame drums]

[Climax - full ensemble]

[Outro - fade out]"""
VOCALS_RULE = """The piece has vocals: lyrics is never empty. Write them in the language the user writes in, with simple, natural words
that are easy to sing (no tongue twisters, no long sentences) and the same mood as the caption.
Structure: section tags on their own lines and a blank line between sections. Start with an [Intro] and end with an [Outro] without
words (the scene needs room), then [Verse], a [Chorus] that repeats as the hook at least twice, an instrumental break between
sections and maybe a [Bridge]. Every sung section has words below its tag (a [Chorus] without words stays silent).
A tag may have one modifier for how it is played or sung: [Chorus - anthemic], [Verse - whispered], [Intro - lute]. Name
instrumental breaks after the instruments of the caption ([Fiddle Solo], [Instrumental - drums]); tags and caption never disagree.
Lines of 6 to 10 syllables, lines at the same place of each section about equally long. One core image for the whole song instead
of a new metaphor in every section, no stacked adjectives, a consistent rhyme (AABB or ABAB). UPPERCASE marks a shouted line, use it
rarely; (parentheses) mark background voices or a choir echo.
Name the voice in the caption (for example "rough male vocals" or "ethereal female choir") and the instruments that carry it, so the
voice does not drown them."""
# sung words per second: about 2 to 3 is the limit (more sounds rushed); background music needs room for the instruments
EFFECTS_PROMPT = """You write the description for an AI sound generator (Stable Audio 3) that creates sound effects, ambiences and
instrumental background music for a scene of a tabletop role playing session; the game master layers them under the music.
Answer with a JSON object only:
{"message": "<one short sentence for the user>", "title": "<a short name for the sound, e.g. Rain on the tent>",
 "caption": "<the description>", "duration": <seconds>}
The caption is ALWAYS in English, also when the user and the instructions below write in another language: the generator only
understands English. It learned from the descriptions of Freesound and AudioSparx, so describe the sound the way they do, in one to
three plain sentences or comma separated terms, at most 400 characters:
- A sound effect: the source (exactly what object, creature or material makes the sound), the action (how it is triggered and how it
  ends, e.g. "slamming shut with a fast decay") and the recording (close mic, dry room, stone hall reverb, distance).
  Example: "A heavy oak door slamming shut in a stone hall, deep wooden thud with a short metallic rattle of the latch, natural reverb".
- An ambience: the place and 3 to 5 layered sources from near to far, steady and without a melody, e.g. "Field recording of a night
  forest, crickets and rustling leaves close by, a distant owl, light wind in the trees, calm and continuous".
- Background music: the genre, 2 or 3 real instruments and how they are played, the mood and the tempo, e.g. "A sombre medieval folk
  piece, solo lute with delicate finger picking, low hurdy-gurdy drone, cavernous reverb, 70 BPM". No voices: the generator cannot sing.
Only things that can be heard: no story, no names of persons or places, no abstract words like "epic" or "beautiful" alone.
duration fits the sound: 1 to 5 seconds for single effects (a door, a sword hit, a spell), 5 to 20 for short sequences (a fight,
a collapsing tunnel), 30 to 120 for ambiences and loops, 60 to 180 for music.
Only the title and the message are in the language the user writes in.
When the user asks for changes, change the previous description accordingly.
"""
STORY_DRAFT_PROMPT = """You help the game master of a tabletop role playing session write the notes of one scene (a block) of an adventure.
Answer with a JSON object only:
{"message": "<one short sentence for the user>", "text": "<the notes in Markdown>"}
The notes are read during play: start with a short read-aloud description of the scene (two to four vivid sentences that name what the
players see, hear and smell), followed by short bullet points for the game master: who is there, what they want, secrets, what the
players can find out or try, and what happens next. Keep every name, place and fact the user gave and do not invent a different plot.
Use plain Markdown only (**bold**, lists, > quotes, no heading above ##), no tables and no HTML.
Write in the language of the user's notes. When the user asks for changes, change the previous text accordingly."""
STORY_LIGHT_PROMPT = """You choose the colored light for a scene of a tabletop role playing session; smart bulbs light the table with it.
Answer with a JSON object only:
{"message": "<one short sentence for the user>", "scene": "<a scene of the list or null>", "color": "<#RRGGBB or null>",
 "temperature": <kelvin or null>, "brightness": <10 to 255>}
Set exactly one of scene, color and temperature, the others are null. Take a scene of the list below when one fits the mood (a fire, an
ocean, a forest); otherwise a color that carries the mood (deep red for danger, cold blue for a crypt, warm amber for a tavern), or a
temperature from 2200 (candle light) to 6500 (cold daylight) for neutral places. Dark scenes are dim (30 to 90), bright ones full
(180 to 255). Write the message in the language of the user.

## SCENES OF THE BULBS
{scenes}"""
EFFECT_KINDS = {
    "sfx": "The user wants a sound effect.",
    "ambience": "The user wants an ambience: a steady background of the place that can be looped.",
    "music": "The user wants instrumental background music.",
}

LYRICS_WORDS_PER_SECOND = (1.2, 1.8)


# English names of the languages the lyrics may be written in, for the prompt (the code itself also works)
LANGUAGE_NAMES = {"de": "German", "en": "English", "fr": "French", "es": "Spanish", "it": "Italian", "nl": "Dutch", "pl": "Polish",
                  "pt": "Portuguese", "ru": "Russian", "cs": "Czech", "sv": "Swedish", "da": "Danish", "no": "Norwegian", "fi": "Finnish",
                  "ja": "Japanese", "zh": "Chinese", "ko": "Korean", "la": "Latin"}


def lyrics_language(language: object) -> str:
    """The rule for the language of the lyrics that the user chose; empty without a valid choice."""
    code = str(language or "").strip().lower()
    if not re.fullmatch(r"[a-z]{2,3}", code):
        return ""
    return (f"Write the lyrics in {LANGUAGE_NAMES.get(code, code)} and set language to {code}, whatever language the user writes in "
            "(this replaces the rule about the language of the lyrics above).")


def lyrics_budget(duration: object) -> str:
    """The length of the lyrics for a piece of `duration` seconds, as a rule for the compose prompt."""
    if not isinstance(duration, (int, float)) or duration <= 0:
        return ""
    low, high = (round(duration * rate / 10) * 10 for rate in LYRICS_WORDS_PER_SECOND)
    return f"The piece is {round(duration)} seconds long: write {max(low, 20)} to {max(high, 30)} words of lyrics in total, not more."
MAX_CAPTION_LENGTH = 512
MAX_STORY_TEXT = 6000
STORY_TASKS = ("draft", "light")

STORY_DRAFT_SCHEMA = {
    "type": "OBJECT",
    "properties": {"message": {"type": "STRING"}, "text": {"type": "STRING"}},
    "required": ["message", "text"],
}

STORY_LIGHT_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "message": {"type": "STRING"},
        "scene": {"type": "STRING", "nullable": True},
        "color": {"type": "STRING", "nullable": True},
        "temperature": {"type": "INTEGER", "nullable": True},
        "brightness": {"type": "INTEGER"},
    },
    "required": ["message", "brightness"],
}


def story_task(context: dict | None) -> str:
    task = (context or {}).get("task")
    return task if task in STORY_TASKS else "draft"


def _story_scenes(context: dict | None) -> list[str]:
    return [str(scene).strip() for scene in (context or {}).get("scenes") or [] if str(scene).strip()][:200]


def to_story_light(raw: dict, scenes: list[str]) -> dict | None:
    """The light of a story answer, checked: a scene of the bulbs, a #RRGGBB color or a temperature (kelvin), with a brightness of 10 to 255;
    None when the model chose nothing usable."""
    try:
        brightness = max(10, min(255, round(float(raw.get("brightness") if raw.get("brightness") is not None else 255))))
    except (TypeError, ValueError):
        brightness = 255
    known = {scene.lower(): scene for scene in scenes}
    scene = known.get(str(raw.get("scene") or "").strip().lower())
    color = str(raw.get("color") or "").strip()
    try:
        temperature = round(float(raw.get("temperature"))) if raw.get("temperature") is not None else None
    except (TypeError, ValueError):
        temperature = None
    light = {"scene": None, "brightness": brightness, "temperature": None, "color": None}
    if scene:
        light["scene"] = scene
    elif re.fullmatch(r"#[0-9a-fA-F]{6}", color):
        light["color"] = color.lower()
    elif temperature is not None and 2200 <= temperature <= 6500:
        light["temperature"] = temperature
    else:
        return None
    return light
MAX_LYRICS_LENGTH = 4096

COMPOSE_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "message": {"type": "STRING"},
        "title": {"type": "STRING"},
        "caption": {"type": "STRING"},
        "lyrics": {"type": "STRING"},
        "language": {"type": "STRING"},
        "bpm": {"type": "INTEGER"},
    },
    "required": ["message", "title", "caption", "lyrics"],
}

EFFECTS_SCHEMA = {
    "type": "OBJECT",
    "properties": {
        "message": {"type": "STRING"},
        "title": {"type": "STRING"},
        "caption": {"type": "STRING"},
        "duration": {"type": "INTEGER"},
    },
    "required": ["message", "title", "caption"],
}
MAX_SOUND_SECONDS = 380

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


# keys and models from the environment (e.g. Docker secrets); a value stored in the settings wins
GEMINI_KEY_ENV, GEMINI_MODEL_ENV = "DT_GEMINI_API_KEY", "DT_GEMINI_MODEL"
GROQ_KEY_ENV, GROQ_MODEL_ENV = "DT_GROQ_API_KEY", "DT_GROQ_MODEL"


def api_key() -> str:
    return setting_or_env(SettingKeys.ASSISTANT_API_KEY, GEMINI_KEY_ENV)[0]


def model() -> str:
    return setting_or_env(SettingKeys.ASSISTANT_MODEL, GEMINI_MODEL_ENV)[0] or DEFAULT_MODEL


def groq_key() -> str:
    return setting_or_env(SettingKeys.GROQ_API_KEY, GROQ_KEY_ENV)[0]


def groq_model() -> str:
    return setting_or_env(SettingKeys.GROQ_MODEL, GROQ_MODEL_ENV)[0] or GROQ_DEFAULT_MODEL


def provider(mode: str) -> str | None:
    """The service that answers in `mode`: Groq for the smart search and the compose mode when it has a key, otherwise Gemini."""
    if mode in GROQ_MODES and groq_key():
        return "groq"
    return "gemini" if api_key() else None


_INSTRUCTION_KEYS = {"general": SettingKeys.ASSISTANT_GENERAL_INSTRUCTIONS, "story": SettingKeys.ASSISTANT_GENERAL_INSTRUCTIONS, "compose": SettingKeys.ASSISTANT_COMPOSE_INSTRUCTIONS,
                     "smart": SettingKeys.ASSISTANT_SMART_INSTRUCTIONS, "effects": SettingKeys.ASSISTANT_EFFECTS_INSTRUCTIONS}

PROMPTS = {
    "music.system": SYSTEM_PROMPT,
    "smart.system": smartsearch.PROMPT,
    "compose.system": COMPOSE_PROMPT,
    "compose.instrumental": INSTRUMENTAL_RULE,
    "compose.vocals": VOCALS_RULE,
    "effects.system": EFFECTS_PROMPT,
    "general.system": GENERAL_PROMPT,
    "story.draft": STORY_DRAFT_PROMPT,
    "story.light": STORY_LIGHT_PROMPT,
}
MAX_PROMPT_LENGTH = 12000


def _stored_prompts() -> dict:
    stored = AppSettings.value(SettingKeys.ASSISTANT_PROMPTS, {}, type=dict) or {}
    return stored if isinstance(stored, dict) else {}


def prompt_text(name: str) -> str:
    """The prompt `name` as the SuperAdmin changed it, otherwise the built-in one."""
    stored = _stored_prompts().get(name)
    return stored if isinstance(stored, str) and stored.strip() else PROMPTS[name]


def prompts() -> list[dict]:
    """Every built-in prompt with its default and the text in use."""
    return [{"name": name, "default": default, "value": prompt_text(name)} for name, default in PROMPTS.items()]


def set_prompts(changes: dict[str, str]):
    """Stores the changed prompts; a text that is empty or the default restores the built-in prompt. Unknown names are ignored."""
    stored = {name: text for name, text in _stored_prompts().items() if name in PROMPTS}
    for name, text in changes.items():
        if name not in PROMPTS:
            continue
        text = str(text or "").strip()[:MAX_PROMPT_LENGTH]
        if not text or text == PROMPTS[name].strip():
            stored.pop(name, None)
        else:
            stored[name] = text
    if stored:
        AppSettings.setValue(SettingKeys.ASSISTANT_PROMPTS, stored)
    else:
        AppSettings.remove(SettingKeys.ASSISTANT_PROMPTS)


def default_instructions(mode: str) -> str | None:
    """The instructions a mode has until they are changed (the song suggestions, the smart search and the composing), None for the others."""
    return {"music": DEFAULT_MUSIC_INSTRUCTIONS, "smart": DEFAULT_SETTING_INSTRUCTIONS, "compose": DEFAULT_SETTING_INSTRUCTIONS}.get(mode, "").strip() or None


def instructions(mode: str = "music") -> str:
    """The additional instructions the SuperAdmin stored for a mode, or the default of the mode (see default_instructions) while nothing is stored."""
    key = _INSTRUCTION_KEYS.get(mode, SettingKeys.ASSISTANT_INSTRUCTIONS)
    return (AppSettings.value(key, "", type=str) or "").strip() or default_instructions(mode) or ""


def system_prompt(mode: str = "music", context: dict | None = None) -> str:
    extra, intro = instructions(mode), "Additional instructions of the game master:"
    if mode == "smart":
        base = smartsearch.prompt((context or {}).get("tags") or [], (context or {}).get("genres") or [], prompt_text("smart.system"))
    elif mode == "compose":
        instrumental = (context or {}).get("instrumental", True)
        base = prompt_text("compose.system") + "\n" + prompt_text("compose.instrumental" if instrumental else "compose.vocals")
        rules = [] if instrumental else [lyrics_budget((context or {}).get("duration")), lyrics_language((context or {}).get("language"))]
        base += "".join(f"\n{rule}" for rule in rules if rule)
    elif mode == "effects":
        base = prompt_text("effects.system") + "\n" + EFFECT_KINDS[effect_kind((context or {}).get("kind"))]
    elif mode == "story":
        task = story_task(context)
        base = prompt_text(f"story.{task}")
        if task == "light":
            base = base.replace("{scenes}", ", ".join(_story_scenes(context)) or "(none)")
    else:
        base = prompt_text("general.system" if mode == "general" else "music.system")
    return f"{base}\n\n{intro}\n{extra}" if extra else base


def configured(mode: str | None = None) -> bool:
    """Gemini has a key; with a mode: a service that answers in this mode has a key."""
    return bool(api_key()) if mode is None else provider(mode) is not None


def groq_configured() -> bool:
    return bool(groq_key())


def _hint(key: str) -> str:
    return key[-4:] if len(key) > 8 else ""


def status() -> dict:
    key, groq = api_key(), groq_key()
    return {"configured": bool(key), "model": model(), "defaultModel": DEFAULT_MODEL, "keyHint": _hint(key),
            "keySource": setting_or_env(SettingKeys.ASSISTANT_API_KEY, GEMINI_KEY_ENV)[1],
            "groqKeySource": setting_or_env(SettingKeys.GROQ_API_KEY, GROQ_KEY_ENV)[1],
            "instructions": instructions(), "defaultInstructions": {mode: default_instructions(mode) for mode in ("music", "smart", "compose")},
            "generalInstructions": instructions("general"), "composeInstructions": instructions("compose"),
            "smartInstructions": instructions("smart"), "effectsInstructions": instructions("effects"),
            "groqConfigured": bool(groq), "groqModel": groq_model(), "groqDefaultModel": GROQ_DEFAULT_MODEL, "groqKeyHint": _hint(groq),
            "groqModels": GROQ_MODELS, "prompts": prompts()}


def _store(key_setting: str, model_setting: str, default_model: str, key: str | None, model_name: str | None):
    """Stores a key ('' removes it) and a model ('' for the default); None keeps the stored value."""
    if key is not None:
        if key.strip():
            AppSettings.setValue(key_setting, key.strip())
        else:
            AppSettings.remove(key_setting)
    if model_name is not None:
        if model_name.strip() and model_name.strip() != default_model:
            AppSettings.setValue(model_setting, model_name.strip())
        else:
            AppSettings.remove(model_setting)


def configure(key: str | None, model_name: str | None, extra_instructions: str | None = None, general_instructions: str | None = None,
              groq_api_key: str | None = None, groq_model_name: str | None = None, compose_instructions: str | None = None,
              smart_instructions: str | None = None, changed_prompts: dict[str, str] | None = None,
              effects_instructions: str | None = None):
    """Stores the keys and models of Gemini and Groq and the additional instructions of the modes; None keeps the stored value."""
    for legacy in _LEGACY_KEYS:
        AppSettings.remove(legacy)
    _store(SettingKeys.ASSISTANT_API_KEY, SettingKeys.ASSISTANT_MODEL, DEFAULT_MODEL, key, model_name)
    _store(SettingKeys.GROQ_API_KEY, SettingKeys.GROQ_MODEL, GROQ_DEFAULT_MODEL, groq_api_key, groq_model_name)
    if changed_prompts is not None:
        set_prompts(changed_prompts)
    for mode, setting, value in (("music", SettingKeys.ASSISTANT_INSTRUCTIONS, extra_instructions),
                                 ("general", SettingKeys.ASSISTANT_GENERAL_INSTRUCTIONS, general_instructions),
                                 ("compose", SettingKeys.ASSISTANT_COMPOSE_INSTRUCTIONS, compose_instructions),
                                 ("smart", SettingKeys.ASSISTANT_SMART_INSTRUCTIONS, smart_instructions),
                                 ("effects", SettingKeys.ASSISTANT_EFFECTS_INSTRUCTIONS, effects_instructions)):
        if value is None:
            continue
        default = default_instructions(mode)
        if value.strip() and value.strip() != default:
            AppSettings.setValue(setting, value.strip()[:MAX_INSTRUCTIONS_LENGTH])
        else:
            AppSettings.remove(setting)  # empty or the default text itself: the default (or nothing, for the modes without one)


def remove(service: str = "gemini"):
    if service == "groq":
        AppSettings.remove(SettingKeys.GROQ_API_KEY)
        AppSettings.remove(SettingKeys.GROQ_MODEL)
    else:
        AppSettings.remove(SettingKeys.ASSISTANT_API_KEY)
        AppSettings.remove(SettingKeys.ASSISTANT_MODEL)


def _post(payload: dict) -> dict:
    request = urllib.request.Request(API_URL.format(model=quote(model(), safe="")), data=json.dumps(payload).encode("utf-8"),
                                     method="POST", headers={"Content-Type": "application/json"})
    return _send(request)


def _send(request: urllib.request.Request, service: str = "gemini") -> dict:
    key = groq_key() if service == "groq" else api_key()
    if not key:
        raise AssistantError(_("The AI assistant is not configured"))
    if service == "groq":
        request.add_header("Authorization", f"Bearer {key}")
        # Cloudflare in front of Groq blocks the default agent of urllib (403, "error code: 1010")
        request.add_header("User-Agent", USER_AGENT)
    else:
        request.add_header("x-goog-api-key", key)
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as e:
        body = _error_body(e)
        error = body.get("error") if isinstance(body, dict) and isinstance(body.get("error"), dict) else {}
        # Groq rejects an answer that does not match the schema; the answer itself is checked here anyway
        if service == "groq" and error.get("code") == "json_validate_failed" and error.get("failed_generation"):
            logger.warning("Groq answered with invalid JSON, using it anyway: {0}", str(error["failed_generation"])[:200])
            return {"choices": [{"message": {"content": str(error["failed_generation"])}}]}
        detail = _detail(e, body)
        if e.code in (401, 403) or (e.code == 400 and "API key" in detail):
            raise AssistantError(_("The AI service rejected the API key ({0})").format(detail)) from e
        if e.code == 429:
            raise AssistantError(_("The AI service is busy, please try again in a moment ({0})").format(detail)) from e
        raise AssistantError(_("The AI service failed ({0}): {1}").format(e.code, detail)) from e
    except (urllib.error.URLError, TimeoutError, ValueError) as e:
        raise AssistantError(_("The AI service is not reachable: {0}").format(e)) from e


def _error_body(error: urllib.error.HTTPError) -> dict | str:
    """The error answer: its JSON, or its text (e.g. of a proxy)."""
    try:
        body = error.read()
    except (OSError, AttributeError):
        return ""
    try:
        return json.loads(body)
    except ValueError:
        return body.decode("utf-8", "replace").strip()[:200] if isinstance(body, bytes) else ""


def _detail(error: urllib.error.HTTPError, body: dict | str | None = None) -> str:
    """The message of the error answer; a plain text answer as it is."""
    body = _error_body(error) if body is None else body
    if isinstance(body, dict):
        message = body.get("error", {}).get("message") if isinstance(body.get("error"), dict) else None
        return str(message or error.reason)
    return f"{error.reason}: {body}" if body else str(error.reason)


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


_SECTION_TAG = re.compile(r"\[[^\]\n]{1,60}\]")


def structure_only(lyrics: str) -> bool:
    """True if the lyrics only hold section tags (the structure of an instrumental piece), no words to sing."""
    lines = [line.strip() for line in lyrics.splitlines() if line.strip()]
    return bool(lines) and all(_SECTION_TAG.fullmatch(line) for line in lines)


def to_piece(raw: dict, instrumental: bool = True) -> dict | None:
    """The piece of a compose answer, cut to what ACE-Step accepts; None without a caption."""
    caption = " ".join(str(raw.get("caption") or "").split())[:MAX_CAPTION_LENGTH]
    if not caption:
        return None
    bpm = raw.get("bpm")
    language = str(raw.get("language") or "").strip().lower()
    lyrics = str(raw.get("lyrics") or "").strip()[:MAX_LYRICS_LENGTH]
    if instrumental and not structure_only(lyrics):
        lyrics = ""  # an instrumental piece keeps its structure, but no words to sing
    return {"title": " ".join(str(raw.get("title") or "").split())[:120] or caption[:60],
            "caption": caption,
            "lyrics": lyrics,
            "language": "" if instrumental or not re.fullmatch(r"[a-z]{2,3}", language) else language,
            "instrumental": instrumental,
            "bpm": bpm if isinstance(bpm, int) and 30 <= bpm <= 300 else None}


def effect_kind(kind: object) -> str:
    """The kind of sound of the effects mode: sfx, ambience or music (sfx for anything else)."""
    return kind if isinstance(kind, str) and kind in EFFECT_KINDS else "sfx"


def to_sound(raw: dict, kind: object = "sfx") -> dict | None:
    """The sound of an effects answer, cut to what Stable Audio accepts; None without a caption."""
    caption = " ".join(str(raw.get("caption") or "").split())[:MAX_CAPTION_LENGTH]
    if not caption:
        return None
    duration = raw.get("duration")
    return {"title": " ".join(str(raw.get("title") or "").split())[:120] or caption[:60],
            "caption": caption,
            "kind": effect_kind(kind),
            "duration": duration if isinstance(duration, int) and 1 <= duration <= MAX_SOUND_SECONDS else None}


def json_schema(schema: dict, enums: bool = True, strict: bool = False, nullable: bool = False) -> dict:
    """The Gemini schema (OBJECT, STRING, nullable) as JSON schema for Groq; without enums the lists of tags and genres are not sent
    twice (the prompt has them, and the answer is checked against them anyway). For the strict mode of Groq every property is
    required, an optional one may be null, and objects allow no other properties."""
    result = {}
    kind = str(schema.get("type", "")).lower()
    if kind:
        result["type"] = [kind, "null"] if schema.get("nullable") or nullable else kind
    if enums and "enum" in schema:
        result["enum"] = schema["enum"]
    if "properties" in schema:
        required = schema.get("required") or []
        result["properties"] = {name: json_schema(value, enums, strict, strict and name not in required)
                                for name, value in schema["properties"].items()}
        if strict:
            result["required"] = list(schema["properties"])
            result["additionalProperties"] = False
    if "items" in schema:
        result["items"] = json_schema(schema["items"], enums, strict)
    if "required" in schema and not strict:
        result["required"] = schema["required"]
    return result


def _gemini_content(system: str, messages: list[dict[str, str]], schema: dict | None) -> str:
    history = [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]} for m in messages]
    payload = {"systemInstruction": {"parts": [{"text": system}]}, "contents": history}
    if schema:
        payload["generationConfig"] = {"responseMimeType": "application/json", "responseSchema": schema}
    data = _post(payload)
    try:
        candidate = data["candidates"][0]
        # thoughts of thinking models are not part of the answer
        return "".join(part.get("text", "") for part in candidate["content"]["parts"] if not part.get("thought")).strip()
    except (KeyError, IndexError, TypeError, AttributeError) as e:
        reason = (data.get("promptFeedback") or {}).get("blockReason") if isinstance(data, dict) else None
        if reason:
            raise AssistantError(_("The AI service refused the question ({0})").format(reason)) from e
        raise AssistantError(_("The AI service sent an unexpected answer")) from e


def _groq_content(system: str, messages: list[dict[str, str]], schema: dict | None) -> str:
    payload = {"model": groq_model(), "messages": [{"role": "system", "content": system}, *messages],
               "reasoning_effort": "low"}  # choosing values needs little thinking, and the thoughts count against the token quota
    if schema:
        # strict: Groq generates only answers that match the schema (constrained decoding)
        payload["response_format"] = {"type": "json_schema", "json_schema": {"name": "answer", "strict": True,
                                                                             "schema": json_schema(schema, enums=False, strict=True)}}
    request = urllib.request.Request(GROQ_URL, data=json.dumps(payload).encode("utf-8"), method="POST",
                                     headers={"Content-Type": "application/json"})
    data = _send(request, "groq")
    try:
        return str(data["choices"][0]["message"]["content"] or "").strip()
    except (KeyError, IndexError, TypeError) as e:
        raise AssistantError(_("The AI service sent an unexpected answer")) from e


def chat(messages: list[dict[str, str]], mode: str = "music", context: dict | None = None) -> dict:
    """Sends the conversation (role user or assistant) and returns the message, the suggested songs and the raw answer.

    The raw answer goes back into the conversation as the assistant turn, so the model knows what it already suggested.
    The general mode answers in Markdown and suggests no songs. The smart mode returns a filter (categories, tags, genres, bpm)
    instead of songs; `context` holds the tags and genres it may choose from.
    """
    history = [{"role": m["role"], "content": m["content"][:MAX_MESSAGE_LENGTH]} for m in messages[-MAX_MESSAGES:]]
    tags, genres = (context or {}).get("tags") or [], (context or {}).get("genres") or []
    schema = {"smart": smartsearch.schema(tags, genres), "compose": COMPOSE_SCHEMA, "effects": EFFECTS_SCHEMA,
              "story": STORY_LIGHT_SCHEMA if story_task(context) == "light" else STORY_DRAFT_SCHEMA,
              "general": None}.get(mode, RESPONSE_SCHEMA)
    service = provider(mode)
    if service is None:
        raise AssistantError(_("The AI assistant is not configured"))
    content = (_groq_content if service == "groq" else _gemini_content)(system_prompt(mode, context), history, schema)
    if mode == "general":
        return {"message": content, "songs": [], "content": content}
    try:
        parsed = json.loads(content)
    except ValueError:
        logger.warning("The assistant answered without JSON: {0}", content[:200])
        parsed = {"message": content, "songs": []}
    if not isinstance(parsed, dict):
        parsed = {"songs": parsed}
    if mode == "smart":
        return {"message": str(parsed.get("message") or "").strip(), "songs": [], "content": content,
                "filter": smartsearch.to_filter(parsed, tags, genres)}
    if mode == "compose":
        instrumental = (context or {}).get("instrumental", True)
        piece = to_piece(parsed, instrumental) or to_piece({"caption": messages[-1]["content"]}, instrumental)
        chosen = str((context or {}).get("language") or "")
        if piece and not instrumental and chosen:
            piece["language"] = chosen  # the language the user chose, also when the model named another one
        return {"message": str(parsed.get("message") or "").strip(), "songs": [], "content": content, "piece": piece}
    if mode == "story":
        reply = {"message": str(parsed.get("message") or "").strip(), "songs": [], "content": content}
        if story_task(context) == "light":
            reply["light"] = to_story_light(parsed, _story_scenes(context))
        else:
            reply["text"] = str(parsed.get("text") or "").strip()[:MAX_STORY_TEXT]
        return reply
    if mode == "effects":
        kind = (context or {}).get("kind")
        sound = to_sound(parsed, kind) or to_sound({"caption": messages[-1]["content"]}, kind)
        return {"message": str(parsed.get("message") or "").strip(), "songs": [], "content": content, "sound": sound}
    return {"message": str(parsed.get("message") or "").strip(), "songs": _songs(parsed.get("songs")), "content": content}
