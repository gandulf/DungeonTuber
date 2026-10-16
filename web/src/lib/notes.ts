// Markdown of the notes of an adventure block. Raw HTML is shown as text and only safe link targets survive, so notes
// (which other users can read once an adventure is public) can never inject markup or scripts.
// Links can point to a block of the adventure: `[text](block:<id>)` (the id survives renames), or `[[Block title]]` for short,
// and to a song: `[text](song:<ufid>)` (a click plays it).
import { Marked } from 'marked';

const escape = (text: string) => text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

const safeUrl = (url: string) => /^(https?:|mailto:|\/|#)/i.test(url.trim());

export interface BlockRef { id: string; title: string }

const BLOCK_PREFIX = 'block:';
const SONG_PREFIX = 'song:';
let known: BlockRef[] = []; // the blocks of the adventure being rendered (the renderer below is synchronous)

const marked = new Marked({ gfm: true, breaks: true });
marked.use({
  renderer: {
    html({ text }) {
      return escape(text);
    },
    link({ href, title, tokens }) {
      const text = this.parser.parseInline(tokens);
      if (href.startsWith(BLOCK_PREFIX)) {
        const id = href.slice(BLOCK_PREFIX.length);
        return `<a href="#" class="block-link${known.some((block) => block.id === id) ? '' : ' broken'}" data-block="${escape(id)}">${text}</a>`;
      }
      if (href.startsWith(SONG_PREFIX)) return `<a href="#" class="song-link" data-song="${escape(href.slice(SONG_PREFIX.length))}">${text}</a>`;
      if (!safeUrl(href)) return text;
      return `<a href="${escape(href)}"${title ? ` title="${escape(title)}"` : ''} target="_blank" rel="noopener noreferrer">${text}</a>`;
    },
    image({ href, title, text }) {
      if (!safeUrl(href)) return escape(text);
      return `<img src="${escape(href)}" alt="${escape(text)}"${title ? ` title="${escape(title)}"` : ''} loading="lazy">`;
    },
  },
});

/** The notes as HTML; `blocks` are the blocks of the adventure that links can point to. */
export function renderNotes(source: string, blocks: BlockRef[] = []): string {
  known = blocks;
  const resolved = source.replace(/\[\[([^[\]\n]+)\]\]/g, (match, title: string) => {
    const hit = blocks.find((block) => block.title.trim().toLowerCase() === title.trim().toLowerCase());
    return hit ? `[${title.trim()}](${BLOCK_PREFIX}${hit.id})` : match;
  });
  return marked.parse(resolved, { async: false });
}

/** The block a click on rendered notes points to (a link to a block), or null. */
export function blockLinkTarget(target: EventTarget | null): string | null {
  const link = (target as Element | null)?.closest?.<HTMLElement>('a[data-block]');
  return link && !link.classList.contains('broken') ? link.dataset.block ?? null : null;
}

/** The song (its UFID) a click on rendered notes points to, or null. */
export function songLinkTarget(target: EventTarget | null): string | null {
  const link = (target as Element | null)?.closest?.<HTMLElement>('a[data-song]');
  return link?.dataset.song ?? null;
}

function insertLink(text: string, start: number, end: number, label: string, target: string): Edit {
  const link = `[${label}](${target})`;
  return { text: text.slice(0, start) + link + text.slice(end), start: start + link.length, end: start + link.length };
}

/** Turns the selection into a link to a block (the title of the block when nothing is selected). */
export function applyBlockLink(text: string, start: number, end: number, block: BlockRef): Edit {
  return insertLink(text, start, end, text.slice(start, end) || block.title || 'block', BLOCK_PREFIX + block.id);
}

/** Turns the selection into a link that plays a song (the title of the song when nothing is selected). */
export function applySongLink(text: string, start: number, end: number, song: { ufid: string; title: string }): Edit {
  return insertLink(text, start, end, text.slice(start, end) || song.title || 'song', SONG_PREFIX + song.ufid);
}

/** What the formatting toolbar of the editor does to the selected text: [before, after] around it, or a prefix for every line. */
export type Format = 'bold' | 'italic' | 'heading' | 'list' | 'quote' | 'link' | 'rule';

export interface Edit { text: string; start: number; end: number }

/** Applies a format to the selection of `text` and returns the new text with the new selection. */
export function applyFormat(text: string, start: number, end: number, format: Format): Edit {
  const selected = text.slice(start, end);
  const wrap = (before: string, after: string, placeholder: string): Edit => {
    const inner = selected || placeholder;
    return { text: text.slice(0, start) + before + inner + after + text.slice(end), start: start + before.length, end: start + before.length + inner.length };
  };
  if (format === 'bold') return wrap('**', '**', 'bold');
  if (format === 'italic') return wrap('*', '*', 'italic');
  if (format === 'link') return wrap('[', '](https://)', 'text');
  if (format === 'rule') {
    const insert = (start > 0 && text[start - 1] !== '\n' ? '\n' : '') + '\n---\n';
    return { text: text.slice(0, start) + insert + text.slice(end), start: start + insert.length, end: start + insert.length };
  }
  // line formats: every line touched by the selection gets the prefix (or loses it when all of them have it)
  const prefix = format === 'heading' ? '## ' : format === 'quote' ? '> ' : '- ';
  const lineStart = text.lastIndexOf('\n', start - 1) + 1;
  const newline = text.indexOf('\n', end);
  const lineEnd = newline < 0 ? text.length : newline;
  const lines = text.slice(lineStart, lineEnd).split('\n');
  const all = lines.every((line) => line.startsWith(prefix));
  const changed = lines.map((line) => (all ? line.slice(prefix.length) : prefix + line)).join('\n');
  return { text: text.slice(0, lineStart) + changed + text.slice(lineEnd), start: lineStart, end: lineStart + changed.length };
}
