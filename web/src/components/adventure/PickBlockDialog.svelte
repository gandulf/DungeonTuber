<script lang="ts">
  import { t } from '../../lib/i18n.svelte';
  import type { BlockRef } from '../../lib/notes';
  import { matcher } from '../../lib/search';
  import { closeDialog } from '../../lib/stores/ui.svelte';
  import Icon from '../Icon.svelte';
  import Modal from '../dialogs/Modal.svelte';

  /** Chooses a block of the adventure for a link in the notes; `onpick` gets it and the dialog closes. `current` marks the block that
   *  the link has now (when one is changed). */
  let { blocks, current = null, onpick }: { blocks: BlockRef[]; current?: string | null; onpick: (block: BlockRef) => void } = $props();

  let query = $state('');
  const shown = $derived.by(() => {
    const fits = query.trim() ? matcher(query) : null;
    return blocks.filter((block) => !fits || fits(block.title || t('Untitled')));
  });

  function pick(block: BlockRef) {
    const chosen = onpick; // read before the dialog is closed: its props are gone afterwards
    closeDialog();
    chosen(block);
  }
</script>

<Modal title={t('Link to a block')} onclose={closeDialog} width="460px">
  <form onsubmit={(e) => { e.preventDefault(); if (shown[0]) pick(shown[0]); }}>
    <input type="search" placeholder={t('Search blocks…')} aria-label={t('Search blocks…')} bind:value={query} />
  </form>
  <ul>
    {#each shown as block (block.id)}
      <li>
        <button type="button" class:current={block.id === current} onclick={() => pick(block)}>
          <Icon name="tree" size={14} /><span class="ellipsis">{block.title || t('Untitled')}</span>
          {#if block.id === current}<Icon name="check" size={14} />{/if}
        </button>
      </li>
    {:else}
      <li class="muted empty">{t('No block found')}</li>
    {/each}
  </ul>
</Modal>

<style>
  form { margin-bottom: 10px; }
  input { width: 100%; box-sizing: border-box; }
  ul { list-style: none; margin: 0; padding: 0; max-height: min(50vh, 420px); overflow-y: auto; display: flex; flex-direction: column; gap: 2px; }
  li button { display: flex; align-items: center; gap: 8px; width: 100%; padding: 7px 10px; border-radius: 9px; text-align: left; color: var(--text); }
  li button:hover { background: var(--hover); }
  li button.current { background: var(--accent-soft); color: var(--accent); font-weight: 600; }
  li button .ellipsis { flex: 1; min-width: 0; }
  .empty { padding: 10px; }
</style>
