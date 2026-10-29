import io
import json
import urllib.error
import urllib.parse

import pytest
from fastapi.testclient import TestClient

from core.settings import AppSettings, SettingKeys
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
                      "keySource": "settings", "groqKeySource": None,
                      "instructions": assistant.DEFAULT_MUSIC_INSTRUCTIONS.strip(),
                      "defaultInstructions": {"music": assistant.DEFAULT_MUSIC_INSTRUCTIONS.strip(), "smart": assistant.DEFAULT_SETTING_INSTRUCTIONS.strip(),
                                              "compose": assistant.DEFAULT_SETTING_INSTRUCTIONS.strip(), "image": assistant.DEFAULT_IMAGE_INSTRUCTIONS},
                      "generalInstructions": "", "composeInstructions": assistant.DEFAULT_SETTING_INSTRUCTIONS.strip(), "smartInstructions": assistant.DEFAULT_SETTING_INSTRUCTIONS.strip(), "effectsInstructions": "", "imageInstructions": assistant.DEFAULT_IMAGE_INSTRUCTIONS, "importInstructions": "", "groqConfigured": False, "groqModel": assistant.GROQ_DEFAULT_MODEL,
                      "groqDefaultModel": assistant.GROQ_DEFAULT_MODEL, "groqKeyHint": "", "groqModels": assistant.GROQ_MODELS,
                      "prompts": assistant.prompts()}
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
    system = request["body"]["systemInstruction"]["parts"][0]["text"]  # the song suggestions have default instructions
    assert system.startswith(assistant.SYSTEM_PROMPT) and system.endswith(assistant.DEFAULT_MUSIC_INSTRUCTIONS.strip())
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

    assert client.put("/api/assistant/config", json={"instructions": ""}).json()["instructions"] == assistant.DEFAULT_MUSIC_INSTRUCTIONS.strip()
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
    client.put("/api/assistant/config", json={"key": "gsk_secret_1234", "instructions": "We play DSA.", "smartInstructions": "We play DSA."})
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


@pytest.fixture
def services(monkeypatch):
    """Answers Gemini and Groq requests with the next prepared content of each service and remembers the requests."""
    calls = []
    answers = {"gemini": [], "groq": []}

    def urlopen(request, timeout=None):
        host = urllib.parse.urlparse(request.full_url).hostname or ""
        service = "groq" if host.lower() == "api.groq.com" else "gemini"
        calls.append({"service": service, "headers": dict(request.header_items()), "body": json.loads(request.data)})
        answer = answers[service].pop(0)
        if isinstance(answer, Exception):
            raise answer
        if service == "groq":
            return _Response(json.dumps({"choices": [{"message": {"role": "assistant", "content": answer}}]}).encode())
        return _Response(json.dumps({"candidates": [{"content": {"parts": [{"text": answer}]}}]}).encode())

    monkeypatch.setattr(assistant.urllib.request, "urlopen", urlopen)
    return calls, answers


def test_groq_answers_the_smart_search_and_the_compose_mode(client, services):
    calls, answers = services
    client.put("/api/assistant/config", json={"key": "gemini_secret_1234", "groqKey": "gsk_groq_secret_5678"})
    status = client.get("/api/assistant/config").json()
    assert status["groqConfigured"] is True and status["groqKeyHint"] == "5678"
    assert "gsk_groq_secret" not in client.get("/api/assistant/config").text
    assert client.get("/api/settings").json()["groqConfigured"] is True
    messages = [{"role": "user", "content": "Ein Kampf"}]

    answers["groq"].append(json.dumps({"message": "Kampf!", "categories": [], "tags": ["Battle"], "genres": []}))
    context = {"tags": ["Battle", "Tavern"], "genres": ["Folk"]}
    result = client.post("/api/assistant/chat", json={"messages": messages, "mode": "smart", "context": context}).json()
    assert result["filter"]["tags"] == ["Battle"]
    request = calls[-1]
    assert request["service"] == "groq" and request["headers"]["Authorization"] == "Bearer gsk_groq_secret_5678"
    assert request["headers"]["User-agent"] == assistant.USER_AGENT  # Cloudflare blocks the default agent of urllib
    body = request["body"]
    assert body["model"] == assistant.GROQ_DEFAULT_MODEL and body["reasoning_effort"] == "low"
    assert body["messages"][0]["role"] == "system" and body["messages"][1:] == messages
    assert body["response_format"]["json_schema"]["strict"] is True
    schema = body["response_format"]["json_schema"]["schema"]
    assert schema["type"] == "object" and schema["properties"]["bpm"]["type"] == ["integer", "null"]
    # strict mode: every property is required, the optional ones may be null, and no other properties are allowed
    assert set(schema["required"]) == set(schema["properties"]) and schema["additionalProperties"] is False
    assert schema["properties"]["tags"]["type"] == ["array", "null"] and schema["properties"]["message"]["type"] == "string"
    item = schema["properties"]["categories"]["items"]
    assert item["required"] == ["key", "value"] and item["additionalProperties"] is False
    assert "enum" not in json.dumps(schema)  # the prompt lists the tags and genres already

    answers["groq"].append(json.dumps({"message": "Wild", "title": "Kampf", "caption": "epic orchestral, drums", "lyrics": None, "bpm": None}))
    result = client.post("/api/assistant/chat", json={"messages": messages, "mode": "compose"}).json()
    assert result["piece"]["caption"] == "epic orchestral, drums" and calls[-1]["service"] == "groq"
    assert result["piece"]["bpm"] is None and result["piece"]["lyrics"] == ""

    # an answer Groq rejects as not matching the schema is used anyway: it is checked here
    failed = {"error": {"message": "Failed to generate JSON. Please adjust your prompt. See 'failed_generation' for more details.",
                        "type": "invalid_request_error", "code": "json_validate_failed",
                        "failed_generation": json.dumps({"message": "Wild", "title": "Kampf", "caption": "folk, fiddle", "bpm": "fast"})}}
    answers["groq"].append(urllib.error.HTTPError(assistant.GROQ_URL, 400, "Bad Request", {}, io.BytesIO(json.dumps(failed).encode())))
    result = client.post("/api/assistant/chat", json={"messages": messages, "mode": "compose"}).json()
    assert result["piece"]["caption"] == "folk, fiddle" and result["piece"]["bpm"] is None

    # the song suggestions and the general chat stay with Gemini
    answers["gemini"].append(json.dumps({"message": "Hier", "songs": [{"title": "Song", "artist": "Band"}]}))
    assert client.post("/api/assistant/chat", json={"messages": messages}).json()["songs"][0]["title"] == "Song"
    assert calls[-1]["service"] == "gemini"
    answers["gemini"].append("Eine Antwort")
    client.post("/api/assistant/chat", json={"messages": messages, "mode": "general"})
    assert calls[-1]["service"] == "gemini"


def test_groq_without_gemini_serves_only_its_modes(client, services):
    calls, answers = services
    client.put("/api/assistant/config", json={"groqKey": "gsk_groq_secret_5678", "groqModel": "openai/gpt-oss-20b"})
    assert client.get("/api/settings").json()["assistantConfigured"] is False
    messages = [{"role": "user", "content": "A fight"}]
    assert client.post("/api/assistant/chat", json={"messages": messages}).status_code == 409
    assert client.post("/api/assistant/chat", json={"messages": messages, "mode": "general"}).status_code == 409

    answers["groq"].append(json.dumps({"message": "Fight", "categories": []}))
    assert client.post("/api/assistant/chat", json={"messages": messages, "mode": "smart"}).status_code == 200
    assert calls[-1]["body"]["model"] == "openai/gpt-oss-20b"

    answers["groq"].append(urllib.error.HTTPError(assistant.GROQ_URL, 429, "Too Many Requests", {},
                                                  io.BytesIO(b'{"error": {"message": "Rate limit reached"}}')))
    response = client.post("/api/assistant/chat", json={"messages": messages, "mode": "smart"})
    assert response.status_code == 502 and "Rate limit reached" in response.json()["detail"]

    answers["groq"].append(urllib.error.HTTPError(assistant.GROQ_URL, 403, "Forbidden", {}, io.BytesIO(b"error code: 1010\n")))
    response = client.post("/api/assistant/chat", json={"messages": messages, "mode": "smart"})
    assert "Forbidden: error code: 1010" in response.json()["detail"]

    assert client.delete("/api/assistant/config", params={"service": "groq"}).json()["groqConfigured"] is False
    assert client.post("/api/assistant/chat", json={"messages": messages, "mode": "smart"}).status_code == 409


def test_each_mode_gets_its_own_instructions(client):
    songs = "Gib bei jeder Anfrage genau 10 Stücke als nummerierte Liste mit YouTube-Links aus."
    client.put("/api/assistant/config", json={"key": "gemini_secret_1234", "instructions": songs, "generalInstructions": "DSA 4.1",
                                              "composeInstructions": "Thorwal klingt nordisch."})
    assert client.get("/api/assistant/config").json()["composeInstructions"] == "Thorwal klingt nordisch."

    # the song suggestions ask for a list of songs: the compose mode must not get them, or it answers with songs
    compose = assistant.system_prompt("compose")
    assert songs not in compose and "Thorwal klingt nordisch." in compose
    assert songs in assistant.system_prompt("music") and "Thorwal" not in assistant.system_prompt("music")
    assert "DSA 4.1" in assistant.system_prompt("general") and songs not in assistant.system_prompt("general")
    # the smart search has instructions of its own (the default), the ones of the song suggestions are not used there
    smart = assistant.system_prompt("smart", {"tags": [], "genres": []})
    assert songs not in smart and smart.endswith(assistant.DEFAULT_SETTING_INSTRUCTIONS.strip())

    client.put("/api/assistant/config", json={"smartInstructions": "Kämpfe brauchen viel Energie."})
    smart = assistant.system_prompt("smart", {"tags": [], "genres": []})
    assert "Kämpfe brauchen viel Energie." in smart and songs not in smart
    assert client.get("/api/assistant/config").json()["smartInstructions"] == "Kämpfe brauchen viel Energie."

    assert client.get("/api/assistant/config").json()["instructions"] == songs


def test_the_modes_have_default_instructions_until_they_are_changed(client):
    music, setting = assistant.DEFAULT_MUSIC_INSTRUCTIONS.strip(), assistant.DEFAULT_SETTING_INSTRUCTIONS.strip()
    status = client.get("/api/assistant/config").json()
    assert (status["instructions"], status["smartInstructions"], status["composeInstructions"]) == (music, setting, setting)
    assert "Barde von Aventurien" in music and "Thorwal" in setting
    assert status["generalInstructions"] == "" and status["effectsInstructions"] == ""  # no defaults for these
    assert assistant.system_prompt("music").endswith(music)
    assert assistant.system_prompt("compose").endswith(setting)
    assert assistant.system_prompt("smart", {"tags": [], "genres": []}).endswith(setting)

    status = client.put("/api/assistant/config", json={"instructions": "Only lutes.", "smartInstructions": "Nur Flöten."}).json()
    assert (status["instructions"], status["smartInstructions"]) == ("Only lutes.", "Nur Flöten.")
    assert assistant.system_prompt("music").endswith("Only lutes.") and assistant.system_prompt("smart", {"tags": [], "genres": []}).endswith("Nur Flöten.")

    # empty, or the default text itself, brings the default back (nothing is stored then)
    status = client.put("/api/assistant/config", json={"instructions": "", "smartInstructions": setting}).json()
    assert (status["instructions"], status["smartInstructions"]) == (music, setting)
    assert not AppSettings.contains(SettingKeys.ASSISTANT_INSTRUCTIONS) and not AppSettings.contains(SettingKeys.ASSISTANT_SMART_INSTRUCTIONS)
    assert client.put("/api/assistant/config", json={"generalInstructions": ""}).json()["generalInstructions"] == ""


def test_the_built_in_prompts_can_be_changed_and_restored(client):
    prompts = {entry["name"]: entry for entry in client.get("/api/assistant/config").json()["prompts"]}
    assert set(prompts) == set(assistant.PROMPTS)
    assert all(entry["value"] == entry["default"] for entry in prompts.values())

    changed = "Antworte immer als Barde. {categories} | {tags} | {genres} | {min}-{max} {unbekannt}"
    status = client.put("/api/assistant/config", json={"prompts": {"smart.system": changed, "compose.vocals": "Singe auf Deutsch.",
                                                                   "unknown.part": "ignored"}}).json()
    values = {entry["name"]: entry["value"] for entry in status["prompts"]}
    assert values["smart.system"] == changed and values["compose.vocals"] == "Singe auf Deutsch."
    assert "unknown.part" not in values

    # the placeholders get the values of the library, other braces stay as they are
    smart = assistant.system_prompt("smart", {"tags": ["Battle"], "genres": ["Folk"]})
    assert smart.startswith("Antworte immer als Barde.") and "| Battle | Folk |" in smart and "{unbekannt}" in smart
    assert "Singe auf Deutsch." in assistant.system_prompt("compose", {"instrumental": False})
    assert assistant.VOCALS_RULE not in assistant.system_prompt("compose", {"instrumental": False})
    assert assistant.INSTRUMENTAL_RULE in assistant.system_prompt("compose", {"instrumental": True})

    # empty or the default restores the built-in prompt
    client.put("/api/assistant/config", json={"prompts": {"smart.system": "", "compose.vocals": assistant.VOCALS_RULE}})
    assert all(entry["value"] == entry["default"] for entry in client.get("/api/assistant/config").json()["prompts"])
    assert assistant.system_prompt("smart", {"tags": [], "genres": []}).startswith(assistant.smartsearch.prompt([], []))


def test_keys_and_models_can_come_from_the_environment(client, monkeypatch):
    monkeypatch.setenv("DT_GEMINI_API_KEY", "env_gemini_secret_1111")
    monkeypatch.setenv("DT_GEMINI_MODEL", "gemini-env-model")
    monkeypatch.setenv("DT_GROQ_API_KEY", "env_groq_secret_2222")
    monkeypatch.setenv("DT_GROQ_MODEL", "openai/gpt-oss-20b")
    status = client.get("/api/assistant/config").json()
    assert (status["configured"], status["keySource"], status["keyHint"], status["model"]) == (True, "environment", "1111", "gemini-env-model")
    assert (status["groqConfigured"], status["groqKeySource"], status["groqModel"]) == (True, "environment", "openai/gpt-oss-20b")
    assert "env_gemini_secret" not in client.get("/api/assistant/config").text
    assert client.get("/api/settings").json()["groqConfigured"] is True
    # a stored key wins, removing it falls back to the environment
    client.put("/api/assistant/config", json={"key": "stored_secret_3333"})
    assert assistant.api_key() == "stored_secret_3333" and client.get("/api/assistant/config").json()["keySource"] == "settings"
    assert client.delete("/api/assistant/config").json()["keySource"] == "environment"
    assert assistant.api_key() == "env_gemini_secret_1111"


def test_the_acoustid_key_can_come_from_the_environment(client, monkeypatch):
    monkeypatch.setenv("DT_ACOUSTID_API_KEY", "acoustid-env-4444")
    status = client.get("/api/metadata/config").json()
    assert (status["configured"], status["keySource"], status["keyHint"]) == (True, "environment", "4444")


def test_the_story_mode_drafts_notes(client, gemini):
    calls, answers = gemini
    client.put("/api/assistant/config", json={"key": "gsk_secret_1234", "generalInstructions": "We play DSA."})
    answers.append(json.dumps({"message": "Hier ist ein Entwurf", "text": "Ihr betretet die **Gruft**.\n\n- Ein Wächter"}))
    draft = client.post("/api/assistant/chat", json={"mode": "story", "context": None,
                                                     "messages": [{"role": "user", "content": "Gruft, Wächter"}]}).json()
    assert draft["text"] == "Ihr betretet die **Gruft**.\n\n- Ein Wächter" and draft["message"] == "Hier ist ein Entwurf" and "light" not in draft
    system = calls[0]["body"]["systemInstruction"]["parts"][0]["text"]
    assert system.startswith(assistant.STORY_DRAFT_PROMPT) and system.endswith("We play DSA.")
    assert set(calls[0]["body"]["generationConfig"]["responseSchema"]["properties"]) == {"message", "text"}


def test_the_tldr_mode_sums_up_the_whole_notes(client, gemini):
    calls, answers = gemini
    client.put("/api/assistant/config", json={"key": "gsk_secret_1234"})
    summary = "- **Wächter** an der Tür\n- weiter: [Gruft](block:b2)"
    answers.append(json.dumps({"message": "Kurzfassung", "text": summary}))
    notes = "x" * 15000  # longer than a draft may send, the summary needs all of the notes
    reply = client.post("/api/assistant/chat", json={"mode": "tldr", "messages": [{"role": "user", "content": notes}]}).json()
    assert reply["text"] == summary
    assert calls[0]["body"]["systemInstruction"]["parts"][0]["text"].startswith(assistant.STORY_TLDR_PROMPT)
    assert calls[0]["body"]["contents"][0]["parts"][0]["text"] == notes



def test_the_image_mode_has_its_own_instructions_with_a_style_default(client):
    style = assistant.DEFAULT_IMAGE_INSTRUCTIONS
    assert client.get("/api/assistant/config").json()["imageInstructions"] == style and "oil painting" in style
    assert assistant.system_prompt("image").endswith(style)
    client.put("/api/assistant/config", json={"generalInstructions": "Wir spielen DSA 4.1."})
    assert "DSA 4.1" not in assistant.system_prompt("image")  # the general chat instructions no longer reach the pictures

    status = client.put("/api/assistant/config", json={"imageInstructions": "watercolor, soft light"}).json()
    assert status["imageInstructions"] == "watercolor, soft light"
    assert assistant.system_prompt("image").endswith("watercolor, soft light")
    assert client.put("/api/assistant/config", json={"imageInstructions": ""}).json()["imageInstructions"] == style


def test_dictation_transcribes_with_groq_whisper(client, services, monkeypatch):
    calls, _answers = services
    assert client.get("/api/settings").json()["dictationConfigured"] is False
    audio = {"file": ("dictation.webm", b"AUDIO", "audio/webm;codecs=opus")}
    assert client.post("/api/assistant/transcribe", files=audio).status_code == 409
    client.put("/api/assistant/config", json={"groqKey": "gsk_groq_secret_5678"})
    assert client.get("/api/settings").json()["dictationConfigured"] is True

    sent = []

    def urlopen(request, timeout=None):
        sent.append({"url": request.full_url, "headers": dict(request.header_items()), "body": request.data})
        return _Response(json.dumps({"text": " Eine Taverne. "}).encode())

    monkeypatch.setattr(assistant.urllib.request, "urlopen", urlopen)
    result = client.post("/api/assistant/transcribe", files=audio, data={"language": "de"})
    assert result.json() == {"text": "Eine Taverne."}
    assert sent[0]["url"] == "https://api.groq.com/openai/v1/audio/transcriptions"
    assert sent[0]["headers"]["Authorization"] == "Bearer gsk_groq_secret_5678"
    assert b"whisper-large-v3-turbo" in sent[0]["body"] and b'name="language"\r\n\r\nde' in sent[0]["body"] and b"AUDIO" in sent[0]["body"]
    assert b'filename="dictation.webm"' in sent[0]["body"]
    assert calls == []


def test_dictation_falls_back_to_gemini_and_validates_the_recording(client, services):
    calls, answers = services
    client.put("/api/assistant/config", json={"key": "gemini_secret_1234"})
    answers["gemini"].append("Eine Taverne.")
    result = client.post("/api/assistant/transcribe", files={"file": ("a.ogg", b"AUDIO", "audio/ogg")})
    assert result.json() == {"text": "Eine Taverne."}
    part = calls[0]["body"]["contents"][0]["parts"][1]["inline_data"]
    assert part["mime_type"] == "audio/ogg" and part["data"] == "QVVESU8="
    assert client.post("/api/assistant/transcribe", files={"file": ("a.ogg", b"", "audio/ogg")}).status_code == 502
    too_long = b"0" * (10 * 1024 * 1024 + 1)
    assert client.post("/api/assistant/transcribe", files={"file": ("a.ogg", too_long, "audio/ogg")}).status_code == 502
    assert client.post("/api/assistant/transcribe", files={"file": ("a.ogg", b"A", "audio/ogg")}, data={"language": "Deutsch!"}).status_code == 422
