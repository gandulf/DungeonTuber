<script lang="ts">
  import { api } from '../../lib/api';
  import { t } from '../../lib/i18n.svelte';
  import { matcher } from '../../lib/search';
  import { refTracks } from '../../lib/stores/adventure.svelte';
  import { effects, loadEffects } from '../../lib/stores/effects.svelte';
  import { globalTab, loadGlobal } from '../../lib/stores/library.svelte';
  import { player, playEffect, playQueue, togglePlay } from '../../lib/stores/player.svelte';
  import { closeDialog, errorToast, toast, ui } from '../../lib/stores/ui.svelte';
  import type { Effect, MusicRef, PlaylistInfo, SongRef, Track } from '../../lib/types';
  import Icon from '../Icon.svelte';
  import Modal from '../dialogs/Modal.svelte';

  /** `onpick` adds a song or playlist; `has` says whether the target holds it already. The dialog stays open to pick several.
   *  With `pool` (the music of the adventure) it picks songs for a block: the adventure's songs come first, its playlists listed song by
   *  song, and the library is there for what the adventure does not hold yet (`fromPool` tells which). Blocks hold songs only.
   *  With `effect` it picks sound effects of the effects folder instead. Every entry can be listened to with its play button. */
  let { onpick = () => {}, has = () => false, single = false, pool, effect: effectPick }: {
    onpick?: (ref: MusicRef, fromPool: boolean) => void; has?: (ref: MusicRef) => boolean;
    /** Picks one song and closes (for a link in the notes). */ single?: boolean;
    pool?: MusicRef[];
    effect?: { onpick: (effect: Effect) => void; has: (path: string) => boolean };
  } = $props();

  const LIMIT = 80;

  // svelte-ignore state_referenced_locally
  let kind = $state<'pool' | 'song' | 'playlist' | 'effect'>(effectPick ? 'effect' : pool ? 'pool' : 'song');

  // loaded once when the dialog opens (an effect that reloads while the list is empty would never stop with an empty folder)
  // svelte-ignore state_referenced_locally
  if (effectPick) void loadEffects();
  // the songs of the library likewise: an effect would start a failed load again and again (loadGlobal reads and writes its state)
  // svelte-ignore state_referenced_locally
  else void loadGlobal();

  // --- listening before picking: a click on the play button of a playing song pauses it, an effect plays or stops
  const songPlaying = (ufid: string | null | undefined, id?: string) =>
    player.playing && !!player.track && (id ? player.track.id === id : !!ufid && player.track.ufid === ufid);

  async function playRef(ref: SongRef) {
    if (songPlaying(ref.ufid)) return togglePlay();
    const tracks = await refTracks(ref);
    if (tracks?.length) await playQueue(tracks);
  }

  function playLibraryTrack(track: Track) {
    if (songPlaying(null, track.id)) togglePlay();
    else void playQueue([track]);
  }

  const effectPlaying = (item: Effect) => player.effectPlaying && player.effect?.path === item.path;

  async function playPlaylist(ref: MusicRef) {
    const tracks = await refTracks(ref);
    if (tracks?.length) await playQueue(tracks);
  }

  function pickEffect(item: Effect) {
    effectPick?.onpick(item);
  }
  let query = $state('');
  let lists = $state<PlaylistInfo[]>([]);
  let loadingLists = $state(false);

  /** The songs of the adventure: its own songs, then the songs of its playlists (`from` names the playlist), each song once. */
  let poolSongs = $state<{ ref: SongRef; from: string | null }[]>([]);
  let loadingPool = $state(false);

  $effect(() => {
    const refs = pool ?? [];
    let stale = false;
    loadingPool = true;
    void (async () => {
      const seen = new Set<string>();
      const songs: { ref: SongRef; from: string | null }[] = [];
      const take = (ref: SongRef, from: string | null) => {
        if (!seen.has(ref.ufid)) {
          seen.add(ref.ufid);
          songs.push({ ref, from });
        }
      };
      for (const ref of refs) if (ref.type === 'song') take(ref, null);
      for (const ref of refs) {
        if (ref.type !== 'playlist' || ref.unavailable) continue;
        for (const track of (await refTracks(ref)) ?? []) {
          if (track.ufid) take({ type: 'song', ufid: track.ufid, path: track.path, title: track.title || track.name }, ref.title || ref.path);
        }
      }
      if (stale) return;
      poolSongs = songs;
      loadingPool = false;
    })();
    return () => (stale = true);
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
  const pooled = $derived(poolSongs.filter((item) => fits(`${item.ref.title} ${item.ref.path} ${item.from ?? ''}`)));
  const songs = $derived(globalTab.tracks.filter((track) => fits(`${track.title ?? ''} ${track.artist ?? ''} ${track.name}`)).slice(0, LIMIT));
  const playlists = $derived(lists.filter((list) => fits(list.name)));
  const effectList = $derived(effects.list.filter((item) => fits(`${item.title ?? ''} ${item.name}`)));

  function songRef(ufid: string | null | undefined, path: string, title: string): MusicRef | null {
    if (!ufid) {
      toast(t('This song has no stable id yet. Refresh the library first.'), 'error');
      return null;
    }
    return { type: 'song', ufid, path, title };
  }

  function pick(ref: MusicRef | null, fromPool = false) {
    if (!ref) return;
    onpick(ref, fromPool);
    if (single) closeDialog();
  }
</script>

{#snippet play(on: boolean, onclick: () => void, label: string)}
  <button type="button" class="play" class:on title={on ? t('Pause') : t('Play')} aria-label={`${on ? t('Pause') : t('Play')}: ${label}`} onclick={onclick}>
    <Icon name={on ? 'pause' : 'play'} size={13} />
  </button>
{/snippet}

<Modal title={effectPick ? t('Add effect') : single ? t('Link a song') : t('Add music')} onclose={closeDialog} width="560px">
  <div class="top">
    <div class="seg" class:hidden={!!effectPick}>
      {#if pool}<button type="button" class:on={kind === 'pool'} onclick={() => (kind = 'pool')}><Icon name="mask" size={14} /> {t('Adventure music')}</button>{/if}
      <!-- for a block only the adventure's music: the library is searched with "Search…" next to "Add" -->
      {#if !pool || single}<button type="button" class:on={kind === 'song'} onclick={() => (kind = 'song')}><Icon name="music" size={14} /> {t('Songs')}</button>{/if}
      {#if !single && !pool}<button type="button" class:on={kind === 'playlist'} onclick={() => void showPlaylists()}><Icon name="playlist" size={14} /> {t('Playlists')}</button>{/if}
    </div>
    <input type="search" placeholder={t('Search…')} bind:value={query} />
  </div>
  <div class="list">
    {#if kind === 'effect'}
      {#if effects.loading && !effects.list.length}<span class="muted">{t('Loading…')}</span>{/if}
      {#each effectList as item (item.id)}
        <div class="line">
          {@render play(effectPlaying(item), () => playEffect(item), item.title || item.name)}
          <button class="row" onclick={() => pickEffect(item)}>
            <Icon name="waves" size={15} />
            <span class="ellipsis">{item.title || item.name}</span>
            {#if effectPick?.has(item.path)}<Icon name="check" size={14} />{/if}
          </button>
        </div>
      {:else}
        {#if !effects.loading}<span class="muted">{effects.list.length ? t('No effects found.') : t('Ambient loops or one-shot effects of the effects folder.')}</span>{/if}
      {/each}
    {:else if kind === 'pool'}
      {#if loadingPool && !poolSongs.length}<span class="muted">{t('Loading…')}</span>{/if}
      {#each pooled as item, index (item.ref.ufid)}
        {#if item.from && item.from !== pooled[index - 1]?.from}
          <span class="label-xs group"><Icon name="playlist" size={12} /> {item.from}</span>
        {/if}
        <div class="line">
          {@render play(songPlaying(item.ref.ufid), () => void playRef(item.ref), item.ref.title || item.ref.path)}
          <button class="row" onclick={() => pick(item.ref, true)}>
            <Icon name="music" size={15} />
            <span class="ellipsis">{item.ref.title || item.ref.path}</span>
            {#if has(item.ref)}<Icon name="check" size={14} />{/if}
          </button>
        </div>
      {:else}
        {#if !loadingPool}<span class="muted">{pool?.length ? t('No songs found.') : (ui.coarse ? t('This adventure has no music yet. Find songs with "Search…" next to "Add".') : t('This adventure has no music yet. Drag songs onto it in the sidebar, or find them with "Search…" next to "Add".'))}</span>{/if}
      {/each}
    {:else if kind === 'song'}
      {#if globalTab.loading && !globalTab.tracks.length}<span class="muted">{t('Loading…')}</span>{/if}
      {#each songs as track (track.id)}
        {@const ref = track.ufid ? ({ type: 'song', ufid: track.ufid, path: track.path, title: track.title || track.name } as MusicRef) : null}
        <div class="line">
          {@render play(songPlaying(null, track.id), () => playLibraryTrack(track), track.title || track.name)}
          <button class="row" onclick={() => pick(songRef(track.ufid, track.path, track.title || track.name))}>
            <Icon name="music" size={15} />
            <span class="ellipsis">{track.title || track.name}</span>
            <span class="muted ellipsis artist">{track.artist ?? ''}</span>
            {#if ref && has(ref)}<Icon name="check" size={14} />{/if}
          </button>
        </div>
      {:else}
        {#if !globalTab.loading}<span class="muted">{t('No songs found.')}</span>{/if}
      {/each}
    {:else}
      {#if loadingLists}<span class="muted">{t('Loading…')}</span>{/if}
      {#each playlists as list (list.playlist_id)}
        {@const ref = { type: 'playlist', id: list.playlist_id, path: list.path, title: list.name } as MusicRef}
        <div class="line">
          {@render play(false, () => void playPlaylist(ref), list.name)}
          <button class="row" onclick={() => pick(ref)}>
            <Icon name="playlist" size={15} />
            <span class="ellipsis">{list.name}</span>
            {#if has(ref)}<Icon name="check" size={14} />{/if}
          </button>
        </div>
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
  @media (max-width: 900px) { .top { flex-wrap: wrap; } .top input { flex-basis: 100%; } } /* phones: the search gets a line of its own */
  .seg button { display: inline-flex; align-items: center; gap: 6px; }
  .list { display: flex; flex-direction: column; gap: 1px; max-height: min(55vh, 460px); overflow-y: auto; }
  .seg.hidden { display: none; }
  .line { display: flex; align-items: center; gap: 2px; }
  .line .row { flex: 1; min-width: 0; }
  .play { flex: none; display: grid; place-items: center; width: 28px; height: 28px; border-radius: 50%; color: var(--muted); }
  .play:hover { background: var(--accent-soft); color: var(--accent); }
  .play.on { background: var(--accent); color: white; }
  .row { display: flex; align-items: center; gap: 10px; padding: 7px 10px; border-radius: 8px; text-align: left; color: var(--text); }
  .row:hover { background: var(--hover); }
  .group { display: flex; align-items: center; gap: 5px; padding: 10px 10px 3px; }
  .artist { margin-left: auto; font-size: var(--fs-sm); max-width: 40%; }
  .row :global(svg:last-child:not(:first-child)) { color: var(--green); flex: none; }
</style>
