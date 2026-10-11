import { describe, expect, it } from 'vitest';
import { displayTags, hasTag, sameTags, tagNames, toggleTagIn, uniqueTags } from './tags';

describe('tags', () => {
  it('lists every tag once, preferring capital first letters', () => {
    expect(uniqueTags([['pop', 'rock'], ['pop'], ['Pop', 'rock'], ['jazz']])).toEqual(['jazz', 'Pop', 'rock']);
    expect(uniqueTags([['rock'], ['rock'], ['Rock']])).toEqual(['Rock']);
    expect(uniqueTags([['dark fantasy'], ['Dark fantasy'], ['Dark Fantasy']])).toEqual(['Dark Fantasy']);
    expect(uniqueTags([['POP'], ['Pop'], ['Pop']])).toEqual(['Pop']); // as many capitals, the more frequent one
  });

  it('shows the tags of a song in the spelling of the list, each once', () => {
    const names = tagNames([['pop', 'Dark'], ['Pop']]);
    expect(displayTags(['pop', 'Pop', 'dark', 'new'], names)).toEqual(['Pop', 'Dark', 'new']);
  });

  it('compares and toggles without case', () => {
    expect(hasTag(['Pop'], 'pop')).toBe(true);
    expect(toggleTagIn(['pop', 'Rock'], 'Pop')).toEqual(['Rock']);
    expect(toggleTagIn(['Rock'], 'Pop')).toEqual(['Rock', 'Pop']);
    expect(sameTags(['Pop', 'rock'], ['Rock', 'pop'])).toBe(true);
    expect(sameTags(['Pop'], ['Pop', 'Rock'])).toBe(false);
  });
});
