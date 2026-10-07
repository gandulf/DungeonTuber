import asyncio
import json
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import write_mp3
from core.mp3 import parse_mp3
from core.settings import AppSettings, SettingKeys
from server.agents import set_agent_token
from server.app import create_app
from server.config import ServerConfig
from server.index import TrackIndex, set_index

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agents" / "voxalyzer"))
from voxalyzer import agent as vox_agent  # noqa: E402

TOKEN = "secret-agent-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
RESULT = {"categories": {"Energy": 7, "Valence": 3}, "tags": ["epic"], "genres": ["Rock"], "bpm": 120}


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


class _Pump(threading.Thread):
    """Plays the Voxalyzer agent: downloads the file like the real agent and answers with a fixed result."""

    def __init__(self, client, websocket):
        super().__init__(daemon=True)
        self.client = client
        self.websocket = websocket
        self.downloads: list[bytes] = []
        self.requests: list[dict] = []

    def run(self):
        try:
            while True:
                request = json.loads(self.websocket.receive_text())
                self.requests.append(request)
                response = self.client.get(request["download"], headers=AUTH)
                self.downloads.append(response.content)
                self.websocket.send_text(json.dumps({"id": request["id"], "ok": True, "result": RESULT}))
        except Exception:
            pass  # connection closed


def _wait(condition, seconds=5):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


def test_analysis_runs_on_the_voxalyzer_agent(client, library):
    set_agent_token(TOKEN)
    song = library / "Battle" / "fight.mp3"
    original = song.read_bytes()

    with client.websocket_connect("/ws/agent", headers=AUTH) as websocket:
        websocket.send_text(json.dumps({"type": "hello", "kind": "voxalyzer", "name": "gpu-box"}))
        assert json.loads(websocket.receive_text()) == {"type": "welcome"}
        pump = _Pump(client, websocket)
        pump.start()

        assert client.get("/api/analysis").json()["backend"] == "agent"
        assert client.get("/api/settings").json()["voxalyzerActive"] is True
        assert client.post("/api/analysis", json={"paths": [song.as_posix()]}).json()["queued"] == 1
        assert _wait(lambda: client.get("/api/analysis").json()["pending"] == 0 and pump.requests)

        assert pump.requests[0]["op"] == "analyze"
        assert pump.downloads == [original]
        entry = parse_mp3(song)
        assert entry.categories == RESULT["categories"] and entry.tags == RESULT["tags"]
        assert entry.genres == RESULT["genres"] and entry.bpm == RESULT["bpm"]
        assert client.get("/api/analysis").json()["failed"] == 0

        ticket_url = pump.requests[0]["download"]
        assert client.get(ticket_url, headers=AUTH).status_code == 404  # tickets are single-use

    assert _wait(lambda: client.get("/api/analysis").json()["backend"] is None)
    assert client.get("/api/settings").json()["voxalyzerActive"] is False


def test_download_needs_the_agent_token(client):
    set_agent_token(TOKEN)
    assert client.get("/api/agents/files/whatever").status_code == 401
    assert client.get("/api/agents/files/whatever", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/api/agents/files/whatever", headers=AUTH).status_code == 404


def test_agent_urls():
    assert vox_agent.agent_url("https://example.org/dt/") == "wss://example.org/dt/ws/agent"
    assert vox_agent.agent_url("localhost:8000") == "ws://localhost:8000/ws/agent"
    assert vox_agent.http_url("https://example.org/dt/", "/api/agents/files/x") == "https://example.org/dt/api/agents/files/x"


def test_to_response_converts_numpy_scalars():
    np = pytest.importorskip("numpy")
    response = vox_agent.to_response({"categories": {"Energy": np.float32(0.5)}, "tags": ["a"], "genres": [], "bpm": np.int64(90), "moods": object()})
    assert response == {"categories": {"Energy": 0.5}, "tags": ["a"], "genres": [], "bpm": 90}


def test_agent_handler_runs_one_analysis_at_a_time(monkeypatch):
    active = []
    peak = []

    def fake_analyze(self, download):
        active.append(download)
        peak.append(len(active))
        time.sleep(0.05)
        active.remove(download)
        return {"ok": download}

    monkeypatch.setattr(vox_agent.Analyzer, "_analyze", fake_analyze)
    analyzer = vox_agent.Analyzer("http://localhost", TOKEN)

    async def go():
        return await asyncio.gather(*(analyzer.handle({"op": "analyze", "download": str(n)}) for n in range(3)))

    assert asyncio.run(go()) == [{"ok": "0"}, {"ok": "1"}, {"ok": "2"}]
    assert max(peak) == 1
    with pytest.raises(ValueError):
        asyncio.run(analyzer.handle({"op": "nope"}))


def test_fake_mode_returns_mock_values_without_models(tmp_path):
    analyzer = vox_agent.Analyzer("http://localhost", TOKEN, fake=True)

    result = asyncio.run(analyzer.handle({"op": "analyze", "download": "/api/agents/files/unused"}))

    assert set(result) == {"categories", "tags", "genres", "bpm"}
    assert all(0 <= value <= 10 for value in result["categories"].values())
    assert result["genres"] and result["bpm"] >= 70
