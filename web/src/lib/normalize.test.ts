import { describe, expect, it } from 'vitest';
import { fileNameFor, metadataPatch, sureMatch } from './normalize';
import type { LookupCandidate, Track } from './types';

const match = (over: Partial<LookupCandidate> = {}): LookupCandidate => ({
  title: 'Clash of Steel', artist: 'Bard', album: 'Steel', track: 3, year: '1999', length: 181, score: 97, source: 'acoustid', recording_id: 'r', ...over,
});

const song = (over: Partial<Track> = {}): Track => ({
  id: 'id', path: '/m/clash.mp3', file: 'clash.mp3', name: 'clash', title: null, artist: null, album: null, track: null, summary: '',
  genres: [], tags: [], length: 181, favorite: false, categories: {}, bpm: null, light: null, chapters: [], has_cover: false, index: null, ...over,
});

describe('sureMatch', () => {
  it('takes the best match at or above the threshold', () => {
    expect(sureMatch([match({ score: 80 }), match({ score: 96, album: 'Best of' }), match({ score: 99 })])?.score).toBe(99);
  });

  it('takes nothing below the threshold', () => {
    expect(sureMatch([match({ score: 94 })])).toBeNull();
    expect(sureMatch([])).toBeNull();
  });

  it('accepts the same song on several albums but not two different songs', () => {
    expect(sureMatch([match({ score: 100 }), match({ score: 98, album: 'Live', artist: 'BARD' })])?.album).toBe('Steel');
    expect(sureMatch([match({ score: 100 }), match({ score: 98, title: 'Clash of Iron' })])).toBeNull();
  });
});

describe('metadataPatch', () => {
  it('changes only what differs and flags the song', () => {
    const flag = { source: 'acoustid', recording_id: 'r' };
    expect(metadataPatch(song(), match())).toEqual({ title: 'Clash of Steel', artist: 'Bard', album: 'Steel', track: 3, name: 'Bard - Clash of Steel', normalized: flag });
    const tagged = song({ title: 'Clash of Steel', artist: 'Bard', album: 'Steel', track: 3, file: 'Bard - Clash of Steel.mp3' });
    expect(metadataPatch(tagged, match())).toEqual({ normalized: flag }); // already right: only flagged
    expect(metadataPatch({ ...tagged, normalized: { ...flag, source: 'acoustid', at: '2026-10-12' } }, match())).toEqual({});
  });

  it('keeps an album and track the match does not know', () => {
    expect(metadataPatch(song({ album: 'Mine', track: 7 }), match({ album: null, track: null }))).not.toHaveProperty('album');
  });
});

it('fileNameFor drops characters a file name cannot have', () => {
  expect(fileNameFor(match({ artist: 'AC/DC', title: 'What? Now' }))).toBe('AC_DC - What_ Now');
  expect(fileNameFor(match({ artist: '' }))).toBe('Clash of Steel');
});
