import { describe, expect, it } from 'vitest';
import { bpmLevel, calculateScore, categoryLevel, emptyFilter, genreLevel, scoreLevel } from './scoring';
import type { FilterConfig } from './types';

const track = (data: Partial<{ categories: Record<string, number>; tags: string[]; genres: string[]; bpm: number | null }> = {}) => ({
  categories: {}, tags: [], genres: [], bpm: null, ...data,
});
const filter = (data: Partial<FilterConfig> = {}): FilterConfig => ({ categories: {}, tags: [], genres: [], bpm: null, ...data });

// Same cases as tests/test_scoring.py
describe('calculateScore', () => {
  it('returns null without filter', () => {
    expect(calculateScore(track({ categories: { Valence: 5 } }), filter())).toBeNull();
    expect(calculateScore(track(), filter({ categories: { Valence: null, Arousal: -1 } }))).toBeNull();
  });

  it('squares category distances', () => {
    const t = track({ categories: { Valence: 5, Arousal: 2 } });
    expect(calculateScore(t, filter({ categories: { Valence: 7 } }))).toBe(4);
    expect(calculateScore(t, filter({ categories: { Valence: 7, Arousal: 5 } }))).toBe(13);
    expect(calculateScore(track(), filter({ categories: { Darkness: 3 } }))).toBe(100);
  });

  it('matches tags against tags and genres', () => {
    const t = track({ tags: ['Dark'], genres: ['Metal'] });
    expect(calculateScore(t, filter({ tags: ['Dark'] }))).toBe(0);
    expect(calculateScore(t, filter({ tags: ['Metal'] }))).toBe(0);
    expect(calculateScore(t, filter({ tags: ['Happy'] }))).toBe(100);
  });

  it('handles genres and bpm', () => {
    const t = track({ genres: ['Rock'], bpm: 120 });
    expect(calculateScore(t, filter({ genres: ['Rock'], bpm: 100 }))).toBe(20);
    expect(calculateScore(t, filter({ genres: ['Pop'] }))).toBe(100);
    expect(calculateScore(track(), filter({ bpm: 100 }))).toBe(100);
  });

  it('rounds like python', () => {
    expect(calculateScore(track({ categories: { Valence: 5.5 } }), filter({ categories: { Valence: 7 } }))).toBe(2);
  });
});

describe('levels', () => {
  it('computes color levels', () => {
    expect(categoryLevel(5, 7)).toBe(0);
    expect(categoryLevel(0, 5)).toBe(1);
    expect(categoryLevel(0, 9)).toBe(2);
    expect(bpmLevel(100, 130)).toBe(0);
    expect(bpmLevel(100, 200)).toBe(2);
    expect(genreLevel(['Rock', 'Pop'], ['Rock'])).toBe(1);
    expect([null, 10, 60, 120, 200].map((s) => scoreLevel(s))).toEqual([null, 0, 1, 2, 3]);
    expect(emptyFilter(filter())).toBe(true);
    expect(emptyFilter(filter({ bpm: 80 }))).toBe(false);
  });
});
