<script lang="ts">
  import { api } from '../../lib/api';
  import { t } from '../../lib/i18n.svelte';
  import { askText, errorToast } from '../../lib/stores/ui.svelte';
  import type { BrowseItem } from '../../lib/types';
  import Icon from '../Icon.svelte';
  import FolderPicker from './FolderPicker.svelte';

  /** All library roots (local and remote) as one folder tree; `selected` is the chosen client path. */
  let { selected = $bindable(), height = '200px' }: { selected: string; height?: string } = $props();

  // svelte-ignore state_referenced_locally
  const start = selected;
  let roots = $state<BrowseItem[]>([]);
  let expanded = $state<string[]>([]);
  let version = $state(0);

  /** Every library root plus the folders leading to the initial selection are expanded. */
  async function loadRoots() {
    try {
      roots = await api.roots();
      const open = roots.map((root) => root.path);
      for (const root of roots) {
        if (!start.startsWith(root.path + '/')) continue;
        let path = root.path;
        for (const part of start.slice(root.path.length + 1).split('/').filter(Boolean)) {
          open.push(path);
          path += `/${part}`;
        }
      }
      expanded = open;
    } catch (e) {
      errorToast(e);
    }
  }

  $effect(() => {
    void loadRoots();
  });

  async function newFolder(parent = selected) {
    const name = await askText(t('New folder'), t('Name'));
    if (!name) return;
    try {
      const created = await api.createFolder(parent, name);
      if (!expanded.includes(parent)) expanded = [...expanded, parent];
      version++;
      selected = created.path;
    } catch (e) {
      errorToast(e);
    }
  }

  // the app's context menu lives outside the modal dialogs (and would be inert there), so the tree brings its own
  let menu = $state<{ x: number; y: number; path: string } | null>(null);

  function openMenu(event: MouseEvent, item: BrowseItem) {
    menu = { x: Math.min(event.clientX, window.innerWidth - 220), y: Math.min(event.clientY, window.innerHeight - 60), path: item.path };
  }

  function menuKey(event: KeyboardEvent) {
    if (menu && event.key === 'Escape') {
      event.preventDefault();
      event.stopPropagation();
      menu = null;
    }
  }
</script>

<svelte:window onpointerdowncapture={(e) => { if (menu && !(e.target as Element).closest?.('.tree-menu')) menu = null; }}
               onkeydowncapture={menuKey} onblur={() => (menu = null)} />

<div class="fill tree">
<div class="folders" role="tree" aria-label={t('Target folder')} style:min-height={height}>
  {#key version}
    {#each roots as item (item.path)}
      <FolderPicker {item} bind:selected bind:expanded onMenu={openMenu} />
    {/each}
  {/key}
</div>
<div class="path">
  <span class="ellipsis grow" title={selected}>{selected}</span>
  <button class="icon-btn" title={t('New folder…')} disabled={!selected} onclick={() => newFolder()}><Icon name="plus" size={15} /></button>
</div>
{#if menu}
  <div class="tree-menu" role="menu" style:left="{menu.x}px" style:top="{menu.y}px">
    <button class="item" role="menuitem" onclick={() => { const parent = menu!.path; menu = null; void newFolder(parent); }}>
      <span class="ic"><Icon name="plus" size={15} /></span>{t('New folder…')}
    </button>
  </div>
{/if}
</div>

<style>
  .path { display: flex; align-items: center; gap: 6px; padding: 2px 6px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface); margin-top: 6px; min-height: 32px; }
  .grow { flex: 1; min-width: 0; font-size: var(--fs-sm); }
  .tree { display: flex; flex-direction: column; flex: 1 1 auto; min-height: 0; }
  .tree-menu { position: fixed; z-index: 10; min-width: 200px; padding: 6px; background: var(--surface); border: 1px solid var(--border); border-radius: 12px; box-shadow: var(--shadow); }
  .item { display: flex; align-items: center; gap: 9px; width: 100%; padding: 7px 10px 7px 7px; border-radius: 8px; text-align: left; color: var(--text); }
  .item:hover { background: var(--accent-soft); }
  .ic { width: 18px; display: flex; justify-content: center; color: var(--muted); }
  .folders { flex: 1 1 0; min-height: 0; overflow: auto; border: 1px solid var(--border); border-radius: 10px; padding: 2px; }
</style>
