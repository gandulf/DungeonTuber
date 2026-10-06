import pytest

from conftest import write_mp3
from core.analyzer import MockBackend, AnalyzerBackend, analyze_file, collect_files, is_analyzed, _analyze_url
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


def test_mock_backend_writes_categories(mp3_file):
    messages = []

    assert analyze_file(mp3_file, MockBackend(), progress=messages.append, skip_analyzed=False) is True

    entry = parse_mp3(mp3_file)
    assert set(entry.categories) == set(get_category_keys())
    assert len(messages) == 2


def test_already_analyzed_files_are_skipped(mp3_file):
    backend = _StaticBackend({"summary": "Real summary", "categories": [{"category": k, "scale": 1} for k in get_category_keys()]})
    analyze_file(mp3_file, backend, skip_analyzed=True)
    assert is_analyzed(mp3_file)

    assert analyze_file(mp3_file, backend, skip_analyzed=True) is False
    assert backend.calls == 1


def test_mock_and_voxalyzer_summaries_are_not_final(mp3_file):
    analyze_file(mp3_file, MockBackend(), skip_analyzed=False)
    assert not is_analyzed(mp3_file)

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


@pytest.mark.parametrize("url, expected", [
    ("http://host:8000", "http://host:8000/analyze"),
    ("http://host:8000/", "http://host:8000/analyze"),
    ("http://host:8000/analyze", "http://host:8000/analyze"),
    ("", None),
    (None, None),
    ("None", None),
])
def test_analyze_url(url, expected):
    assert _analyze_url(url) == expected
