"""The mood tags of the Voxalyzer: the MIREX cluster plus the strongest mood/theme labels."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "agents" / "voxalyzer"))
from voxalyzer.utils import mood_tags  # noqa: E402

LABELS = ["epic", "dark", "melancholic", "corporate", "calm", "adventure"]


def test_the_strongest_moods_join_the_cluster():
    assert mood_tags("Exuberant", LABELS, [0.6, 0.4, 0.05, 0.0, 0.02, 0.3]) == ["Exuberant", "Epic", "Dark", "Adventure"]


def test_at_most_the_limit_and_only_above_the_threshold():
    assert mood_tags("Aggressive", LABELS, [0.6, 0.4, 0.3, 0.0, 0.2, 0.15], limit=2) == ["Aggressive", "Epic", "Dark"]
    assert mood_tags("Cheerful", LABELS, [0.09, 0.05, 0.01, 0.0, 0.02, 0.03]) == ["Cheerful"]


def test_duplicates_and_ignored_themes_are_skipped():
    tags = mood_tags("Melancholic", LABELS, [0.1, 0.2, 0.5, 0.9, 0.0, 0.0], ignore=frozenset({"corporate"}))
    assert tags == ["Melancholic", "Dark", "Epic"]
