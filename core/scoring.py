"""Match score of a song against the current filter (lower is better).

Kept in sync with the web frontend's TypeScript port.
"""
import numbers

from core.mp3 import Mp3Entry
from core.settings import FilterConfig

MISSING_CATEGORY_PENALTY = 10 ** 2
MISSING_TAG_PENALTY = 100
MISSING_BPM_PENALTY = 100


def calculate_score(data: Mp3Entry, filter_config: FilterConfig) -> int | None:
    """Sum of squared category distances, +100 per missing tag/genre, + |bpm difference|. None if no filter is set."""
    score = None

    for cat_key, desired_value in filter_config.categories.items():
        if desired_value is not None and desired_value >= 0:
            score = score or 0
            current_value = data.get_category_value(cat_key)
            if isinstance(current_value, numbers.Number):
                score += (current_value - desired_value) ** 2
            else:
                score += MISSING_CATEGORY_PENALTY

    tags = data.tags or []
    genres = data.genres or []

    for desired_tag in filter_config.tags:
        score = score or 0
        if desired_tag not in tags and desired_tag not in genres:
            score += MISSING_TAG_PENALTY

    for desired_genre in filter_config.genres:
        score = score or 0
        if desired_genre not in genres:
            score += MISSING_TAG_PENALTY

    if filter_config.bpm is not None:
        score = score or 0
        if data.bpm is None:
            score += MISSING_BPM_PENALTY
        else:
            score += abs(filter_config.bpm - data.bpm)

    return round(score) if score is not None else None


def category_distance_level(desired_value: int | None, value: int | None) -> int | None:
    """0 = close, 1 = medium, 2 = far (used for cell coloring)."""
    if value is None or desired_value is None:
        return None
    diff = abs(desired_value - value)
    return 0 if diff < 4 else 1 if diff < 7 else 2


def bpm_distance_level(desired_value: int | None, value: int | None) -> int | None:
    if value is None or desired_value is None or desired_value == 0:
        return None
    diff = abs(desired_value - value)
    return 0 if diff <= 40 else 1 if diff <= 80 else 2


def genre_match_level(desired_values: list[str] | None, values: list[str] | str | None) -> int | None:
    """0 = all desired genres present, 1 = some, 2 = none."""
    if values is None or not desired_values:
        return None
    if isinstance(values, str):
        values = [value.strip() for value in values.split(",")]

    found = sum(1 for desired in desired_values if desired in values)
    if found == len(desired_values):
        return 0
    return 1 if found > 0 else 2


def score_level(score: int | None) -> int | None:
    """0 = green (<50), 1 = yellow (<100), 2 = orange (<150), 3 = red."""
    if score is None:
        return None
    return 0 if score < 50 else 1 if score < 100 else 2 if score < 150 else 3
