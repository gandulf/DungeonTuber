"""The smart search of the AI assistant: the model translates a scene into the filter of the app (the mood categories, tags, genres
and BPM), and the songs of the library are ranked by it (core/scoring.py, web/src/lib/scoring.ts). Only songs that exist are found:
the model never names songs, it only picks values, and the response schema allows only the values the app knows.
"""
from core.settings import CATEGORY_MAX, CATEGORY_MIN, MusicCategory, get_music_categories

MAX_VALUES = 300
BPM_RANGE = (40, 220)

PROMPT = """You are a precise music analysis assistant for Pen-and-Paper sessions such as The Dark Eye (Das Schwarze Auge, DSA).
Your sole task is to translate a scene description (in any language) into the filter of a music library, which then ranks its songs.

## RULES
1. Use integer values from {min} to {max} for the categories.
2. Set only the categories that really matter for the scene (usually 3 to 6); leave out the others, they then do not count.
3. Tags and genres are hard requirements: every tag or genre that a song lacks ranks it far down. Choose at most 2 tags and 1 genre,
   and only when the scene clearly calls for them; often none is best.
4. Set a BPM only when the tempo matters for the scene (e.g. 60 for a slow funeral, 150 for a hectic chase); otherwise leave it out.
5. Use only the keys, tags and genres listed below.
6. "message" is one short sentence for the user that explains the choice, in the language the user writes in.
7. On a follow-up (e.g. "darker", "more calm") change the previous filter accordingly.

## CATEGORIES (key: description; levels)
{categories}

## TAGS OF THE LIBRARY
{tags}

## GENRES OF THE LIBRARY
{genres}"""


def _category_line(category: MusicCategory) -> str:
    levels = "; ".join(f"{level}: {text}" for level, text in sorted(category.levels.items(), key=lambda item: int(item[0])))
    return f"- {category.key} ({category.name}): {category.description}" + (f" [{levels}]" if levels else "")


def _clean(values: list[str] | None) -> list[str]:
    seen, result = set(), []
    for value in values or []:
        value = str(value).strip()
        if value and value.lower() not in seen:
            seen.add(value.lower())
            result.append(value)
    return result[:MAX_VALUES]


def prompt(tags: list[str], genres: list[str]) -> str:
    return PROMPT.format(min=CATEGORY_MIN, max=CATEGORY_MAX, categories="\n".join(_category_line(c) for c in get_music_categories()),
                         tags=", ".join(_clean(tags)) or "(none)", genres=", ".join(_clean(genres)) or "(none)")


def schema(tags: list[str], genres: list[str]) -> dict:
    """The answer Gemini has to give; enums keep it to the values the app knows."""
    keys = [category.key for category in get_music_categories()]
    properties = {
        "message": {"type": "STRING"},
        "categories": {"type": "ARRAY", "items": {
            "type": "OBJECT",
            "properties": {"key": {"type": "STRING", "enum": keys}, "value": {"type": "INTEGER"}},
            "required": ["key", "value"],
        }},
        "bpm": {"type": "INTEGER", "nullable": True},
    }
    if _clean(tags):
        properties["tags"] = {"type": "ARRAY", "items": {"type": "STRING", "enum": _clean(tags)}}
    if _clean(genres):
        properties["genres"] = {"type": "ARRAY", "items": {"type": "STRING", "enum": _clean(genres)}}
    return {"type": "OBJECT", "properties": properties, "required": ["message", "categories"]}


def _pick(values: object, allowed: list[str], limit: int) -> list[str]:
    """The values that the library knows, in its spelling."""
    known = {value.lower(): value for value in _clean(allowed)}
    picked = []
    for value in values if isinstance(values, list) else []:
        match = known.get(str(value).strip().lower())
        if match and match not in picked:
            picked.append(match)
    return picked[:limit]


def to_filter(parsed: dict, tags: list[str], genres: list[str]) -> dict:
    """The filter of the app from the answer, checked against the categories, tags and genres the app knows."""
    keys = {category.key for category in get_music_categories()}
    categories = {}
    for entry in parsed.get("categories") or []:
        if not isinstance(entry, dict) or entry.get("key") not in keys:
            continue
        try:
            categories[entry["key"]] = max(CATEGORY_MIN, min(CATEGORY_MAX, round(float(entry["value"]))))
        except (TypeError, ValueError, KeyError):
            continue
    bpm = parsed.get("bpm")
    try:
        bpm = round(float(bpm)) if bpm is not None else None
    except (TypeError, ValueError):
        bpm = None
    if bpm is not None and not BPM_RANGE[0] <= bpm <= BPM_RANGE[1]:
        bpm = None
    return {"categories": categories, "tags": _pick(parsed.get("tags"), tags, 2), "genres": _pick(parsed.get("genres"), genres, 1), "bpm": bpm}
