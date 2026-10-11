import io
import json
import urllib.error

import pytest
from fastapi.testclient import TestClient

from server import assistant
from server.app import create_app
from server.auth import set_password
from server.config import ServerConfig
from server.index import TrackIndex, set_index


@pytest.fixture
def client(tmp_path):
    index = TrackIndex(tmp_path / "library.db")
    set_index(index)
    with TestClient(create_app(ServerConfig(web_dir=tmp_path / "no-web"))) as test_client:
        yield test_client
    index.close()
    set_index(None)


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


@pytest.fixture
def gemini(monkeypatch):
    """Answers every request with the next prepared content and remembers the requests."""
    calls = []
    answers = []

    def urlopen(request, timeout=None):
        calls.append({"url": request.full_url, "headers": dict(request.header_items()), "body": json.loads(request.data)})
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        # a thinking model sends its thoughts as parts of their own
        parts = [{"text": "Hmm, a tavern…", "thought": True}, {"text": answer}]
        return _Response(json.dumps({"candidates": [{"content": {"role": "model", "parts": parts}}]}).encode())

    monkeypatch.setattr(assistant.urllib.request, "urlopen", urlopen)
    return calls, answers


def test_chat_needs_a_configured_key(client):
    assert client.get("/api/settings").json()["assistantConfigured"] is False
    assert client.post("/api/assistant/chat", json={"messages": [{"role": "user", "content": "Tavern"}]}).status_code == 409


def test_the_key_is_never_sent_back(client):
    status = client.put("/api/assistant/config", json={"key": "gsk_secret_1234", "model": ""}).json()
    assert status == {"configured": True, "model": assistant.DEFAULT_MODEL, "defaultModel": assistant.DEFAULT_MODEL, "keyHint": "1234",
                      "instructions": "", "generalInstructions": ""}
    assert "gsk_secret" not in client.get("/api/assistant/config").text
    assert client.get("/api/settings").json()["assistantConfigured"] is True
    # without a key the stored one is kept
    assert client.put("/api/assistant/config", json={"model": "other-model"}).json()["model"] == "other-model"
    assert assistant.api_key() == "gsk_secret_1234"
    assert client.delete("/api/assistant/config").json()["configured"] is False


def test_only_the_superadmin_configures_the_assistant(client):
    set_password("secret")
    client.post("/api/auth/login", json={"password": "secret"})
    client.put("/api/assistant/config", json={"key": "gsk_secret_1234"})
    client.post("/api/users", json={"name": "anna", "password": "pw1234"})
    client.post("/api/auth/logout")
    client.post("/api/auth/login", json={"username": "anna", "password": "pw1234"})

    assert client.get("/api/assistant/config").status_code == 403
    assert client.put("/api/assistant/config", json={"key": "mine"}).status_code == 403
    assert client.delete("/api/assistant/config").status_code == 403
    assert client.get("/api/settings").json()["assistantConfigured"] is True


def test_chat_returns_the_suggested_songs(client, gemini):
    calls, answers = gemini
    client.put("/api/assistant/config", json={"key": "gsk_secret_1234"})
    songs = [{"title": f"Song {i}", "artist": "Band"} for i in range(12)] + [{"title": "Song 1", "artist": "Band"}, {"artist": "no title"}]
    content = json.dumps({"message": "Here you go", "songs": songs})
    answers.append(content)

    result = client.post("/api/assistant/chat", json={"messages": [{"role": "user", "content": "A dark dungeon"}]}).json()
    assert result["message"] == "Here you go"
    assert [s["title"] for s in result["songs"]] == [f"Song {i}" for i in range(10)]
    assert result["content"] == content

    request = calls[0]
    assert request["headers"]["X-goog-api-key"] == "gsk_secret_1234"
    assert request["url"].endswith(f"/models/{assistant.DEFAULT_MODEL}:generateContent")
    assert request["body"]["systemInstruction"]["parts"][0]["text"] == assistant.SYSTEM_PROMPT
    assert request["body"]["contents"] == [{"role": "user", "parts": [{"text": "A dark dungeon"}]}]
    assert request["body"]["generationConfig"]["responseMimeType"] == "application/json"


def test_chat_keeps_the_conversation(client, gemini):
    calls, answers = gemini
    client.put("/api/assistant/config", json={"key": "gsk_secret_1234"})
    answers.append("not json at all")
    messages = [{"role": "user", "content": "Tavern"}, {"role": "assistant", "content": "{\"songs\": []}"}, {"role": "user", "content": "10 more"}]

    result = client.post("/api/assistant/chat", json={"messages": messages}).json()
    assert result == {"message": "not json at all", "songs": [], "content": "not json at all"}
    assert calls[0]["body"]["contents"] == [{"role": "user", "parts": [{"text": "Tavern"}]}, {"role": "model", "parts": [{"text": "{\"songs\": []}"}]},
                                           {"role": "user", "parts": [{"text": "10 more"}]}]
    assert client.post("/api/assistant/chat", json={"messages": messages[:2]}).status_code == 400


def test_chat_reports_a_rejected_key(client, gemini):
    _calls, answers = gemini
    client.put("/api/assistant/config", json={"key": "gsk_wrong_1234"})
    body = io.BytesIO(json.dumps({"error": {"code": 400, "message": "API key not valid. Please pass a valid API key.", "status": "INVALID_ARGUMENT"}}).encode())
    answers.append(urllib.error.HTTPError(assistant.API_URL, 400, "Bad Request", {}, body))

    response = client.post("/api/assistant/chat", json={"messages": [{"role": "user", "content": "Battle"}]})
    assert response.status_code == 502
    assert "rejected the API key" in response.json()["detail"] and "API key not valid" in response.json()["detail"]


def test_instructions_extend_the_system_prompt(client, gemini):
    calls, answers = gemini
    client.put("/api/assistant/config", json={"key": "gsk_secret_1234", "instructions": "  We play Call of Cthulhu in the 1920s.  "})
    assert client.get("/api/assistant/config").json()["instructions"] == "We play Call of Cthulhu in the 1920s."
    # without instructions the stored ones are kept
    assert client.put("/api/assistant/config", json={"model": ""}).json()["instructions"] == "We play Call of Cthulhu in the 1920s."
    answers.append(json.dumps({"songs": []}))

    client.post("/api/assistant/chat", json={"messages": [{"role": "user", "content": "A seance"}]})
    system = calls[0]["body"]["systemInstruction"]["parts"][0]["text"]
    assert system.startswith(assistant.SYSTEM_PROMPT) and system.endswith("We play Call of Cthulhu in the 1920s.")

    assert client.put("/api/assistant/config", json={"instructions": ""}).json()["instructions"] == ""
    assert client.put("/api/assistant/config", json={"instructions": "x" * 5000}).status_code == 422


def test_a_custom_model_is_used(client, gemini):
    calls, answers = gemini
    client.put("/api/assistant/config", json={"key": "gsk_secret_1234", "model": "gemini-3.5-flash-lite"})
    answers.append(json.dumps({"message": "", "songs": []}))
    client.post("/api/assistant/chat", json={"messages": [{"role": "user", "content": "Rain"}]})
    assert calls[0]["url"].endswith("/models/gemini-3.5-flash-lite:generateContent")


def test_the_models_come_from_google(client, monkeypatch):
    assert client.get("/api/assistant/models").json() == {"models": assistant.KNOWN_MODELS, "live": False}  # no key yet

    listed = {"models": [
        {"name": "models/gemini-3.5-flash-lite", "displayName": "Gemini 3.5 Flash-Lite", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-3.8-flash", "displayName": "Gemini 3.8 Flash", "supportedGenerationMethods": ["generateContent", "countTokens"]},
        {"name": "models/gemini-2.5-flash-image", "displayName": "Nano Banana", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-embedding-2", "displayName": "Embedding", "supportedGenerationMethods": ["embedContent"]},
        {"name": "models/gemma-4-27b-it", "displayName": "Gemma", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-3.1-pro-preview", "displayName": "Gemini 3.1 Pro Preview", "supportedGenerationMethods": ["generateContent"]},
    ]}
    requests = []

    def urlopen(request, timeout=None):
        requests.append(request)
        return _Response(json.dumps(listed).encode())

    monkeypatch.setattr(assistant.urllib.request, "urlopen", urlopen)
    client.put("/api/assistant/config", json={"key": "gsk_secret_1234"})
    result = client.get("/api/assistant/models").json()
    assert result == {"live": True, "models": [{"id": "gemini-3.8-flash", "name": "Gemini 3.8 Flash"},
                                               {"id": "gemini-3.5-flash-lite", "name": "Gemini 3.5 Flash-Lite"}]}
    assert requests[0].get_header("X-goog-api-key") == "gsk_secret_1234"

    def offline(request, timeout=None):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(assistant.urllib.request, "urlopen", offline)
    assert client.get("/api/assistant/models").json()["live"] is False


def test_the_general_chat_answers_in_text_with_its_own_instructions(client, gemini):
    calls, answers = gemini
    client.put("/api/assistant/config", json={"key": "gsk_secret_1234", "instructions": "Music only",
                                              "generalInstructions": "We play DSA 4.1 use the official rule book from ulisses-spiele or wiki-aventurica."})
    assert client.get("/api/assistant/config").json()["generalInstructions"] == "We play DSA 4.1 use the official rule book from ulisses-spiele or wiki-aventurica."
    answers.append("**Initiative** = INI-Basiswert + 1W6")

    result = client.post("/api/assistant/chat", json={"mode": "general", "messages": [{"role": "user", "content": "Wie geht Initiative?"}]}).json()
    assert result == {"message": "**Initiative** = INI-Basiswert + 1W6", "songs": [], "content": "**Initiative** = INI-Basiswert + 1W6"}
    body = calls[0]["body"]
    system = body["systemInstruction"]["parts"][0]["text"]
    assert system.startswith(assistant.GENERAL_PROMPT) and system.endswith("We play DSA 4.1 use the official rule book from ulisses-spiele or wiki-aventurica.") and "Music only" not in system
    assert "generationConfig" not in body  # free text, no song list

    assert client.post("/api/assistant/chat", json={"mode": "other", "messages": [{"role": "user", "content": "x"}]}).status_code == 422


def test_the_smart_search_answers_with_a_filter_of_known_values(client, gemini):
    calls, answers = gemini
    client.put("/api/assistant/config", json={"key": "gsk_secret_1234", "instructions": "We play DSA."})
    answers.append(json.dumps({"message": "Dunkel und angespannt", "bpm": 300,
                               "categories": [{"key": "Darkness", "value": 9.4}, {"key": "Arousal", "value": 14}, {"key": "Invented", "value": 5}],
                               "tags": ["DARK", "unknown", "Ritual", "Combat"], "genres": ["ambient", "Metal"]}))
    context = {"tags": ["Dark", "Ritual", "Combat", "dark"], "genres": ["Ambient", "Metal"]}

    result = client.post("/api/assistant/chat", json={"mode": "smart", "context": context,
                                                      "messages": [{"role": "user", "content": "Ein düsteres Ritual"}]}).json()
    assert result["message"] == "Dunkel und angespannt" and result["songs"] == []
    assert result["filter"] == {"categories": {"Darkness": 9, "Arousal": 10}, "tags": ["Dark", "Ritual"], "genres": ["Ambient"], "bpm": None}

    body = calls[0]["body"]
    system = body["systemInstruction"]["parts"][0]["text"]
    assert "- Darkness (" in system and "Dark, Ritual, Combat" in system and "Ambient, Metal" in system and system.endswith("We play DSA.")
    schema = body["generationConfig"]["responseSchema"]["properties"]
    assert schema["tags"]["items"]["enum"] == ["Dark", "Ritual", "Combat"] and schema["genres"]["items"]["enum"] == ["Ambient", "Metal"]
    assert "Darkness" in schema["categories"]["items"]["properties"]["key"]["enum"]


def test_the_smart_search_without_tags_or_genres(client, gemini):
    calls, answers = gemini
    client.put("/api/assistant/config", json={"key": "gsk_secret_1234"})
    answers.append(json.dumps({"message": "", "categories": [{"key": "Valence", "value": 8}], "bpm": 120}))
    result = client.post("/api/assistant/chat", json={"mode": "smart", "messages": [{"role": "user", "content": "Tavern"}]}).json()
    assert result["filter"] == {"categories": {"Valence": 8}, "tags": [], "genres": [], "bpm": 120}
    properties = calls[0]["body"]["generationConfig"]["responseSchema"]["properties"]
    assert "tags" not in properties and "genres" not in properties
