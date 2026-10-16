// Pure helpers for adventures: blocks, the links between them and the path through them.
import { plainText } from './adventureAi';
import { matcher } from './search';
import type { Adventure, AdventureBlock, AdventureLink, MusicRef } from './types';

type Graph = Pick<Adventure, 'blocks' | 'links'>;

export function newId(): string {
  return crypto.randomUUID();
}

export function newBlock(title = '', index = 0): AdventureBlock {
  return { id: newId(), title, markdown: '', played: false, pos: [index * 40, index * 40], autoplay: true, music: [], effects: [], images: [], cover: null };
}

/** The grid of the stored block positions: a block took this much room and these gaps when the graph showed small nodes. The cards of
 *  the graph and the map are larger, so they are drawn at the positions stretched by CARD_SCALE; the stored files keep their units. */
export const NODE_W = 170;
export const NODE_H = 56;
const GAP_X = 80;
const GAP_Y = 30;

/** Size of a block card and the space between cards (screen pixels at zoom 1). */
export const CARD = { w: 200, h: 196 };
export const CARD_GAP = { x: 64, y: 36 };
export const CARD_SCALE = { x: (CARD.w + CARD_GAP.x) / (NODE_W + GAP_X), y: (CARD.h + CARD_GAP.y) / (NODE_H + GAP_Y) };

/** Where a card is drawn for a stored position, and back. */
export const toCard = (pos: [number, number]): [number, number] => [Math.round(pos[0] * CARD_SCALE.x), Math.round(pos[1] * CARD_SCALE.y)];
export const fromCard = (x: number, y: number): [number, number] => [Math.round(x / CARD_SCALE.x), Math.round(y / CARD_SCALE.y)];

/** Adds a block at the end of the list, to the right of the one that was last, and links that block to it (without a label, so it is the
 *  default next block). */
export function appendBlock(graph: Graph, title = ''): AdventureBlock {
  const last = graph.blocks[graph.blocks.length - 1];
  const block = newBlock(title, graph.blocks.length);
  if (last) block.pos = [last.pos[0] + NODE_W + GAP_X, last.pos[1]];
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

export interface BlockHit {
  block: AdventureBlock;
  /** A piece of the notes around the first word of the query that was found literally (`match`), or their start. */
  before: string;
  match: string;
  after: string;
}

const SNIPPET = 48;

/** The blocks whose title or notes fit the query (tolerant like the song search: any order, small typos), those with a fitting
 *  title first, each with a snippet of its notes for the list. */
export function searchBlocks(blocks: AdventureBlock[], query: string, limit = 20): BlockHit[] {
  if (!query.trim()) return [];
  const fits = matcher(query);
  const terms = query.trim().split(/\s+/).filter((word) => word.length > 1).sort((a, b) => b.length - a.length);
  const hits: (BlockHit & { inTitle: boolean })[] = [];
  for (const block of blocks) {
    const text = plainText(block.markdown, Infinity).replace(/\s+/g, ' '); // all of the notes, not the start a prompt gets
    if (!fits(`${block.title} ${text}`)) continue;
    const lower = text.toLowerCase();
    const found = terms.map((term) => ({ term, at: lower.indexOf(term.toLowerCase()) })).find((item) => item.at >= 0);
    const hit = found
      ? { before: (found.at > SNIPPET ? '…' : '') + text.slice(Math.max(0, found.at - SNIPPET), found.at), match: text.slice(found.at, found.at + found.term.length),
          after: text.slice(found.at + found.term.length, found.at + found.term.length + SNIPPET * 2) }
      : { before: text.slice(0, SNIPPET * 2), match: '', after: '' };
    hits.push({ block, ...hit, inTitle: fits(block.title) });
  }
  return hits.sort((a, b) => Number(b.inTitle) - Number(a.inTitle)).slice(0, limit).map(({ inTitle: _, ...hit }) => hit);
}

/** Moves the entry at `from` so that it lands where the entry at `to` was dropped on: `to` counts the positions before the move
 *  (0 = first, `list.length` = after the last). Returns whether the order changed. */
export function moveEntry<T>(list: T[], from: number, to: number): boolean {
  if (from < 0 || from >= list.length || to < 0 || to > list.length) return false;
  const target = to > from ? to - 1 : to;
  if (target === from) return false;
  const [entry] = list.splice(from, 1);
  list.splice(target, 0, entry);
  return true;
}

/** Assigns a song or playlist to the adventure (its own playlist) unless it holds it already. */
export function addAdventureMusic(adventure: Pick<Adventure, 'music'>, ref: MusicRef): boolean {
  if (adventure.music.some((item) => refKey(item) === refKey(ref))) return false;
  adventure.music.push(ref);
  return true;
}

/** Adds a song or playlist to a block and, so the block keeps choosing from it, to the adventure; returns whether the block changed. */
export function assignMusic(adventure: Pick<Adventure, 'music'>, block: AdventureBlock, ref: MusicRef): boolean {
  addAdventureMusic(adventure, ref);
  return addMusic(block, ref);
}

/** The blocks that play a song or playlist of the adventure. */
export const blocksUsing = (adventure: Pick<Adventure, 'blocks'>, ref: MusicRef): AdventureBlock[] =>
  adventure.blocks.filter((block) => block.music.some((item) => refKey(item) === refKey(ref)));

/** Takes a song or playlist out of the adventure and out of every block that plays it (the blocks choose from the adventure's music). */
export function removeAdventureMusic(adventure: Pick<Adventure, 'blocks' | 'music'>, ref: MusicRef) {
  const key = refKey(ref);
  adventure.music = adventure.music.filter((item) => refKey(item) !== key);
  for (const block of adventure.blocks) block.music = block.music.filter((item) => refKey(item) !== key);
}

/** Adds a song or playlist to a block unless it is there already. */
export function addMusic(block: AdventureBlock, ref: MusicRef): boolean {
  if (block.music.some((item) => refKey(item) === refKey(ref))) return false;
  block.music.push(ref);
  return true;
}

/** Arranges the blocks in columns by their distance from the first block (blocks nothing leads to start their own tree below). */
export function autoLayout(graph: Graph) {
  const cells = layers(graph);
  for (const block of graph.blocks) {
    const [column, row] = cells.get(block.id)!;
    block.pos = [column * (NODE_W + GAP_X), row * (NODE_H + GAP_Y)];
  }
}

/** The column (distance from the first block) and the row of every block, as autoLayout places them. */
function layers(graph: Graph): Map<string, [number, number]> {
  const depth = new Map<string, number>();
  for (const root of graph.blocks) {
    if (depth.has(root.id)) continue;
    depth.set(root.id, 0);
    const queue = [root.id];
    while (queue.length) {
      const id = queue.shift()!;
      for (const link of linksFrom(graph, id)) {
        if (!depth.has(link.to)) {
          depth.set(link.to, depth.get(id)! + 1);
          queue.push(link.to);
        }
      }
    }
  }
  const rows = new Map<number, number>();
  const cells = new Map<string, [number, number]>();
  for (const block of graph.blocks) {
    const column = depth.get(block.id) ?? 0;
    const row = rows.get(column) ?? 0;
    rows.set(column, row + 1);
    cells.set(block.id, [column, row]);
  }
  return cells;
}

export interface CardLayout {
  /** The top left corner of every card. */
  pos: Map<string, [number, number]>;
  width: number;
  height: number;
}

/** Where the cards of the adventure map (the welcome screen of play mode) go: the arrangement of the graph editor, stretched to the
 *  size of a card so that cards do not overlap where the blocks did not; blocks that were never arranged (all in one spot) get the
 *  columns of autoLayout. */
export function cardLayout(graph: Graph, card: { w: number; h: number } = CARD, gap: { x: number; y: number } = CARD_GAP): CardLayout {
  const pos = new Map<string, [number, number]>();
  const [first, ...rest] = graph.blocks;
  if (!first) return { pos, width: 0, height: 0 };
  if (rest.every((block) => block.pos[0] === first.pos[0] && block.pos[1] === first.pos[1])) {
    for (const [id, [column, row]] of layers(graph)) pos.set(id, [column * (card.w + gap.x), row * (card.h + gap.y)]);
  } else {
    const [sx, sy] = [(card.w + gap.x) / (NODE_W + GAP_X), (card.h + gap.y) / (NODE_H + GAP_Y)];
    const [left, top] = [Math.min(...graph.blocks.map((block) => block.pos[0])), Math.min(...graph.blocks.map((block) => block.pos[1]))];
    for (const block of graph.blocks) pos.set(block.id, [Math.round((block.pos[0] - left) * sx), Math.round((block.pos[1] - top) * sy)]);
  }
  const corners = [...pos.values()];
  return { pos, width: Math.max(...corners.map(([x]) => x)) + card.w, height: Math.max(...corners.map(([, y]) => y)) + card.h };
}
