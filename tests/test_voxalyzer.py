import hashlib
import os
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agents" / "voxalyzer"))
from voxalyzer import cli, models  # noqa: E402
from voxalyzer.utils import get_best, rescale, to_ten  # noqa: E402


def test_parser_without_paths_means_agent_mode():
    args = cli.build_parser().parse_args(["--token", "t"])
    assert args.paths == [] and args.token == "t" and not args.fake and not args.force


def test_parser_accepts_flags_and_paths():
    args = cli.build_parser().parse_args(["--force", "--clean", "--fake", "a.mp3", "dir"])
    assert args.force and args.clean and args.fake
    assert args.paths == ["a.mp3", "dir"]


def test_agent_mode_needs_a_token(monkeypatch):
    monkeypatch.delenv("DT_AGENT_TOKEN", raising=False)
    with pytest.raises(SystemExit) as exit_info:
        cli.main([])
    assert exit_info.value.code == 2


def test_log_dir_uses_appdata_or_falls_back(monkeypatch, tmp_path):
    monkeypatch.setenv("APPDATA", str(tmp_path))
    assert cli.log_dir() == tmp_path / "DungeonTuber" / "logs"
    monkeypatch.delenv("APPDATA")
    assert cli.log_dir().parts[-2:] == ("DungeonTuber", "logs")
    assert cli.log_dir().parts[:len(tmp_path.parts)] != tmp_path.parts


def test_every_model_of_the_analyzer_is_listed():
    source = (Path(__file__).resolve().parent.parent / "agents" / "voxalyzer" / "voxalyzer" / "analyzer.py").read_text(encoding="utf-8")
    used = set(re.findall(r'model_path\("([^"]+)"\)', source))
    assert used == set(models.MODELS) and len(used) == 16


@pytest.fixture
def served_models(tmp_path, monkeypatch):
    """Two small 'models' served from a folder through a file:// URL."""
    server = tmp_path / "server"
    server.mkdir()
    files = {"a.onnx": b"first", "b.onnx": b"second"}
    for name, content in files.items():
        (server / name).write_bytes(content)
    monkeypatch.setattr(models, "MODELS", {name: hashlib.sha256(content).hexdigest() for name, content in files.items()})
    monkeypatch.setenv("DT_MODELS_URL", server.as_uri())
    monkeypatch.setenv("DT_MODEL_DIR", str(tmp_path / "cache"))
    return server


def test_missing_models_are_downloaded_and_verified(served_models, tmp_path):
    directory = models.ensure_models()

    assert directory == tmp_path / "cache"
    assert (directory / "a.onnx").read_bytes() == b"first" and (directory / "b.onnx").read_bytes() == b"second"
    assert not list(directory.glob("*.part"))
    assert models.model_path("a.onnx") == str(directory / "a.onnx")


def test_existing_models_are_not_downloaded_again(served_models, tmp_path):
    models.ensure_models()
    (served_models / "a.onnx").unlink()  # would fail if the file was requested again

    models.ensure_models()


def test_damaged_models_are_replaced_and_bad_downloads_rejected(served_models, tmp_path):
    models.ensure_models()
    (tmp_path / "cache" / "a.onnx").write_bytes(b"damaged")
    models.ensure_models()
    assert (tmp_path / "cache" / "a.onnx").read_bytes() == b"first"

    (served_models / "b.onnx").write_bytes(b"tampered")
    (tmp_path / "cache" / "b.onnx").unlink()
    with pytest.raises(OSError, match="b.onnx"):
        models.ensure_models()
    assert not (tmp_path / "cache" / "b.onnx").exists() and not list((tmp_path / "cache").glob("*.part"))


def test_to_ten_and_rescale():
    assert to_ten(0.5) == 5
    assert to_ten(1.05) == 10
    with pytest.raises(Exception):
        to_ten(-0.1)
    assert rescale(5) == 5.0
    with pytest.raises(Exception):
        rescale(0)


def test_get_best_returns_labels_above_threshold_or_top_one():
    assert get_best(["a", "b", "c"], [0.1, 0.5, 0.4]) == ["b", "c"]
    assert get_best(["a", "b"], [0.1, 0.2]) == ["b"]


def test_process_paths_skips_unknown_arguments(caplog):
    pytest.importorskip("librosa")
    pytest.importorskip("onnxruntime")
    cli.process_paths([os.path.join("no", "such", "file.txt")])
    assert "Unrecognized argument" in caplog.text
