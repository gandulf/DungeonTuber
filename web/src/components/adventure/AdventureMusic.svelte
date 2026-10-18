<script lang="ts">
  import { canDropOnAdventure, dropOnAdventure, setMusicDrag } from '../../lib/actions';
  import { addAdventureMusic, blocksUsing, refKey, removeAdventureMusic } from '../../lib/adventures';
  import { t } from '../../lib/i18n.svelte';
  import { matcher } from '../../lib/search';
  import { adventures, change, missingMusic, refTracks } from '../../lib/stores/adventure.svelte';
  import { player, playQueue } from '../../lib/stores/player.svelte';
  import { askConfirm, openDialog, ui } from '../../lib/stores/ui.svelte';
  import type { MusicRef } from '../../lib/types';
  import Icon from '../Icon.svelte';
  import PickMusicDialog from './PickMusicDialog.svelte';

  /** The adventure's own playlist: the songs assigned to the adventure (dropped on it in the sidebar, or added here). The blocks
   *  choose their music from it. `onselect` shows a block that plays a song. */
  let { onselect }: { onselect: (blockId: string) => void } = $props();

  const adventure = $derived(adventures.current!);
  const editable = $derived(adventure.editable);

  let query = $state('');
  let over = $state(false);
  const fits = $derived(matcher(query));
  const shown = $derived(adventure.music.filter((ref) => fits(`${ref.title} ${ref.path}`)));

  async function play(ref: MusicRef) {
    const tracks = await refTracks(ref);
    if (tracks?.length) await playQueue(tracks);
  }

  // songs and playlists that can no longer be found are marked (checked again when the list changes)
  let missing = $state(new Set<string>());
  $effect(() => {
    const refs = adventure.music.map((ref) => ({ ...ref }));
    let stale = false;
    void missingMusic(refs).then((found) => { if (!stale) missing = found; });
    return () => (stale = true);
  });
  const missingTitle = $derived(t('No longer found: removed, moved or not visible to you.'));

  /** Plays the whole adventure music (the songs of its playlists included; what can no longer be found is left out). Shuffle and
   *  repeat follow the player. */
  let loadingAll = $state(false);
  async function playAll() {
    loadingAll = true;
    try {
      const lists = await Promise.all(adventure.music.filter((ref) => !missing.has(refKey(ref))).map((ref) => refTracks(ref)));
      const seen = new Set<string>();
      const tracks = lists.flatMap((list) => list ?? []).filter((track) => !seen.has(track.id) && !!seen.add(track.id));
      if (tracks.length) await playQueue(tracks);
    } finally {
      loadingAll = false;
    }
  }

  const playing = (ref: MusicRef) => ref.type === 'song' && player.playing && player.track?.ufid === ref.ufid;

  function addDialog() {
    openDialog(PickMusicDialog, {
      onpick: (ref: MusicRef) => change((a) => addAdventureMusic(a, ref)),
      has: (ref: MusicRef) => adventure.music.some((item) => refKey(item) === refKey(ref)),
    });
  }

  async function remove(ref: MusicRef) {
    const used = blocksUsing(adventure, ref);
    if (used.length && !(await askConfirm(t('"{0}" is played by {1} block(s). Remove it from them too?', ref.title || ref.path, used.length)))) return;
    change((a) => removeAdventureMusic(a, ref));
  }
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<section class="music" class:over
         ondragover={(e) => { if (editable && canDropOnAdventure(e.dataTransfer)) { e.preventDefault(); over = true; } }}
         ondragleave={(e) => { if (e.currentTarget === e.target) over = false; }}
         ondrop={(e) => { e.preventDefault(); over = false; void dropOnAdventure(adventure.id, adventure.title, e.dataTransfer); }}>
  <div class="bar">
    <span class="label-xs">{t('Adventure music')}</span>
    <span class="muted small">{adventure.music.length}</span>
    <span class="grow"></span>
    <button class="btn sm primary" disabled={loadingAll || adventure.music.length === missing.size} title={t('Play all songs of the adventure')}
            onclick={() => void playAll()}><Icon name="play" size={13} />{t('Play')}</button>
    {#if adventure.music.length > 8}<input type="search" placeholder={t('Search…')} bind:value={query} />{/if}
    {#if editable}<button class="btn sm" onclick={addDialog}><Icon name="plus" size={13} />{t('Add')}</button>{/if}
  </div>
  <p class="hint muted">{ui.coarse ? t('The songs of this adventure; its blocks choose their music from them. Add songs with "Add to adventure…" in the menu of a song (press and hold it).')
                                    : t('The songs of this adventure; its blocks choose their music from them. Drag songs from the file tree or the song list onto the adventure in the sidebar, or here.')}</p>

  <div class="list" role="list">
    {#each shown as ref (refKey(ref))}
      {@const used = blocksUsing(adventure, ref)}
      {@const on = playing(ref)}
      {@const gone = missing.has(refKey(ref))}
      <!-- dragged onto a block in the list on the left, the song (or the songs of a playlist) is added to that block -->
      <div class="item" class:missing={gone} draggable={editable && !gone} role="listitem" title={editable && !gone && !ui.coarse ? t('Drag onto a block to add it there') : undefined}
           ondragstart={(e) => setMusicDrag(e.dataTransfer, [$state.snapshot(ref) as MusicRef])}>
        <button type="button" class="play-item" class:on disabled={gone} title={gone ? missingTitle : t('Play')} onclick={() => void play(ref)}>
          <Icon name={on ? 'volume' : ref.type === 'song' ? 'music' : 'playlist'} size={15} />
          <span class="ellipsis">{ref.title || ref.path || t('Untitled')}</span>
        </button>
        {#if gone}<span class="warn" title={missingTitle}>{ref.type === 'playlist' && ref.unavailable ? t('unavailable') : t('not found')}</span>{/if}
        <span class="uses">
          {#each used.slice(0, 3) as block (block.id)}
            <button type="button" class="chip" title={t('Show the block')} onclick={() => onselect(block.id)}>{block.title || t('Untitled')}</button>
          {/each}
          {#if used.length > 3}<span class="muted small">+{used.length - 3}</span>{/if}
        </span>
        {#if editable}<button class="icon-btn mini" title={t('Remove')} aria-label={t('Remove')} onclick={() => void remove(ref)}><Icon name="close" size={13} /></button>{/if}
      </div>
    {:else}
      <span class="muted small empty">{adventure.music.length ? t('No songs found.') : t('No music assigned yet.')}</span>
    {/each}
  </div>
</section>

<style>
  .music { display: flex; flex-direction: column; gap: 8px; padding: 12px 14px; border-radius: 12px; background: var(--surface); border: 1px solid var(--border); min-height: 200px; }
  .music.over { outline: 2px dashed var(--accent); outline-offset: -2px; }
  .bar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
  .bar input { max-width: 180px; }
  .grow { flex: 1; }
  .btn { display: inline-flex; align-items: center; gap: 6px; }
  .hint { margin: 0; font-size: var(--fs-xs); line-height: 1.4; }
  .list { display: flex; flex-direction: column; gap: 2px; }
  .item { display: flex; align-items: center; gap: 8px; min-width: 0; border-radius: 7px; }
  .item[draggable='true'] { cursor: grab; }
  .play-item { flex: 1; min-width: 0; display: flex; align-items: center; gap: 8px; padding: 5px 6px; border-radius: 7px; text-align: left; color: var(--text); cursor: pointer; }
  .play-item:hover:not(:disabled) { background: var(--hover); }
  .play-item.on { color: var(--accent); }
  .play-item:disabled { cursor: default; opacity: 0.6; }
  .uses { display: flex; align-items: center; gap: 4px; flex: none; max-width: 45%; overflow: hidden; }
  .chip { max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding: 1px 8px; font-size: var(--fs-xs); }
  .mini { width: 24px; height: 24px; }
  .small { font-size: var(--fs-sm); }
  .empty { padding: 6px; }
  .item.missing .play-item { color: var(--red); text-decoration: line-through; cursor: not-allowed; }
  .warn { flex: none; font-size: var(--fs-xs); color: var(--red); border: 1px solid var(--red); border-radius: 6px; padding: 0 6px; }
</style>
