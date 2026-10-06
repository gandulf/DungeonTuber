<script lang="ts">
  import { api } from '../../lib/api';
  import { t } from '../../lib/i18n.svelte';
  import { openTab, reloadDirTabs } from '../../lib/stores/library.svelte';
  import { closeDialog, errorToast } from '../../lib/stores/ui.svelte';
  import FolderTree from './FolderTree.svelte';
  import Modal from './Modal.svelte';

  let { directory, ids = [] }: { directory: string; ids?: string[] } = $props();

  let name = $state('');
  // svelte-ignore state_referenced_locally
  let target = $state(directory);
  let busy = $state(false);

  async function create() {
    const playlistName = name.trim();
    if (!playlistName || !target) return;
    // props are read from the dialog slot, so take them before it is cleared
    const songs = ids;
    const folder = target;
    busy = true;
    closeDialog();
    try {
      const created = await api.createPlaylist(`${folder}/${playlistName}`, songs);
      reloadDirTabs(folder);
      await openTab('playlist', created.path);
    } catch (e) {
      errorToast(e);
    }
  }
</script>

<Modal resizable title={t('New Playlist')} onclose={closeDialog} width="640px">
  <form class="fields" onsubmit={(e) => { e.preventDefault(); void create(); }}>
    <label>
      <span class="label-xs">{t('Name')}</span>
      <input type="text" bind:value={name} />
    </label>
    <div class="section fill">
      <span class="label-xs">{t('Target folder')}</span>
      <FolderTree bind:selected={target} height="220px" />
    </div>
    <button type="submit" hidden aria-label={t('Create')}></button>
  </form>
  {#snippet footer()}
    <button class="btn" onclick={closeDialog}>{t('Cancel')}</button>
    <button class="btn primary" disabled={busy || !name.trim() || !target} onclick={create}>{t('Create')}</button>
  {/snippet}
</Modal>

<style>
  .fields { display: flex; flex-direction: column; gap: 14px; flex: 1; min-height: 0; }
  label { display: flex; flex-direction: column; gap: 6px; }
  .section { display: flex; flex-direction: column; gap: 6px; }
  .section.fill { flex: 1 1 auto; min-height: 0; }
</style>
