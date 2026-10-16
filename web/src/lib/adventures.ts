// Pure helpers for adventures: blocks, the links between them and the path through them.
import type { Adventure, AdventureBlock, AdventureLink, MusicRef } from './types';

type Graph = Pick<Adventure, 'blocks' | 'links'>;

export function newId(): string {
  return crypto.randomUUID();
}

export function newBlock(title = '', index = 0): AdventureBlock {
  return { id: newId(), title, markdown: '', played: false, pos: [index * 40, index * 40], autoplay: true, music: [], effects: [], light: null, images: [] };
}

/** Adds a block at the end of the list and links the block that was last to it (without a label, so it is the default next block). */
export function appendBlock(graph: Graph, title = ''): AdventureBlock {
  const last = graph.blocks[graph.blocks.length - 1];
  const block = newBlock(title, graph.blocks.length);
  graph.blocks.push(block);
  if (last) addLink(graph, last.id, block.id);
  return block;
}

export const blockById = (graph: Graph, id: string | null): AdventureBlock | null => graph.blocks.find((block) => block.id === id) ?? null;

export const linksFrom = (graph: Graph, id: string): AdventureLink[] => graph.links.filter((link) => link.from === id);

export const linksTo = (graph: Graph, id: string): AdventureLink[] => graph.links.filter((link) => link.to === id);

/** The block that follows by default: the first link without a label, else the first link. */
export function defaultNext(graph: Graph, id: string): AdventureBlock | null {
  const links = linksFrom(graph, id);
  const link = links.find((item) => !item.label) ?? links[0];
  return link ? blockById(graph, link.to) : null;
}

/** Adds a link (no self links, no duplicates); returns whether the graph changed. */
export function addLink(graph: Graph, from: string, to: string, label: string | null = null): boolean {
  if (from === to || !blockById(graph, from) || !blockById(graph, to)) return false;
  if (graph.links.some((link) => link.from === from && link.to === to && (link.label ?? null) === (label || null))) return false;
  graph.links.push({ from, to, label: label || null });
  return true;
}

export function removeLink(graph: Graph, link: AdventureLink) {
  const index = graph.links.indexOf(link);
  if (index >= 0) graph.links.splice(index, 1);
}

/** Removes a block and every link that touches it; returns the block to select instead (the neighbour in the list), or null if none is left. */
export function removeBlock(graph: Graph, id: string): string | null {
  const index = graph.blocks.findIndex((block) => block.id === id);
  if (index < 0) return graph.blocks[0]?.id ?? null;
  graph.blocks.splice(index, 1);
  graph.links = graph.links.filter((link) => link.from !== id && link.to !== id);
  return (graph.blocks[index] ?? graph.blocks[index - 1])?.id ?? null;
}

export function moveBlock(graph: Graph, id: string, offset: number) {
  const index = graph.blocks.findIndex((block) => block.id === id);
  const target = index + offset;
  if (index < 0 || target < 0 || target >= graph.blocks.length) return;
  const [block] = graph.blocks.splice(index, 1);
  graph.blocks.splice(target, 0, block);
}

/** The block to start a session with: the first one not played yet, in list order (the first block when all are played or none is). */
export function startBlock(graph: Graph): AdventureBlock | null {
  return graph.blocks.find((block) => !block.played) ?? graph.blocks[0] ?? null;
}

/** Blocks that no link leads to and that are not the first one: they can only be reached by hand. */
export function unreachable(graph: Graph): AdventureBlock[] {
  const reached = new Set<string>(graph.blocks[0] ? [graph.blocks[0].id] : []);
  const open = [...reached];
  while (open.length) {
    const id = open.pop()!;
    for (const link of linksFrom(graph, id)) {
      if (!reached.has(link.to)) {
        reached.add(link.to);
        open.push(link.to);
      }
    }
  }
  return graph.blocks.filter((block) => !reached.has(block.id));
}

export const refKey = (ref: MusicRef) => (ref.type === 'song' ? `song:${ref.ufid}` : `playlist:${ref.id}`);

/** Adds a song or playlist to a block unless it is there already. */
export function addMusic(block: AdventureBlock, ref: MusicRef): boolean {
  if (block.music.some((item) => refKey(item) === refKey(ref))) return false;
  block.music.push(ref);
  return true;
}
