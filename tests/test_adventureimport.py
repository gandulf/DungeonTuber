import time

import pytest
from fastapi.testclient import TestClient

from conftest import write_mp3
from core.settings import AppSettings, SettingKeys
from server import adventureimport
from server.app import create_app
from server.config import ServerConfig
from server.index import TrackIndex, set_index

OUTLINE = {
    "title": "Die Gruft",
    "scenes": [
        {"key": "s1", "title": "Ankunft", "pages": "4-5", "summary": "Die Helden kommen an."},
        {"key": "s2", "title": "Die Gruft", "pages": "6", "summary": "Unten ist es dunkel."},
        {"key": "s2", "title": "Doppelt", "summary": "dropped"},
        {"key": "s3", "title": "Epilog", "summary": "Ende."},
        {"key": "", "title": "ohne Schlüssel", "summary": "dropped"},
    ],
    "links": [{"from": "s1", "to": "s2", "label": "sie folgen der Spur"}, {"from": "s2", "to": "s3"}, {"from": "s2", "to": "s9"}],
}


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
    AppSettings.remove(SettingKeys.ASSISTANT_API_KEY)


def test_the_outline_and_the_notes_become_linked_blocks():
    adventure = adventureimport.build(OUTLINE, {"s1": "> Wind.\n\nWeiter zu [[s2]], nicht zu [[s9]].", "s2": "Dunkel."}, "anna")
    assert adventure["title"] == "Die Gruft" and adventure["owner"] == "anna" and adventure["visibility"] == "private"
    assert [block["title"] for block in adventure["blocks"]] == ["Ankunft", "Die Gruft", "Epilog"]
    first, second, third = adventure["blocks"]
    assert f"[Die Gruft](block:{second['id']})" in first["markdown"] and "[[s9]]" in first["markdown"]
    assert first["markdown"].endswith("*Pages: 4-5*")
    assert third["markdown"] == "Ende."  # no notes and no pages: the summary
    assert adventure["links"] == [{"from": first["id"], "to": second["id"], "label": "sie folgen der Spur"},
                                  {"from": second["id"], "to": third["id"], "label": None}]


def test_the_book_is_read_in_batches_and_the_upload_is_removed(monkeypatch):
    asked, removed = [], []
    monkeypatch.setattr(adventureimport, "SCENES_PER_REQUEST", 2)
    monkeypatch.setattr(adventureimport, "upload", lambda pdf, name: {"name": "files/1", "uri": "uri"})
    monkeypatch.setattr(adventureimport, "remove", lambda file: removed.append(file["name"]))

    def ask(file, system, text, schema):
        asked.append(text)
        if schema is adventureimport.OUTLINE_SCHEMA:
            return OUTLINE
        if "s3" in text.split("these scenes:")[1]:
            raise adventureimport.ImportFailed("busy")  # these scenes keep their summary
        return {"scenes": [{"key": "s1", "markdown": "Notes 1"}, {"key": "s2", "markdown": "Notes 2"}]}

    monkeypatch.setattr(adventureimport, "ask", ask)
    steps = []
    adventure = adventureimport.convert(b"%PDF", "gruft.pdf", "anna", lambda step, total: steps.append((step, total)))
    assert len(asked) == 3 and steps == [(0, 1), (1, 3), (2, 3)]
    assert [block["markdown"].split("\n")[0] for block in adventure["blocks"]] == ["Notes 1", "Notes 2", "Ende."]
    assert removed == ["files/1"]


def test_an_import_runs_in_the_background_and_stores_a_private_adventure(client, monkeypatch):
    pdf = {"file": ("gruft.pdf", b"%PDF-1.7 ...", "application/pdf")}
    assert client.post("/api/adventures/import", files=pdf).status_code == 400  # no AI key
    AppSettings.setValue(SettingKeys.ASSISTANT_API_KEY, "gemini_key_1234")
    assert client.post("/api/adventures/import", files={"file": ("x.pdf", b"not a pdf", "application/pdf")}).status_code == 400

    monkeypatch.setattr(adventureimport, "convert", lambda data, name, owner, progress: adventureimport.build(OUTLINE, {}, owner))
    job = client.post("/api/adventures/import", files=pdf).json()
    assert job["status"] == "running" and job["name"] == "gruft.pdf"
    for _ in range(100):
        job = client.get(f"/api/adventures/import/{job['id']}").json()
        if job["status"] != "running":
            break
        time.sleep(0.02)
    assert job["status"] == "done" and job["error"] is None
    adventure = client.get(f"/api/adventures/{job['adventure']}").json()
    assert adventure["title"] == "Die Gruft" and adventure["visibility"] == "private" and len(adventure["blocks"]) == 3
    assert client.get("/api/adventures/import/unknown").status_code == 404


def test_a_failed_import_reports_its_error(client, monkeypatch):
    AppSettings.setValue(SettingKeys.ASSISTANT_API_KEY, "gemini_key_1234")

    def fail(data, name, owner, progress):
        raise adventureimport.ImportFailed("The AI found no scenes in the PDF")

    monkeypatch.setattr(adventureimport, "convert", fail)
    job = client.post("/api/adventures/import", files={"file": ("a.pdf", b"%PDF", "application/pdf")}).json()
    for _ in range(100):
        job = client.get(f"/api/adventures/import/{job['id']}").json()
        if job["status"] != "running":
            break
        time.sleep(0.02)
    assert job == {**job, "status": "error", "error": "The AI found no scenes in the PDF", "adventure": None}
    assert client.get("/api/adventures").json()["adventures"] == []
