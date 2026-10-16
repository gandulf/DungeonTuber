// The notes of a block in the WYSIWYG editor (Tiptap) and back to Markdown, which stays the stored format (play mode renders it with
// lib/notes.ts). The editor and the round-trip tests use the same extensions, so what the tests check is what the editor writes.
// Our own syntax: links to blocks `[text](block:<id>)` and songs `[text](song:<ufid>)`, images of the adventure
// `![alt|300x200](image:<name>)` (the size after the bar keeps the aspect ratio, see notes.ts).
import type { AnyExtension, JSONContent } from '@tiptap/core';
import Image from '@tiptap/extension-image';
import { Markdown, MarkdownManager } from '@tiptap/markdown';
import StarterKit from '@tiptap/starter-kit';
import { imageSize } from './notes';

export const BLOCK_PREFIX = 'block:';
export const SONG_PREFIX = 'song:';
export const IMAGE_PREFIX = 'image:';

/** Notes are written with single line breaks, which the notes always showed as breaks (marked's `breaks`). */
export const MARKED_OPTIONS = { gfm: true, breaks: true };

const sizeSuffix = (width: unknown, height: unknown) => {
  const [w, h] = [Number(width) || 0, Number(height) || 0].map((value) => Math.round(value));
  return w && h ? `|${w}x${h}` : w ? `|${w}` : h ? `|x${h}` : '';
};

/** An image in the text, of the adventure (`image:<name>`) or from the web; its size is written after the bar of the alt text. */
export const NoteImage = Image.extend<{ resolveSrc: (src: string) => string } & Record<string, unknown>>({
  addOptions() {
    return {
      ...this.parent!(),
      inline: true,
      resolveSrc: (src: string) => src,
    } as never;
  },
  addAttributes() {
    const parent = this.parent!() as Record<string, Record<string, unknown>>;
    const resolve = (src: unknown) => this.options.resolveSrc(String(src ?? ''));
    // the browser loads image:<name> from the adventure; the document (and the Markdown) keeps the short form
    return { ...parent, src: { ...parent.src, renderHTML: (attributes: Record<string, unknown>) => ({ src: resolve(attributes.src) }) } };
  },
  parseMarkdown: (token, helpers) => {
    const { alt, width, height } = imageSize(String(token.text ?? ''));
    return helpers.createNode('image', { src: token.href, title: token.title || null, alt: alt || null, width, height });
  },
  renderMarkdown: (node) => {
    const attrs = node.attrs ?? {};
    const alt = `${String(attrs.alt ?? '').replace(/[[\]|]/g, '')}${sizeSuffix(attrs.width, attrs.height)}`;
    return attrs.title ? `![${alt}](${attrs.src ?? ''} "${attrs.title}")` : `![${alt}](${attrs.src ?? ''})`;
  },
});

/** The extensions of the notes. `resolveImage` turns `image:<name>` into the address the browser loads (none in the tests). */
export function noteExtensions(options: { resolveImage?: (src: string) => string; resize?: boolean; extra?: AnyExtension[] } = {}): AnyExtension[] {
  return [
    // code and code blocks have no button, but notes that use them keep them
    StarterKit.configure({
      underline: false, // Markdown has no underline
      // links to blocks and songs are links with our own protocols; they open with Ctrl/Cmd + click (see NotesEditor.svelte)
      link: {
        openOnClick: false,
        autolink: true,
        protocols: ['block', 'song'],
        HTMLAttributes: { target: null, rel: null },
      },
    }),
    NoteImage.configure({
      resolveSrc: options.resolveImage ?? ((src: string) => src),
      ...(options.resize ? { resize: { enabled: true, alwaysPreserveAspectRatio: true, minWidth: 40, minHeight: 30 } } : {}),
    }),
    Markdown.configure({ markedOptions: MARKED_OPTIONS }),
    ...(options.extra ?? []),
  ];
}

/** Markdown to the editor's document and back without an editor (the tests, and checks of what the editor will write). */
export function markdownManager(): MarkdownManager {
  return new MarkdownManager({ markedOptions: MARKED_OPTIONS, extensions: noteExtensions() });
}

/** The Markdown the notes are stored as: what the serializer writes, with `[[Block title]]` that had no block yet left readable
 *  (the serializer escapes the brackets, which would keep it from becoming a link once the block exists). */
export function toStoredMarkdown(markdown: string): string {
  return markdown.replace(/\\\[\\\[([^\]\n]+?)\\\]\\\]/g, '[[$1]]').trim();
}

export function roundTrip(markdown: string, manager = markdownManager()): string {
  return toStoredMarkdown(manager.serialize(manager.parse(markdown) as JSONContent));
}
