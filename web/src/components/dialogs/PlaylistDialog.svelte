<script lang="ts">
  import { dirname } from '../../lib/actions';
  import { api } from '../../lib/api';
  import { moveFavorites } from '../../lib/stores/data.svelte';
  import { t } from '../../lib/i18n.svelte';
  import { closeTab, library, openTab, reloadDirTabs, reloadPlaylistTabs } from '../../lib/stores/library.svelte';
  import { closeDialog, errorToast } from '../../lib/stores/ui.svelte';
  import Icon from '../Icon.svelte';
  import FolderSelect from './FolderSelect.svelte';
  import Modal from './Modal.svelte';

  /** Without `playlist` a new playlist is created in `directory`; with it the name and visibility of that playlist are edited. */
  let { directory = '', ids = [], playlist }: { directory?: string; ids?: string[]; playlist?: { path: string; name: string; private: boolean } } = $props();

  // svelte-ignore state_referenced_locally
  let name = $state(playlist?.name ?? '');
  // svelte-ignore state_referenced_locally
  let target = $state(directory);
  // svelte-ignore state_referenced_locally
  let isPrivate = $state(playlist?.private ?? false);
  let busy = $state(false);

  async function create() {
    const playlistName = name.trim();
    if (!playlistName || !target) return;
    // props are read from the dialog slot, so take them before it is cleared
    const songs = ids;
    const folder = target;
    const hidden = isPrivate;
    busy = true;
    closeDialog();
    try {
      const created = await api.createPlaylist(`${folder}/${playlistName}`, songs, hidden);
      reloadDirTabs(folder);
      await openTab('playlist', created.path);
    } catch (e) {
      errorToast(e);
    }
  }

  async function save() {
    const edited = playlist!;
    const playlistName = name.trim();
    if (!playlistName) return;
    const hidden = isPrivate;
    busy = true;
    closeDialog();
    try {
      let path = edited.path;
      if (playlistName !== edited.name) {
        path = (await api.rename(edited.path, `${playlistName}.m3u`)).path;
        const old = library.tabs.find((tab) => tab.type === 'playlist' && tab.path === edited.path);
        if (old) {
          const wasActive = library.active === old.key;
          closeTab(old.key);
          await openTab('playlist', path, wasActive);
        }
        reloadDirTabs(dirname(path));
        await moveFavorites(edited.path, path);
      }
      if (hidden !== edited.private) await api.setPlaylistVisibility(path, hidden);
      reloadPlaylistTabs(path);
    } catch (e) {
      errorToast(e);
    }
  }

  const submit = () => void (playlist ? save() : create());
</script>

<Modal title={playlist ? t('Edit Playlist') : t('New Playlist')} onclose={closeDialog} width="460px">
  <form class="fields" onsubmit={(e) => { e.preventDefault(); submit(); }}>
    <label>
      <span class="label-xs">{t('Name')}</span>
      <input type="text" bind:value={name} />
    </label>
    <div class="section">
      <span class="label-xs">{t('Visibility')}</span>
      <div class="seg">
        <button type="button" class:on={!isPrivate} onclick={() => (isPrivate = false)}><Icon name="users" size={14} />{t('Public')}</button>
        <button type="button" class:on={isPrivate} onclick={() => (isPrivate = true)}><Icon name="lock" size={14} />{t('Private')}</button>
      </div>
      <span class="hint muted">{isPrivate ? t('Only you can see this playlist.') : t('Everyone can see this playlist.')}</span>
    </div>
    {#if !playlist}
      <div class="section stretch">
        <span class="label-xs">{t('Target folder')}</span>
        <FolderSelect bind:selected={target} />
      </div>
    {/if}
    <button type="submit" hidden aria-label={playlist ? t('Save') : t('Create')}></button>
  </form>
  {#snippet footer()}
    <button class="btn" onclick={closeDialog}>{t('Cancel')}</button>
    {#if playlist}
      <button class="btn primary" disabled={busy || !name.trim()} onclick={submit}>{t('Save')}</button>
    {:else}
      <button class="btn primary" disabled={busy || !name.trim() || !target} onclick={submit}>{t('Create')}</button>
    {/if}
  {/snippet}
</Modal>

<style>
  .fields { display: flex; flex-direction: column; gap: 14px; flex: 1; min-height: 0; }
  label { display: flex; flex-direction: column; gap: 6px; }
  .section { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; }
  .section.stretch { align-items: stretch; }
  .seg button { display: inline-flex; align-items: center; gap: 6px; }
  .hint { font-size: var(--fs-sm); }
</style>
