/**
 * Tolerant text search: the words of the query have to appear in the text, in any order, as a word, the start of a word,
 * a part of a word or with a small typo. "fistful dollars" finds "A Fistful of Dollars", "dolars" finds "Dollars".
 * Longer queries may contain a wrong or missing word for every MATCHES_PER_MISS words that are found, so
 * "The Good, the Bad and the Ugly - Main Theme" still finds "The Good, the Bad and the Ugly".
 */

export const MATCHES_PER_MISS = 3;

/** Lower case, without accents and punctuation: "Für a Fistful-of Dollars!" -> "fur a fistful of dollars". */
export function normalize(text: string): string {
  return text.toLowerCase().replace(/ß/g, 'ss').normalize('NFD').replace(/\p{M}+/gu, '')
    .replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
}

// the texts of a library are searched again on every key press
const cache = new Map<string, string>();

function normalizedText(text: string): string {
  let result = cache.get(text);
  if (result === undefined) {
    if (cache.size > 20000) cache.clear();
    result = normalize(text);
    cache.set(text, result);
  }
  return result;
}

const words = (text: string) => (text ? text.split(' ') : []);

/** Typos allowed in a word of this length. */
const tolerance = (length: number) => (length >= 8 ? 2 : length >= 4 ? 1 : 0);

/** Levenshtein distance, or max + 1 as soon as it is certain to exceed max. */
function distance(a: string, b: string, max: number): number {
  if (Math.abs(a.length - b.length) > max) return max + 1;
  let previous = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    const current = [i];
    let best = i;
    for (let j = 1; j <= b.length; j++) {
      current[j] = Math.min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      best = Math.min(best, current[j]);
    }
    if (best > max) return max + 1;
    previous = current;
  }
  return previous[b.length];
}

function wordMatches(term: string, word: string): boolean {
  if (word.includes(term)) return true;
  const max = tolerance(term.length);
  if (!max) return false;
  // the whole word with a typo ("dolars" ~ "dollars") or its start while it is still being typed ("dolla" ~ "dollars")
  return distance(term, word, max) <= max || (word.length > term.length && distance(term, word.slice(0, term.length), max) <= max);
}

export interface Matcher {
  (text: string): boolean;
}

/** How well a text fits the query: 0 when it holds the query as it is, otherwise 1 + the number of words that are missing; null when it
 *  does not fit (see MATCHES_PER_MISS). An empty query fits everything with 0. */
export function ranker(query: string): (text: string) => number | null {
  const normalized = normalize(query);
  const terms = words(normalized);
  if (!terms.length) return () => 0;
  const compact = normalized.replace(/ /g, '');
  return (text: string) => {
    const haystack = normalizedText(text);
    if (haystack.includes(normalized) || haystack.replace(/ /g, '').includes(compact)) return 0;
    const candidates = words(haystack);
    let misses = 0;
    for (const term of terms) {
      if (candidates.some((word) => wordMatches(term, word))) continue;
      misses++;
      if (misses > Math.floor((terms.length - misses) / MATCHES_PER_MISS)) return null; // gives up early
    }
    return 1 + misses;
  };
}

/** A test for texts that fit the query; an empty query fits everything. */
export function matcher(query: string): Matcher {
  const rank = ranker(query);
  return (text: string) => rank(text) !== null;
}

/** Words that say nothing about a song (English and German, plus the articles of a few other languages). */
const FILLER_WORDS = new Set([
  'a', 'an', 'the', 'and', 'or', 'of', 'to', 'in', 'on', 'at', 'by', 'for', 'from', 'with', 'into', 'is', 'it', 'its', 'my', 'your',
  'der', 'die', 'das', 'den', 'dem', 'des', 'ein', 'eine', 'einer', 'eines', 'einem', 'einen', 'und', 'oder', 'von', 'vom', 'zu', 'zum', 'zur',
  'im', 'am', 'an', 'auf', 'mit', 'fur', 'aus', 'bei',
  'le', 'la', 'les', 'l', 'un', 'une', 'de', 'du', 'des', 'et', 'el', 'los', 'las', 'y', 'il', 'lo', 'gli', 'e',
]);

/** The words of the text without filler words; the text itself when nothing else is left. */
export function withoutFillers(text: string): string {
  const kept = words(normalize(text)).filter((word) => !FILLER_WORDS.has(word));
  return kept.length ? kept.join(' ') : normalize(text);
}

/**
 * Queries for a song title, the most specific first: the whole title and the title without an addition like
 * "- Main Theme" or "(From the Film)", each without filler words.
 */
export function songQueries(title: string): string[] {
  const base = title.split(/\s[-–—|:]\s|[([]/)[0];
  return [...new Set([withoutFillers(title), withoutFillers(base)].filter(Boolean))];
}
