<script lang="ts">
  import { t } from '../../lib/i18n.svelte';
  import { confirmState } from '../../lib/stores/ui.svelte';
  import Modal from './Modal.svelte';

  function close(ok: boolean) {
    const resolve = confirmState.resolve;
    confirmState.open = false;
    confirmState.resolve = null;
    resolve?.(ok);
  }
</script>

{#if confirmState.open}
  <Modal title={t('Confirm')} onclose={() => close(false)} width="400px">
    <p>{confirmState.message}</p>
    {#snippet footer()}
      <button class="btn" onclick={() => close(false)}>{t('Cancel')}</button>
      <button class="btn primary" onclick={() => close(true)}>{t('Ok')}</button>
    {/snippet}
  </Modal>
{/if}
