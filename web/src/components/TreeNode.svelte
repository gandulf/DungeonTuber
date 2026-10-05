<script lang="ts">
  import TreeNode from './TreeNode.svelte';
  import { api } from '../lib/api';
  import { prefs, savePrefs } from '../lib/prefs.svelte';
  import { reloadDirTabs } from '../lib/stores/library.svelte';
  import { errorToast } from '../lib/stores/ui.svelte';
  import type { BrowseItem } from '../lib/types';
  import Icon from './Icon.svelte';

  let { item, depth, selected = $bindable(), onOpen, onMenu, onGoInto }: {
    item: BrowseItem;
    depth: number;
    selected: string | null;
    onOpen: (item: BrowseItem) => void;
    onMenu: (event: MouseEvent, item: BrowseItem) => void;
    onGoInto: (path: string) => void;
  } = $props();

  let children = $state<BrowseItem[] | null>(null);
  // svelte-ignore state_referenced_locally
  let expanded = $state(prefs.expanded.includes(item.path));
  let dragOver = $state(false);

  async function load() {
    try {
      children = (await api.browse(item.path, prefs.smartFilter)).items;
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

  function onKey(event: KeyboardEvent) {
    if (event.key === 'Enter') onOpen(item);
    else if (event.key === 'ArrowRight' && item.type === 'dir' && !expanded) toggle();
    else if (event.key === 'ArrowLeft' && expanded) toggle();
  }

  function dragStart(event: DragEvent) {
    event.dataTransfer?.setData('application/x-dungeontuber-path', item.path);
    if (event.dataTransfer) event.dataTransfer.effectAllowed = 'move';
  }

  async function drop(event: DragEvent) {
    dragOver = false;
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
  <button class="row" class:selected={selected === item.path} class:over={dragOver} style:padding-left="{depth * 14 - 8}px"
          title={item.file ?? item.name} draggable="true"
          onclick={() => (selected = item.path)} ondblclick={() => onOpen(item)}
          onkeydown={onKey} oncontextmenu={(e) => { selected = item.path; onMenu(e, item); }} ondragstart={dragStart}
          ondragover={(e) => { if (item.type === 'dir' && e.dataTransfer?.types.includes('application/x-dungeontuber-path')) { e.preventDefault(); dragOver = true; } }}
          ondragleave={() => (dragOver = false)} ondrop={drop}>
    {#if item.type === 'dir'}
      <span class="twisty" role="presentation" onclick={toggle} ondblclick={(e) => e.stopPropagation()}>
        <Icon name={expanded ? 'chevron-down' : 'chevron-right'} size={13} />
      </span>
      <span class="folder"><Icon name="folder" size={16} /></span>
    {:else}
      <span class="twisty"></span>
      <span class="file"><Icon name={item.type === 'm3u' ? 'playlist' : 'music'} size={15} /></span>
    {/if}
    <span class="ellipsis name">{item.name}</span>
    {#if item.type === 'dir'}
      <span class="go" role="presentation" title="Go Into" onclick={(e) => { e.stopPropagation(); onGoInto(item.path); }}>
        <Icon name="forward" size={13} />
      </span>
    {/if}
  </button>
  {#if expanded && children}
    {#each children as child (child.path)}
      <TreeNode item={child} depth={depth + 1} bind:selected {onOpen} {onMenu} {onGoInto} />
    {/each}
  {/if}
</div>

<style>
  .row { display: flex; align-items: center; gap: 4px; width: 100%; padding: 3px 6px; border-radius: var(--radius-sm); text-align: left; color: var(--text); }
  .row:hover { background: var(--hover); }
  .row.selected { background: var(--accent-soft); }
  .row.over { outline: 2px dashed var(--accent); }
  .twisty { width: 16px; display: flex; justify-content: center; color: var(--muted); flex: none; }
  .folder { color: #e0a82e; display: flex; }
  .file { color: var(--muted); display: flex; }
  .name { flex: 1; }
  .go { opacity: 0; color: var(--muted); display: flex; padding: 2px; border-radius: 4px; }
  .row:hover .go { opacity: 1; }
  .go:hover { background: var(--hover); color: var(--text); }
</style>
