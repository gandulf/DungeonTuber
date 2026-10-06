<script lang="ts">
  import { t } from '../../lib/i18n.svelte';
  import { prompt } from '../../lib/stores/ui.svelte';
  import Modal from './Modal.svelte';

  function close(value: string | null) {
    const resolve = prompt.resolve;
    prompt.open = false;
    prompt.resolve = null;
    resolve?.(value === null ? null : value.trim() || null);
  }

  function focus(node: HTMLInputElement) {
    setTimeout(() => { node.focus(); node.select(); });
  }
</script>

{#if prompt.open}
  <Modal title={prompt.title} onclose={() => close(null)} width="420px">
    <form onsubmit={(e) => { e.preventDefault(); close(prompt.value); }}>
      <label>
        {#if prompt.label}<span class="label-xs">{prompt.label}</span>{/if}
        <input type="text" bind:value={prompt.value} use:focus />
      </label>
    </form>
    {#snippet footer()}
      <button class="btn" onclick={() => close(null)}>{t('Cancel')}</button>
      <button class="btn primary" onclick={() => close(prompt.value)}>{t('Ok')}</button>
    {/snippet}
  </Modal>
{/if}

<style>
  label { display: flex; flex-direction: column; gap: 6px; }
</style>
