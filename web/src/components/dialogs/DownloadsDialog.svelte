<script lang="ts">
  import { t } from '../../lib/i18n.svelte';
  import { jobs, type JobKind } from '../../lib/stores/downloads.svelte';
  import { closeDialog } from '../../lib/stores/ui.svelte';
  import type { DownloadItem } from '../../lib/types';
  import Modal from './Modal.svelte';

  let { kind = 'downloads' }: { kind?: JobKind } = $props();
  // svelte-ignore state_referenced_locally
  const status = jobs(kind);
  const labels: Record<DownloadItem['state'], string> = {
    queued: 'Queued',
    downloading: 'Downloading',
    running: 'Analyzing',
    done: 'Done',
    skipped: 'Skipped',
    failed: 'Failed',
  };
</script>

<Modal title={kind === 'downloads' ? t('Downloads') : t('Analysis')} onclose={closeDialog} width="640px">
  {#if status.items.length}
    <ul>
      {#each status.items as item (item.id)}
        <li class={item.state}>
          <div class="line">
            <span class="ellipsis title" title={item.title}>{item.title}</span>
            <span class="state">{t(labels[item.state])}{item.state === 'downloading' ? ` ${item.percent}%` : ''}</span>
          </div>
          {#if item.state === 'downloading'}
            <progress max="100" value={item.percent}></progress>
          {:else if item.state === 'running'}
            <progress></progress>
          {/if}
          {#if item.message && item.state !== 'done'}<span class="message muted">{item.message}</span>{/if}
        </li>
      {/each}
    </ul>
    <span class="muted summary">{t('{0} remaining · {1} finished · {2} failed', status.pending, status.done, status.failed)}</span>
  {:else}
    <span class="muted">{kind === 'downloads' ? t('No downloads') : t('No analysis running')}</span>
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
