import pytest

from conftest import write_mp3
from core.analyzer import AnalyzerBackend, analyze_file, collect_files, is_analyzed
from core.mp3 import parse_mp3
from core.settings import get_category_keys


class _StaticBackend(AnalyzerBackend):
    def __init__(self, response):
        self.response = response
        self.calls = 0

    def analyze_mp3(self, file_path):
        self.calls += 1
        return self.response


def _full_response(summary="Analyzed with Voxalyzer 1.0"):
    return {"summary": summary, "categories": [{"category": key, "scale": 5} for key in get_category_keys()], "tags": ["Calm"]}


def test_analysis_writes_categories_genres_and_bpm(mp3_file):
    messages = []
    response = {"categories": {key: 4 for key in get_category_keys()}, "tags": ["Calm"], "genres": ["Ambient"], "bpm": 97.4}

    assert analyze_file(mp3_file, _StaticBackend(response), progress=messages.append, skip_analyzed=False) is True

    entry = parse_mp3(mp3_file)
    assert set(entry.categories) == set(get_category_keys())
    assert entry.genres == ["Ambient"] and entry.bpm == 97
    assert len(messages) == 2


def test_missing_genres_and_bpm_keep_existing_values(mp3_file):
    analyze_file(mp3_file, _StaticBackend({"categories": {"Energy": 1}, "genres": ["Rock"], "bpm": 120}), skip_analyzed=False)
    analyze_file(mp3_file, _StaticBackend({"categories": {"Energy": 2}, "genres": [], "bpm": None}), skip_analyzed=False)

    entry = parse_mp3(mp3_file)
    assert entry.categories == {"Energy": 2} and entry.genres == ["Rock"] and entry.bpm == 120


def test_already_analyzed_files_are_skipped(mp3_file):
    backend = _StaticBackend({"summary": "Real summary", "categories": [{"category": k, "scale": 1} for k in get_category_keys()]})
    analyze_file(mp3_file, backend, skip_analyzed=True)
    assert is_analyzed(mp3_file)

    assert analyze_file(mp3_file, backend, skip_analyzed=True) is False
    assert backend.calls == 1


def test_voxalyzer_summaries_are_not_final(mp3_file):
    analyze_file(mp3_file, _StaticBackend(_full_response()), skip_analyzed=False)
    assert not is_analyzed(mp3_file)


def test_response_without_categories_changes_nothing(mp3_file):
    assert analyze_file(mp3_file, _StaticBackend({"summary": "x"}), skip_analyzed=False) is False
    assert analyze_file(mp3_file, _StaticBackend(None), skip_analyzed=False) is False
    assert parse_mp3(mp3_file).summary == ""


def test_backend_errors_propagate(mp3_file):
    class Failing(AnalyzerBackend):
        def analyze_mp3(self, file_path):
            raise ConnectionError("down")

    with pytest.raises(ConnectionError):
        analyze_file(mp3_file, Failing(), skip_analyzed=False)


def test_collect_files(tmp_path):
    a = write_mp3(tmp_path / "a.mp3")
    write_mp3(tmp_path / "sub" / "b.mp3")

    assert collect_files(a) == [a]
    assert sorted(p.name for p in collect_files(tmp_path)) == ["a.mp3", "b.mp3"]
