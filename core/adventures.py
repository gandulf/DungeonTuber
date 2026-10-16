"""Adventures: blocks of formatted notes with music, effects and lights, linked into a path (see docs/ADVENTURES_PLAN.md).

An adventure is a plain dict (JSON in a `.dtadv` file). `normalize` turns whatever a client sends into a valid one, so the stored
files never hold unknown fields, dangling links or oversized text.
"""
import time
import uuid

VERSION = 1
VISIBILITIES = ("private", "public")

MAX_BLOCKS = 500
MAX_LINKS = 2000
MAX_TEXT = 100_000
MAX_TITLE = 200
MAX_REFS = 100
MAX_IMAGES = 50
MAX_FIELD = 1000

LIGHT_FIELDS = {"scene": str, "brightness": int, "temperature": int, "color": str}


def new_id() -> str:
    return str(uuid.uuid4())


def _text(value: object, limit: int = MAX_FIELD) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _number(value: object, default: float = 0.0) -> float:
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else default


def normalize_music(raw: object) -> list[dict]:
    """Songs (by UFID, with the last known path) and playlists (by playlist id) a block plays."""
    result = []
    for item in raw[:MAX_REFS] if isinstance(raw, list) else []:
        if not isinstance(item, dict):
            continue
        kind = item.get("type")
        if kind == "song" and _text(item.get("ufid")):
            result.append({"type": "song", "ufid": _text(item["ufid"]), "path": _text(item.get("path")), "title": _text(item.get("title"))})
        elif kind == "playlist" and _text(item.get("id")):
            result.append({"type": "playlist", "id": _text(item["id"]), "path": _text(item.get("path")), "title": _text(item.get("title"))})
    return result


def normalize_effects(raw: object) -> list[dict]:
    """Sound effects of the effects folder: looped ambience or one-shots, optionally started when the block is entered."""
    result = []
    for item in raw[:MAX_REFS] if isinstance(raw, list) else []:
        if isinstance(item, dict) and _text(item.get("path")):
            result.append({"path": _text(item["path"]), "name": _text(item.get("name")), "loop": bool(item.get("loop", False)),
                           "autostart": bool(item.get("autostart", False))})
    return result


def normalize_light(raw: object) -> dict | None:
    if not isinstance(raw, dict):
        return None
    light = {}
    for key, kind in LIGHT_FIELDS.items():
        value = raw.get(key)
        if kind is int and isinstance(value, (int, float)) and not isinstance(value, bool):
            light[key] = int(value)
        elif kind is str and isinstance(value, str) and value:
            light[key] = value[:MAX_FIELD]
    return light or None


def normalize_block(raw: dict) -> dict:
    pos = raw.get("pos")
    return {
        "id": _text(raw.get("id"), 64) or new_id(),
        "title": _text(raw.get("title"), MAX_TITLE),
        "markdown": raw["markdown"][:MAX_TEXT] if isinstance(raw.get("markdown"), str) else "",
        "played": bool(raw.get("played", False)),
        "pos": [_number(pos[0]), _number(pos[1])] if isinstance(pos, list) and len(pos) == 2 else [0.0, 0.0],
        "autoplay": bool(raw.get("autoplay", True)),
        "music": normalize_music(raw.get("music")),
        "effects": normalize_effects(raw.get("effects")),
        "light": normalize_light(raw.get("light")),
        "images": [_text(image) for image in (raw.get("images") or [])[:MAX_IMAGES] if _text(image)] if isinstance(raw.get("images"), list) else [],
    }


def normalize(data: dict, owner: str | None = None, previous: dict | None = None) -> dict:
    """A valid adventure from client data. `previous` (the stored version) keeps what a client may not change: the id, the owner and the
    creation time."""
    previous = previous or {}
    blocks, seen = [], set()
    for raw in data.get("blocks", [])[:MAX_BLOCKS] if isinstance(data.get("blocks"), list) else []:
        if not isinstance(raw, dict):
            continue
        block = normalize_block(raw)
        if block["id"] not in seen:
            seen.add(block["id"])
            blocks.append(block)
    links, pairs = [], set()
    for raw in data.get("links", [])[:MAX_LINKS] if isinstance(data.get("links"), list) else []:
        if not isinstance(raw, dict):
            continue
        source, target, label = _text(raw.get("from"), 64), _text(raw.get("to"), 64), _text(raw.get("label"), MAX_TITLE) or None
        if source in seen and target in seen and source != target and (source, target, label) not in pairs:
            pairs.add((source, target, label))
            links.append({"from": source, "to": target, "label": label})
    visibility = data.get("visibility") if data.get("visibility") in VISIBILITIES else previous.get("visibility", "private")
    now = time.time()
    return {
        "version": VERSION,
        "id": previous.get("id") or _text(data.get("id"), 64) or new_id(),
        "title": _text(data.get("title"), MAX_TITLE) or previous.get("title") or "Adventure",
        "owner": previous.get("owner") or owner,
        "visibility": visibility,
        "created": previous.get("created") or now,
        "updated": now,
        "blocks": blocks,
        "links": links,
    }


def new_adventure(title: str, owner: str) -> dict:
    first = {"title": title, "markdown": "", "pos": [0, 0]}
    return normalize({"title": title, "blocks": [first]}, owner=owner)


def summary(adventure: dict) -> dict:
    """What the list of adventures shows."""
    return {
        "id": adventure["id"], "title": adventure["title"], "owner": adventure["owner"], "visibility": adventure["visibility"],
        "blocks": len(adventure["blocks"]), "played": sum(1 for block in adventure["blocks"] if block["played"]),
        "updated": adventure["updated"],
    }
