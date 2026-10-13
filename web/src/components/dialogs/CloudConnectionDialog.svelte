<script lang="ts">
  import { keyField, secretField } from '../../lib/autofill';
  import { t } from '../../lib/i18n.svelte';
  import { errorToast } from '../../lib/stores/ui.svelte';
  import Modal from './Modal.svelte';

  /** The connection to a cloud function on Modal: its URL and the key and secret of a proxy auth token. The stored values are never
   *  sent back to the browser, so the fields start empty and all three are entered again. */
  let { title, hint, save, onclose }: {
    title: string; hint: string; save: (url: string, key: string, secret: string) => Promise<void>; onclose: () => void;
  } = $props();

  let url = $state('');
  let key = $state('');
  let secret = $state('');
  let saving = $state(false);
  const id = $props.id();
  const complete = $derived(!!url.trim() && !!key.trim() && !!secret.trim());

  async function submit() {
    if (!complete || saving) return;
    saving = true;
    try {
      await save(url.trim(), key.trim(), secret.trim());
      onclose();
    } catch (e) {
      errorToast(e);
    } finally {
      saving = false;
    }
  }
</script>

<Modal {title} {onclose} width="480px">
  <form id="{id}-connection" onsubmit={(e) => { e.preventDefault(); void submit(); }}>
    <span class="muted small">{hint}</span>
    <label class="field">{t('Endpoint URL')}<input type="url" {...keyField} placeholder="https://…modal.run" bind:value={url} /></label>
    <label class="field">{t('Key')}<input type="text" {...keyField} placeholder="wk-…" bind:value={key} /></label>
    <label class="field">{t('Secret')}<input type="password" {...secretField} placeholder="ws-…" bind:value={secret} /></label>
  </form>
  {#snippet footer()}
    <button class="btn" type="button" onclick={onclose}>{t('Cancel')}</button>
    <button class="btn primary" type="submit" form="{id}-connection" disabled={!complete || saving}>{t('Save')}</button>
  {/snippet}
</Modal>

<style>
  form { display: flex; flex-direction: column; gap: 10px; }
  .field { display: flex; flex-direction: column; gap: 5px; }
</style>
