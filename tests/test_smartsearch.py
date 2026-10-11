from core.settings import CATEGORY_MAX, CATEGORY_MIN, get_music_categories
from server import smartsearch


def _keys():
    return [category.key for category in get_music_categories()]


def test_prompt_lists_categories_tags_and_genres():
    text = smartsearch.prompt(["Battle", "battle ", "Tavern"], ["Folk"])
    for key in _keys():
        assert f"- {key} (" in text
    assert "Battle, Tavern" in text
    assert "Folk" in text
    assert f"from {CATEGORY_MIN} to {CATEGORY_MAX}" in text


def test_prompt_without_tags_or_genres():
    text = smartsearch.prompt([], [])
    assert text.count("(none)") == 2


def test_schema_restricts_values_to_known_ones():
    schema = smartsearch.schema(["Battle", "BATTLE", ""], ["Folk"])
    properties = schema["properties"]
    assert properties["categories"]["items"]["properties"]["key"]["enum"] == _keys()
    assert properties["tags"]["items"]["enum"] == ["Battle"]
    assert properties["genres"]["items"]["enum"] == ["Folk"]
    assert schema["required"] == ["message", "categories"]


def test_schema_omits_empty_tags_and_genres():
    properties = smartsearch.schema([], None)["properties"]
    assert "tags" not in properties
    assert "genres" not in properties


def test_to_filter_clamps_and_drops_unknown_categories():
    key = _keys()[0]
    parsed = {"categories": [
        {"key": key, "value": CATEGORY_MAX + 50},
        {"key": "unknown", "value": 3},
        {"key": key},
        "garbage",
    ]}
    result = smartsearch.to_filter(parsed, [], [])
    assert result["categories"] == {key: CATEGORY_MAX}

    parsed = {"categories": [{"key": key, "value": "abc"}]}
    assert smartsearch.to_filter(parsed, [], [])["categories"] == {}

    parsed = {"categories": [{"key": key, "value": CATEGORY_MIN - 50}]}
    assert smartsearch.to_filter(parsed, [], [])["categories"] == {key: CATEGORY_MIN}


def test_to_filter_picks_known_tags_and_genres_in_library_spelling():
    parsed = {"tags": ["battle", "Unknown", "TAVERN", "Forest", "battle"], "genres": ["folk", "Metal"]}
    result = smartsearch.to_filter(parsed, ["Battle", "Tavern", "Forest"], ["Folk", "Metal"])
    assert result["tags"] == ["Battle", "Tavern"]
    assert result["genres"] == ["Folk"]


def test_to_filter_ignores_non_list_tags():
    result = smartsearch.to_filter({"tags": "Battle", "genres": None}, ["Battle"], [])
    assert result["tags"] == []
    assert result["genres"] == []


def test_to_filter_bpm():
    low, high = smartsearch.BPM_RANGE
    assert smartsearch.to_filter({"bpm": 120.4}, [], [])["bpm"] == 120
    assert smartsearch.to_filter({"bpm": low - 1}, [], [])["bpm"] is None
    assert smartsearch.to_filter({"bpm": high + 1}, [], [])["bpm"] is None
    assert smartsearch.to_filter({"bpm": "fast"}, [], [])["bpm"] is None
    assert smartsearch.to_filter({}, [], [])["bpm"] is None
