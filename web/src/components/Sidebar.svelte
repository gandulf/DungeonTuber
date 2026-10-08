<script lang="ts">
  import { api } from '../lib/api';
  import { analyze, canDelete, canDropOnPlaylist, deleteItems, dropOnPlaylist, newPlaylist, openImportDialog, openItem, openUploadDialog, uploadFiles } from '../lib/actions';
  import { itemsFromDrop } from '../lib/upload';
  import { t } from '../lib/i18n.svelte';
  import { openSettings, setTheme } from '../lib/menus';
  import { prefs, savePrefs } from '../lib/prefs.svelte';
  import { addFavoriteFolder, data, removeFavoriteFolder } from '../lib/stores/data.svelte';
  import { closeTab, library, openTab, reloadDirTabs, selectTab } from '../lib/stores/library.svelte';
  import { askText, errorToast, openMenu, ui, type MenuItem } from '../lib/stores/ui.svelte';
  import { onEvent } from '../lib/ws';
  import type { BrowseItem } from '../lib/types';
  import Icon from './Icon.svelte';
  import TreeNode from './TreeNode.svelte';

  let roots = $state<BrowseItem[]>([]);
  let refreshKey = $state(0);
  let selected = $state<string | null>(null);
  let dropTarget = $state(false);
  let overPlaylist = $state<string | null>(null);

  const playlists = $derived(library.tabs.filter((tab) => tab.type === 'playlist'));

  async function loadRoots() {
    try {
      const loaded = await api.roots();
      // every library root starts expanded, so all storages show up as plain folders next to each other
      const fresh = loaded.filter((r) => !prefs.seenRoots.includes(r.path));
      if (fresh.length) {
        prefs.seenRoots = [...prefs.seenRoots, ...fresh.map((r) => r.path)];
        prefs.expanded = [...prefs.expanded, ...fresh.map((r) => r.path)];
        savePrefs();
      }
      roots = loaded;
    } catch (e) {
      errorToast(e);
    }
  }

  function refresh() {
    refreshKey++;
    void loadRoots();
  }

  $effect(() => {
    void loadRoots();
    const stops = [onEvent('library.changed', () => refresh()), onEvent('storages.changed', () => void loadRoots())];
    return () => stops.forEach((stop) => stop());
  });

  async function createFolder(parent: string) {
    const name = await askText(t('New folder'), t('Name'));
    if (!name) return;
    try {
      await api.createFolder(parent, name);
      reloadDirTabs(parent);
      refresh();
    } catch (e) {
      errorToast(e);
    }
  }

  async function renameFolder(item: BrowseItem) {
    const name = await askText(t('Rename'), t('Folder name'), item.name);
    if (!name || name === item.name) return;
    try {
      const result = await api.rename(item.path, name);
      const inside = (path: string) => path === item.path || path.startsWith(item.path + '/');
      for (const tab of [...library.tabs]) if (inside(tab.path)) closeTab(tab.key);
      if (data.user.favorites.some(inside)) {
        const moved = data.user.favorites.map((p) => (inside(p) ? result.path + p.slice(item.path.length) : p));
        data.user = await api.putUserState({ favorites: moved });
      }
      refresh();
    } catch (e) {
      errorToast(e);
    }
  }

  function itemMenu(item: BrowseItem): MenuItem[] {
    const items: MenuItem[] = [{ label: t('Open'), icon: item.type === 'mp3' ? 'play' : 'folder', action: () => openItem(item) }];
    if (item.type === 'dir') {
      items.push(
        { label: t('Add to favorites'), icon: 'bookmark', action: () => addFavoriteFolder(item.path) },
        { label: t('New Playlist…'), icon: 'playlist', action: () => newPlaylist([], item.path) },
        { label: t('New folder…'), icon: 'plus', action: () => createFolder(item.path) },
        { label: t('Upload songs…'), icon: 'upload', tour: 'menu-upload', action: () => openUploadDialog(item.path) },
        { label: t('Import from YouTube…'), icon: 'cloud', tour: 'menu-import', action: () => openImportDialog(item.path) },
      );
    }
    if (item.type !== 'm3u' && data.settings?.voxalyzerActive !== false) {
      items.push({ label: t('Analyze'), icon: 'sparkles', action: () => analyze([item.path]) });
    }
    items.push({ separator: true }, { label: t('Refresh'), icon: 'refresh', action: refresh });
    if (item.storage === undefined && canDelete(item.uploaded_by)) {
      if (item.type === 'dir') items.push({ label: t('Rename'), icon: 'edit', action: () => renameFolder(item) });
      items.push({ label: t('Delete'), icon: 'trash', action: () => deleteItems([{ path: item.path, name: item.name, dir: item.type === 'dir' }]) });
    }
    return items;
  }

  function treeMenu(event: MouseEvent) {
    openMenu(event, [
      { label: t('Upload songs…'), icon: 'upload', action: () => openUploadDialog() },
      { label: t('Import from YouTube…'), icon: 'cloud', action: () => openImportDialog() },
      { label: t('Refresh'), icon: 'refresh', action: refresh },
    ]);
  }

  async function onDrop(event: DragEvent) {
    event.preventDefault();
    dropTarget = false;
    const items = await itemsFromDrop(event.dataTransfer);
    if (!items.length) return;
    if (roots.length === 1) await uploadFiles(roots[0].path, items);
    else openUploadDialog(undefined, items); // several libraries: let the user pick the target folder
  }

  const lastPart = (path: string) => path.split('/').filter(Boolean).pop() ?? path;
</script>

<div class="sidebar">
  <div class="brand">
    <img src="/icon.png" alt="" width="30" height="30" />
    <div class="brand-text">
      <span class="name">Dungeon Tuber</span>
      <span class="tag">{t('Music for your table')}</span>
    </div>
  </div>

  <nav class="nav">
    <div class="nav-section">
      <span class="label-xs">{t('Library')}</span>
      {#each data.user.favorites as path (path)}
        <button class="nav-item" title={path} onclick={() => openTab('dir', path)}
                oncontextmenu={(e) => openMenu(e, [
                  { label: t('Open'), icon: 'folder', action: () => openTab('dir', path) },
                  { label: t('Upload songs…'), icon: 'upload', action: () => openUploadDialog(path) },
                  { label: t('Import from YouTube…'), icon: 'cloud', action: () => openImportDialog(path) },
                  { label: t('Remove from favorites'), icon: 'trash', action: () => removeFavoriteFolder(path) },
                ])}>
          <Icon name="bookmark" size={16} /><span class="ellipsis">{lastPart(path)}</span>
        </button>
      {:else}
        <span class="empty muted">{t('Right-click a folder to add it to the library.')}</span>
      {/each}
    </div>

    <div class="nav-section">
      <div class="row">
        <span class="label-xs">{t('Playlists')}</span>
        <button class="icon-btn mini" title={t('New Playlist…')} onclick={() => newPlaylist()}><Icon name="plus" size={14} /></button>
      </div>
      {#each playlists as playlist (playlist.key)}
        <button class="nav-item" class:active={library.active === playlist.key} class:over={overPlaylist === playlist.key} title={playlist.path} onclick={() => selectTab(playlist.key)}
                ondragover={(e) => { if (canDropOnPlaylist(e.dataTransfer)) { e.preventDefault(); overPlaylist = playlist.key; } }}
                ondragleave={() => (overPlaylist = null)}
                ondrop={(e) => { e.preventDefault(); overPlaylist = null; void dropOnPlaylist(playlist.path, e.dataTransfer); }}
                oncontextmenu={(e) => openMenu(e, [
                  { label: t('Open'), icon: 'playlist', action: () => selectTab(playlist.key) },
                  { label: t('Remove from list'), icon: 'close', action: () => closeTab(playlist.key) },
                ])}>
          <Icon name="playlist" size={16} /><span class="ellipsis">{playlist.name}</span>
        </button>
      {:else}
        <span class="empty muted">{t('Open a .m3u file from the tree.')}</span>
      {/each}
    </div>

    <div class="nav-section files">
      <div class="row">
        <span class="label-xs">{t('Files')}</span>
        <span class="grow"></span>
        <button class="icon-btn mini" title={t('Refresh')} onclick={refresh}><Icon name="refresh" size={14} /></button>
      </div>
      <div class="tree" class:drop={dropTarget} role="tree" tabindex="-1"
           ondragover={(e) => { if (e.dataTransfer?.types.includes('Files')) { e.preventDefault(); dropTarget = true; } }}
           ondragleave={() => (dropTarget = false)} ondrop={onDrop} oncontextmenu={treeMenu}>
        {#key refreshKey}
          {#each roots as item (item.path)}
            <TreeNode {item} depth={1} bind:selected onOpen={openItem} onMenu={(e, i) => openMenu(e, itemMenu(i))} />
          {/each}
        {/key}
      </div>
    </div>
  </nav>

  <footer class="foot">
    <button class="icon-btn" title={t('Settings')} onclick={openSettings}><Icon name="settings" size={18} /></button>
    <button class="icon-btn" title={t('Theme')} onclick={() => setTheme(prefs.theme === 'dark' ? 'light' : 'dark')}>
      <Icon name={prefs.theme === 'dark' ? 'sun' : 'moon'} size={18} />
    </button>
    <button class="icon-btn" title={t('Show Tour')} onclick={() => (ui.tour = true)}><Icon name="compass" size={18} /></button>
  </footer>
</div>

<style>
  .sidebar { display: flex; flex-direction: column; height: 100%; min-height: 0; }
  .brand { display: flex; align-items: center; gap: 10px; padding: 16px 16px 10px; }
  .brand img { border-radius: 9px; box-shadow: 0 0 18px rgba(var(--ambient), 0.45); }
  .brand-text { display: flex; flex-direction: column; min-width: 0; }
  .name { font-family: var(--font-display); font-weight: 700; font-size: 16px; letter-spacing: -0.01em; }
  .tag { font-size: var(--fs-xs); color: var(--faint); }
  .nav { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 14px; padding: 6px 10px; overflow: hidden; }
  .nav-section { display: flex; flex-direction: column; gap: 1px; }
  .nav-section .label-xs { padding: 4px 8px 6px; }
  .row { display: flex; align-items: center; justify-content: space-between; }
  .grow { flex: 1; }
  .mini { width: 24px; height: 24px; }
  .nav-item { display: flex; align-items: center; gap: 10px; padding: 7px 10px; border-radius: 9px; color: var(--muted); text-align: left; transition: background 0.15s, color 0.15s; }
  .nav-item:hover { background: var(--hover); color: var(--text); }
  .nav-item.over { outline: 2px dashed var(--accent); outline-offset: -2px; }
  .nav-item.active { background: var(--accent-soft); color: var(--accent); font-weight: 600; }
  .empty { font-size: var(--fs-xs); padding: 2px 10px 4px; line-height: 1.4; }
  .files { flex: 1; min-height: 0; }
  .tree { flex: 1; overflow: auto; min-height: 80px; border-radius: 10px; padding: 4px; }
  .tree.drop { box-shadow: inset 0 0 0 2px var(--accent); }
  .foot { display: flex; gap: 4px; padding: 10px 12px 14px; border-top: 1px solid var(--border); }
</style>
