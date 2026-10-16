// The words of the header search, marked in the notes of the block it led to (CSS Custom Highlight API: the text is not changed,
// so it also works inside the editor), and the first of them scrolled into view. Styled by ::highlight(search-hit) in app.css.

const NAME = 'search-hit';

/** The words of a search worth marking: two letters or more, lower case, each once, longest first (they win where words overlap). */
export function searchTerms(query: string): string[] {
  return [...new Set(query.toLowerCase().split(/\s+/).filter((word) => word.length > 1))].sort((a, b) => b.length - a.length);
}

/** Where the words occur in a text (case-insensitive), as [start, end) without overlaps, in order. */
export function matchOffsets(text: string, terms: string[]): [number, number][] {
  const lower = text.toLowerCase();
  const found: [number, number][] = [];
  for (const term of terms) {
    for (let at = lower.indexOf(term); at >= 0; at = lower.indexOf(term, at + term.length)) {
      if (!found.some(([start, end]) => at < end && at + term.length > start)) found.push([at, at + term.length]);
    }
  }
  return found.sort((a, b) => a[0] - b[0]);
}

const supported = () => typeof CSS !== 'undefined' && 'highlights' in CSS && typeof Highlight !== 'undefined';

export function clearHighlight() {
  if (supported()) CSS.highlights.delete(NAME);
}

/** Marks the words in the text below `root` and scrolls the first one into the middle of the view; false when none is there. */
export function highlightTerms(root: Element | null, terms: string[]): boolean {
  clearHighlight();
  if (!root || !terms.length) return false;
  const ranges: Range[] = [];
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    for (const [start, end] of matchOffsets(node.textContent ?? '', terms)) {
      const range = document.createRange();
      range.setStart(node, start);
      range.setEnd(node, end);
      ranges.push(range);
    }
  }
  if (!ranges.length) return false;
  if (supported()) CSS.highlights.set(NAME, new Highlight(...ranges));
  ranges[0].startContainer.parentElement?.scrollIntoView({ block: 'center', behavior: 'smooth' });
  return true;
}
