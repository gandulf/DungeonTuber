<script lang="ts">
  import TreeNode from './TreeNode.svelte';
  import { api } from '../lib/api';
  import { prefs, savePrefs } from '../lib/prefs.svelte';
  import { canDropOnPlaylist, dropOnPlaylist, uploadFiles } from '../lib/actions';
  import { itemsFromDrop } from '../lib/upload';
  import { reloadDirTabs } from '../lib/stores/library.svelte';
  import { errorToast } from '../lib/stores/ui.svelte';
  import type { BrowseItem } from '../lib/types';
  import Icon from './Icon.svelte';

  let { item, depth, selected = $bindable(), onOpen, onMenu }: {
    item: BrowseItem;
    depth: number;
    selected: string | null;
    onOpen: (item: BrowseItem) => void;
    onMenu: (event: MouseEvent, item: BrowseItem) => void;
  } = $props();

  let children = $state<BrowseItem[] | null>(null);
  // svelte-ignore state_referenced_locally
  let expanded = $state(prefs.expanded.includes(item.path));
  let dragOver = $state(false);
  const isRoot = $derived(item.storage !== undefined);

  async function load() {
    try {
      children = (await api.browse(item.path)).items;
    } catch (e) {
      errorToast(e);
      children = [];
    }
  }

  $effect(() => {
    if (expanded && children === null && item.type === 'dir') void load();
  });

  function toggle(event?: Event) {
    event?.stopPropagation();
    expanded = !expanded;
    prefs.expanded = expanded ? [...prefs.expanded, item.path] : prefs.expanded.filter((p) => p !== item.path);
    savePrefs();
  }

  /** The visible rows of the whole tree in display order (collapsed folders render no children). */
  function rows(from: HTMLElement): HTMLElement[] {
    return [...(from.closest('[role="tree"]')?.querySelectorAll<HTMLElement>('[role="treeitem"] > .row') ?? [])];
  }

  function focusRow(row: HTMLElement | null | undefined, event: KeyboardEvent) {
    event.preventDefault();
    row?.focus();
  }

  function onKey(event: KeyboardEvent) {
    const row = event.currentTarget as HTMLElement;
    if (event.key === 'Enter') onOpen(item);
    else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      const all = rows(row);
      focusRow(all[all.indexOf(row) + (event.key === 'ArrowDown' ? 1 : -1)], event);
    } else if (event.key === 'Home' || event.key === 'End') {
      const all = rows(row);
      focusRow(event.key === 'Home' ? all[0] : all.at(-1), event);
    } else if (event.key === 'ArrowRight' && item.type === 'dir') {
      if (!expanded) toggle();
      else focusRow(row.parentElement?.querySelector<HTMLElement>(':scope > [role="treeitem"] > .row'), event);
    } else if (event.key === 'ArrowLeft') {
      if (expanded) toggle();
      else focusRow(row.parentElement?.parentElement?.closest('[role="treeitem"]')?.querySelector<HTMLElement>(':scope > .row'), event);
    }
  }

  function dragStart(event: DragEvent) {
    event.dataTransfer?.setData('application/x-dungeontuber-path', item.path);
    if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move';
  }

  /** Folders take files and moved items, playlists take songs. */
  function accepts(event: DragEvent): boolean {
    const types = event.dataTransfer?.types ?? [];
    if (item.type === 'm3u') return canDropOnPlaylist(event.dataTransfer);
    return item.type === 'dir' && (types.includes('Files') || types.includes('application/x-dungeontuber-path'));
  }

  async function drop(event: DragEvent) {
    dragOver = false;
    if (item.type === 'm3u') {
      if (!canDropOnPlaylist(event.dataTransfer)) return;
      event.preventDefault();
      event.stopPropagation();
      await dropOnPlaylist(item.path, event.dataTransfer);
      return;
    }
    if (item.type === 'dir' && event.dataTransfer?.types.includes('Files')) {
      event.preventDefault();
      event.stopPropagation();
      const items = await itemsFromDrop(event.dataTransfer);
      if (items.length) await uploadFiles(item.path, items);
      return;
    }
    const source = event.dataTransfer?.getData('application/x-dungeontuber-path');
    if (!source || item.type !== 'dir' || source === item.path) return;
    event.preventDefault();
    event.stopPropagation();
    try {
      await api.move(source, item.path);
      reloadDirTabs(item.path);
      children = null;
      if (expanded) void load();
    } catch (e) {
      errorToast(e);
    }
  }
</script>

<div role="treeitem" aria-expanded={item.type === 'dir' ? expanded : undefined} aria-selected={selected === item.path}>
  <button class="row" class:selected={selected === item.path} class:over={dragOver} class:lib-root={isRoot} style:padding-left="{depth * 14 - 8}px"
          title={item.file ?? item.name} draggable={!isRoot}
          onclick={() => (selected = item.path)} onfocus={() => (selected = item.path)} ondblclick={() => onOpen(item)}
          onkeydown={onKey} oncontextmenu={(e) => { selected = item.path; onMenu(e, item); }} ondragstart={dragStart}
          ondragover={(e) => { if (accepts(e)) { e.preventDefault(); dragOver = true; } }}
          ondragleave={() => (dragOver = false)} ondrop={drop}>
    {#if item.type === 'dir'}
      <span class="twisty" role="presentation" onclick={toggle} ondblclick={(e) => e.stopPropagation()}>
        <Icon name={expanded ? 'chevron-down' : 'chevron-right'} size={13} />
      </span>
      <span class="folder"><Icon name={isRoot && item.storage !== 'local' ? 'cloud' : 'folder'} size={16} /></span>
    {:else}
      <span class="twisty"></span>
      <span class="file"><Icon name={item.type === 'm3u' ? 'playlist' : 'music'} size={15} /></span>
    {/if}
    <span class="ellipsis name">{item.name}</span>
  </button>
  {#if expanded && children}
    {#each children as child (child.path)}
      <TreeNode item={child} depth={depth + 1} bind:selected {onOpen} {onMenu} />
    {/each}
  {/if}
</div>

<style>
  .row { display: flex; align-items: center; gap: 5px; width: 100%; padding: 4px 6px; border-radius: 8px; text-align: left; color: var(--muted); }
  .row:hover { background: var(--hover); color: var(--text); }
  .row.selected { background: var(--accent-soft); color: var(--accent); }
  .row.over { outline: 2px dashed var(--accent); outline-offset: -2px; }
  .row:focus-visible { outline-offset: -2px; }
  .twisty { width: 16px; display: flex; justify-content: center; color: var(--muted); flex: none; }
  .folder { color: var(--gold); display: flex; opacity: 0.85; }
  .file { color: var(--muted); display: flex; }
  .name { flex: 1; }
  .row.lib-root { font-weight: 600; color: var(--text); }
</style>
