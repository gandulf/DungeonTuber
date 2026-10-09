<script lang="ts">
  import { t } from '../../lib/i18n.svelte';
  import { toast } from '../../lib/stores/ui.svelte';
  import Icon from '../Icon.svelte';
  import Modal from './Modal.svelte';

  let { token, name, onclose }: { token: string; name: string; onclose: () => void } = $props();

  async function copy() {
    try {
      await navigator.clipboard.writeText(token);
      toast(t('Copied'), 'success');
    } catch {
      toast(t('Copy failed'), 'error');
    }
  }

  /** The settings all agents of a machine share (agents.json, see agents/README.md); the token only passes through this browser. */
  function download() {
    const config = { server: location.origin, token };
    const link = document.createElement('a');
    link.href = URL.createObjectURL(new Blob([JSON.stringify(config, null, 2) + '\n'], { type: 'application/json' }));
    link.download = 'agents.json';
    link.click();
    URL.revokeObjectURL(link.href);
  }
</script>

<Modal title={t('New agent token')} {onclose} width="560px">
  <p class="warn"><strong>{t('Copy this token now, it is only shown once.')}</strong></p>
  {#if name}<span class="muted small">{name}</span>{/if}
  <input class="token" type="text" readonly value={token} onfocus={(e) => e.currentTarget.select()} />
  <div class="row">
    <button class="btn primary" onclick={copy}>{t('Copy')}</button>
    <button class="btn" onclick={download}><Icon name="download" size={14} /> {t('Download agents.json')}</button>
  </div>
  <p class="muted small">{t('Put agents.json next to the agents: all agents on a machine then start without arguments.')}</p>
  {#snippet footer()}
    <button class="btn" onclick={onclose}>{t('Close')}</button>
  {/snippet}
</Modal>

<style>
  .warn { margin: 0 0 6px; padding: 10px 12px; border-radius: var(--radius-sm); background: var(--gold-soft); color: var(--gold); }
  .token { font-family: monospace; margin: 8px 0 12px; }
  .row { display: flex; gap: 8px; }
  p { margin: 12px 0 0; }
</style>
