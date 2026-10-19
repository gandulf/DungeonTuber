"""Adventure files (`.dtadv`, JSON) in the hidden `.adventures` folder of the library roots, local or remote (see core/adventures.py)."""
import io
import json
import logging
import re
import uuid

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
    return store_new(model.new_adventure(title, owner))


def has_library() -> bool:
    return bool(get_roots())


def store_new(adventure: dict) -> tuple[Location, dict]:
    """Stores a new (normalized) adventure in the first library, e.g. one imported from a PDF."""
    roots = get_roots()
    if not roots:
        raise NoLibrary()
    folder = Location(roots[0], FOLDER)
    try:
        if not folder.storage.exists(folder.rel):
            folder.storage.mkdir(folder.rel)
    except AlreadyExists:
        pass
    slug = re.sub(r"[^\w]+", "-", adventure["title"], flags=re.UNICODE).strip("-").lower()[:40] or "adventure"
    location = folder.child(f"{slug}-{adventure['id'][:8]}{SUFFIX}")
    save(location, adventure)
    return location, adventure


def delete(location: Location, adventure_id: str | None = None):
    """Deletes an adventure with its images."""
    location.storage.delete(location.rel)
    if adventure_id:
        folder = assets_folder(location, adventure_id)
        try:
            folder.storage.delete(folder.rel)
        except StorageError:
            pass  # it had no images


def all_music(adventure: dict):
    """The music of the adventure and of its blocks (a block holds copies of the adventure's references)."""
    yield from adventure.get("music", [])
    for block in adventure["blocks"]:
        yield from block["music"]


def mark_unavailable(adventure: dict, user: str, hidden) -> dict:
    """Playlists the viewer may not see (private ones of somebody else) are marked, so the adventure shows them as unavailable."""
    for ref in all_music(adventure):
        if ref["type"] == "playlist" and any(hidden(location, user) for location in playlists.find(ref["id"])):
            ref["unavailable"] = True
    return adventure


def private_playlists(adventure: dict) -> list[str]:
    """Names of the private playlists an adventure refers to (they would be unavailable to others once it is public)."""
    index = get_index()
    names: list[str] = []
    for ref in all_music(adventure):
        if ref["type"] != "playlist":
            continue
        for location in playlists.find(ref["id"]):
            name = ref["title"] or location.stem
            if index.is_private(location) and name not in names:
                names.append(name)
    return names


# --- images ----------------------------------------------------------------

IMAGE_TYPES = {"PNG": ("png", "image/png"), "JPEG": ("jpg", "image/jpeg"), "GIF": ("gif", "image/gif"), "WEBP": ("webp", "image/webp")}
MAX_IMAGE_BYTES = 8 * 1024 * 1024
IMAGE_NAME = model.IMAGE_NAME
IMAGE_LINK = re.compile(r"image:([0-9a-f]{12}\.(?:png|jpg|gif|webp))")


class InvalidImage(Exception):
    pass


def assets_folder(location: Location, adventure_id: str) -> Location:
    """The folder next to the adventure file that holds its images."""
    return location.parent.child(f"{adventure_id}.assets")


def save_image(location: Location, adventure_id: str, data: bytes) -> str:
    """Stores an uploaded image (PNG, JPEG, GIF or WEBP) and returns its name, which the notes refer to as `image:<name>`."""
    if not data or len(data) > MAX_IMAGE_BYTES:
        raise InvalidImage("Empty or too large image")
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as image:
            kind = IMAGE_TYPES.get(image.format or "")
    except Exception:
        raise InvalidImage("Unsupported image")
    if kind is None:
        raise InvalidImage("Unsupported image")
    name = f"{uuid.uuid4().hex[:12]}.{kind[0]}"
    target = assets_folder(location, adventure_id).child(name)
    target.storage.write(target.rel, data)
    return name


def read_image(location: Location, adventure_id: str, name: str) -> tuple[bytes, str] | None:
    if not IMAGE_NAME.match(name):
        return None
    image = assets_folder(location, adventure_id).child(name)
    try:
        data = image.storage.read_bytes(image.rel)
    except StorageError:
        return None
    return data, next(mime for extension, mime in IMAGE_TYPES.values() if extension == name.rsplit(".", 1)[1])


PDF_NAME = "book.pdf"


def save_pdf(location: Location, adventure_id: str, data: bytes):
    """Keeps the PDF of the book next to the adventure; the notes link to its pages (`pdf:<page>`)."""
    target = assets_folder(location, adventure_id).child(PDF_NAME)
    target.storage.write(target.rel, data, overwrite=True)


def read_pdf(location: Location, adventure_id: str) -> bytes | None:
    pdf = assets_folder(location, adventure_id).child(PDF_NAME)
    try:
        return pdf.storage.read_bytes(pdf.rel)
    except StorageError:
        return None


def referenced_images(adventure: dict) -> set[str]:
    """The images the notes and the covers of the blocks use."""
    used = {name for block in adventure["blocks"] for name in IMAGE_LINK.findall(block["markdown"])}
    return used | {block["cover"] for block in adventure["blocks"] if block.get("cover")}


def remove_unused_images(location: Location, adventure: dict) -> int:
    """Deletes the images no block refers to any more (in its notes or as its cover); returns how many."""
    folder = assets_folder(location, adventure["id"])
    try:
        entries = folder.storage.list(folder.rel)
    except StorageError:
        return 0
    used = referenced_images(adventure)
    removed = 0
    for entry in entries:
        if not entry.is_dir and IMAGE_NAME.match(entry.name) and entry.name not in used:
            folder.storage.delete(entry.path)
            removed += 1
    return removed
