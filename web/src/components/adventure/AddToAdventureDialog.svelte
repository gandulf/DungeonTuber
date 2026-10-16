<script lang="ts">
  import { api } from '../../lib/api';
  import { refKey } from '../../lib/adventures';
  import { t } from '../../lib/i18n.svelte';
  import { imageUrl } from '../../lib/notes';
  import { addSongsToAdventure, adventures, loadAdventures } from '../../lib/stores/adventure.svelte';
  import { closeDialog, errorToast, toast } from '../../lib/stores/ui.svelte';
  import type { Adventure, AdventureBlock, SongRef, Track } from '../../lib/types';
  import Icon from '../Icon.svelte';
  import Modal from '../dialogs/Modal.svelte';

  /** "Add to adventure…" of the context menu of songs: the adventures changed last, then the blocks of the chosen one. */
  let { tracks }: { tracks: Track[] } = $props();

  const RECENT = 12;

  // songs are kept by their stable id (UFID): songs without one cannot be added
  const refs = $derived(tracks.filter((track) => track.ufid).map((track): SongRef => ({ type: 'song', ufid: track.ufid!, path: track.path, title: track.title || track.name })));
  const skipped = $derived(tracks.length - refs.length);

  const recent = $derived(adventures.list.filter((item) => item.editable).sort((a, b) => b.updated - a.updated).slice(0, RECENT));

  let chosen = $state<Adventure | null>(null);
  let loading = $state(false);
  let busy = $state(false);

  $effect(() => {
    if (!adventures.loaded) void loadAdventures();
  });

  async function choose(id: string) {
    // the open adventure may hold changes that are not saved yet
    if (adventures.current?.id === id) {
      chosen = adventures.current;
      return;
    }
    loading = true;
    try {
      chosen = await api.adventure(id);
    } catch (e) {
      errorToast(e);
    } finally {
      loading = false;
    }
  }

  const holdsAll = (block: AdventureBlock) => refs.every((ref) => block.music.some((item) => refKey(item) === refKey(ref)));

  const poolHoldsAll = (adventure: Adventure) => refs.every((ref) => adventure.music.some((item) => refKey(item) === refKey(ref)));

  /** Adds the songs to the adventure's music and, with a block, to that block too. */
  async function add(block: AdventureBlock | null) {
    if (!chosen || busy || !refs.length) return;
    busy = true;
    try {
      const added = await addSongsToAdventure(chosen.id, refs, block?.id);
      const name = block ? block.title || t('Untitled') : chosen.title;
      toast(added ? t('Added to "{0}"', name) : block ? t('The block already has these songs.') : t('The adventure already has these songs.'), added ? 'success' : 'info');
      closeDialog();
    } catch (e) {
      errorToast(e);
    } finally {
      busy = false;
    }
  }
</script>

<Modal title={t('Add to adventure')} onclose={closeDialog} width="480px">
  {#if skipped}
    <p class="note muted">{refs.length ? t('{0} song(s) have no stable id yet and are left out. Refresh the library first.', skipped) : t('This song has no stable id yet. Refresh the library first.')}</p>
  {/if}
  {#if chosen}
    <div class="head">
      <button class="icon-btn mini" title={t('Back')} aria-label={t('Back')} onclick={() => (chosen = null)}><Icon name="back" size={15} /></button>
      <Icon name="mask" size={16} /><span class="ellipsis strong">{chosen.title}</span>
    </div>
    <div class="list">
      <button class="row pool" disabled={busy || !refs.length} onclick={() => void add(null)}>
        <span class="avatar empty"><Icon name="playlist" size={14} /></span>
        <span class="ellipsis">{t('Only to the adventure music')}</span>
        <span class="muted count"><Icon name="music" size={12} />{chosen.music.length}</span>
        {#if poolHoldsAll(chosen)}<Icon name="check" size={14} />{/if}
      </button>
      <span class="label-xs blocks-label">{t('Blocks')}</span>
      {#each chosen.blocks as block (block.id)}
        {@const done = holdsAll(block)}
        <button class="row" disabled={busy || !refs.length} onclick={() => void add(block)}>
          {#if block.cover}<img class="avatar" src={imageUrl(chosen.id, block.cover)} alt="" />{:else}<span class="avatar empty"><Icon name="mask" size={14} /></span>{/if}
          <span class="ellipsis">{block.title || t('Untitled')}</span>
          <span class="muted count">{#if block.music.length}<Icon name="music" size={12} />{block.music.length}{/if}</span>
          {#if done}<Icon name="check" size={14} />{/if}
        </button>
      {/each}
    </div>
  {:else}
    <span class="label-xs">{t('Recent adventures')}</span>
    <div class="list">
      {#if loading || (!adventures.loaded && !recent.length)}<span class="muted">{t('Loading…')}</span>{/if}
      {#each recent as item (item.id)}
        <button class="row" disabled={loading} onclick={() => void choose(item.id)}>
          <Icon name="mask" size={16} />
          <span class="ellipsis">{item.title}</span>
          <span class="muted count">{t('{0} blocks', item.blocks)}</span>
          <Icon name="forward" size={14} />
        </button>
      {:else}
        {#if adventures.loaded}<span class="muted">{t('No adventures you can change yet.')}</span>{/if}
      {/each}
    </div>
  {/if}
  {#snippet footer()}
    <button class="btn" onclick={closeDialog}>{t('Cancel')}</button>
  {/snippet}
</Modal>

<style>
  .note { margin: 0 0 10px; font-size: var(--fs-sm); }
  .head { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
  .strong { font-weight: 600; }
  .mini { width: 26px; height: 26px; }
  .list { display: flex; flex-direction: column; gap: 1px; max-height: min(55vh, 420px); overflow-y: auto; margin-top: 6px; }
  .row { display: flex; align-items: center; gap: 10px; padding: 7px 10px; border-radius: 8px; text-align: left; color: var(--text); }
  .row:hover:not(:disabled) { background: var(--hover); }
  .row > .ellipsis { flex: 1; min-width: 0; }
  .count { display: inline-flex; align-items: center; gap: 4px; font-size: var(--fs-xs); flex: none; }
  .avatar { flex: none; width: 28px; height: 28px; border-radius: 50%; object-fit: cover; border: 1px solid var(--border); }
  .avatar.empty { display: grid; place-items: center; color: var(--muted); background: var(--surface); }
  .row :global(svg:last-child:not(:first-child)) { flex: none; }
  .pool { font-weight: 600; }
  .blocks-label { padding: 10px 10px 4px; }
</style>
