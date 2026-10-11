import json
import sys
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core import ytimport
from core.ytimport import ImportFailed, RemoteEntry
from server import songcheck
from server.agents import set_agent_token
from server.app import create_app
from server.config import ServerConfig
from server.index import TrackIndex, set_index

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agents" / "youtube"))
import dt_youtube_agent as ytagent  # noqa: E402

TOKEN = "secret-agent-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


def video(title: str, uploader: str = "", vid: str = "abc") -> RemoteEntry:
    return RemoteEntry(f"https://www.youtube.com/watch?v={vid}", title, 180, uploader)


@pytest.fixture(autouse=True)
def empty_cache():
    songcheck._cache.clear()
    yield
    songcheck._cache.clear()


@pytest.fixture
def client(tmp_path):
    index = TrackIndex(tmp_path / "library.db")
    set_index(index)
    with TestClient(create_app(ServerConfig(web_dir=tmp_path / "no-web"))) as test_client:
        yield test_client
    index.close()
    set_index(None)


def test_a_video_matches_the_words_of_the_title():
    assert songcheck.title_words("The Good, the Bad and the Ugly - Main Theme") == ["good", "bad", "ugly"]
    assert songcheck.matches("The Good, the Bad and the Ugly - Main Theme",
                             video("Ennio Morricone - The Good, The Bad And The Ugly (Main Title)"))
    assert songcheck.matches("Concerning Hobbits", video("The Lord of the Rings Soundtrack - Concerning Hobbits", "Howard Shore"))
    assert songcheck.matches("Für Elise", video("Beethoven - Fur Elise (Piano)"))
    assert not songcheck.matches("Whispers of the Ancient Tavern", video("Medieval Tavern Music - Ancient Ambience"))
    assert songcheck.matches("Whispers of the Old Ancient Tavern", video("Whispers of the Ancient Tavern"))  # one of four words missing


def test_verify_searches_once_and_remembers(monkeypatch):
    calls = []

    def search(queries):
        calls.append(queries)
        return [[video("Unrelated"), video("Drunken Sailor (Sea Shanty)", "The Longest Johns", "ds")], [video("Something else")]]

    monkeypatch.setattr(songcheck.ytimport, "search", search)
    songs = [{"title": "Drunken Sailor", "artist": "Traditional"}, {"title": "Invented Song", "artist": "Nobody"}]
    results = songcheck.verify(songs)
    assert results == [{"found": True, "url": "https://www.youtube.com/watch?v=ds", "title": "Drunken Sailor (Sea Shanty)",
                        "channel": "The Longest Johns", "duration": 180}, {"found": False}]
    assert calls == [["Drunken Sailor Traditional", "Invented Song Nobody"]]
    assert songcheck.verify(songs) == results and len(calls) == 1  # from the cache


def test_without_youtube_the_songs_stay_unchecked(monkeypatch):
    def search(queries):
        raise ImportFailed("YouTube asks for a sign-in")

    monkeypatch.setattr(songcheck.ytimport, "search", search)
    assert songcheck.verify([{"title": "Drunken Sailor"}]) == [{"found": None}]
    assert songcheck._cache == {}  # asked again next time


def test_search_returns_the_hits_of_every_query(monkeypatch):
    class FakeYoutubeDL:
        def __init__(self, options):
            assert options["extract_flat"] is True

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def extract_info(self, url, download):
            from yt_dlp.utils import DownloadError
            assert url.startswith("ytsearch3:") and download is False
            if "broken" in url:
                raise DownloadError("broken")
            return {"entries": [{"id": "x1", "title": url[10:], "channel": "Chan", "duration": 61}]}

    monkeypatch.setattr("yt_dlp.YoutubeDL", FakeYoutubeDL)
    found = ytimport.search(["first song", "broken one"])
    assert found == [[RemoteEntry("https://www.youtube.com/watch?v=x1", "first song", 61, "Chan")], []]
    with pytest.raises(ImportFailed):
        ytimport.search(["broken"])


def test_the_route_checks_the_songs(client, monkeypatch):
    monkeypatch.setattr(songcheck.ytimport, "search", lambda queries: [[video("Drunken Sailor")] for _ in queries])
    response = client.post("/api/assistant/verify", json={"songs": [{"title": "Drunken Sailor", "artist": "Trad."}]})
    assert response.status_code == 200 and response.json()["results"][0]["found"] is True
    assert client.post("/api/assistant/verify", json={"songs": []}).status_code == 422


def test_the_search_goes_through_the_youtube_agent(client, monkeypatch):
    monkeypatch.setattr(songcheck.ytimport, "search", lambda queries: pytest.fail("the server must not search itself"))
    set_agent_token(TOKEN)
    with client.websocket_connect("/ws/agent", headers=AUTH) as websocket:
        websocket.send_text(json.dumps({"type": "hello", "kind": "youtube", "name": "home-pc"}))
        assert json.loads(websocket.receive_text()) == {"type": "welcome"}
        requests = []

        def pump():
            request = json.loads(websocket.receive_text())
            requests.append(request)
            entries = [[{"url": "https://www.youtube.com/watch?v=ag", "title": "Drunken Sailor", "duration": 99, "uploader": "Agent", "chapters": None}]]
            websocket.send_text(json.dumps({"id": request["id"], "ok": True, "result": entries}))

        thread = threading.Thread(target=pump, daemon=True)
        thread.start()
        result = client.post("/api/assistant/verify", json={"songs": [{"title": "Drunken Sailor", "artist": "Trad."}]}).json()
        thread.join(5)
    assert requests[0]["op"] == "search" and requests[0]["queries"] == ["Drunken Sailor Trad."]
    assert result["results"][0] == {"found": True, "url": "https://www.youtube.com/watch?v=ag", "title": "Drunken Sailor",
                                    "channel": "Agent", "duration": 99}


def test_the_agent_answers_a_search(monkeypatch):
    import asyncio
    monkeypatch.setattr(ytagent.ytimport, "search", lambda queries: [[video(f"Hit for {q}")] for q in queries])
    worker = ytagent.Worker("http://localhost", TOKEN)
    result = asyncio.run(worker.handle({"op": "search", "queries": ["a", "b"]}, lambda **k: None))
    assert [entries[0]["title"] for entries in result] == ["Hit for a", "Hit for b"]
