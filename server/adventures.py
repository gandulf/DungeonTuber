"""Adventure files (`.dtadv`, JSON) in the hidden `.adventures` folder of the library roots, local or remote (see core/adventures.py)."""
import io
import json
import logging
import re
import time
import uuid
import zipfile

from core import adventures as model
from core.i18n import _
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


# --- export and import as a ZIP file ------------------------------------------------------------------------------------------------------
# The file holds manifest.json (what it is), adventure.json (the adventure as the server stores it), book.pdf (the book it was imported from, if
# it has one) and assets/<name> (the images of the notes and the covers, with the names the notes refer to).

PACKAGE_FORMAT = "dungeontuber-adventure"
PACKAGE_VERSION = 1
MANIFEST_NAME = "manifest.json"
ADVENTURE_NAME = "adventure.json"
MAX_PACKAGE_UPLOAD = 400 * 1024 * 1024  # the ZIP file as it is uploaded
MAX_PACKAGE_SIZE = 600 * 1024 * 1024  # everything in it, unpacked (a ZIP bomb is stopped by this)
MAX_PACKAGE_FILES = 200
MAX_PDF_BYTES = 50 * 1024 * 1024


class PackageError(Exception):
    """The file is not an adventure file of this app (or damaged); the message says why and goes to the user."""


def export_package(location: Location, adventure: dict) -> bytes:
    """The adventure with its images and its book as a ZIP file."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(MANIFEST_NAME, json.dumps({"format": PACKAGE_FORMAT, "version": PACKAGE_VERSION, "id": adventure["id"], "title": adventure["title"],
                                                    "exported": time.time()}, ensure_ascii=False, indent=1))
        archive.writestr(ADVENTURE_NAME, json.dumps(adventure, ensure_ascii=False, indent=1))
        folder = assets_folder(location, adventure["id"])
        try:
            entries = folder.storage.list(folder.rel)
        except StorageError:
            entries = []  # no images and no book
        for entry in entries:
            if entry.is_dir:
                continue
            if entry.name == PDF_NAME:
                archive.writestr(PDF_NAME, folder.storage.read_bytes(entry.path), compress_type=zipfile.ZIP_STORED)  # a PDF is compressed already
            elif IMAGE_NAME.match(entry.name):
                archive.writestr(f"assets/{entry.name}", folder.storage.read_bytes(entry.path), compress_type=zipfile.ZIP_STORED)
    return buffer.getvalue()


def read_package(data: bytes) -> tuple[dict, dict[str, bytes]]:
    """Reads and checks an adventure file: the adventure (as in the file, not yet normalized) and its assets by name (the images and PDF_NAME)."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise PackageError(_("This is not an adventure file (ZIP)")) from None
    with archive:
        infos = archive.infolist()
        if len(infos) > MAX_PACKAGE_FILES or sum(info.file_size for info in infos) > MAX_PACKAGE_SIZE:
            raise PackageError(_("The adventure file is too large"))
        names = {info.filename for info in infos}
        if ADVENTURE_NAME not in names:
            raise PackageError(_("This is not an adventure file of Dungeon Tuber"))
        try:
            if MANIFEST_NAME in names and json.loads(archive.read(MANIFEST_NAME)).get("format") != PACKAGE_FORMAT:
                raise PackageError(_("This is not an adventure file of Dungeon Tuber"))
            adventure = json.loads(archive.read(ADVENTURE_NAME))
        except (ValueError, AttributeError):
            raise PackageError(_("The adventure file is damaged")) from None
        if not isinstance(adventure, dict) or not isinstance(adventure.get("blocks"), list):
            raise PackageError(_("The adventure file is damaged"))
        assets: dict[str, bytes] = {}
        for info in infos:
            name = info.filename
            if name == PDF_NAME:
                content = archive.read(name)
                if not content.startswith(b"%PDF") or len(content) > MAX_PDF_BYTES:
                    raise PackageError(_("The book in the adventure file is not a valid PDF"))
                assets[PDF_NAME] = content
            elif name.startswith("assets/") and IMAGE_NAME.match(name[len("assets/"):]):
                content = archive.read(name)
                if not _is_image(content):
                    raise PackageError(_("An image in the adventure file is not valid"))
                assets[name[len("assets/"):]] = content
    return adventure, assets


def _is_image(data: bytes) -> bool:
    if not data or len(data) > MAX_IMAGE_BYTES:
        return False
    try:
        from PIL import Image
        with Image.open(io.BytesIO(data)) as image:
            return (image.format or "") in IMAGE_TYPES
    except Exception:
        return False


def install_package(data: dict, assets: dict[str, bytes], owner: str, existing: tuple[Location, dict] | None = None, copy: bool = False) -> tuple[Location, dict]:
    """Stores an adventure read from an adventure file. A new one is private and belongs to `owner`. With `existing` (the adventure with the same
    id) that one is replaced (its owner and visibility stay, its old images and book are removed); with `copy` it becomes a new adventure with an id
    of its own."""
    data = dict(data)
    if copy:
        data["id"] = model.new_id()
        data["title"] = f"{str(data.get('title') or '').strip() or _('Imported adventure')} ({_('copy')})"
        existing = None
    previous = existing[1] if existing else None
    adventure = model.normalize({**data, "visibility": previous["visibility"] if previous else "private"}, owner=owner, previous=previous)
    adventure["pdf"] = (str(data.get("pdf") or "").strip()[:model.MAX_TITLE] or PDF_NAME) if PDF_NAME in assets else ""
    if existing:
        location = existing[0]
        folder = assets_folder(location, adventure["id"])
        try:
            folder.storage.delete(folder.rel)
        except StorageError:
            pass  # it had no images
        save(location, adventure)
    else:
        location, adventure = store_new(adventure)
    for name, content in assets.items():
        target = assets_folder(location, adventure["id"]).child(name)
        target.storage.write(target.rel, content, overwrite=True)
    return location, adventure
