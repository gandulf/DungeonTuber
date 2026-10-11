// Tags and genres ignore upper and lower case: "Pop" and "pop" are the same tag.

export const tagKey = (tag: string) => tag.trim().toLowerCase();

export function hasTag(list: readonly string[] | null | undefined, tag: string): boolean {
  const key = tagKey(tag);
  return !!list?.some((entry) => tagKey(entry) === key);
}

/** The list without the tag, in whatever spelling it is there. */
export function withoutTag(list: readonly string[], tag: string): string[] {
  const key = tagKey(tag);
  return list.filter((entry) => tagKey(entry) !== key);
}

export function toggleTagIn(list: readonly string[], tag: string): string[] {
  return hasTag(list, tag) ? withoutTag(list, tag) : [...list, tag];
}

/** Both lists hold the same tags, ignoring case and order. */
export function sameTags(a: readonly string[], b: readonly string[]): boolean {
  const keys = (list: readonly string[]) => [...new Set(list.map(tagKey))].sort().join('\n');
  return keys(a) === keys(b);
}

/** Words of the spelling that start with a capital letter. */
const capitals = (spelling: string) => spelling.split(/[\s\-/&]+/).filter((word) => /^\p{Lu}/u.test(word)).length;

/** The spelling to show: the most words with a capital first letter ("Dark Fantasy" before "dark fantasy"),
 *  then the most frequent one, then the first one seen. */
function preferred(counts: Map<string, number>): string {
  let best = '';
  for (const [spelling, count] of counts) {
    if (!best || capitals(spelling) > capitals(best) || (capitals(spelling) === capitals(best) && count > counts.get(best)!)) best = spelling;
  }
  return best;
}

/** The spelling to show for every tag (by tagKey) of the lists. */
export function tagNames(lists: Iterable<readonly string[]>): Map<string, string> {
  const spellings = new Map<string, Map<string, number>>();
  for (const list of lists) {
    for (const tag of list) {
      const key = tagKey(tag);
      if (!key) continue;
      const counts = spellings.get(key) ?? new Map<string, number>();
      counts.set(tag.trim(), (counts.get(tag.trim()) ?? 0) + 1);
      spellings.set(key, counts);
    }
  }
  return new Map([...spellings].map(([key, counts]) => [key, preferred(counts)]));
}

/** Every tag once, in the spelling to show, sorted alphabetically. */
export function uniqueTags(lists: Iterable<readonly string[]>): string[] {
  return [...tagNames(lists).values()].sort((a, b) => a.localeCompare(b));
}

/** The tags of one song in the spelling to show, each once. */
export function displayTags(tags: readonly string[], names: Map<string, string>): string[] {
  return [...new Set(tags.map((tag) => names.get(tagKey(tag)) ?? tag.trim()))];
}
