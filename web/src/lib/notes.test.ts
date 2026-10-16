import { describe, expect, it } from 'vitest';
import { applyBlockLink, applyFormat, applySongLink, blockLinkTarget, renderNotes, songLinkTarget } from './notes';

describe('renderNotes', () => {
  it('renders headings, emphasis and lists', () => {
    const html = renderNotes('# Crypt\n\nThe **door** is *locked*.\n\n- key\n- lever');
    expect(html).toContain('<h1>Crypt</h1>');
    expect(html).toContain('<strong>door</strong>');
    expect(html).toContain('<li>lever</li>');
  });

  it('shows raw HTML as text', () => {
    const html = renderNotes('<script>alert(1)</script>\n\n<img src=x onerror=alert(1)>');
    expect(html).not.toContain('<script');
    expect(html).not.toContain('<img');
    expect(html).toContain('&lt;script&gt;');
  });

  it('drops unsafe link targets and keeps safe ones', () => {
    expect(renderNotes('[x](javascript:alert(1))')).not.toContain('href');
    expect(renderNotes('[x](https://example.com)')).toContain('href="https://example.com"');
    expect(renderNotes('![map](javascript:alert(1))')).not.toContain('<img');
  });
});

describe('links to blocks', () => {
  const blocks = [{ id: 'b1', title: 'The Crypt' }, { id: 'b2', title: 'Tavern' }];

  it('renders block links inline, by id and by title', () => {
    const html = renderNotes('Go to [the crypt](block:b1) or [[Tavern]] or [[Nowhere]] or [gone](block:zzz).', blocks);
    expect(html).toContain('<a href="#" class="block-link" data-block="b1">the crypt</a>');
    expect(html).toContain('data-block="b2">Tavern</a>');
    expect(html).toContain('[[Nowhere]]');
    expect(html).toContain('class="block-link broken" data-block="zzz"');
  });

  it('still renders normal links and drops unsafe ones', () => {
    expect(renderNotes('[x](https://example.com)', blocks)).toContain('target="_blank"');
    expect(renderNotes('[x](javascript:alert(1))', blocks)).not.toContain('href');
  });

  it('finds the clicked block and ignores broken links', () => {
    const link = (block: string, broken = false) => ({ closest: () => ({ classList: { contains: () => broken }, dataset: { block } }) }) as unknown as EventTarget;
    expect(blockLinkTarget(link('b1'))).toBe('b1');
    expect(blockLinkTarget(link('zzz', true))).toBeNull();
    expect(blockLinkTarget({ closest: () => null } as unknown as EventTarget)).toBeNull();
    expect(blockLinkTarget(null)).toBeNull();
  });

  it('turns the selection into a link', () => {
    expect(applyBlockLink('see here now', 4, 8, blocks[0]).text).toBe('see [here](block:b1) now');
    expect(applyBlockLink('', 0, 0, blocks[1]).text).toBe('[Tavern](block:b2)');
  });
});

describe('links to songs', () => {
  it('renders a song link that plays the song', () => {
    expect(renderNotes('Hear [the bard](song:u-1) sing.')).toContain('<a href="#" class="song-link" data-song="u-1">the bard</a>');
  });

  it('finds the clicked song and builds links', () => {
    const link = { closest: () => ({ dataset: { song: 'u-1' } }) } as unknown as EventTarget;
    expect(songLinkTarget(link)).toBe('u-1');
    expect(songLinkTarget({ closest: () => null } as unknown as EventTarget)).toBeNull();
    expect(applySongLink('listen now', 7, 10, { ufid: 'u-1', title: 'Bard' }).text).toBe('listen [now](song:u-1)');
    expect(applySongLink('', 0, 0, { ufid: 'u-1', title: 'Bard' }).text).toBe('[Bard](song:u-1)');
  });
});

describe('applyFormat', () => {
  it('wraps the selection or a placeholder', () => {
    expect(applyFormat('a door b', 2, 6, 'bold')).toEqual({ text: 'a **door** b', start: 4, end: 8 });
    expect(applyFormat('', 0, 0, 'italic')).toEqual({ text: '*italic*', start: 1, end: 7 });
    expect(applyFormat('see here', 4, 8, 'link').text).toBe('see [here](https://)');
  });

  it('prefixes every selected line and removes the prefix again', () => {
    const list = applyFormat('one\ntwo\nthree', 2, 6, 'list');
    expect(list.text).toBe('- one\n- two\nthree');
    expect(applyFormat(list.text, list.start, list.end, 'list').text).toBe('one\ntwo\nthree');
    expect(applyFormat('title', 0, 0, 'heading').text).toBe('## title');
    expect(applyFormat('a\nb', 3, 3, 'quote').text).toBe('a\n> b');
  });

  it('inserts a rule on its own line', () => {
    expect(applyFormat('text', 4, 4, 'rule').text).toBe('text\n\n---\n');
  });
});
