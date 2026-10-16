<script lang="ts">
  import { tick } from 'svelte';
  import { blockById, defaultNext, linksFrom, refKey, startBlock } from '../../lib/adventures';
  import { clearHighlight, highlightTerms } from '../../lib/highlight';
  import { t } from '../../lib/i18n.svelte';
  import { blockLinkTarget, imageUrl, renderNotes, songLinkTarget } from '../../lib/notes';
  import { adventures, enterBlock, playSongLink, previousBlock, refTracks, setPlayed, startEffect } from '../../lib/stores/adventure.svelte';
  import { player, playQueue } from '../../lib/stores/player.svelte';
  import type { MusicRef } from '../../lib/types';
  import { openDialog } from '../../lib/stores/ui.svelte';
  import Icon from '../Icon.svelte';
  import ImagePopup from '../dialogs/ImagePopup.svelte';
  import AdventureMap from './AdventureMap.svelte';

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

  /** The song or playlist of the button is what the player plays right now. */
  const playingRef = (ref: MusicRef) =>
    player.playing && !!player.track && (ref.type === 'song' ? player.track.ufid === ref.ufid : !!members[refKey(ref)]?.has(player.track.id));
  const effectPlaying = (path: string) => player.effectPlaying && player.effect?.path === path;

  async function playRef(ref: MusicRef) {
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

  /** The overview of all blocks (the map) instead of the scene being played; before the session starts it is the welcome screen. */
  let overview = $state(false);

  function openFromMap(id: string) {
    overview = false;
    if (id === block?.id) return;
    if (block) advance(id);
    else void enterBlock(id);
  }
</script>

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
    </div>
    <AdventureMap {adventure} current={block?.id ?? start?.id ?? null} playing={!!block} onopen={openFromMap} />
  </div>
{:else}
  <article class="play">
    <div class="bar">
      <button class="icon-btn" title={t('Back')} disabled={!adventures.history.length} onclick={previousBlock}><Icon name="back" size={17} /></button>
      <select aria-label={t('Jump to a block')} value={block.id} onchange={(e) => void enterBlock(e.currentTarget.value)}>
        {#each adventure.blocks as item (item.id)}<option value={item.id}>{item.played ? '✓ ' : ''}{item.title || t('Untitled')}</option>{/each}
      </select>
      <button class="btn sm" title={t('All blocks and their links')} onclick={() => (overview = true)}><Icon name="compass" size={13} />{t('Overview')}</button>
      <span class="grow"></span>
      {#if adventure.editable}
        <button class="btn sm" class:on={block.played} onclick={() => setPlayed(block.id, !block.played)}>
          <Icon name="check" size={13} />{block.played ? t('Played') : t('Mark as played')}
        </button>
      {/if}
    </div>

    <div class="headline">
      {#if block.cover}
        {@const src = imageUrl(adventure.id, block.cover)}
        <button type="button" class="cover" title={t('Double-click to enlarge')}
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
              <button class="chip" class:on={playingRef(ref)} disabled={ref.type === 'playlist' && ref.unavailable} onclick={() => void playRef(ref)}
                      title={ref.type === 'playlist' && ref.unavailable ? t('unavailable') : ''}>
                <Icon name={playingRef(ref) ? 'volume' : ref.type === 'song' ? 'music' : 'playlist'} size={14} />{ref.title || ref.path}
              </button>
            {/each}
          </div>
        {/if}
        {#if block.effects.length}
          <div class="chips" aria-label={t('Effects')}>
            {#each block.effects as effect (effect.path)}
              <button class="chip" class:on={effectPlaying(effect.path)} onclick={() => void startEffect(effect)}>
                <Icon name={effectPlaying(effect.path) ? 'volume' : 'waves'} size={14} />{effect.name || effect.path}
              </button>
            {/each}
          </div>
        {/if}
      </div>
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
  .intro { display: flex; align-items: center; flex-wrap: wrap; gap: 12px 14px; color: var(--muted); }
  .intro-text { min-width: 0; }
  .intro h2 { margin: 0; color: var(--text); font-family: var(--font-display); }
  .intro p { margin: 2px 0 0; }
  .start .btn, .bar .btn { display: inline-flex; align-items: center; gap: 8px; }
  .play { display: flex; flex-direction: column; gap: 16px; max-width: 820px; width: 100%; margin: 0 auto; }
  .bar { display: flex; align-items: center; gap: 8px; }
  .bar select { min-width: 0; max-width: 60%; }
  .grow { flex: 1; }
  .btn.on { background: var(--accent-soft); border-color: var(--accent); color: var(--accent); }
  .headline { display: flex; align-items: center; gap: 16px; min-width: 0; }
  .cover { flex: none; display: block; padding: 0; width: clamp(96px, 16vw, 168px); aspect-ratio: 16 / 10; border-radius: 10px; overflow: hidden; border: 1px solid var(--border); cursor: zoom-in; }
  .cover img { display: block; width: 100%; height: 100%; object-fit: cover; }
  h1 { margin: 0; font-family: var(--font-display); font-size: clamp(1.5rem, 3vw, 2.2rem); letter-spacing: -0.01em; }
  .tools { display: flex; flex-direction: column; gap: 12px; }
  .chips { display: flex; flex-wrap: wrap; gap: 8px; }
  .chip { display: inline-flex; align-items: center; gap: 6px; }
  .notes { font-size: 1.1rem; line-height: 1.7; overflow-wrap: anywhere; }
  .notes :global(img) { max-width: 100%; border-radius: 8px; }
  .notes :global(blockquote) { margin: 0.8em 0; padding: 4px 14px; border-left: 3px solid var(--accent); color: var(--muted); }
  footer { display: flex; flex-wrap: wrap; gap: 10px; padding-top: 8px; border-top: 1px solid var(--border); }
  footer .btn { display: inline-flex; align-items: center; gap: 8px; }
</style>
