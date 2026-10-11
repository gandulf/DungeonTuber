import { describe, expect, it } from 'vitest';
import { matcher, normalize, ranker, songQueries, withoutFillers } from './search';

const finds = (query: string, text: string) => matcher(query)(text);

describe('search', () => {
  it('normalizes case, accents and punctuation', () => {
    expect(normalize('Für a Fistful-of Dollars!')).toBe('fur a fistful of dollars');
    expect(normalize('Straße')).toBe('strasse');
  });

  it('finds the words in any order and with words in between', () => {
    expect(finds('Fistful dollars', 'Für a fistful of dollars')).toBe(true);
    expect(finds('dollars fistful', 'A Fistful of Dollars')).toBe(true);
    expect(finds('fistful euros', 'A Fistful of Dollars')).toBe(false);
  });

  it('still finds plain parts of the text', () => {
    expect(finds('ful of dol', 'A Fistful of Dollars')).toBe(true);
    expect(finds('tavern', 'The Prancing Pony Tavern')).toBe(true);
    expect(finds('', 'anything')).toBe(true);
  });

  it('tolerates small typos and unfinished words', () => {
    expect(finds('dolars', 'A Fistful of Dollars')).toBe(true);
    expect(finds('fistfull dollers', 'A Fistful of Dollars')).toBe(true);
    expect(finds('dolla', 'A Fistful of Dollars')).toBe(true);
    expect(finds('ecstasy gold', 'The Ecstasy of Gold')).toBe(true);
    expect(finds('fastful', 'A Fistful of Dollars')).toBe(true);
  });

  it('lets longer queries miss a word for every three words found', () => {
    expect(finds('The Good, The Bad and The Ugly - Main Theme', 'The Good, The Bad and The Ugly')).toBe(true);
    expect(finds('fistful of dollars theme', 'A Fistful of Dollars')).toBe(true);
    expect(finds('fistful dollars theme', 'A Fistful of Dollars')).toBe(false); // two words found are not enough
    expect(finds('fistful of dollars main theme', 'A Fistful of Dollars')).toBe(false); // two misses need six words found
    expect(finds('the good the bad theme', 'The Good, The Bad and The Ugly')).toBe(true);
    expect(finds('the good the bad main theme', 'The Good, The Bad and The Ugly')).toBe(false);
  });

  it('is strict for short words', () => {
    expect(finds('cat', 'A Fistful of Dollars')).toBe(false);
    expect(finds('dragon', 'A Fistful of Dollars')).toBe(false);
  });

  it('ignores accents and spaces of the query', () => {
    expect(finds('fur', 'Für Elise')).toBe(true);
    expect(finds('fistfulof', 'A Fistful of Dollars')).toBe(true);
  });

  it('drops filler words from a query', () => {
    expect(withoutFillers('The Good, the Bad and the Ugly')).toBe('good bad ugly');
    expect(withoutFillers('Der Herr der Ringe')).toBe('herr ringe');
    expect(withoutFillers('The The')).toBe('the the'); // nothing else left
  });

  it('builds the queries for a suggested song', () => {
    expect(songQueries('The Good, the Bad and the Ugly - Main Theme')).toEqual(['good bad ugly main theme', 'good bad ugly']);
    expect(songQueries('Concerning Hobbits (From The Lord of the Rings)')).toEqual(['concerning hobbits lord rings', 'concerning hobbits']);
    expect(songQueries('Drunken Sailor')).toEqual(['drunken sailor']);
  });

  it('ranks the texts: the whole query first, then by missing words', () => {
    const rank = ranker('fistful of dollars theme');
    expect(rank('A Fistful of Dollars Theme')).toBe(0);
    expect(rank('Fistful of Dollars')).toBe(2); // one word missing
    expect(rank('Dollars')).toBeNull();
    expect(ranker('')('anything')).toBe(0);
  });
});
