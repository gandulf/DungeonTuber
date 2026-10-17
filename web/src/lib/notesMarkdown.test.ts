import { describe, expect, it } from 'vitest';
import { markdownManager, roundTrip } from './notesMarkdown';
import { renderNotes } from './notes';

// what the WYSIWYG editor stores must say the same as what the notes said before
describe('notes markdown round trip', () => {
  const manager = markdownManager();
  const same = (markdown: string) => expect(roundTrip(markdown, manager)).toBe(markdown);

  it('keeps headings, emphasis, lists, quotes and dividers', () => {
    same('# Crypt\n\nThe **door** is *locked*.\n\n- key\n- lever');
    same('> Read aloud: the air is cold.\n\n1. first\n2. second');
    same('Before\n\n---\n\nafter');
    same('Roll `1d20` and add\n\n```\nDC 15\n```');
  });

  it('keeps highlighted text in its color', () => {
    same('A ==yellow== and a **=={green}bold green==** mark.');
    same('=={purple}secret==');
    // the editor writes the highlight inside the other marks; it says the same
    expect(roundTrip('=={green}**bold green**==', manager)).toBe('**=={green}bold green==**');
    const doc = JSON.stringify(manager.parse('=={red}danger== and ==hint=='));
    expect(doc).toContain('"color":"red"');
    expect(doc).toContain('"color":"yellow"');
    // not a highlight: an unknown color, spaces inside or a single =
    expect(JSON.stringify(manager.parse('== y == and a = b'))).not.toContain('highlight');
  });

  it('keeps links to blocks, songs and the web', () => {
    same('Go to [the crypt](block:b2) or play [Fight](song:u-1).');
    same('Web [link](https://example.com).');
    const doc = manager.parse('[the crypt](block:b2)');
    expect(JSON.stringify(doc)).toContain('"href":"block:b2"');
  });

  it('keeps images of the adventure with their size', () => {
    same('A map ![map|300x200](image:0123456789ab.png) here');
    same('![map](image:0123456789ab.png)');
    same('![|x120](image:0123456789ab.png)');
    const image = JSON.stringify(manager.parse('![map|300x200](image:0123456789ab.png)'));
    expect(image).toContain('"alt":"map"');
    expect(image).toContain('"width":300');
    expect(image).toContain('"height":200');
  });

  it('writes single line breaks so that they still show as breaks', () => {
    const stored = roundTrip('Line one\nLine two', manager);
    expect(renderNotes(stored)).toBe(renderNotes('Line one\nLine two'));
  });

  it('keeps a [[Block title]] without a block readable and escapes other syntax', () => {
    expect(roundTrip('See [[Crypt]] later', manager)).toBe('See [[Crypt]] later');
    expect(renderNotes(roundTrip('3 * 4 is 12', manager))).toBe(renderNotes('3 * 4 is 12'));
  });
});
