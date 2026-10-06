<script lang="ts">
  import { t } from '../../lib/i18n.svelte';
  import { closeDialog } from '../../lib/stores/ui.svelte';
  import FolderTree from './FolderTree.svelte';
  import Modal from './Modal.svelte';

  let { title, directory = '', onselect }: { title: string; directory?: string; onselect: (path: string) => void | Promise<void> } = $props();

  // svelte-ignore state_referenced_locally
  let selected = $state(directory);

  function choose() {
    // props are read from the dialog slot, so take them before it is cleared
    const callback = onselect;
    const path = selected;
    closeDialog();
    void callback(path);
  }
</script>

<Modal resizable {title} onclose={closeDialog} width="640px">
  <FolderTree bind:selected height="320px" />
  {#snippet footer()}
    <button class="btn" onclick={closeDialog}>{t('Cancel')}</button>
    <button class="btn primary" disabled={!selected} onclick={choose}>{t('Ok')}</button>
  {/snippet}
</Modal>
