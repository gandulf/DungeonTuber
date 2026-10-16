import { describe, expect, it } from 'vitest';
import { matchOffsets, searchTerms } from './highlight';

describe('search highlight', () => {
  it('takes the words of the search worth marking', () => {
    expect(searchTerms('  Gruft der  Wirt a ')).toEqual(['gruft', 'wirt', 'der']);
    expect(searchTerms('Wirt wirt')).toEqual(['wirt']);
    expect(searchTerms('')).toEqual([]);
  });

  it('finds every occurrence without overlaps, longest word first', () => {
    expect(matchOffsets('Der Wirt und die Gruft, der Wirt!', ['gruft', 'wirt'])).toEqual([[4, 8], [17, 22], [28, 32]]);
    expect(matchOffsets('Kellergruft', ['gruft', 'kellergruft'].sort((a, b) => b.length - a.length))).toEqual([[0, 11]]);
    expect(matchOffsets('nothing here', ['gruft'])).toEqual([]);
  });
});
