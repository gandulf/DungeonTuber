import { describe, expect, it } from 'vitest';
import { blockPrompt, cardText, MAX_TLDR_SOURCE, plainText, rankTracks, tagsAndGenres, tldrPrompt } from './adventureAi';
import type { Track } from './types';

const song = (name: string, categories: Record<string, number>, tags: string[] = [], genres: string[] = []): Track =>
  ({ id: name, name, title: name, categories, tags, genres, bpm: null } as unknown as Track);

describe('plainText', () => {
  it('drops marks, links and images but keeps the words', () => {
    const text = plainText('# The **door**\n\n> Roll [perception](block:b1) and [[Crypt]]\n\n![map](image:0123456789ab.png)\n- a *key*\n\n\n\nEnd');
    expect(text).toBe('The door\n\nRoll perception and Crypt\n\na key\n\nEnd');
  });

  it('cuts long notes', () => {
    expect(plainText('word '.repeat(1000)).length).toBeLessThanOrEqual(1500);
  });

  it('joins the title and the notes of a block', () => {
    expect(blockPrompt({ title: ' Arrival ', markdown: 'A **dark** road' })).toBe('Arrival\n\nA dark road');
    expect(blockPrompt({ title: '', markdown: '' })).toBe('');
  });
});

describe('tagsAndGenres', () => {
  it('lists every spelling once, sorted', () => {
    const found = tagsAndGenres([song('a', {}, ['Dark', 'ritual'], ['Ambient']), song('b', {}, ['dark', 'Combat'], ['ambient'])]);
    expect(found.tags).toEqual(['Combat', 'Dark', 'ritual']);
    expect(found.genres).toEqual(['Ambient']);
  });
});

describe('rankTracks', () => {
  it('puts the closest songs first and skips songs the filter cannot judge', () => {
    const tracks = [song('far', { Darkness: 1 }), song('near', { Darkness: 9 }), song('mid', { Darkness: 6 })];
    const ranked = rankTracks(tracks, { categories: { Darkness: 9 }, tags: [], genres: [], bpm: null }, 2);
    expect(ranked.map((item) => item.track.name)).toEqual(['near', 'mid']);
    expect(rankTracks(tracks, { categories: {}, tags: [], genres: [], bpm: null })).toEqual([]);
  });

  it('counts missing tags against a song', () => {
    const tracks = [song('plain', { Darkness: 9 }), song('tagged', { Darkness: 9 }, ['Ritual'])];
    const ranked = rankTracks(tracks, { categories: { Darkness: 9 }, tags: ['Ritual'], genres: [], bpm: null });
    expect(ranked.map((item) => item.track.name)).toEqual(['tagged', 'plain']);
  });
});

describe('tldrPrompt', () => {
  it('sends the whole notes with their links, cut to what the server takes', () => {
    const prompt = tldrPrompt('Crypt', { title: 'Door', markdown: 'Roll [perception](block:b1).' }, ' only checks ');
    expect(prompt.split('\n')).toEqual(['Adventure: Crypt', 'Scene: Door', 'Wishes: only checks', 'Notes (Markdown):', 'Roll [perception](block:b1).']);
    expect(tldrPrompt('A', { title: 'B', markdown: 'x'.repeat(30000) })).toHaveLength(MAX_TLDR_SOURCE);
  });
});

describe('cardText', () => {
  it('shows the summary point by point, else the notes', () => {
    expect(cardText({ tldr: '- **Goal**: the crypt\n- go to [Door](block:b2)', markdown: 'Long notes' })).toBe('Goal: the crypt · go to Door');
    expect(cardText({ tldr: '  ', markdown: '> The *wind* howls.' })).toBe('The wind howls.');
  });
});
