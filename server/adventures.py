"""Adventure files (`.dtadv`, JSON) in the hidden `.adventures` folder of the library roots, local or remote (see core/adventures.py)."""
import json
import logging
import re

from core import adventures as model
from core.storage import AlreadyExists, StorageError
from server import playlists
from server.index import get_index
from server.paths import Location
from server.roots import get_roots

logger = logging.getLogger(__file__)

FOLDER = ".adventures"
SUFFIX = ".dtadv"


class NoLibrary(Exception):
    pass


def _folders() -> list[Location]:
    return [Location(root, FOLDER) for root in get_roots()]


def read(location: Location) -> dict | None:
    try:
        data = json.loads(location.storage.read_bytes(location.rel).decode("utf-8-sig"))
    except (StorageError, OSError, ValueError) as e:
        logger.warning("Could not read adventure {0}: {1}", location.client_path, e)
        return None
    if not isinstance(data, dict) or not data.get("id"):
        return None
    adventure = model.normalize(data, previous=data)
    adventure["updated"] = data.get("updated") or adventure["created"]  # reading does not change an adventure
    return adventure


def list_all() -> list[tuple[Location, dict]]:
    found = []
    for folder in _folders():
        try:
            entries = folder.storage.list(folder.rel)
        except StorageError:
            continue  # no adventures in this library yet
        for entry in entries:
            if not entry.is_dir and entry.name.endswith(SUFFIX):
                location = Location(folder.root, entry.path)
                adventure = read(location)
                if adventure:
                    found.append((location, adventure))
    return found


def find(adventure_id: str) -> tuple[Location, dict] | None:
    return next(((location, adventure) for location, adventure in list_all() if adventure["id"] == adventure_id), None)


def save(location: Location, adventure: dict):
    location.storage.write(location.rel, json.dumps(adventure, ensure_ascii=False, indent=1).encode("utf-8"), overwrite=True)


def create(title: str, owner: str) -> tuple[Location, dict]:
    """A new adventure with one block, in the first library."""
    roots = get_roots()
    if not roots:
        raise NoLibrary()
    folder = Location(roots[0], FOLDER)
    try:
        if not folder.storage.exists(folder.rel):
            folder.storage.mkdir(folder.rel)
    except AlreadyExists:
        pass
    adventure = model.new_adventure(title, owner)
    slug = re.sub(r"[^\w]+", "-", adventure["title"], flags=re.UNICODE).strip("-").lower()[:40] or "adventure"
    location = folder.child(f"{slug}-{adventure['id'][:8]}{SUFFIX}")
    save(location, adventure)
    return location, adventure


def delete(location: Location):
    location.storage.delete(location.rel)


def mark_unavailable(adventure: dict, user: str, hidden) -> dict:
    """Playlists the viewer may not see (private ones of somebody else) are marked, so the adventure shows them as unavailable."""
    for block in adventure["blocks"]:
        for ref in block["music"]:
            if ref["type"] == "playlist" and any(hidden(location, user) for location in playlists.find(ref["id"])):
                ref["unavailable"] = True
    return adventure


def private_playlists(adventure: dict) -> list[str]:
    """Names of the private playlists an adventure refers to (they would be unavailable to others once it is public)."""
    index = get_index()
    names: list[str] = []
    for block in adventure["blocks"]:
        for ref in block["music"]:
            if ref["type"] != "playlist":
                continue
            for location in playlists.find(ref["id"]):
                name = ref["title"] or location.stem
                if index.is_private(location) and name not in names:
                    names.append(name)
    return names
