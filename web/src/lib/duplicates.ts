import type { Track } from './types';

/** Songs whose lengths differ by no more than this many seconds count as the same recording. */
export const LENGTH_TOLERANCE = 3;

const normalize = (text: string) =>
  text.toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g, '').replace(/[^\p{L}\p{N}]+/gu, ' ').trim();

/** What identifies a song apart from its file: artist and title (the file name when there is no title), without case, accents and punctuation. */
export function duplicateKey(track: Track): string {
  const title = normalize(track.title || track.name);
  if (!title) return '';
  const artist = normalize(track.artist ?? '');
  return artist ? `${artist}|${title}` : title;
}

/** `exact`: the file has the same content as another one; `similar`: the same artist and title with (nearly) the same length. */
export type DuplicateKind = 'exact' | 'similar';

export interface Duplicates {
  /** Every song that has at least one duplicate. */
  tracks: Track[];
  /** Track id -> id of its group of duplicates; sorting by it puts the duplicates of a song next to each other. */
  groups: Record<string, string>;
  kinds: Record<string, DuplicateKind>;
  groupCount: number;
}

/** The songs of the library that exist more than once, in any folder: byte for byte the same files (`exactGroups`, lists of track ids
 *  that the server found by their content) and songs with the same artist and title and (nearly) the same length. A song that is
 *  linked to others by both ways ends up in one group. */
export function findDuplicates(tracks: Track[], exactGroups: string[][] = []): Duplicates {
  const byId = new Map(tracks.map((track) => [track.id, track]));
  // union-find over the track ids
  const parent = new Map<string, string>();
  const find = (id: string): string => {
    let root = id;
    while (parent.get(root) !== root) root = parent.get(root)!;
    parent.set(id, root);
    return root;
  };
  const union = (a: string, b: string) => parent.set(find(a), find(b));
  for (const track of tracks) parent.set(track.id, track.id);

  const exact = new Set<string>();
  for (const group of exactGroups) {
    const ids = group.filter((id) => byId.has(id));
    if (ids.length < 2) continue;
    for (const id of ids) {
      exact.add(id);
      union(ids[0], id);
    }
  }

  const byKey = new Map<string, Track[]>();
  for (const track of tracks) {
    const key = duplicateKey(track);
    if (!key) continue;
    const list = byKey.get(key);
    if (list) list.push(track);
    else byKey.set(key, [track]);
  }
  const similar = new Set<string>();
  for (const list of byKey.values()) {
    if (list.length < 2) continue;
    const sorted = [...list].sort((a, b) => a.length - b.length);
    for (let i = 1; i < sorted.length; i++) {
      if (sorted[i].length - sorted[i - 1].length > LENGTH_TOLERANCE) continue;
      union(sorted[i - 1].id, sorted[i].id);
      similar.add(sorted[i - 1].id);
      similar.add(sorted[i].id);
    }
  }

  const members = new Map<string, Track[]>();
  for (const id of new Set([...exact, ...similar])) {
    const root = find(id);
    const list = members.get(root);
    if (list) list.push(byId.get(id)!);
    else members.set(root, [byId.get(id)!]);
  }
  const found: Track[] = [];
  const groups: Record<string, string> = {};
  const kinds: Record<string, DuplicateKind> = {};
  for (const list of members.values()) {
    if (list.length < 2) continue;
    list.sort((a, b) => duplicateKey(a).localeCompare(duplicateKey(b)) || a.length - b.length || a.path.localeCompare(b.path));
    const id = `${duplicateKey(list[0])}|${String(Math.round(list[0].length)).padStart(6, '0')}|${list[0].id}`;
    for (const track of list) {
      groups[track.id] = id;
      kinds[track.id] = exact.has(track.id) ? 'exact' : 'similar';
    }
    found.push(...list);
  }
  return { tracks: found, groups, kinds, groupCount: new Set(Object.values(groups)).size };
}
