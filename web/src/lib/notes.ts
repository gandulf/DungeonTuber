// Markdown of the notes of an adventure block. Raw HTML is shown as text and only safe link targets survive, so notes
// (which other users can read once an adventure is public) can never inject markup or scripts.
// Links can point to a block of the adventure: `[text](block:<id>)` (the id survives renames), or `[[Block title]]` for short,
// and to a song: `[text](song:<ufid>)` (a click plays it). Images of the adventure are `![alt](image:<name>)`; a size after a bar in
// the alt text keeps the aspect ratio: `![map|300](…)` is 300 px wide, `![map|x200](…)` 200 px high, `![map|300x200](…)` fits into
// that box.
import { Marked } from 'marked';

const escape = (text: string) => text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

const safeUrl = (url: string) => /^(https?:|mailto:|\/|#)/i.test(url.trim());

export interface BlockRef { id: string; title: string }

const BLOCK_PREFIX = 'block:';
const SONG_PREFIX = 'song:';
const IMAGE_PREFIX = 'image:';
const IMAGE_NAME = /^[0-9a-f]{12}\.(png|jpg|gif|webp)$/;

/** The song ids (UFIDs) the notes link to. */
export const songLinkIds = (markdown: string) => [...markdown.matchAll(/\]\(song:([^)\s]+)\)/g)].map((match) => match[1]);

/** Marks the song links of rendered notes whose song can no longer be found (`missing` holds `song:<ufid>` keys) with `title`. */
export function markMissingSongLinks(element: HTMLElement, missing: Set<string>, title: string) {
  for (const link of element.querySelectorAll<HTMLElement>('a[data-song]')) {
    const gone = missing.has(`song:${link.dataset.song}`);
    link.classList.toggle('missing', gone);
    if (gone) link.title = title;
    else link.removeAttribute('title');
  }
}

/** Where an image of an adventure (a picture of the notes or the cover of a block) is served from. */
export const imageUrl = (adventure: string, name: string) => `/api/adventures/${encodeURIComponent(adventure)}/images/${encodeURIComponent(name)}`;

const IMAGE_SIZE = /^(.*?)\s*\|\s*(\d{1,5})?(?:\s*[x×]\s*(\d{1,5}))?\s*$/;
const MAX_SIZE = 4000;

/** The alt text of an image without its size (`map|300x200`) and the size in pixels; null where it is not given. */
export function imageSize(text: string): { alt: string; width: number | null; height: number | null } {
  const match = IMAGE_SIZE.exec(text);
  const [width, height] = [match?.[2], match?.[3]].map((value) => (value && +value > 0 ? Math.min(+value, MAX_SIZE) : null));
  if (!match || (width === null && height === null)) return { alt: text, width: null, height: null };
  return { alt: match[1], width, height };
}

/** The <img> of the notes: with a size it scales to it and keeps its aspect ratio (both: it fits into the box). */
function imageTag(src: string, text: string, title?: string | null): string {
  const { alt, width, height } = imageSize(text);
  const style = width && height ? ` style="width:${width}px;height:${height}px;object-fit:contain"`
    : width ? ` style="width:${width}px;height:auto"` : height ? ` style="height:${height}px;width:auto;object-fit:contain"` : '';
  return `<img src="${src}" alt="${escape(alt)}"${title ? ` title="${escape(title)}"` : ''}${style} loading="lazy">`;
}

let adventureId = ''; // the adventure being rendered: where its images are served from
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
      if (href.startsWith(IMAGE_PREFIX)) {
        const name = href.slice(IMAGE_PREFIX.length);
        return IMAGE_NAME.test(name) && adventureId ? imageTag(`/api/adventures/${escape(adventureId)}/images/${name}`, text) : escape(imageSize(text).alt);
      }
      if (!safeUrl(href)) return escape(imageSize(text).alt);
      return imageTag(escape(href), text, title);
    },
  },
});

/** The notes as HTML; `blocks` are the blocks of the adventure that links can point to. */
export function renderNotes(source: string, blocks: BlockRef[] = [], adventure = ''): string {
  known = blocks;
  adventureId = adventure;
  return marked.parse(resolveBlockTitles(source, blocks), { async: false });
}

/** `[[Block title]]` as a link to that block (by its id, which survives renaming); titles without a block stay as they are. */
export function resolveBlockTitles(source: string, blocks: BlockRef[]): string {
  return source.replace(/\[\[([^[\]\n]+)\]\]/g, (match, title: string) => {
    const hit = blocks.find((block) => block.title.trim().toLowerCase() === title.trim().toLowerCase());
    return hit ? `[${title.trim()}](${BLOCK_PREFIX}${hit.id})` : match;
  });
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
