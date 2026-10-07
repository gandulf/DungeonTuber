<script lang="ts">
  import { t } from '../../lib/i18n.svelte';
  import { downloads } from '../../lib/stores/downloads.svelte';
  import { closeDialog } from '../../lib/stores/ui.svelte';
  import type { DownloadItem } from '../../lib/types';
  import Modal from './Modal.svelte';

  const labels: Record<DownloadItem['state'], string> = {
    queued: 'Queued',
    downloading: 'Downloading',
    done: 'Done',
    skipped: 'Skipped',
    failed: 'Failed',
  };
</script>

<Modal title={t('Downloads')} onclose={closeDialog} width="640px">
  {#if downloads.items.length}
    <ul>
      {#each downloads.items as item (item.id)}
        <li class={item.state}>
          <div class="line">
            <span class="ellipsis title" title={item.title}>{item.title}</span>
            <span class="state">{t(labels[item.state])}{item.state === 'downloading' ? ` ${item.percent}%` : ''}</span>
          </div>
          {#if item.state === 'downloading'}
            <progress max="100" value={item.percent}></progress>
          {/if}
          {#if item.message && item.state !== 'done'}<span class="message muted">{item.message}</span>{/if}
        </li>
      {/each}
    </ul>
    <span class="muted summary">{t('{0} remaining · {1} finished · {2} failed', downloads.pending, downloads.done, downloads.failed)}</span>
  {:else}
    <span class="muted">{t('No downloads')}</span>
  {/if}
  {#snippet footer()}
    <button class="btn" onclick={closeDialog}>{t('Close')}</button>
  {/snippet}
</Modal>

<style>
  ul { list-style: none; margin: 0 0 10px; padding: 0; display: flex; flex-direction: column; gap: 8px; max-height: 360px; overflow: auto; }
  li { display: flex; flex-direction: column; gap: 4px; padding: 8px 10px; border: 1px solid var(--border); border-radius: 10px; }
  .line { display: flex; justify-content: space-between; gap: 12px; }
  .title { min-width: 0; }
  .state { flex: none; font-size: var(--fs-sm); color: var(--muted); }
  .failed .state { color: var(--danger, #d33); }
  .done .state { color: var(--accent); }
  progress { width: 100%; height: 6px; accent-color: var(--accent); }
  .message { font-size: var(--fs-sm); }
  .summary { font-size: var(--fs-sm); }
</style>
