<script lang="ts">
  import { api } from '../../lib/api';
  import { t } from '../../lib/i18n.svelte';
  import { matcher } from '../../lib/search';
  import { globalTab, loadGlobal } from '../../lib/stores/library.svelte';
  import { closeDialog, errorToast, toast } from '../../lib/stores/ui.svelte';
  import type { MusicRef, PlaylistInfo } from '../../lib/types';
  import Icon from '../Icon.svelte';
  import Modal from '../dialogs/Modal.svelte';

  /** `onpick` adds a song or playlist to the block; `has` says whether the block holds it already. The dialog stays open to pick several. */
  let { onpick, has, single = false }: { onpick: (ref: MusicRef) => void; has: (ref: MusicRef) => boolean; /** Picks one song and closes (for a link in the notes). */ single?: boolean } = $props();

  const LIMIT = 80;

  let kind = $state<'song' | 'playlist'>('song');
  let query = $state('');
  let lists = $state<PlaylistInfo[]>([]);
  let loadingLists = $state(false);
  let added = $state(0); // makes the "added" marks update

  $effect(() => {
    void loadGlobal();
  });

  async function showPlaylists() {
    kind = 'playlist';
    if (lists.length || loadingLists) return;
    loadingLists = true;
    try {
      lists = (await api.libraryPlaylists()).playlists;
    } catch (e) {
      errorToast(e);
    } finally {
      loadingLists = false;
    }
  }

  const fits = $derived(matcher(query));
  const songs = $derived(globalTab.tracks.filter((track) => fits(`${track.title ?? ''} ${track.artist ?? ''} ${track.name}`)).slice(0, LIMIT));
  const playlists = $derived(lists.filter((list) => fits(list.name)));

  function songRef(ufid: string | null | undefined, path: string, title: string): MusicRef | null {
    if (!ufid) {
      toast(t('This song has no stable id yet. Refresh the library first.'), 'error');
      return null;
    }
    return { type: 'song', ufid, path, title };
  }

  function pick(ref: MusicRef | null) {
    if (!ref) return;
    onpick(ref);
    added++;
    if (single) closeDialog();
  }
</script>

<Modal title={single ? t('Link a song') : t('Add music')} onclose={closeDialog} width="560px">
  <div class="top">
    <div class="seg">
      <button type="button" class:on={kind === 'song'} onclick={() => (kind = 'song')}><Icon name="music" size={14} /> {t('Songs')}</button>
      {#if !single}<button type="button" class:on={kind === 'playlist'} onclick={() => void showPlaylists()}><Icon name="playlist" size={14} /> {t('Playlists')}</button>{/if}
    </div>
    <input type="search" placeholder={t('Search…')} bind:value={query} />
  </div>
  <div class="list" data-added={added}>
    {#if kind === 'song'}
      {#if globalTab.loading && !globalTab.tracks.length}<span class="muted">{t('Loading…')}</span>{/if}
      {#each songs as track (track.id)}
        {@const ref = track.ufid ? ({ type: 'song', ufid: track.ufid, path: track.path, title: track.title || track.name } as MusicRef) : null}
        <button class="row" onclick={() => pick(songRef(track.ufid, track.path, track.title || track.name))}>
          <Icon name="music" size={15} />
          <span class="ellipsis">{track.title || track.name}</span>
          <span class="muted ellipsis artist">{track.artist ?? ''}</span>
          {#if ref && has(ref)}<Icon name="check" size={14} />{/if}
        </button>
      {:else}
        {#if !globalTab.loading}<span class="muted">{t('No songs found.')}</span>{/if}
      {/each}
    {:else}
      {#if loadingLists}<span class="muted">{t('Loading…')}</span>{/if}
      {#each playlists as list (list.playlist_id)}
        {@const ref = { type: 'playlist', id: list.playlist_id, path: list.path, title: list.name } as MusicRef}
        <button class="row" onclick={() => pick(ref)}>
          <Icon name="playlist" size={15} />
          <span class="ellipsis">{list.name}</span>
          {#if has(ref)}<Icon name="check" size={14} />{/if}
        </button>
      {:else}
        {#if !loadingLists}<span class="muted">{t('No playlists found.')}</span>{/if}
      {/each}
    {/if}
  </div>
  {#snippet footer()}
    <button class="btn primary" onclick={closeDialog}>{t('Done')}</button>
  {/snippet}
</Modal>

<style>
  .top { display: flex; gap: 10px; align-items: center; margin-bottom: 10px; }
  .top input { flex: 1; min-width: 0; }
  .seg button { display: inline-flex; align-items: center; gap: 6px; }
  .list { display: flex; flex-direction: column; gap: 1px; max-height: min(55vh, 460px); overflow-y: auto; }
  .row { display: flex; align-items: center; gap: 10px; padding: 7px 10px; border-radius: 8px; text-align: left; color: var(--text); }
  .row:hover { background: var(--hover); }
  .artist { margin-left: auto; font-size: var(--fs-sm); max-width: 40%; }
  .row :global(svg:last-child:not(:first-child)) { color: var(--green); flex: none; }
</style>
