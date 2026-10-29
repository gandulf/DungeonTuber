<script lang="ts">
  import { cardText } from '../../lib/adventureAi';
  import { t } from '../../lib/i18n.svelte';
  import { imageUrl } from '../../lib/notes';
  import type { AdventureBlock } from '../../lib/types';
  import Icon from '../Icon.svelte';

  /** What a block card shows (the map of play mode and the graph of the editor draw the frame around it): the cover, a badge, the
   *  title, the summary (TL;DR) or else the start of the notes, and what the block plays. `badge` replaces the "played" mark. */
  let { block, adventureId, badge = null }: { block: AdventureBlock; adventureId: string; badge?: string | null } = $props();

  const notes = $derived(cardText(block));
</script>

<span class="art">
  {#if block.cover}<img src={imageUrl(adventureId, block.cover)} alt="" loading="lazy" draggable="false" />
  {:else}<Icon name="mask" size={26} />{/if}
  {#if badge}<span class="badge">{badge}</span>
  {:else if block.played}<span class="badge done"><Icon name="check" size={11} />{t('Played')}</span>{/if}
  {#if block.music.length || block.effects.length}
    <span class="meta">
      {#if block.music.length}<Icon name="music" size={11} />{block.music.length}{/if}
      {#if block.effects.length}<Icon name="waves" size={11} />{block.effects.length}{/if}
    </span>
  {/if}
</span>
<span class="title ellipsis">{block.title || t('Untitled')}</span>
<span class="text" class:muted={!notes}>{notes || t('No notes yet.')}</span>

<style>
  .art { position: relative; flex: none; display: grid; place-items: center; height: 108px; background: var(--surface); color: var(--muted); }
  .art img { width: 100%; height: 100%; object-fit: cover; pointer-events: none; }
  .badge { position: absolute; left: 8px; top: 8px; display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 999px;
           font-size: var(--fs-xs); font-weight: 600; background: var(--accent); color: white; }
  .badge.done { background: var(--bg-2); color: var(--muted); border: 1px solid var(--border); }
  .meta { position: absolute; right: 8px; top: 8px; display: inline-flex; align-items: center; gap: 4px; padding: 2px 8px; border-radius: 999px;
          font-size: var(--fs-xs); background: var(--bg-2); color: var(--muted); border: 1px solid var(--border); }
  .title { padding: 4px 12px 0; font-weight: 650; }
  .text { padding: 0 12px; font-size: var(--fs-xs); line-height: 1.4; color: var(--muted); display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2;
          -webkit-box-orient: vertical; overflow: hidden; }
</style>
