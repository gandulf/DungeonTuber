from core.mp3 import Mp3Entry
from core.scoring import calculate_score, category_distance_level, bpm_distance_level, genre_match_level, score_level
from core.settings import FilterConfig


def _entry(**kwargs):
    return Mp3Entry("x.mp3", name="x.mp3", **kwargs)


def test_no_filter_gives_no_score():
    assert calculate_score(_entry(categories={"Valence": 5}), FilterConfig()) is None


def test_unset_category_values_are_ignored():
    assert calculate_score(_entry(), FilterConfig(categories={"Valence": None, "Arousal": -1})) is None


def test_category_distance_is_squared():
    entry = _entry(categories={"Valence": 5, "Arousal": 2})

    assert calculate_score(entry, FilterConfig(categories={"Valence": 7})) == 4
    assert calculate_score(entry, FilterConfig(categories={"Valence": 7, "Arousal": 5})) == 13


def test_missing_category_costs_100():
    assert calculate_score(_entry(), FilterConfig(categories={"Darkness": 3})) == 100


def test_tags_match_tags_or_genres():
    entry = _entry(tags=["Dark"], genre=["Metal"])

    assert calculate_score(entry, FilterConfig(tags=["Dark"])) == 0
    assert calculate_score(entry, FilterConfig(tags=["Metal"])) == 0
    assert calculate_score(entry, FilterConfig(tags=["Happy"])) == 100


def test_genres_and_bpm():
    entry = _entry(genre=["Rock"], bpm=120)

    assert calculate_score(entry, FilterConfig(genres=["Rock"], bpm=100)) == 20
    assert calculate_score(entry, FilterConfig(genres=["Pop"])) == 100
    assert calculate_score(_entry(), FilterConfig(bpm=100)) == 100


def test_float_categories_are_rounded():
    assert calculate_score(_entry(categories={"Valence": 5.5}), FilterConfig(categories={"Valence": 7})) == 2


def test_levels():
    assert category_distance_level(5, 7) == 0
    assert category_distance_level(0, 5) == 1
    assert category_distance_level(0, 9) == 2
    assert category_distance_level(None, 3) is None

    assert bpm_distance_level(0, 100) is None
    assert bpm_distance_level(100, 130) == 0
    assert bpm_distance_level(100, 170) == 1
    assert bpm_distance_level(100, 200) == 2

    assert genre_match_level(["Rock", "Pop"], ["Rock", "Pop"]) == 0
    assert genre_match_level(["Rock", "Pop"], "Rock, Jazz") == 1
    assert genre_match_level(["Rock"], ["Jazz"]) == 2
    assert genre_match_level([], ["Jazz"]) is None

    assert [score_level(s) for s in (None, 10, 60, 120, 200)] == [None, 0, 1, 2, 3]
