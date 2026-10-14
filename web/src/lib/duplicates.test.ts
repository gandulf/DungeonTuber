import { describe, expect, it } from 'vitest';
import { duplicateKey, findDuplicates } from './duplicates';
import type { Track } from './types';

const song = (id: string, title: string | null, artist: string | null, length: number, name = id): Track => ({ id, name, title, artist, length, path: `/music/${id}.mp3` } as Track);

describe('duplicates', () => {
  it('ignores case, accents and punctuation', () => {
    expect(duplicateKey(song('a', 'Café Théâtre!', 'The BARD', 1))).toBe(duplicateKey(song('b', 'cafe theatre', 'the bard', 1)));
  });

  it('uses the file name when a song has no title', () => {
    expect(duplicateKey(song('a', null, null, 1, 'Tavern Song'))).toBe('tavern song');
    expect(duplicateKey(song('a', null, null, 1, '!!!'))).toBe('');
  });

  it('groups the same song of different folders and keeps different versions apart', () => {
    const result = findDuplicates([
      song('1', 'Tavern', 'Bard', 180),
      song('2', 'tavern', 'bard', 181),
      song('3', 'Tavern', 'Bard', 300), // a long version
      song('4', 'Tavern', 'Other', 180),
      song('5', 'Forest', 'Bard', 120),
    ]);
    expect(result.tracks.map((track) => track.id)).toEqual(['1', '2']);
    expect(result.groupCount).toBe(1);
    expect(result.groups['1']).toBe(result.groups['2']);
    expect(result.groups['3']).toBeUndefined();
    expect(result.kinds['1']).toBe('similar');
  });

  it('finds files with the same content whatever they are called', () => {
    const result = findDuplicates([song('a', 'Inn', 'Bard', 100), song('b', 'Totally different', 'Someone', 100), song('c', 'Forest', 'Bard', 50)], [['a', 'b'], ['x', 'y']]);
    expect(result.tracks.map((track) => track.id).sort()).toEqual(['a', 'b']);
    expect(result.kinds).toEqual({ a: 'exact', b: 'exact' });
    expect(result.groupCount).toBe(1);
  });

  it('puts songs that are linked by content and by name into one group', () => {
    const result = findDuplicates(
      [song('a', 'Inn', 'Bard', 100), song('b', 'Other name', 'Bard', 100), song('c', 'inn', 'bard', 101)],
      [['a', 'b']],
    );
    expect(result.groupCount).toBe(1);
    expect(new Set(Object.values(result.groups)).size).toBe(1);
    expect(result.kinds).toEqual({ a: 'exact', b: 'exact', c: 'similar' });
  });
});
