<script lang="ts">
  import { Editor, Extension, type Range } from '@tiptap/core';
  import { Placeholder } from '@tiptap/extensions';
  import Suggestion from '@tiptap/suggestion';
  import { onMount } from 'svelte';
  import { api } from '../../lib/api';
  import { clearHighlight, highlightTerms } from '../../lib/highlight';
  import { t } from '../../lib/i18n.svelte';
  import { imageUrl, resolveBlockTitles, type BlockRef } from '../../lib/notes';
  import { BLOCK_PREFIX, IMAGE_PREFIX, noteExtensions, SONG_PREFIX, toStoredMarkdown } from '../../lib/notesMarkdown';
  import { HIGHLIGHT_COLORS, type HighlightColor } from '../../lib/notes';
  import { askText, errorToast, openDialog } from '../../lib/stores/ui.svelte';
  import type { MusicRef } from '../../lib/types';
  import Icon from '../Icon.svelte';
  import PickMusicDialog from './PickMusicDialog.svelte';

  /** The notes of a block as a WYSIWYG editor (Tiptap). They are stored as Markdown (lib/notesMarkdown.ts): `onchange` gets the
   *  Markdown after each change, a new `value` from outside (the AI draft) replaces the text. Links to blocks (typed with `[[`)
   *  and songs open with Ctrl/Cmd + click; images are pasted, dropped or picked and stored in the adventure. */
  let { value, adventureId, blocks, pool, highlight = null, onhighlighted = () => {}, onchange, onopenblock, onplaysong, missingSongs = [] }: {
    /** Songs (UFIDs) of song links that can no longer be found: their links are marked. */
    missingSongs?: string[];
    /** Words of the header search to mark (once); `onhighlighted` says they were taken. */
    highlight?: string[] | null;
    onhighlighted?: () => void;
    value: string;
    adventureId: string;
    /** The other blocks, the targets of block links. */
    blocks: BlockRef[];
    /** The music of the adventure, offered first for a song link. */
    pool: MusicRef[];
    onchange: (markdown: string) => void;
    onopenblock: (id: string) => void;
    onplaysong: (ufid: string) => void;
  } = $props();

  let element = $state<HTMLDivElement | null>(null);

  // links to missing songs are marked by a style sheet of attribute selectors: ProseMirror redraws its links whenever it likes, so
  // classes set on them would not last
  const scope = `notes-${Math.random().toString(36).slice(2, 10)}`;
  $effect(() => {
    if (!missingSongs.length) return;
    const quoted = (text: string) => `"${text.replace(/["\\]/g, '\\$&')}"`;
    const links = missingSongs.map((ufid) => `[data-notes="${scope}"] .ProseMirror a[href=${quoted(`song:${ufid}`)}]`).join(',');
    const sheet = document.createElement('style');
    sheet.textContent = `${links} { color: var(--red) !important; background: var(--red-soft) !important; text-decoration: line-through !important; }`
      + links.split(',').map((selector) => `${selector}::before`).join(',') + ` { content: '⚠ ' !important; }`;
    document.head.append(sheet);
    return () => sheet.remove();
  });
  let fileInput = $state<HTMLInputElement | null>(null);
  let editor = $state<Editor | null>(null);
  let version = $state(0); // the toolbar follows every change of the editor
  let lastValue = ''; // the Markdown the editor holds, to tell its own changes from changes from outside

  // --- [[ : the blocks that fit what is typed, as a list at the caret
  let suggest = $state<{ items: BlockRef[]; index: number; left: number; top: number; command: (block: BlockRef) => void } | null>(null);

  function showSuggest(props: { items: BlockRef[]; clientRect?: (() => DOMRect | null) | null; command: (block: BlockRef) => void }) {
    const rect = props.clientRect?.();
    if (!rect || !props.items.length) {
      suggest = null;
      return;
    }
    suggest = { items: props.items, index: Math.min(suggest?.index ?? 0, props.items.length - 1), left: rect.left, top: rect.bottom + 4, command: props.command };
  }

  function linkText(chain: ReturnType<Editor['chain']>, range: Range | null, text: string, href: string) {
    const content = [{ type: 'text', text, marks: [{ type: 'link', attrs: { href } }] }, { type: 'text', text: ' ' }];
    return (range ? chain.insertContentAt(range, content) : chain.insertContent(content)).run();
  }

  const BlockSuggestion = Extension.create({
    name: 'blockSuggestion',
    addProseMirrorPlugins() {
      return [
        Suggestion<BlockRef, BlockRef>({
          editor: this.editor,
          char: '[[',
          allowSpaces: true,
          allowedPrefixes: null,
          items: ({ query }) => {
            const needle = query.replace(/\]+$/, '').trim().toLowerCase();
            return blocks.filter((block) => block.title.toLowerCase().includes(needle)).slice(0, 8);
          },
          command: ({ editor: target, range, props: block }) => linkText(target.chain().focus(), range, block.title || t('Untitled'), BLOCK_PREFIX + block.id),
          render: () => ({
            onStart: showSuggest,
            onUpdate: showSuggest,
            onExit: () => (suggest = null),
            onKeyDown: ({ event }) => {
              if (!suggest) return false;
              if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                suggest.index = (suggest.index + (event.key === 'ArrowDown' ? 1 : suggest.items.length - 1)) % suggest.items.length;
                return true;
              }
              if (event.key === 'Enter' || event.key === 'Tab') {
                suggest.command(suggest.items[suggest.index]);
                return true;
              }
              if (event.key === 'Escape') {
                suggest = null;
                return true;
              }
              return false;
            },
          }),
        }),
      ];
    },
  });

  // --- images: uploaded into the adventure and referred to as image:<name>
  const imageOf = (files: FileList | null | undefined) => [...(files ?? [])].find((file) => file.type.startsWith('image/'));

  async function upload(file: File, at?: number) {
    try {
      const { name } = await api.uploadAdventureImage(adventureId, file);
      const node = { type: 'image', attrs: { src: IMAGE_PREFIX + name, alt: file.name.replace(/\.[^.]+$/, '') } };
      const chain = editor?.chain().focus();
      (at === undefined ? chain?.insertContent(node) : chain?.insertContentAt(at, node))?.run();
    } catch (e) {
      errorToast(e);
    }
  }

  // --- links: the selected text becomes the link, or without a selection the title is inserted as the link's text
  function link(href: string, title: string) {
    if (!editor) return;
    const chain = editor.chain().focus();
    if (editor.state.selection.empty) linkText(chain, null, title, href);
    else chain.extendMarkRange('link').setLink({ href }).run();
  }

  async function webLink() {
    if (!editor) return;
    if (editor.isActive('link')) {
      editor.chain().focus().extendMarkRange('link').unsetLink().run();
      return;
    }
    const href = (await askText(t('Link'), t('Address'), 'https://'))?.trim();
    if (href) link(href, href);
  }

  function songLink() {
    openDialog(PickMusicDialog, {
      single: true,
      pool,
      onpick: (ref: MusicRef) => {
        if (ref.type === 'song') link(SONG_PREFIX + ref.ufid, ref.title || ref.path);
      },
    });
  }

  /** Ctrl/Cmd + click on a link to a block opens it, on a song link plays it. */
  function followLink(event: MouseEvent): boolean {
    const href = (event.target as Element | null)?.closest?.('a')?.getAttribute('href') ?? '';
    if (!href.startsWith(BLOCK_PREFIX) && !href.startsWith(SONG_PREFIX)) return false;
    event.preventDefault();
    if (!(event.ctrlKey || event.metaKey)) return true; // a plain click puts the caret into the link
    if (href.startsWith(BLOCK_PREFIX)) onopenblock(href.slice(BLOCK_PREFIX.length));
    else onplaysong(href.slice(SONG_PREFIX.length));
    return true;
  }

  /** What the editor shows for the stored notes. Empty notes are an empty document (an empty paragraph): parsed as Markdown they
   *  would give a document without any block, which the editor's plugins cannot work with. */
  const content = (markdown: string) =>
    markdown.trim() ? { content: resolveBlockTitles(markdown, blocks), contentType: 'markdown' as const } : { content: '', contentType: 'html' as const };

  onMount(() => {
    lastValue = value;
    const instance = new Editor({
      element: element!,
      extensions: noteExtensions({
        resize: true,
        resolveImage: (src) => (src.startsWith(IMAGE_PREFIX) ? imageUrl(adventureId, src.slice(IMAGE_PREFIX.length)) : src),
        extra: [Placeholder.configure({ placeholder: t('Describe the scene… Type [[ to link a block.') }), BlockSuggestion],
      }),
      ...content(value),
      onUpdate: ({ editor: changed }) => {
        clearHighlight(); // the marks of a search are for reading, not for editing
        lastValue = toStoredMarkdown(changed.getMarkdown());
        onchange(lastValue);
      },
      // a transaction can come while Svelte updates the page (the blur when another block is shown): the toolbar follows after it
      onTransaction: () => queueMicrotask(() => version++),
      editorProps: {
        handlePaste: (_view, event) => {
          const file = imageOf(event.clipboardData?.files);
          if (!file) return false;
          void upload(file);
          return true;
        },
        handleDrop: (view, event, _slice, moved) => {
          const file = moved ? undefined : imageOf(event.dataTransfer?.files);
          if (!file) return false;
          void upload(file, view.posAtCoords({ left: event.clientX, top: event.clientY })?.pos);
          return true;
        },
        handleDOMEvents: { click: (_view, event) => followLink(event) },
      },
    });
    editor = instance;
    return () => {
      clearHighlight();
      instance.destroy();
    };
  });

  // the words of the header search: marked once the editor shows the text, and the first one scrolled into view
  $effect(() => {
    const terms = highlight;
    const surface = editor && element?.querySelector('.ProseMirror');
    if (!terms?.length || !surface) return;
    onhighlighted();
    requestAnimationFrame(() => highlightTerms(surface, terms));
  });

  // a new text from outside (the AI draft) replaces what the editor shows
  $effect(() => {
    const next = value;
    if (!editor || next === lastValue) return;
    lastValue = next;
    const { content: text, contentType } = content(next);
    editor.commands.setContent(text, { contentType, emitUpdate: false });
  });

  const active = (name: string, attrs?: Record<string, unknown>) => {
    void version;
    return editor?.isActive(name, attrs) ?? false;
  };
  const can = (action: 'undo' | 'redo') => {
    void version;
    return !!editor?.can()[action]();
  };
  const run = (apply: (chain: ReturnType<Editor['chain']>) => ReturnType<Editor['chain']>) => editor && apply(editor.chain().focus()).run();

  // every button shows an icon of the app's own set (one stroke style), no letters or emoji
  type Tool = { icon: string; title: string; on?: () => boolean; click: () => void; disabled?: () => boolean };
  const tools: (Tool | null)[] = [
    { icon: 'bold', title: 'Bold', on: () => active('bold'), click: () => run((c) => c.toggleBold()) },
    { icon: 'italic', title: 'Italic', on: () => active('italic'), click: () => run((c) => c.toggleItalic()) },
    { icon: 'strike', title: 'Strikethrough', on: () => active('strike'), click: () => run((c) => c.toggleStrike()) },
    null,
    { icon: 'heading-1', title: 'Heading', on: () => active('heading', { level: 2 }), click: () => run((c) => c.toggleHeading({ level: 2 })) },
    { icon: 'heading-2', title: 'Subheading', on: () => active('heading', { level: 3 }), click: () => run((c) => c.toggleHeading({ level: 3 })) },
    { icon: 'list', title: 'List', on: () => active('bulletList'), click: () => run((c) => c.toggleBulletList()) },
    { icon: 'list-ordered', title: 'Numbered list', on: () => active('orderedList'), click: () => run((c) => c.toggleOrderedList()) },
    { icon: 'quote', title: 'Read-aloud text (quote)', on: () => active('blockquote'), click: () => run((c) => c.toggleBlockquote()) },
    { icon: 'divider', title: 'Divider', click: () => run((c) => c.setHorizontalRule()) },
    null,
    { icon: 'link', title: 'Link to a web page', on: () => active('link') && !blockOrSongLink(), click: () => void webLink() },
    { icon: 'music', title: 'Link the selected text to a song', click: songLink },
    { icon: 'image', title: 'Insert an image', click: () => fileInput?.click() },
    null,
    { icon: 'undo', title: 'Undo', click: () => run((c) => c.undo()), disabled: () => !can('undo') },
    { icon: 'redo', title: 'Redo', click: () => run((c) => c.redo()), disabled: () => !can('redo') },
  ];

  // highlighting: the button uses the color picked last, the arrow next to it picks another one (or takes the highlight away)
  let highlightColor = $state<HighlightColor>(HIGHLIGHT_COLORS[0]);
  let highlightMenu = $state(false);
  const COLOR_NAMES: Record<HighlightColor, string> = { yellow: 'Yellow', green: 'Green', blue: 'Blue', red: 'Red', purple: 'Purple' };
  function applyHighlight(color: HighlightColor | null) {
    if (color) highlightColor = color;
    highlightMenu = false;
    run((c) => (color && !active('highlight', { color }) ? c.setHighlight(color) : c.setHighlight(null)));
  }

  function blockOrSongLink(): boolean {
    const href = String(editor?.getAttributes('link').href ?? '');
    return href.startsWith(BLOCK_PREFIX) || href.startsWith(SONG_PREFIX);
  }
</script>

<div class="notes-editor">
  <div class="toolbar" role="toolbar" aria-label={t('Format')}>
    {#each tools as tool, index (index)}
      {#if tool}
        <button type="button" class="fmt" class:on={tool.on?.()} disabled={tool.disabled?.()} title={t(tool.title)} aria-label={t(tool.title)}
                onmousedown={(e) => e.preventDefault()} onclick={tool.click}><Icon name={tool.icon} size={16} /></button>
        {#if tool.icon === 'strike'}
          <span class="hl-tool">
            <button type="button" class="fmt hl-main" class:on={active('highlight')} title={t('Highlight')} aria-label={t('Highlight')}
                    onmousedown={(e) => e.preventDefault()} onclick={() => applyHighlight(highlightColor)}>
              <Icon name="marker" size={16} /><span class="hl-bar hl-{highlightColor}"></span></button>
            <button type="button" class="fmt hl-more" title={t('Highlight color')} aria-label={t('Highlight color')} aria-haspopup="menu"
                    aria-expanded={highlightMenu} onmousedown={(e) => e.preventDefault()} onclick={() => (highlightMenu = !highlightMenu)}>
              <Icon name={highlightMenu ? 'chevron-up' : 'chevron-down'} size={12} /></button>
            {#if highlightMenu}
              <span class="hl-menu" role="menu">
                {#each HIGHLIGHT_COLORS as color (color)}
                  <button type="button" role="menuitem" class="hl-swatch hl-{color}" class:on={active('highlight', { color })} title={t(COLOR_NAMES[color])}
                          aria-label={t(COLOR_NAMES[color])} onmousedown={(e) => e.preventDefault()} onclick={() => applyHighlight(color)}></button>
                {/each}
                <button type="button" role="menuitem" class="fmt" title={t('Remove highlight')} aria-label={t('Remove highlight')}
                        onmousedown={(e) => e.preventDefault()} onclick={() => applyHighlight(null)}><Icon name="close" size={14} /></button>
              </span>
            {/if}
          </span>
        {/if}
      {:else}
        <span class="sep" aria-hidden="true"></span>
      {/if}
    {/each}
    {#if blocks.length}
      <select class="block-pick" aria-label={t('Link to a block')} title={t('Link the selected text to a block (or type [[)')} value=""
              onchange={(e) => { const target = blocks.find((block) => block.id === e.currentTarget.value); e.currentTarget.value = ''; if (target) link(BLOCK_PREFIX + target.id, target.title || t('Untitled')); }}>
        <option value="">{t('Block link…')}</option>
        {#each blocks as block (block.id)}<option value={block.id}>{block.title || t('Untitled')}</option>{/each}
      </select>
    {/if}
    <input bind:this={fileInput} type="file" accept="image/png,image/jpeg,image/gif,image/webp" hidden
           onchange={(e) => { const file = e.currentTarget.files?.[0]; e.currentTarget.value = ''; if (file) void upload(file); }} />
  </div>
  <div class="surface selectable" data-notes={scope} bind:this={element}></div>
  <span class="hint muted">{t('Ctrl + click opens a block link or plays a song link.')}</span>
  {#if suggest}
    <ul class="suggest" role="listbox" aria-label={t('Blocks')} style:left="{suggest.left}px" style:top="{suggest.top}px">
      {#each suggest.items as item, index (item.id)}
        <li role="option" aria-selected={index === suggest.index} class:on={index === suggest.index}>
          <button type="button" onmousedown={(e) => { e.preventDefault(); suggest?.command(item); }}>{item.title || t('Untitled')}</button>
        </li>
      {/each}
    </ul>
  {/if}
</div>

<style>
  .notes-editor { display: flex; flex-direction: column; gap: 6px; }
  .toolbar { position: sticky; top: 0; z-index: 2; display: flex; align-items: center; flex-wrap: wrap; gap: 2px; padding: 4px; border-radius: 10px; background: var(--bg-2); border: 1px solid var(--border); }
  .fmt { display: inline-flex; align-items: center; justify-content: center; width: 30px; height: 30px; padding: 0; border-radius: 7px; color: var(--muted); }
  .fmt:hover:not(:disabled) { background: var(--hover); color: var(--text); }
  .fmt.on { background: var(--accent-soft); color: var(--accent); }
  .fmt:disabled { opacity: 0.35; }
  .sep { width: 1px; height: 18px; margin: 0 4px; background: var(--border); }
  .hl-tool { position: relative; display: inline-flex; align-items: center; }
  .hl-main { position: relative; }
  .hl-bar { position: absolute; left: 7px; right: 7px; bottom: 4px; height: 3px; border-radius: 2px; }
  .hl-more { width: 16px; }
  .hl-menu { position: absolute; top: calc(100% + 4px); left: 0; z-index: 5; display: flex; align-items: center; gap: 4px; padding: 6px; border-radius: 10px;
             background: var(--bg-2); border: 1px solid var(--border-strong, var(--border)); box-shadow: var(--shadow); }
  .hl-swatch { width: 22px; height: 22px; padding: 0; border-radius: 50%; border: 2px solid transparent; }
  .hl-swatch.on, .hl-swatch:hover { border-color: var(--text); }
  .block-pick { margin-left: auto; max-width: 160px; font-size: var(--fs-sm); }
  .hint { font-size: var(--fs-xs); }
  .suggest { position: fixed; z-index: 50; margin: 0; padding: 4px; list-style: none; min-width: 200px; max-width: 320px; border-radius: 10px; background: var(--bg-2); border: 1px solid var(--border-strong, var(--border)); box-shadow: var(--shadow); }
  .suggest button { display: block; width: 100%; padding: 6px 10px; border-radius: 7px; text-align: left; color: var(--text); }
  .suggest li.on button, .suggest button:hover { background: var(--accent-soft); color: var(--accent); }

  /* the text itself: it looks like the notes in play mode */
  .surface :global(.ProseMirror) { min-height: 220px; padding: 12px 14px; border-radius: 10px; background: var(--bg); border: 1px solid var(--border); line-height: 1.6;
                                   overflow-wrap: anywhere; outline: none; }
  .surface :global(.ProseMirror:focus) { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
  .surface :global(.ProseMirror > *:first-child) { margin-top: 0; }
  .surface :global(.ProseMirror p) { margin: 0 0 0.6em; }
  .surface :global(.ProseMirror h2), .surface :global(.ProseMirror h3) { margin: 0.8em 0 0.3em; }
  .surface :global(.ProseMirror blockquote) { margin: 0.6em 0; padding-left: 12px; border-left: 3px solid var(--accent); color: var(--muted); }
  .surface :global(.ProseMirror hr) { border: none; border-top: 1px solid var(--border-strong, var(--border)); margin: 1em 0; }
  .surface :global(.ProseMirror hr.ProseMirror-selectednode) { border-top-color: var(--accent); }
  .surface :global(.ProseMirror a) { color: var(--accent); text-decoration: underline; cursor: text; }
  .surface :global(.ProseMirror a[href^="block:"]) { text-decoration: none; padding: 0 6px; border-radius: 6px; background: var(--accent-soft); }
  .surface :global(.ProseMirror a[href^="block:"]::before) { content: '↪ '; }
  .surface :global(.ProseMirror a[href^="song:"]) { text-decoration: none; padding: 0 6px; border-radius: 6px; background: var(--accent-soft); }
  .surface :global(.ProseMirror a[href^="song:"]::before) { content: '♪ '; }
  .surface :global(.ProseMirror img) { max-width: 100%; border-radius: 8px; object-fit: contain; vertical-align: bottom; }
  .surface :global(.ProseMirror img.ProseMirror-selectednode), .surface :global([data-resize-container].ProseMirror-selectednode img) { outline: 2px solid var(--accent); }
  .surface :global([data-resize-container]) { display: inline-block; max-width: 100%; }
  .surface :global([data-resize-handle]) { width: 10px; height: 10px; border-radius: 3px; background: var(--accent); border: 2px solid var(--bg); opacity: 0; transition: opacity 0.15s; z-index: 1; }
  .surface :global([data-resize-container]:hover [data-resize-handle]), .surface :global([data-resize-state="true"] [data-resize-handle]) { opacity: 1; }
  .surface :global(.ProseMirror p.is-editor-empty:first-child::before) { content: attr(data-placeholder); float: left; height: 0; color: var(--faint); pointer-events: none; }
</style>
