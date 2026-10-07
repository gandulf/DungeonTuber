import hashlib
import time
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import write_mp3
from core import tools, ytimport
from core.settings import AppSettings, SettingKeys
from core.ytimport import Downloaded, ImportFailed, RemoteEntry, Resolved
from server import downloads
from server.app import create_app
from server.config import ServerConfig
from server.index import TrackIndex, set_index


def test_only_youtube_links_are_accepted():
    for url in ("https://www.youtube.com/watch?v=abc", "https://youtu.be/abc", "http://music.youtube.com/playlist?list=x"):
        assert ytimport.check_url(f"  {url} ") == url
    for url in ("file:///etc/passwd", "https://example.com/watch?v=abc", "https://youtube.com.evil.org/x", "ftp://youtube.com/x", "", "abc"):
        with pytest.raises(ImportFailed):
            ytimport.check_url(url)


def test_playlist_links():
    assert ytimport._is_playlist("https://www.youtube.com/playlist?list=PLabc")
    assert ytimport._is_playlist("https://www.youtube.com/watch?v=abc&list=PLabc&index=3")
    assert not ytimport._is_playlist("https://www.youtube.com/watch?v=abc")
    assert not ytimport._is_playlist("https://www.youtube.com/watch?v=abc&list=RDabc")


def test_video_links_of_a_playlist_offer_both():
    assert ytimport._has_video("https://www.youtube.com/watch?v=abc&list=PLabc")
    assert not ytimport._has_video("https://www.youtube.com/playlist?list=PLabc")
    assert not ytimport._has_video("https://www.youtube.com/watch?v=abc")
    assert not ytimport._has_video("https://www.youtube.com/watch?v=abc&list=RDabc")


def test_file_names():
    assert ytimport.file_name('AC/DC: "Back" in <Black>?') == "ACDC Back in Black.mp3"
    assert ytimport.file_name("  ...  ", "id123") == "id123.mp3"
    assert len(ytimport.file_name("x" * 500)) == ytimport.MAX_NAME + len(".mp3")


def test_entries_of_a_playlist():
    assert ytimport._entry({"id": "abc", "url": "https://www.youtube.com/watch?v=abc", "title": "A", "duration": 5, "channel": "Me"}) == \
        RemoteEntry("https://www.youtube.com/watch?v=abc", "A", 5, "Me")
    assert ytimport._entry({"id": "xyz", "title": "B"}).url == "https://www.youtube.com/watch?v=xyz"
    assert ytimport._entry({"url": "https://example.com/video", "title": "C"}) is None


def test_chapters_and_artist():
    assert ytimport._chapters({"chapters": [{"title": "Intro", "start_time": 0}, {"title": "Fight", "start_time": 12.5}]}) == \
        [{"title": "Intro", "time": 0, "light": None}, {"title": "Fight", "time": 12500, "light": None}]
    assert ytimport._chapters({}) == []
    assert ytimport._artist({"channel": "Some Band - Topic"}) == "Some Band"
    assert ytimport._artist({"artist": "Band", "channel": "Other"}) == "Band"


def test_download_tools_are_verified(tmp_path, monkeypatch):
    archive = tmp_path / "deno-test.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr(tools._exe("deno"), b"#!/bin/sh\n")
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksums = tmp_path / "deno-test.zip.sha256sum"
    checksums.write_text(f"{digest}  deno-test.zip\n")
    monkeypatch.setenv("DT_TOOLS_DIR", str(tmp_path / "tools"))
    monkeypatch.setattr(tools.shutil, "which", lambda name: None)
    monkeypatch.setitem(tools.DOWNLOADS, "deno", lambda: tools.Download(archive.as_uri(), checksums.as_uri()))

    path = tools.ensure_tool("deno")
    assert Path(path).read_bytes() == b"#!/bin/sh\n"
    assert tools.find_tool("deno") == path

    Path(path).unlink()
    checksums.write_text(f"{'0' * 64}  deno-test.zip\n")
    with pytest.raises(OSError):
        tools.ensure_tool("deno")
    assert tools.find_tool("deno") is None


# --- server ----------------------------------------------------------------

@pytest.fixture
def client(tmp_path):
    root = tmp_path / "music"
    root.mkdir()
    AppSettings.setValue(SettingKeys.LIBRARY_ROOTS, [root.as_posix()])
    index = TrackIndex(tmp_path / "library.db")
    set_index(index)
    with TestClient(create_app(ServerConfig(web_dir=tmp_path / "no-web"))) as test_client:
        test_client.root = root
        yield test_client
    index.close()
    set_index(None)


def fake_download(url, directory, progress=None, max_minutes=240, album=None, percent=None, split=False):
    if "broken" in url:
        raise ImportFailed("Video unavailable")
    name = url.rsplit("=", 1)[1]
    write_mp3(Path(directory) / f"{name}.mp3")
    return Downloaded(Path(directory) / f"{name}.mp3", f"Song {name}.mp3", f"Song {name}")


def wait_until_idle():
    for _ in range(100):
        status = downloads.download_queue.status()
        if status["pending"] == 0:
            return status
        time.sleep(0.05)
    raise AssertionError("the import did not finish")


def test_resolve(client, monkeypatch):
    seen = []
    monkeypatch.setattr("server.routes.imports.resolve", lambda url, whole=None: seen.append((url, whole)) or Resolved("Mix", whole is not False, [RemoteEntry("https://youtu.be/a", "A", 60)], True))
    result = client.post("/api/import/resolve", json={"url": "https://www.youtube.com/playlist?list=x"}).json()
    assert result["playlist"] and result["entries"][0]["title"] == "A" and result["maxMinutes"] == 240
    assert result["hasVideo"] and seen == [("https://www.youtube.com/playlist?list=x", None)]
    assert not client.post("/api/import/resolve", json={"url": "https://www.youtube.com/playlist?list=x", "whole": False}).json()["playlist"]

    monkeypatch.undo()
    assert client.post("/api/import/resolve", json={"url": "https://example.com/x"}).status_code == 400


def test_import_stores_songs_and_creates_a_playlist(client, monkeypatch):
    monkeypatch.setattr(downloads, "download", fake_download)
    target = client.root.resolve().as_posix()
    urls = ["https://www.youtube.com/watch?v=one", "https://www.youtube.com/watch?v=two", "https://www.youtube.com/watch?v=broken"]
    entries = [{"url": url, "title": url[-3:]} for url in urls]

    response = client.post("/api/import", json={"dir": target, "entries": entries, "album": "Mix", "playlist": "Mix"})
    assert response.status_code == 200 and response.json()["queued"] == 3
    status = wait_until_idle()
    assert (status["pending"], status["done"], status["failed"]) == (0, 2, 1)
    assert [(item["title"], item["state"]) for item in status["items"]] == [("Song one", "done"), ("Song two", "done"), ("ken", "failed")]
    assert status["items"][2]["message"] == "Video unavailable"

    assert (client.root / "Song one.mp3").is_file() and (client.root / "Song two.mp3").is_file()
    assert not (client.root / "Song broken.mp3").exists()
    assert (client.root / "Mix.m3u").read_text(encoding="utf-8").count(".mp3") == 2

    # the same links again: nothing is overwritten and no second playlist entry appears
    client.post("/api/import", json={"dir": target, "entries": entries[:1]})
    again = wait_until_idle()
    assert again["failed"] == 0 and again["items"][0]["state"] == "skipped"
    assert len(list(client.root.glob("*.mp3"))) == 2


def test_import_into_a_new_folder(client, monkeypatch):
    monkeypatch.setattr(downloads, "download", fake_download)
    target = client.root.resolve().as_posix()
    entries = [{"url": "https://www.youtube.com/watch?v=one"}]
    assert client.post("/api/import", json={"dir": target, "entries": entries, "folder": "My: Mix", "playlist": "My Mix"}).status_code == 200
    wait_until_idle()
    assert (client.root / "My Mix" / "Song one.mp3").is_file() and (client.root / "My Mix" / "My Mix.m3u").is_file()
    assert not (client.root / "Song one.mp3").exists()


def test_import_validates_the_request(client):
    target = client.root.resolve().as_posix()
    assert client.post("/api/import", json={"dir": target, "entries": [{"url": "https://example.com/a"}]}).status_code == 400
    assert client.post("/api/import", json={"dir": target, "entries": []}).status_code == 400
    assert client.post("/api/import", json={"dir": (client.root.parent / "elsewhere").as_posix(), "entries": [{"url": "https://youtu.be/a"}]}).status_code in (403, 404)


def test_import_can_analyze_the_new_songs(client, monkeypatch):
    monkeypatch.setattr(downloads, "download", fake_download)
    submitted = []
    monkeypatch.setattr(downloads.analysis_queue, "submit", lambda locations: submitted.extend(locations) or len(locations))
    target = client.root.resolve().as_posix()
    entries = [{"url": "https://www.youtube.com/watch?v=one"}]

    monkeypatch.setattr("server.routes.imports.current_backend", lambda: None)
    assert client.post("/api/import", json={"dir": target, "entries": entries, "analyze": True}).status_code == 409

    monkeypatch.setattr("server.routes.imports.current_backend", lambda: object())
    assert client.post("/api/import", json={"dir": target, "entries": entries, "analyze": True}).status_code == 200
    wait_until_idle()
    assert [location.name for location in submitted] == ["Song one.mp3"]


def test_import_splits_chapters_into_a_folder(client, monkeypatch):
    def split_download(url, directory, progress=None, max_minutes=240, album=None, percent=None, split=False):
        parts = [Downloaded(write_mp3(Path(directory) / f"p{n}.mp3"), f"0{n} Part {n}.mp3", f"Part {n}") for n in (1, 2)] if split else []
        return Downloaded(write_mp3(Path(directory) / "whole.mp3"), "Long: Video.mp3", "Long Video", parts)

    monkeypatch.setattr(downloads, "download", split_download)
    target = client.root.resolve().as_posix()
    entries = [{"url": "https://www.youtube.com/watch?v=one"}]

    client.post("/api/import", json={"dir": target, "entries": entries, "split": True, "playlist": "Long"})
    assert wait_until_idle()["done"] == 1
    assert sorted(p.name for p in (client.root / "Long Video").glob("*.mp3")) == ["01 Part 1.mp3", "02 Part 2.mp3"]
    assert (client.root / "Long.m3u").read_text(encoding="utf-8").count(".mp3") == 2


COOKIES = "\n".join([
    "# Netscape HTTP Cookie File",
    "\t".join([".youtube.com", "TRUE", "/", "TRUE", "1999999999", "SID", "secret1"]),
    "\t".join(["#HttpOnly_.google.com", "TRUE", "/", "TRUE", "1999999999", "SAPISID", "secret2"]),
    "\t".join([".example.com", "TRUE", "/", "FALSE", "1999999999", "other", "not-wanted"]),
    "\t".join([".notyoutube.com", "TRUE", "/", "FALSE", "1999999999", "evil", "not-wanted"]),
    "garbage line",
])


def test_cookies_keep_only_youtube():
    cleaned = ytimport.clean_cookies(COOKIES)
    assert "secret1" in cleaned and "secret2" in cleaned and "not-wanted" not in cleaned and cleaned.startswith("# Netscape HTTP Cookie File")
    with pytest.raises(ImportFailed):
        ytimport.clean_cookies("nothing useful here")


def test_cookies_are_stored_and_used_by_yt_dlp(client, monkeypatch):
    monkeypatch.setattr(ytimport, "_runtime", lambda progress: {})
    assert client.get("/api/import/cookies").json() == {"set": False, "updated": None}
    assert "cookiefile" not in ytimport._options(None)

    assert client.put("/api/import/cookies", json={"content": "garbage"}).status_code == 400
    state = client.put("/api/import/cookies", json={"content": COOKIES}).json()
    assert state["set"] and state["updated"]
    assert "secret1" in ytimport.cookies_file().read_text(encoding="utf-8")
    assert "secret" not in client.get("/api/import/cookies").text
    assert ytimport._options(None)["cookiefile"] == str(ytimport.cookies_file())
    assert "stored cookies" in ytimport._clean_error(Exception("ERROR: [youtube] x: Sign in to confirm you’re not a bot"))

    assert client.delete("/api/import/cookies").json()["set"] is False
    assert "administrator" in ytimport._clean_error(Exception("ERROR: [youtube] x: Sign in to confirm you’re not a bot"))
