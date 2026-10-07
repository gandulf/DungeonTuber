import json
import sys
from pathlib import Path

import pytest

from core import agentconfig

ROOT = Path(__file__).resolve().parent.parent
COPIES = [ROOT / "agents" / "wiz" / "agentconfig.py", ROOT / "agents" / "voxalyzer" / "voxalyzer" / "agentconfig.py"]

sys.path.insert(0, str(ROOT / "agents" / "voxalyzer"))
sys.path.insert(0, str(ROOT / "agents" / "youtube"))
from voxalyzer import cli as vox_cli  # noqa: E402
import dt_youtube_agent  # noqa: E402


@pytest.fixture(autouse=True)
def clean_environment(monkeypatch, tmp_path):
    for name in ("DT_SERVER", "DT_AGENT_TOKEN", "DT_AGENT_NAME", "DT_AGENT_CONFIG"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))  # an agents.json of the developer must not leak into the tests
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg"))
    monkeypatch.setattr(sys, "argv", [str(tmp_path / "nowhere" / "agent.py")])


def write_config(path: Path, **values):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(values), encoding="utf-8")
    return path


def test_the_agents_use_the_same_code():
    original = agentconfig.__file__
    for copy in COPIES:
        assert copy.read_text(encoding="utf-8") == Path(original).read_text(encoding="utf-8"), f"{copy} differs from core/agentconfig.py"


def test_config_is_searched_in_order(monkeypatch, tmp_path):
    assert agentconfig.agent_config() == {}

    write_config(agentconfig.data_dir() / "agents.json", server="https://data.example.com", token="data-token")
    assert agentconfig.agent_config()["server"] == "https://data.example.com"

    write_config(tmp_path / "nowhere" / "agents.json", server="https://program.example.com", token="program-token", name="pc")
    assert agentconfig.agent_config() == {"server": "https://program.example.com", "token": "program-token", "name": "pc"}

    explicit = write_config(tmp_path / "explicit.json", token="explicit-token", ignored="x", name="")
    monkeypatch.setenv("DT_AGENT_CONFIG", str(explicit))
    assert agentconfig.agent_config() == {"token": "explicit-token"}  # unknown and empty keys are dropped


def test_broken_files_are_ignored(tmp_path):
    (tmp_path / "nowhere").mkdir()
    (tmp_path / "nowhere" / "agents.json").write_text("not json", encoding="utf-8")
    assert agentconfig.agent_config() == {}
    (tmp_path / "nowhere" / "agents.json").write_text("[1, 2]", encoding="utf-8")
    assert agentconfig.agent_config() == {}


@pytest.mark.parametrize("build", [dt_youtube_agent.build_parser, vox_cli.build_parser])
def test_command_line_beats_environment_beats_file(build, monkeypatch, tmp_path):
    write_config(tmp_path / "nowhere" / "agents.json", server="https://file.example.com", token="file-token", name="file-name")
    args = build().parse_args([])
    assert (args.server, args.token, args.name) == ("https://file.example.com", "file-token", "file-name")

    monkeypatch.setenv("DT_SERVER", "https://env.example.com")
    monkeypatch.setenv("DT_AGENT_TOKEN", "env-token")
    args = build().parse_args([])
    assert (args.server, args.token, args.name) == ("https://env.example.com", "env-token", "file-name")

    args = build().parse_args(["--server", "https://cli.example.com", "--token", "cli-token"])
    assert (args.server, args.token) == ("https://cli.example.com", "cli-token")
