import { describe, expect, it } from 'vitest';
import { addAdventureMusic, addLink, addMusic, appendBlock, blocksUsing, moveEntry, searchBlocks, removeAdventureMusic, autoLayout, CARD, CARD_GAP, cardLayout, fromCard, toCard, NODE_H, NODE_W, defaultNext, moveBlock, newBlock, removeBlock, nextBlock, removeLink, shownBlocks, startBlock, unreachable } from './adventures';
import type { Adventure, MusicRef } from './types';

function graph(...titles: string[]): Pick<Adventure, 'blocks' | 'links'> {
  return { blocks: titles.map((title, index) => ({ ...newBlock(title, index), id: title })), links: [] };
}

describe('adventure graph', () => {
  it('adds links without self links, unknown blocks or duplicates', () => {
    const g = graph('a', 'b');
    expect(addLink(g, 'a', 'b')).toBe(true);
    expect(addLink(g, 'a', 'b')).toBe(false);
    expect(addLink(g, 'a', 'b', 'door')).toBe(true);
    expect(addLink(g, 'a', 'a')).toBe(false);
    expect(addLink(g, 'a', 'x')).toBe(false);
    expect(g.links).toHaveLength(2);
    removeLink(g, g.links[0]);
    expect(g.links).toEqual([{ from: 'a', to: 'b', label: 'door' }]);
  });

  it('follows the unlabeled link by default', () => {
    const g = graph('a', 'b', 'c');
    addLink(g, 'a', 'b', 'secret');
    addLink(g, 'a', 'c');
    expect(defaultNext(g, 'a')?.id).toBe('c');
    expect(defaultNext(g, 'c')).toBeNull();
    g.links.pop();
    expect(defaultNext(g, 'a')?.id).toBe('b');
  });

  it('removes a block with its links and picks a neighbour', () => {
    const g = graph('a', 'b', 'c');
    addLink(g, 'a', 'b');
    addLink(g, 'b', 'c');
    expect(removeBlock(g, 'b')).toBe('c');
    expect(g.links).toEqual([]);
    expect(removeBlock(g, 'c')).toBe('a');
    expect(removeBlock(g, 'a')).toBeNull();
  });

  it('moves blocks within the list', () => {
    const g = graph('a', 'b', 'c');
    moveBlock(g, 'c', -1);
    moveBlock(g, 'a', -1);
    expect(g.blocks.map((block) => block.id)).toEqual(['a', 'c', 'b']);
  });

  it('starts with the first block not played yet and finds blocks nothing leads to', () => {
    const g = graph('a', 'b', 'c');
    g.blocks[0].played = true;
    expect(startBlock(g)?.id).toBe('b');
    addLink(g, 'a', 'b');
    expect(unreachable(g).map((block) => block.id)).toEqual(['c']);
  });

  it('links a new block from the last one', () => {
    const g = graph('a', 'b');
    const block = appendBlock(g, 'c');
    expect(g.blocks.map((item) => item.id)).toEqual(['a', 'b', block.id]);
    expect(g.links).toEqual([{ from: 'b', to: block.id, label: null }]);
    const first = graph();
    appendBlock(first, 'start');
    expect(first.links).toEqual([]);
  });

  it('places a new block to the right of the last one', () => {
    const g = graph('a');
    g.blocks[0].pos = [40, 100];
    expect(appendBlock(g, 'b').pos).toEqual([40 + NODE_W + 80, 100]);
  });

  it('arranges blocks in columns by distance from the first block', () => {
    const g = graph('a', 'b', 'c', 'd');
    addLink(g, 'a', 'b');
    addLink(g, 'a', 'c');
    autoLayout(g);
    const at = (id: string) => g.blocks.find((block) => block.id === id)!.pos;
    expect(at('a')).toEqual([0, 0]);
    expect(at('b')[0]).toBe(NODE_W + 80);
    expect(at('c')[0]).toBe(at('b')[0]);
    expect(at('c')[1]).toBe(NODE_H + 30);
    expect(at('d')).toEqual([0, NODE_H + 30]); // nothing leads to it: its own tree below the first one
  });

  it('lays out the cards of the map like the graph, stretched to the card size', () => {
    const card = { w: 200, h: 190 }, gap = { x: 50, y: 30 };
    const g = graph('a', 'b', 'c');
    addLink(g, 'a', 'b');
    g.blocks[0].pos = [100, 50];
    g.blocks[1].pos = [100 + NODE_W + 80, 50];
    g.blocks[2].pos = [100, 50 + NODE_H + 30];
    const layout = cardLayout(g, card, gap);
    expect(layout.pos.get('a')).toEqual([0, 0]);
    expect(layout.pos.get('b')).toEqual([250, 0]);
    expect(layout.pos.get('c')).toEqual([0, 220]);
    expect([layout.width, layout.height]).toEqual([450, 410]);

    // blocks that were never arranged (all in one spot) get columns by their distance from the first block
    for (const block of g.blocks) block.pos = [0, 0];
    const columns = cardLayout(g, card, gap);
    expect(columns.pos.get('b')).toEqual([250, 0]);
    expect(columns.pos.get('c')).toEqual([0, 220]);
    expect(cardLayout(graph(), card, gap)).toEqual({ pos: new Map(), width: 0, height: 0 });
  });

  it('draws stored positions as cards and keeps drags in stored units', () => {
    expect(toCard([0, 0])).toEqual([0, 0]);
    expect(toCard([NODE_W + 80, NODE_H + 30])).toEqual([CARD.w + CARD_GAP.x, CARD.h + CARD_GAP.y]); // one grid step is one card step
    expect(fromCard(...toCard([250, 172]))).toEqual([250, 172]);
  });

  it('keeps the music of the adventure and takes it out of the blocks with it', () => {
    const g = { ...graph('a', 'b'), music: [] as MusicRef[] };
    const song: MusicRef = { type: 'song', ufid: 'u1', path: 'x.mp3', title: 'X' };
    expect(addAdventureMusic(g, song)).toBe(true);
    expect(addAdventureMusic(g, { ...song, path: 'moved.mp3' })).toBe(false);
    addMusic(g.blocks[1], song);
    expect(blocksUsing(g, song).map((block) => block.id)).toEqual(['b']);
    removeAdventureMusic(g, song);
    expect(g.music).toEqual([]);
    expect(g.blocks[1].music).toEqual([]);
  });

  it('searches the titles and notes of the blocks', () => {
    const g = graph('Tavern', 'Crypt', 'Forest');
    g.blocks[0].markdown = 'The **innkeeper** hides a secret about the crypt below the cellar.';
    g.blocks[1].markdown = '> Cold air, flickering torches and a sealed sarcophagus.';
    g.blocks[2].markdown = 'Wolves howl in the distance.';
    expect(searchBlocks(g.blocks, '')).toEqual([]);
    // a fitting title comes first; the notes are searched without their Markdown marks
    expect(searchBlocks(g.blocks, 'crypt').map((hit) => hit.block.title)).toEqual(['Crypt', 'Tavern']);
    const [hit] = searchBlocks(g.blocks, 'innkeeper');
    expect([hit.before, hit.match, hit.after.slice(0, 6)]).toEqual(['The ', 'innkeeper', ' hides']);
    expect(searchBlocks(g.blocks, 'sarcophagus torches').map((item) => item.block.title)).toEqual(['Crypt']); // any order
    expect(searchBlocks(g.blocks, 'wolfes').map((item) => item.block.title)).toEqual(['Forest']); // a small typo
    expect(searchBlocks(g.blocks, 'dragon')).toEqual([]);
    // long notes are searched to their end (the AI prompts only get their start)
    g.blocks[2].markdown = `${'Fog in the woods. '.repeat(150)}At last the dragon hoard.`;
    expect(searchBlocks(g.blocks, 'hoard').map((item) => item.block.title)).toEqual(['Forest']);
  });

  it('moves an entry to where it was dropped', () => {
    const list = ['a', 'b', 'c', 'd'];
    expect(moveEntry(list, 0, 2)).toBe(true); // dropped before c
    expect(list).toEqual(['b', 'a', 'c', 'd']);
    expect(moveEntry(list, 3, 0)).toBe(true);
    expect(list).toEqual(['d', 'b', 'a', 'c']);
    expect(moveEntry(list, 1, 4)).toBe(true); // after the last
    expect(list).toEqual(['d', 'a', 'c', 'b']);
    expect(moveEntry(list, 1, 1)).toBe(false);
    expect(moveEntry(list, 1, 2)).toBe(false); // right behind itself: same place
    expect(moveEntry(list, 5, 0)).toBe(false);
  });

  it('adds a song or playlist to a block once', () => {
    const [block] = graph('a').blocks;
    expect(addMusic(block, { type: 'song', ufid: 'u1', path: 'x.mp3', title: 'X' })).toBe(true);
    expect(addMusic(block, { type: 'song', ufid: 'u1', path: 'moved.mp3', title: 'X' })).toBe(false);
    expect(addMusic(block, { type: 'playlist', id: 'u1', path: 'p.m3u', title: 'P' })).toBe(true);
  });
});

describe('embedded (inline) blocks', () => {
  function withInline() {
    const g = graph('a', 'b', 'p');
    g.blocks[2].inline = true;
    addLink(g, 'a', 'b');
    return g;
  }

  it('are not part of the layout of the overview and the graph', () => {
    const g = withInline();
    expect(shownBlocks(g).map((block) => block.id)).toEqual(['a', 'b']);
    expect([...cardLayout(g).pos.keys()]).toEqual(['a', 'b']);
    autoLayout(g);
    expect(g.blocks[2].pos).toEqual([2 * 40, 2 * 40]); // never arranged
  });

  it('are not marked as unreachable and do not start a session', () => {
    const g = withInline();
    expect(unreachable(g)).toEqual([]);
    g.blocks[0].played = true;
    g.blocks[1].played = true;
    expect(startBlock(g)?.id).toBe('a'); // all scenes played: the first block, not the embedded one
  });
});

describe('next block (the right arrow key)', () => {
  it('follows a single link, else the next block of the list', () => {
    const g = graph('a', 'b', 'c', 'd');
    addLink(g, 'a', 'c'); // a single link wins over the list order
    expect(nextBlock(g, 'a')?.id).toBe('c');
    expect(nextBlock(g, 'b')?.id).toBe('c'); // no link: the next in the list
    expect(nextBlock(g, 'd')).toBeNull(); // the end of the list
  });

  it('takes the next block of the list when there is a choice', () => {
    const g = graph('a', 'b', 'c', 'd');
    addLink(g, 'a', 'd', 'left door');
    addLink(g, 'a', 'c', 'right door');
    expect(nextBlock(g, 'a')?.id).toBe('b');
  });

  it('skips embedded blocks in the list and does not continue from one', () => {
    const g = graph('a', 'p', 'b');
    g.blocks[1].inline = true;
    expect(nextBlock(g, 'a')?.id).toBe('b');
    expect(nextBlock(g, 'p')).toBeNull();
  });
});
