// Port of core/scoring.py – keep both in sync (see scoring.test.ts).
import type { FilterConfig, Track } from './types';

export const MISSING_CATEGORY_PENALTY = 100;
export const MISSING_TAG_PENALTY = 100;
export const MISSING_BPM_PENALTY = 100;

// Python's round() uses banker's rounding.
function pyRound(value: number): number {
  const floor = Math.floor(value);
  const diff = value - floor;
  if (Math.abs(diff - 0.5) < 1e-9) return floor % 2 === 0 ? floor : floor + 1;
  return Math.round(value);
}

export function calculateScore(track: Pick<Track, 'categories' | 'tags' | 'genres' | 'bpm'>, filter: FilterConfig): number | null {
  let score: number | null = null;

  for (const [key, desired] of Object.entries(filter.categories)) {
    if (desired !== null && desired !== undefined && desired >= 0) {
      score ??= 0;
      const current = track.categories?.[key];
      score += typeof current === 'number' ? (current - desired) ** 2 : MISSING_CATEGORY_PENALTY;
    }
  }

  const tags = track.tags ?? [];
  const genres = track.genres ?? [];

  for (const tag of filter.tags) {
    score ??= 0;
    if (!tags.includes(tag) && !genres.includes(tag)) score += MISSING_TAG_PENALTY;
  }

  for (const genre of filter.genres) {
    score ??= 0;
    if (!genres.includes(genre)) score += MISSING_TAG_PENALTY;
  }

  if (filter.bpm !== null && filter.bpm !== undefined) {
    score ??= 0;
    score += track.bpm === null || track.bpm === undefined ? MISSING_BPM_PENALTY : Math.abs(filter.bpm - track.bpm);
  }

  return score === null ? null : pyRound(score);
}

/** 0 = close, 1 = medium, 2 = far */
export function categoryLevel(desired: number | null | undefined, value: number | null | undefined): number | null {
  if (value === null || value === undefined || desired === null || desired === undefined || desired < 0) return null;
  const diff = Math.abs(desired - value);
  return diff < 4 ? 0 : diff < 7 ? 1 : 2;
}

export function bpmLevel(desired: number | null | undefined, value: number | null | undefined): number | null {
  if (value === null || value === undefined || !desired) return null;
  const diff = Math.abs(desired - value);
  return diff <= 40 ? 0 : diff <= 80 ? 1 : 2;
}

export function genreLevel(desired: string[], values: string[] | null | undefined): number | null {
  if (!values || desired.length === 0) return null;
  const found = desired.filter((genre) => values.includes(genre)).length;
  return found === desired.length ? 0 : found > 0 ? 1 : 2;
}

/** 0 = green (<50), 1 = yellow (<100), 2 = orange (<150), 3 = red */
export function scoreLevel(score: number | null): number | null {
  if (score === null) return null;
  return score < 50 ? 0 : score < 100 ? 1 : score < 150 ? 2 : 3;
}

export function emptyFilter(filter: FilterConfig): boolean {
  return Object.values(filter.categories).every((v) => v === null || v === undefined || v < 0)
    && filter.tags.length === 0 && filter.genres.length === 0 && (filter.bpm === null || filter.bpm === undefined);
}
