<script lang="ts">
  import { tick, type Snippet } from 'svelte';
  import { blockById, defaultNext, linksFrom, nextBlock, refKey, startBlock } from '../../lib/adventures';
  import { clearHighlight, highlightTerms } from '../../lib/highlight';
  import { t } from '../../lib/i18n.svelte';
  import { blockLinkTarget, imageUrl, markMissingSongLinks, pdfLinkTarget, renderNotes, songLinkIds, songLinkTarget } from '../../lib/notes';
  import { adventures, effectKey, enterBlock, missingEntries, openPdf, playSongLink, previousBlock, refTracks, setPlayed, startEffect } from '../../lib/stores/adventure.svelte';
  import { scrollsSideways, swipeOf } from '../../lib/swipe';
  import { player, playQueue, togglePlay } from '../../lib/stores/player.svelte';
  import type { MusicRef } from '../../lib/types';
  import { openDialog, ui } from '../../lib/stores/ui.svelte';
  import { prefs, savePrefs } from '../../lib/prefs.svelte';
  import Icon from '../Icon.svelte';
  import ImagePopup from '../dialogs/ImagePopup.svelte';
  import AdventureMap from './AdventureMap.svelte';

  /** Buttons of the adventure view put at the end of the play bar (on phones it has no header line of its own). */
  let { tools }: { tools?: Snippet } = $props();

  const adventure = $derived(adventures.current!);
  const block = $derived(blockById(adventure, adventures.playing));
  const start = $derived(startBlock(adventure));
  const choices = $derived(block ? linksFrom(adventure, block.id) : []);
  const preferred = $derived(block ? defaultNext(adventure, block.id) : null);

  // the songs of every playlist of the block, to show which button is playing
  let members = $state<Record<string, Set<string>>>({});
  $effect(() => {
    const refs = block?.music.filter((ref) => ref.type === 'playlist') ?? [];
    let stale = false;
    void (async () => {
      const next: Record<string, Set<string>> = {};
      for (const ref of refs) next[refKey(ref)] = new Set(((await refTracks(ref)) ?? []).map((track) => track.id));
      if (!stale) members = next;
    })();
    return () => (stale = true);
  });

  // songs, playlists and effects of the block (and songs its notes link to) that can no longer be found are marked
  let missing = $state(new Set<string>());
  $effect(() => {
    if (!block) return;
    let stale = false;
    const songs = songLinkIds(block.markdown);
    void missingEntries(block, songs).then((found) => { if (!stale) missing = found; });
    return () => (stale = true);
  });
  $effect(() => {
    void block?.markdown;
    if (notesElement) markMissingSongLinks(notesElement, missing, t('This song was not found in the library.'));
  });
  const missingTitle = $derived(t('No longer found: removed, moved or not visible to you.'));

  /** The song or playlist of the button is what the player plays right now. */
  const playingRef = (ref: MusicRef) =>
    player.playing && !!player.track && (ref.type === 'song' ? player.track.ufid === ref.ufid : !!members[refKey(ref)]?.has(player.track.id));
  const effectPlaying = (path: string) => player.effectPlaying && player.effect?.path === path;

  /** Plays a song or playlist of the block; the one that is playing pauses (like the effects). */
  async function playRef(ref: MusicRef) {
    if (playingRef(ref)) return togglePlay();
    const tracks = await refTracks(ref);
    if (tracks?.length) await playQueue(tracks);
  }

  function notesClick(event: MouseEvent) {
    const song = songLinkTarget(event.target);
    if (song) {
      event.preventDefault();
      void playSongLink(song);
      return;
    }
    const pdfPage = pdfLinkTarget(event.target);
    if (pdfPage) {
      event.preventDefault();
      void openPdf(pdfPage);
      return;
    }
    const target = blockLinkTarget(event.target);
    if (!target) return;
    event.preventDefault();
    advance(target);
  }

  // the words of the header search are marked in the notes of the block it went to; another block clears the marks
  let notesElement = $state<HTMLDivElement | null>(null);
  $effect(() => {
    void block?.id;
    clearHighlight();
    return clearHighlight; // also when play mode is left
  });
  $effect(() => {
    const wanted = adventures.highlight;
    if (!wanted || !block || wanted.blockId !== block.id || !notesElement) return;
    const [element, terms] = [notesElement, wanted.terms];
    adventures.highlight = null;
    void tick().then(() => highlightTerms(element, terms));
  });

  function advance(id: string) {
    if (block && !block.played && adventure.editable) setPlayed(block.id, true);
    void enterBlock(id);
  }

  /** Arrow keys: right goes to the next block (the only linked one; with none or several links the next of the list), left back to the one before. They leave the
   *  arrows alone where those have a meaning of their own (text fields, sliders) and while a dialog or a menu is open. */
  function onKey(event: KeyboardEvent) {
    if (event.key !== 'ArrowRight' && event.key !== 'ArrowLeft') return;
    if (!block || overview || event.defaultPrevented || event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
    if ((event.target as Element | null)?.closest?.('input, textarea, select, [contenteditable], [role="slider"]') || document.querySelector('dialog[open]') || ui.menu) return;
    if (event.key === 'ArrowLeft' ? goBack() : goNext()) event.preventDefault();
  }

  /** To the next block (see nextBlock); false when there is none. */
  function goNext(): boolean {
    const next = block ? nextBlock(adventure, block.id) : null;
    if (next) advance(next.id);
    return !!next;
  }

  /** Back to the block before, false when there is none. */
  function goBack(): boolean {
    if (!adventures.history.length) return false;
    previousBlock();
    return true;
  }

  // touch screens: swipe left for the next block, right for the one before (the arrow keys of play mode); not where a finger has its own
  // job (a text field, a table that scrolls sideways), while text is selected, or while a dialog or a menu is open
  let swipe: { x: number; y: number; time: number } | null = null;

  function swipeStart(event: TouchEvent) {
    swipe = null;
    const touch = event.touches[0];
    const target = event.target as Element | null;
    if (event.touches.length !== 1 || !touch || overview) return;
    if (target?.closest('input, textarea, select, [contenteditable], [role="slider"]') || scrollsSideways(target, event.currentTarget as Element)) return;
    swipe = { x: touch.clientX, y: touch.clientY, time: Date.now() };
  }

  function swipeEnd(event: TouchEvent) {
    const [start, touch] = [swipe, event.changedTouches[0]];
    swipe = null;
    if (!start || !touch || !block || getSelection()?.toString() || document.querySelector('dialog[open]') || ui.menu) return;
    const direction = swipeOf(touch.clientX - start.x, touch.clientY - start.y, Date.now() - start.time);
    if (direction === 'left') goNext();
    else if (direction === 'right') goBack();
  }

  /** The overview of all blocks (the map) instead of the scene being played; before the session starts it is the welcome screen. */
  let overview = $state(false);

  function openFromMap(id: string) {
    overview = false;
    if (id === block?.id) return;
    if (block) advance(id);
    else void enterBlock(id);
  }
</script>

<svelte:window onkeydown={onKey} />

{#if !block || overview}
  <div class="start">
    <div class="intro">
      <Icon name="mask" size={34} />
      <div class="intro-text">
        <h2>{adventure.title}</h2>
        {#if block}
          <p class="muted">{t('The scene being played is marked. Click a block to go there.')}</p>
        {:else if start}
          <p class="muted">{adventure.blocks.some((item) => item.played) ? t('Continue where you stopped.') : t('Start the session with the first scene.')}</p>
        {:else}
          <p class="muted">{t('This adventure has no blocks yet.')}</p>
        {/if}
      </div>
      <span class="grow"></span>
      {#if block}
        <button class="btn primary" onclick={() => (overview = false)}><Icon name="back" size={15} />{t('Back to the scene')}</button>
      {:else if start}
        <button class="btn primary" onclick={() => void enterBlock(start.id)}><Icon name="play" size={15} />{start.title || t('Untitled')}</button>
      {/if}
      {@render tools?.()}
    </div>
    <AdventureMap {adventure} current={block?.id ?? start?.id ?? null} playing={!!block} onopen={openFromMap} />
  </div>
{:else}
  <article class="play" ontouchstart={swipeStart} ontouchend={swipeEnd}>
    <div class="bar">
      <button class="icon-btn" title="{t('Back')} (←)" disabled={!adventures.history.length} onclick={previousBlock}><Icon name="back" size={17} /></button>
      <select aria-label={t('Jump to a block')} value={block.id} onchange={(e) => void enterBlock(e.currentTarget.value)}>
        {#each adventure.blocks.filter((entry) => !entry.inline || entry.id === block.id) as item (item.id)}<option value={item.id}>{item.played ? '✓ ' : ''}{item.title || t('Untitled')}</option>{/each}
      </select>
      <button class="btn sm" title={t('All blocks and their links')} aria-label={t('Overview')} onclick={() => (overview = true)}><Icon name="compass" size={13} /><span class="label">{t('Overview')}</span></button>
      <span class="grow"></span>
      {#if adventure.editable}
        <!-- the button shows whether the block is played (on phones as an icon only) -->
        <button class="btn sm" class:on={block.played} title={t('Mark as played')} aria-label={t('Played')} aria-pressed={block.played} onclick={() => setPlayed(block.id, !block.played)}>
          <Icon name="check" size={13} /><span class="label">{t('Played')}</span>
        </button>
      {/if}
      {@render tools?.()}
    </div>

    <div class="headline">
      {#if block.cover}
        {@const src = imageUrl(adventure.id, block.cover)}
        <button type="button" class="cover" title={t('Double-click to enlarge')}
                onclick={() => { if (ui.coarse) openDialog(ImagePopup, { src, title: block.title || t('Cover image') }); }}
                ondblclick={() => openDialog(ImagePopup, { src, title: block.title || t('Cover image') })}>
          <img {src} alt={block.title || t('Cover image')} />
        </button>
      {/if}
      <h1 class="selectable">{block.title || t('Untitled')}</h1>
    </div>

    <!-- the music and, on a line of its own, the effects of the block -->
    {#if block.music.length || block.effects.length}
      <div class="tools">
        {#if block.music.length}
          <div class="chips" aria-label={t('Music')}>
            {#each block.music as ref (refKey(ref))}
              {@const gone = missing.has(refKey(ref))}
              <button class="chip" class:on={playingRef(ref)} class:missing={gone} disabled={gone} onclick={() => void playRef(ref)} title={gone ? missingTitle : ''}>
                <Icon name={gone ? 'info' : playingRef(ref) ? 'volume' : ref.type === 'song' ? 'music' : 'playlist'} size={14} />{ref.title || ref.path}
              </button>
            {/each}
          </div>
        {/if}
        {#if block.effects.length}
          <div class="chips" aria-label={t('Effects')}>
            {#each block.effects as effect (effect.path)}
              {@const gone = missing.has(effectKey(effect))}
              <button class="chip" class:on={effectPlaying(effect.path)} class:missing={gone} disabled={gone} onclick={() => void startEffect(effect)} title={gone ? missingTitle : ''}>
                <Icon name={gone ? 'info' : effectPlaying(effect.path) ? 'volume' : 'waves'} size={14} />{effect.name || effect.path}
              </button>
            {/each}
          </div>
        {/if}
      </div>
    {/if}

    <!-- the short summary (TL;DR) to scan the scene at a glance; folded away it stays a one-line button -->
    {#if block.tldr.trim()}
      <section class="tldr" class:open={prefs.tldrOpen}>
        <button type="button" class="tldr-head" aria-expanded={prefs.tldrOpen} onclick={() => { prefs.tldrOpen = !prefs.tldrOpen; savePrefs(); }}>
          <Icon name={prefs.tldrOpen ? 'chevron-down' : 'chevron-right'} size={14} /><span class="label-xs">{t('TL;DR')}</span>
        </button>
        {#if prefs.tldrOpen}
          <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
          <div class="tldr-text selectable" onclick={notesClick}>{@html renderNotes(block.tldr, adventure.blocks, adventure.id)}</div>
        {/if}
      </section>
    {/if}

    <!-- svelte-ignore a11y_click_events_have_key_events, a11y_no_static_element_interactions -->
    <div class="notes selectable" bind:this={notesElement} onclick={notesClick}>{@html renderNotes(block.markdown, adventure.blocks, adventure.id) || `<p class="muted">${t('No notes yet.')}</p>`}</div>

    <footer>
      {#each choices as link (link)}
        {@const target = blockById(adventure, link.to)}
        {#if target}
          <button class="btn" class:primary={target.id === preferred?.id} onclick={() => advance(target.id)}>
            {link.label || target.title || t('Untitled')}<Icon name="forward" size={15} />
          </button>
        {/if}
      {:else}
        <span class="muted">{t('End of this path.')}</span>
      {/each}
    </footer>
  </article>
{/if}

<style>
  .start { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 16px; width: 100%; }
  .intro { display: flex; flex: none; align-items: center; flex-wrap: wrap; gap: 12px 14px; color: var(--muted); }
  /* low screens (a phone held sideways): the line under the title gives its room to the map */
  @media (max-height: 600px) { .intro p { display: none; } }
  @media (max-width: 900px), (max-height: 600px) {
    .start { gap: 10px; }
    .intro { gap: 8px 10px; }
    .intro > :global(svg) { display: none; } /* the mask beside the title */
    .intro h2 { font-size: 1.15rem; }
  }
  .intro-text { min-width: 0; }
  .intro h2 { margin: 0; color: var(--text); font-family: var(--font-display); }
  .intro p { margin: 2px 0 0; }
  .start .btn, .bar .btn { display: inline-flex; align-items: center; gap: 8px; }
  .play { display: flex; flex-direction: column; gap: 16px; max-width: 820px; width: 100%; margin: 0 auto; }
  .bar { display: flex; align-items: center; gap: 8px; }
  .bar select { min-width: 0; max-width: 60%; }
  .grow { flex: 1; }
  /* phones: the play bar is one line: the block list takes the room, the buttons are icons */
  @media (max-width: 900px) {
    .bar { gap: 6px; }
    .bar select { flex: 1; max-width: none; }
    .bar .grow { display: none; }
    .bar .label { display: none; }
  }
  .btn.on { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); }
  .headline { display: flex; align-items: center; gap: 16px; min-width: 0; }
  .cover { flex: none; display: block; padding: 0; width: clamp(96px, 16vw, 168px); aspect-ratio: 16 / 10; border-radius: 10px; overflow: hidden; border: 1px solid var(--border); cursor: zoom-in; }
  .cover img { display: block; width: 100%; height: 100%; object-fit: cover; }
  h1 { margin: 0; font-family: var(--font-display); font-size: clamp(1.5rem, 3vw, 2.2rem); letter-spacing: -0.01em; }
  .tools { display: flex; flex-direction: column; gap: 12px; }
  .chips { display: flex; flex-wrap: wrap; gap: 8px; }
  .chip { display: inline-flex; align-items: center; gap: 6px; }
  .chip.missing { color: var(--red); background: var(--red-soft); border-color: var(--red); border-style: dashed; text-decoration: line-through; cursor: not-allowed; }
  .notes { font-size: 1.1rem; line-height: 1.7; overflow-wrap: anywhere; }
  .notes :global(img) { max-width: 100%; border-radius: 8px; }
  .notes :global(blockquote) { margin: 0.8em 0; padding: 4px 14px; border-left: 3px solid var(--accent); color: var(--muted); }
  .tldr { display: flex; flex-direction: column; gap: 4px; padding: 6px 14px; border-radius: 10px; background: var(--accent-soft); border-left: 3px solid var(--accent); }
  .tldr.open { padding-bottom: 10px; }
  .tldr-head { display: inline-flex; align-items: center; gap: 6px; align-self: flex-start; padding: 2px 0; color: var(--accent); }
  .tldr-text { line-height: 1.55; overflow-wrap: anywhere; }
  .tldr-text :global(ul) { margin: 0; padding-left: 1.2em; }
  .tldr-text :global(p) { margin: 0 0 0.4em; }
  footer { display: flex; flex-wrap: wrap; gap: 10px; padding-top: 8px; border-top: 1px solid var(--border); }
  footer .btn { display: inline-flex; align-items: center; gap: 8px; }
</style>
