<script lang="ts">
  import { api } from '../lib/api';
  import { analyze, newPlaylist, openItem, uploadFiles } from '../lib/actions';
  import { t } from '../lib/i18n.svelte';
  import { prefs, savePrefs } from '../lib/prefs.svelte';
  import { addFavoriteFolder, data, removeFavoriteFolder } from '../lib/stores/data.svelte';
  import { openTab, reloadDirTabs } from '../lib/stores/library.svelte';
  import { askText, errorToast, openMenu, type MenuItem } from '../lib/stores/ui.svelte';
  import { onEvent } from '../lib/ws';
  import type { BrowseItem, BrowseResult } from '../lib/types';
  import Icon from './Icon.svelte';
  import TreeNode from './TreeNode.svelte';

  let roots = $state<BrowseItem[]>([]);
  let root = $state<BrowseResult | null>(null);
  let history: string[] = [];
  let refreshKey = $state(0);
  let selected = $state<string | null>(null);
  let dropTarget = $state(false);

  async function loadRoots() {
    try {
      roots = await api.roots();
      const start = prefs.treeRoot && roots.some((r) => prefs.treeRoot!.startsWith(r.path)) ? prefs.treeRoot : roots[0]?.path;
      if (start) await goTo(start, false);
    } catch (e) {
      errorToast(e);
    }
  }

  async function goTo(path: string, remember = true) {
    try {
      const result = await api.browse(path, prefs.smartFilter);
      if (remember && root) history.push(root.path);
      root = result;
      prefs.treeRoot = result.path;
      savePrefs();
    } catch (e) {
      errorToast(e);
    }
  }

  function back() {
    const path = history.pop();
    if (path) void goTo(path, false);
  }

  function refresh() {
    refreshKey++;
    if (root) void goTo(root.path, false);
  }

  $effect(() => {
    void loadRoots();
    return onEvent('library.changed', () => refresh());
  });

  function itemMenu(item: BrowseItem): MenuItem[] {
    const items: MenuItem[] = [{ label: t('Open'), icon: item.type === 'mp3' ? 'play' : 'folder', action: () => openItem(item) }];
    if (item.type === 'dir') {
      items.push(
        { label: t('Go Into'), icon: 'forward', action: () => goTo(item.path) },
        { label: t('Add to favorites'), icon: 'star', action: () => addFavoriteFolder(item.path) },
        { label: t('<New Playlist>'), icon: 'playlist', action: () => newPlaylist([], item.path) },
        { label: t('New folder'), icon: 'plus', action: () => createFolder(item.path) },
      );
    }
    if (item.type !== 'm3u' && data.settings?.voxalyzerActive !== false) {
      items.push({ label: t('Analyze'), icon: 'sparkles', action: () => analyze([item.path]) });
    }
    items.push({ separator: true }, { label: t('Refresh'), icon: 'refresh', action: refresh });
    return items;
  }

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

  function rootMenu(event: MouseEvent) {
    if (!root) return;
    openMenu(event, [
      { label: t('Smart Filter'), checked: prefs.smartFilter, action: () => { prefs.smartFilter = !prefs.smartFilter; savePrefs(); refresh(); } },
      { label: t('Add to favorites'), icon: 'star', action: () => addFavoriteFolder(root!.path) },
      { label: t('New folder'), icon: 'plus', action: () => createFolder(root!.path) },
      { label: t('Refresh'), icon: 'refresh', action: refresh },
      ...(roots.length > 1 ? [{ separator: true }, ...roots.map((r) => ({ label: r.path, icon: 'folder', action: () => goTo(r.path) }))] : []),
    ]);
  }

  async function onDrop(event: DragEvent) {
    event.preventDefault();
    dropTarget = false;
    const files = [...(event.dataTransfer?.files ?? [])];
    if (files.length && root) await uploadFiles(root.path, files);
  }

  function favoriteName(path: string) {
    return path.split('/').filter(Boolean).pop() ?? path;
  }
</script>

{#if data.settings?.favorites?.length}
  <div class="section">
    <div class="section-title"><Icon name="star" size={16} /> {t('Favorites')}</div>
    <div class="panel list">
      {#each data.settings.favorites as path (path)}
        <button class="fav" title={path} ondblclick={() => openTab('dir', path)} onclick={() => goTo(path)}
                oncontextmenu={(e) => openMenu(e, [
                  { label: t('Open'), icon: 'folder', action: () => openTab('dir', path) },
                  { label: t('Go Into'), icon: 'forward', action: () => goTo(path) },
                  { label: t('Remove from favorites'), icon: 'trash', action: () => removeFavoriteFolder(path) },
                ])}>
          <Icon name="folder" size={16} /><span class="ellipsis">{favoriteName(path)}</span>
        </button>
      {/each}
    </div>
  </div>
{/if}

<div class="section grow">
  <div class="section-title">
    <Icon name="folder" size={16} /> {t('Files')}
    <span class="grow"></span>
    <button class="icon-btn" title={t('Back')} disabled={!history.length} onclick={back}><Icon name="back" size={15} /></button>
    <button class="icon-btn" title={t('Go to parent')} disabled={!root?.parent} onclick={() => root?.parent && goTo(root.parent)}><Icon name="up" size={15} /></button>
    <button class="icon-btn" title={t('Refresh')} onclick={refresh}><Icon name="refresh" size={15} /></button>
  </div>
  <div class="panel tree" class:drop={dropTarget} role="tree" tabindex="-1"
       ondragover={(e) => { if (e.dataTransfer?.types.includes('Files')) { e.preventDefault(); dropTarget = true; } }}
       ondragleave={() => (dropTarget = false)} ondrop={onDrop} oncontextmenu={rootMenu}>
    {#if root}
      <button class="root" title={root.path} ondblclick={() => openTab('dir', root!.path)}>
        <Icon name="folder" size={16} /><span class="ellipsis">{root.name || root.path}</span>
      </button>
      {#key refreshKey}
        {#each root.items as item (item.path)}
          <TreeNode {item} depth={1} bind:selected onOpen={openItem} onMenu={(e, i) => openMenu(e, itemMenu(i))} onGoInto={goTo} />
        {/each}
      {/key}
    {/if}
  </div>
</div>

<style>
  .section { display: flex; flex-direction: column; gap: 4px; min-height: 0; }
  .section.grow { flex: 1; }
  .grow { flex: 1; }
  .list { padding: 4px; max-height: 180px; overflow: auto; }
  .fav, .root { display: flex; align-items: center; gap: 7px; width: 100%; padding: 4px 6px; border-radius: var(--radius-sm); text-align: left; color: var(--text); }
  .fav:hover, .root:hover { background: var(--hover); }
  .fav :global(svg), .root :global(svg) { color: #e0a82e; }
  .root { font-weight: 600; }
  .tree { flex: 1; overflow: auto; padding: 4px; min-height: 120px; }
  .tree.drop { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft); }
</style>
