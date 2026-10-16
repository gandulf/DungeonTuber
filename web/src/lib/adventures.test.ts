import { describe, expect, it } from 'vitest';
import { addLink, addMusic, appendBlock, defaultNext, moveBlock, newBlock, removeBlock, removeLink, startBlock, unreachable } from './adventures';
import type { Adventure } from './types';

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

  it('adds a song or playlist to a block once', () => {
    const [block] = graph('a').blocks;
    expect(addMusic(block, { type: 'song', ufid: 'u1', path: 'x.mp3', title: 'X' })).toBe(true);
    expect(addMusic(block, { type: 'song', ufid: 'u1', path: 'moved.mp3', title: 'X' })).toBe(false);
    expect(addMusic(block, { type: 'playlist', id: 'u1', path: 'p.m3u', title: 'P' })).toBe(true);
  });
});
