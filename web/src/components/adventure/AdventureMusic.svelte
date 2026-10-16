<script lang="ts">
  import { canDropOnAdventure, dropOnAdventure } from '../../lib/actions';
  import { addAdventureMusic, blocksUsing, refKey, removeAdventureMusic } from '../../lib/adventures';
  import { t } from '../../lib/i18n.svelte';
  import { matcher } from '../../lib/search';
  import { adventures, change, refTracks } from '../../lib/stores/adventure.svelte';
  import { player, playQueue } from '../../lib/stores/player.svelte';
  import { askConfirm, openDialog } from '../../lib/stores/ui.svelte';
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
    {#if adventure.music.length > 8}<input type="search" placeholder={t('Search…')} bind:value={query} />{/if}
    {#if editable}<button class="btn sm" onclick={addDialog}><Icon name="plus" size={13} />{t('Add')}</button>{/if}
  </div>
  <p class="hint muted">{t('The songs of this adventure; its blocks choose their music from them. Drag songs from the file tree or the song list onto the adventure in the sidebar, or here.')}</p>

  <div class="list">
    {#each shown as ref (refKey(ref))}
      {@const used = blocksUsing(adventure, ref)}
      {@const on = playing(ref)}
      <div class="item">
        <button type="button" class="play-item" class:on disabled={ref.type === 'playlist' && ref.unavailable} title={t('Play')} onclick={() => void play(ref)}>
          <Icon name={on ? 'volume' : ref.type === 'song' ? 'music' : 'playlist'} size={15} />
          <span class="ellipsis">{ref.title || ref.path || t('Untitled')}</span>
        </button>
        {#if ref.type === 'playlist' && ref.unavailable}<span class="warn">{t('unavailable')}</span>{/if}
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
  .item { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .play-item { flex: 1; min-width: 0; display: flex; align-items: center; gap: 8px; padding: 5px 6px; border-radius: 7px; text-align: left; color: var(--text); cursor: pointer; }
  .play-item:hover:not(:disabled) { background: var(--hover); }
  .play-item.on { color: var(--accent); }
  .play-item:disabled { cursor: default; opacity: 0.6; }
  .uses { display: flex; align-items: center; gap: 4px; flex: none; max-width: 45%; overflow: hidden; }
  .chip { max-width: 120px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding: 1px 8px; font-size: var(--fs-xs); }
  .mini { width: 24px; height: 24px; }
  .small { font-size: var(--fs-sm); }
  .empty { padding: 6px; }
  .warn { font-size: var(--fs-xs); color: var(--red); border: 1px solid var(--red); border-radius: 6px; padding: 0 6px; }
</style>
