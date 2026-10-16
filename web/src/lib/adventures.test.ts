import { describe, expect, it } from 'vitest';
import { addLink, addMusic, appendBlock, autoLayout, NODE_H, NODE_W, defaultNext, moveBlock, newBlock, removeBlock, removeLink, startBlock, unreachable } from './adventures';
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

  it('adds a song or playlist to a block once', () => {
    const [block] = graph('a').blocks;
    expect(addMusic(block, { type: 'song', ufid: 'u1', path: 'x.mp3', title: 'X' })).toBe(true);
    expect(addMusic(block, { type: 'song', ufid: 'u1', path: 'moved.mp3', title: 'X' })).toBe(false);
    expect(addMusic(block, { type: 'playlist', id: 'u1', path: 'p.m3u', title: 'P' })).toBe(true);
  });
});
