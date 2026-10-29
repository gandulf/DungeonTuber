// What the AI helpers of an adventure block send and do with the answers (the calls themselves are in components/adventure/AiDialog.svelte).
import { calculateScore } from './scoring';
import { displayTags, tagNames } from './tags';
import type { AdventureBlock, FilterConfig, SmartFilter, Track } from './types';

const MAX_NOTES = 1500;

/** The notes as plain text for a prompt: without the links, images and Markdown marks, cut to a length a prompt can carry
 *  (`limit`; the search of the blocks takes all of it). */
export function plainText(markdown: string, limit = MAX_NOTES): string {
  return markdown
    .replace(/!\[[^\]]*\]\([^)]*\)/g, '') // images
    .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1') // links keep their text
    .replace(/\[\[([^\]]*)\]\]/g, '$1')
    .replace(/^[ \t]{0,3}(#{1,6}|>|[-*+]|\d+[.)])[ \t]+/gm, '')
    .replace(/[*_`~]/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim()
    .slice(0, limit);
}

/** The short text of a block card (the graph and the map): its summary (TL;DR), one point after the other, or else the start of its notes. */
export function cardText(block: Pick<AdventureBlock, 'markdown' | 'tldr'>): string {
  const summary = plainText(block.tldr ?? '').split(/\n+/).map((line) => line.trim()).filter(Boolean).join(' · ');
  return summary || plainText(block.markdown);
}

/** What the AI gets to know of a block: its title and its notes. */
export function blockPrompt(block: Pick<AdventureBlock, 'title' | 'markdown'>): string {
  return [block.title.trim(), plainText(block.markdown)].filter(Boolean).join('\n\n');
}

/** The most the summary (TL;DR) of a block is written from (see MAX_TLDR_SOURCE in server/assistant.py). */
export const MAX_TLDR_SOURCE = 20000;

/** What the AI gets to write the summary (TL;DR) of a block from: the whole notes as Markdown, links included, so that the summary
 *  can link the same blocks, songs and pages. */
export function tldrPrompt(adventureTitle: string, block: Pick<AdventureBlock, 'title' | 'markdown'>, wishes = ''): string {
  const head = [`Adventure: ${adventureTitle}`, `Scene: ${block.title}`, ...(wishes.trim() ? [`Wishes: ${wishes.trim()}`] : []), 'Notes (Markdown):', ''].join('\n');
  return head + block.markdown.trim().slice(0, MAX_TLDR_SOURCE - head.length);
}

/** The tags and genres of the songs, "Pop" and "pop" listed once: the values the smart search may choose from. */
export function tagsAndGenres(tracks: Track[]): { tags: string[]; genres: string[] } {
  const names = tagNames(tracks.flatMap((track) => [track.tags, track.genres]));
  const sorted = (values: string[]) => displayTags(values, names).sort((a, b) => a.localeCompare(b));
  return { tags: sorted(tracks.flatMap((track) => track.tags)), genres: sorted(tracks.flatMap((track) => track.genres)) };
}

export interface Ranked { track: Track; score: number }

/** The songs that fit a filter best (lowest distance first); songs the filter cannot judge are left out. */
export function rankTracks(tracks: Track[], filter: SmartFilter | FilterConfig, limit = 10): Ranked[] {
  const config: FilterConfig = { categories: { ...filter.categories }, tags: [...filter.tags], genres: [...filter.genres], bpm: filter.bpm ?? null };
  const ranked: Ranked[] = [];
  for (const track of tracks) {
    const score = calculateScore(track, config);
    if (score !== null) ranked.push({ track, score });
  }
  return ranked.sort((a, b) => a.score - b.score || (a.track.title ?? a.track.name).localeCompare(b.track.title ?? b.track.name)).slice(0, limit);
}
