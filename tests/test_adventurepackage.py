import io
import json
import zipfile

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from conftest import write_mp3
from core.settings import AppSettings, SettingKeys
from server import adventures
from server.app import create_app
from server.auth import set_password
from server.config import ServerConfig
from server.index import TrackIndex, set_index


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "music"
    write_mp3(root / "Battle" / "fight.mp3")
    AppSettings.setValue(SettingKeys.LIBRARY_ROOTS, [root.as_posix()])
    return root


@pytest.fixture
def client(tmp_path, library):
    index = TrackIndex(tmp_path / "library.db")
    set_index(index)
    with TestClient(create_app(ServerConfig(web_dir=tmp_path / "no-web"))) as test_client:
        yield test_client
    index.close()
    set_index(None)


def _png(color="navy") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (6, 4), color).save(buffer, "PNG")
    return buffer.getvalue()


def _zip(files: dict[str, bytes | str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _adventure_with_assets(client):
    """An adventure with a picture in its notes, a cover and the book of an import."""
    created = client.post("/api/adventures", json={"title": "Die Gruft"}).json()
    image = client.post(f"/api/adventures/{created['id']}/images", files={"file": ("a.png", _png(), "image/png")}).json()["name"]
    cover = client.post(f"/api/adventures/{created['id']}/images", files={"file": ("b.png", _png("red"), "image/png")}).json()["name"]
    block = created["blocks"][0]
    block.update({"markdown": f"Ein Bild: ![x](image:{image})", "cover": cover})
    client.put(f"/api/adventures/{created['id']}", json={**created, "blocks": [block]})
    location, stored = adventures.find(created["id"])
    adventures.save_pdf(location, created["id"], b"%PDF-1.7 the book")
    stored["pdf"] = "Gruft.pdf"
    adventures.save(location, stored)
    return created["id"], image, cover


def _upload(client, data: bytes, **form):
    return client.post("/api/adventures/import-package", files={"file": ("gruft.zip", data, "application/zip")}, data={k: str(v).lower() for k, v in form.items()})


def test_an_adventure_is_exported_with_its_images_and_its_book(client):
    adventure_id, image, cover = _adventure_with_assets(client)
    response = client.get(f"/api/adventures/{adventure_id}/export")
    assert response.status_code == 200 and response.headers["content-type"] == "application/zip"
    assert response.headers["content-disposition"].startswith('attachment; filename="Die-Gruft.zip"')
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert sorted(archive.namelist()) == sorted(["manifest.json", "adventure.json", "book.pdf", f"assets/{image}", f"assets/{cover}"])
        assert json.loads(archive.read("manifest.json"))["format"] == "dungeontuber-adventure"
        assert json.loads(archive.read("adventure.json"))["title"] == "Die Gruft"
        assert archive.read("book.pdf") == b"%PDF-1.7 the book"
    assert client.get("/api/adventures/unknown/export").status_code == 404


def test_an_exported_adventure_comes_back_as_it_was(client):
    adventure_id, image, cover = _adventure_with_assets(client)
    package = client.get(f"/api/adventures/{adventure_id}/export").content
    assert client.delete(f"/api/adventures/{adventure_id}").status_code == 200
    assert client.get(f"/api/adventures/{adventure_id}").status_code == 404

    result = _upload(client, package).json()
    assert result == {"status": "imported", "id": adventure_id, "title": "Die Gruft", "overwritten": False}
    restored = client.get(f"/api/adventures/{adventure_id}").json()
    assert restored["title"] == "Die Gruft" and restored["pdf"] == "Gruft.pdf" and restored["visibility"] == "private"
    assert restored["blocks"][0]["cover"] == cover and f"image:{image}" in restored["blocks"][0]["markdown"]
    assert client.get(f"/api/adventures/{adventure_id}/pdf").content == b"%PDF-1.7 the book"
    assert client.get(f"/api/adventures/{adventure_id}/images/{image}").content == _png()
    assert client.get(f"/api/adventures/{adventure_id}/images/{cover}").status_code == 200


def test_a_duplicate_asks_first_and_is_replaced_only_when_told_to(client):
    adventure_id, image, cover = _adventure_with_assets(client)
    package = client.get(f"/api/adventures/{adventure_id}/export").content
    # the adventure changes after the export: a new title and an image that the file does not have
    changed = client.get(f"/api/adventures/{adventure_id}").json()
    extra = client.post(f"/api/adventures/{adventure_id}/images", files={"file": ("c.png", _png("green"), "image/png")}).json()["name"]
    client.put(f"/api/adventures/{adventure_id}", json={**changed, "title": "Geändert"})

    asked = _upload(client, package).json()
    assert asked == {"status": "exists", "id": adventure_id, "title": "Die Gruft", "editable": True}
    assert client.get(f"/api/adventures/{adventure_id}").json()["title"] == "Geändert"  # nothing happened yet

    result = _upload(client, package, overwrite=True).json()
    assert result["status"] == "imported" and result["overwritten"] is True
    assert client.get(f"/api/adventures/{adventure_id}").json()["title"] == "Die Gruft"
    assert client.get(f"/api/adventures/{adventure_id}/images/{image}").status_code == 200
    assert client.get(f"/api/adventures/{adventure_id}/images/{extra}").status_code == 404  # the old images are replaced by those of the file
    assert len(client.get("/api/adventures").json()["adventures"]) == 1


def test_a_copy_gets_an_id_of_its_own(client):
    adventure_id, image, _cover = _adventure_with_assets(client)
    package = client.get(f"/api/adventures/{adventure_id}/export").content
    result = _upload(client, package, copy=True).json()
    assert result["status"] == "imported" and result["id"] != adventure_id and result["title"] == "Die Gruft (copy)" and result["overwritten"] is False
    assert client.get(f"/api/adventures/{result['id']}/images/{image}").status_code == 200
    assert client.get(f"/api/adventures/{result['id']}/pdf").content == b"%PDF-1.7 the book"
    assert len(client.get("/api/adventures").json()["adventures"]) == 2


def test_files_that_are_no_adventures_are_refused(client, monkeypatch):
    good = {"adventure.json": json.dumps({"id": "x1", "title": "T", "blocks": []})}
    assert _upload(client, b"not a zip at all").status_code == 400
    assert _upload(client, _zip({"other.txt": "x"})).status_code == 400  # no adventure.json
    assert _upload(client, _zip({**good, "manifest.json": json.dumps({"format": "something else"})})).status_code == 400
    assert _upload(client, _zip({"adventure.json": "{broken"})).status_code == 400
    assert _upload(client, _zip({"adventure.json": json.dumps({"id": "x1", "blocks": "no list"})})).status_code == 400
    assert _upload(client, _zip({**good, "assets/0123456789ab.png": b"no image"})).status_code == 400
    assert _upload(client, _zip({**good, "book.pdf": b"no pdf"})).status_code == 400
    monkeypatch.setattr(adventures, "MAX_PACKAGE_SIZE", 10)  # a ZIP bomb: more unpacked than allowed
    assert _upload(client, _zip({**good, "assets/0123456789ab.png": _png()})).status_code == 400
    monkeypatch.setattr(adventures, "MAX_PACKAGE_SIZE", 600 * 1024 * 1024)
    monkeypatch.setattr(adventures, "MAX_PACKAGE_FILES", 2)
    assert _upload(client, _zip({**good, "a.txt": "1", "b.txt": "2"})).status_code == 400
    monkeypatch.setattr(adventures, "MAX_PACKAGE_FILES", 200)
    # files that do not belong in it are ignored (no path tricks): a minimal file works
    ok = _upload(client, _zip({**good, "../../evil.txt": "x", "assets/../evil.png": _png(), "notes.txt": "x"}))
    assert ok.status_code == 200 and ok.json()["status"] == "imported"
    assert [a["title"] for a in client.get("/api/adventures").json()["adventures"]] == ["T"]


def test_only_the_owner_overwrites_an_adventure(client):
    set_password("secret")
    client.post("/api/auth/login", json={"password": "secret"})
    client.post("/api/users", json={"name": "anna", "password": "pw1234"})
    adventure_id, _image, _cover = _adventure_with_assets(client)
    package = client.get(f"/api/adventures/{adventure_id}/export").content
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "anna", "password": "pw1234"})

    asked = _upload(client, package).json()
    assert asked["status"] == "exists" and asked["editable"] is False
    assert _upload(client, package, overwrite=True).status_code == 403
    copy = _upload(client, package, copy=True).json()  # her own copy works
    assert copy["status"] == "imported" and copy["id"] != adventure_id
    own = client.get(f"/api/adventures/{copy['id']}").json()
    assert own["owner"] == "anna" and own["visibility"] == "private" and own["editable"] is True
