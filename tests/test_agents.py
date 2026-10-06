import asyncio
import json
import sys
import threading
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from core.lights import light_registry
from core.settings import AppSettings
from server.agents import set_agent_token, valid_agent_token
from server.app import create_app
from server.config import ServerConfig
from server.index import TrackIndex, set_index

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agents" / "wiz"))
import dt_wiz_agent  # noqa: E402


@pytest.fixture
def client(tmp_path):
    index = TrackIndex(tmp_path / "library.db")
    set_index(index)
    with TestClient(create_app(ServerConfig(web_dir=tmp_path / "no-web"))) as test_client:
        yield test_client
    index.close()
    set_index(None)
    light_registry.lights.clear()
    light_registry.fake_bulbs = False
    light_registry.remote_bulbs = None


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


class _Pump(threading.Thread):
    """Plays the agent: answers the requests of the server with simulated bulbs."""

    def __init__(self, websocket):
        super().__init__(daemon=True)
        self.websocket = websocket
        self.bulbs = dt_wiz_agent.Bulbs("255.255.255.255", 1, fake=True)
        self.requests: list[dict] = []

    def run(self):
        try:
            while True:
                request = json.loads(self.websocket.receive_text())
                self.requests.append(request)
                try:
                    reply = {"id": request["id"], "ok": True, "result": asyncio.run(self.bulbs.handle(request))}
                except Exception as e:
                    reply = {"id": request["id"], "ok": False, "error": str(e)}
                self.websocket.send_text(json.dumps(reply))
        except Exception:
            pass  # connection closed


def _connect(client, token, kind="lights"):
    websocket = client.websocket_connect("/ws/agent", headers=_auth(token))
    return websocket


def _wait(condition, seconds=5):
    deadline = time.time() + seconds
    while time.time() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


def test_agent_token_is_stored_as_hash(client):
    token = client.post("/api/agents/token").json()["token"]

    assert valid_agent_token(token)
    assert not valid_agent_token(token + "x")
    assert not valid_agent_token(None)
    assert token not in Path(AppSettings.path).read_text()
    assert client.get("/api/agents").json() == {"tokenSet": True, "connected": []}

    second = client.post("/api/agents/token").json()["token"]
    assert second != token and not valid_agent_token(token)


def test_agent_connection_needs_the_agent_token(client):
    with pytest.raises(WebSocketDisconnect):  # no token configured yet
        with _connect(client, "anything"):
            pass

    set_agent_token("secret-agent-token")
    for headers in ({}, _auth("wrong")):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/agent", headers=headers):
                pass


def test_lights_through_agent(client):
    set_agent_token("secret-agent-token")
    assert client.get("/api/lights").json()["agent"] is False

    with _connect(client, "secret-agent-token") as websocket:
        websocket.send_text(json.dumps({"type": "hello", "kind": "lights", "name": "home"}))
        assert json.loads(websocket.receive_text()) == {"type": "welcome"}
        pump = _Pump(websocket)
        pump.start()

        assert _wait(lambda: len(light_registry.lights) == 3 and all(light.control for light in light_registry.lights))
        data = client.get("/api/lights").json()
        assert data["agent"] is True
        assert all(light["online"] for light in data["lights"])
        assert client.get("/api/agents").json()["connected"] == [{"kind": "lights", "name": "home"}]

        mac = data["lights"][0]["mac"]
        light = client.patch(f"/api/lights/{mac}", json={"state": True, "color": "#00ff00", "brightness": 80}).json()
        assert light["color"] == "#00ff00"
        pilot = [r for r in pump.requests if r["op"] == "pilot"][-1]
        assert pilot["mac"] == mac and (pilot["params"]["r"], pilot["params"]["g"], pilot["params"]["b"]) == (0, 255, 0)
        assert pilot["params"]["state"] is True

        client.patch(f"/api/lights/{mac}", json={"state": False})
        assert pump.requests[-1]["op"] == "off"
        assert client.post("/api/lights/cue", json={"color": "#0000ff"}).json()["applied"] == 3

    assert _wait(lambda: not client.get("/api/lights").json()["agent"])
    lights = client.get("/api/lights").json()["lights"]
    assert len(lights) == 3 and not any(light["online"] for light in lights)
    # without an agent the lights are offline: changes are kept but nothing is sent
    assert client.patch(f"/api/lights/{lights[0]['mac']}", json={"state": True}).json()["state"] is True


def test_agent_failure_is_reported(client):
    set_agent_token("secret-agent-token")
    with _connect(client, "secret-agent-token") as websocket:
        websocket.send_text(json.dumps({"type": "hello", "kind": "lights", "name": "home"}))
        websocket.receive_text()
        pump = _Pump(websocket)
        pump.start()
        assert _wait(lambda: len(light_registry.lights) == 3)
        mac = client.get("/api/lights").json()["lights"][0]["mac"]
        pump.bulbs._bulbs.clear()  # the agent lost its bulbs

        assert client.patch(f"/api/lights/{mac}", json={"state": True, "color": "#ff0000"}).status_code == 502


def test_agent_url():
    assert dt_wiz_agent.agent_url("https://dt.example.com") == "wss://dt.example.com/ws/agent"
    assert dt_wiz_agent.agent_url("localhost:8765/") == "ws://localhost:8765/ws/agent"
    assert dt_wiz_agent.agent_url("http://host/prefix/") == "ws://host/prefix/ws/agent"
