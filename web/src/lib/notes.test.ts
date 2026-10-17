import { describe, expect, it } from 'vitest';
import { blockLinkTarget, imageSize, renderNotes, resolveBlockTitles, songLinkIds, songLinkTarget } from './notes';

describe('renderNotes', () => {
  it('renders highlighted text in its color and nothing else', () => {
    expect(renderNotes('A ==note== and =={blue}*more*==')).toContain('<mark class="hl hl-yellow">note</mark> and <mark class="hl hl-blue"><em>more</em></mark>');
    // an unknown color is plain text in a yellow highlight: nothing of it reaches the markup
    expect(renderNotes('=={x" onclick="y}text==')).toBe('<p><mark class="hl hl-yellow">{x&quot; onclick=&quot;y}text</mark></p>\n');
  });

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

  it('turns [[Block title]] into a link by id before the editor reads the notes', () => {
    expect(resolveBlockTitles('See [[tavern]] and [[Nowhere]]', blocks)).toBe('See [tavern](block:b2) and [[Nowhere]]');
  });

  it('finds the clicked block and ignores broken links', () => {
    const link = (block: string, broken = false) => ({ closest: () => ({ classList: { contains: () => broken }, dataset: { block } }) }) as unknown as EventTarget;
    expect(blockLinkTarget(link('b1'))).toBe('b1');
    expect(blockLinkTarget(link('zzz', true))).toBeNull();
    expect(blockLinkTarget({ closest: () => null } as unknown as EventTarget)).toBeNull();
    expect(blockLinkTarget(null)).toBeNull();
  });

});

describe('images', () => {
  const blocks = [{ id: 'b1', title: 'The Crypt' }, { id: 'b2', title: 'Tavern' }, { id: 'b3', title: 'Crypt door' }];

  it('serves images of the adventure and refuses other sources', () => {
    expect(renderNotes('![map](image:0123456789ab.png)', [], 'adv-1')).toContain('src="/api/adventures/adv-1/images/0123456789ab.png"');
    expect(renderNotes('![map](image:../x.png)', [], 'adv-1')).not.toContain('<img');
    expect(renderNotes('![map](image:0123456789ab.png)')).not.toContain('<img');
  });

  it('sizes images after a bar in the alt text and keeps their aspect ratio', () => {
    const image = (alt: string) => renderNotes(`![${alt}](image:0123456789ab.png)`, [], 'adv-1');
    expect(image('map|300')).toContain('alt="map" style="width:300px;height:auto"');
    expect(image('map | x200')).toContain('alt="map" style="height:200px;width:auto;object-fit:contain"');
    expect(image('map|300x200')).toContain('style="width:300px;height:200px;object-fit:contain"');
    expect(image('|99999')).toContain('alt="" style="width:4000px;height:auto"');
    expect(image('a|b')).toContain('alt="a|b" loading');
    expect(image('map|0')).toContain('alt="map|0" loading');
    expect(renderNotes('![logo|120](https://example.com/a.png)')).toContain('alt="logo" style="width:120px;height:auto"');
    expect(imageSize('map|x')).toEqual({ alt: 'map|x', width: null, height: null });
  });


});

describe('links to songs', () => {
  it('renders a song link that plays the song', () => {
    expect(renderNotes('Hear [the bard](song:u-1) sing.')).toContain('<a href="#" class="song-link" data-song="u-1">the bard</a>');
  });

  it('finds the clicked song', () => {
    const link = { closest: () => ({ dataset: { song: 'u-1' } }) } as unknown as EventTarget;
    expect(songLinkTarget(link)).toBe('u-1');
    expect(songLinkTarget({ closest: () => null } as unknown as EventTarget)).toBeNull();
  });
});

describe('songLinkIds', () => {
  it('lists the songs the notes link to', () => {
    expect(songLinkIds('Hear [the bard](song:u-1) and [the drums](song:u-2), not [a block](block:b-1).')).toEqual(['u-1', 'u-2']);
    expect(songLinkIds('No links.')).toEqual([]);
  });
});
