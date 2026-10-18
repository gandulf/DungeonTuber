<script lang="ts">
  import { longpress } from '../../lib/longpress';
  import FolderPicker from './FolderPicker.svelte';
  import { api } from '../../lib/api';
  import { errorToast } from '../../lib/stores/ui.svelte';
  import type { BrowseItem } from '../../lib/types';
  import Icon from '../Icon.svelte';

  let { item, depth = 1, selected = $bindable(), expanded = $bindable(), onMenu }: {
    item: BrowseItem;
    depth?: number;
    selected: string;
    expanded: string[];
    onMenu?: (event: MouseEvent, item: BrowseItem) => void;
  } = $props();

  let children = $state<BrowseItem[] | null>(null);
  const open = $derived(expanded.includes(item.path));
  const isRoot = $derived(item.storage !== undefined);

  // children are loaded as soon as the node is shown, so the caret can be hidden for folders without subfolders
  $effect(() => {
    if (children === null) void load();
  });

  async function load() {
    try {
      children = (await api.browse(item.path)).items.filter((child) => child.type === 'dir');
    } catch (e) {
      errorToast(e);
      children = [];
    }
  }

  // with a finger a tap on a folder selects it and unfolds it (touch has no double click)
  let touching = false;

  function toggle(event: Event) {
    event.stopPropagation();
    expanded = open ? expanded.filter((path) => path !== item.path) : [...expanded, item.path];
  }
</script>

<div role="treeitem" aria-expanded={children?.length ? open : undefined} aria-selected={selected === item.path}>
  <button class="row" class:selected={selected === item.path} class:lib-root={isRoot} style:padding-left="{depth * 14 - 8}px"
          title={item.path} use:longpress onpointerdown={(e) => (touching = e.pointerType !== 'mouse')}
          onclick={(e) => { selected = item.path; if (touching && children?.length && !open) toggle(e); }}
          oncontextmenu={(e) => { if (onMenu) { e.preventDefault(); e.stopPropagation(); onMenu(e, item); } }} ondblclick={(e) => children?.length && toggle(e)}>
    <span class="twisty" role="presentation" onclick={(e) => children?.length && toggle(e)} ondblclick={(e) => e.stopPropagation()}>
      {#if children?.length}<Icon name={open ? 'chevron-down' : 'chevron-right'} size={13} />{/if}
    </span>
    <span class="folder"><Icon name={isRoot && item.storage !== 'local' ? 'cloud' : 'folder'} size={15} /></span>
    <span class="ellipsis">{item.name}</span>
  </button>
  {#if open && children}
    {#each children as child (child.path)}
      <FolderPicker item={child} depth={depth + 1} bind:selected bind:expanded {onMenu} />
    {/each}
  {/if}
</div>

<style>
  .row { display: flex; align-items: center; gap: 5px; width: 100%; padding: 4px 6px; border-radius: 8px; text-align: left; color: var(--muted); }
  @media (hover: hover) { .row:hover { background: var(--hover); color: var(--text); } }
  .row.selected { background: var(--accent-soft); color: var(--accent); }
  .row.lib-root { font-weight: 600; }
  .twisty { width: 16px; display: flex; justify-content: center; flex: none; }
  .folder { color: var(--gold); display: flex; opacity: 0.85; }
  @media (pointer: coarse) {
    .row { min-height: 44px; padding-top: 0; padding-bottom: 0; -webkit-touch-callout: none; user-select: none; -webkit-tap-highlight-color: transparent; }
    .row:active { background: var(--hover); }
    .twisty { align-self: stretch; width: 36px; margin: 0 -6px 0 -4px; align-items: center; }
  }
</style>
