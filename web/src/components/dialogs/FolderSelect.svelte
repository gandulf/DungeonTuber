<script lang="ts">
  import { t } from '../../lib/i18n.svelte';
  import Icon from '../Icon.svelte';
  import FolderTree from './FolderTree.svelte';

  /** A compact field showing the chosen folder; clicking it opens the folder tree in a popup below (or above) it. */
  let { selected = $bindable() }: { selected: string } = $props();

  let button = $state<HTMLButtonElement | null>(null);
  let popup = $state<HTMLDivElement | null>(null);
  let open = $state(false);
  let position = $state({ left: 0, top: 0, width: 0, height: 0 });

  const parts = $derived(selected.split('/').filter(Boolean));
  const name = $derived(parts.at(-1) ?? selected);
  const parent = $derived(parts.slice(0, -1).join('/'));

  const id = $props.id();

  /** Places the popup below the field, or above it when there is more room there. */
  function place(event: Event) {
    if ((event as ToggleEvent).newState !== 'open') return;
    const rect = button!.getBoundingClientRect();
    const below = window.innerHeight - rect.bottom - 12;
    const above = rect.top - 12;
    const height = Math.min(340, Math.max(below, above));
    const width = Math.max(rect.width, 320);
    position = {
      left: Math.max(8, Math.min(rect.left, window.innerWidth - width - 8)),
      width,
      height,
      top: below >= height || below >= above ? rect.bottom + 4 : rect.top - height - 4,
    };
  }

  // picking a folder closes the popup
  let shown = '';
  $effect(() => {
    if (open && shown && selected !== shown) popup?.hidePopover();
    shown = open ? selected : '';
  });
</script>

<button type="button" class="field" bind:this={button} popovertarget="{id}-folders" aria-haspopup="tree" aria-expanded={open} title={selected}>
  <span class="folder"><Icon name="folder" size={16} /></span>
  <span class="text">
    <span class="ellipsis name">{selected ? name : t('Target folder')}</span>
    {#if parent}<span class="ellipsis parent">{parent}</span>{/if}
  </span>
  <Icon name={open ? 'chevron-up' : 'chevron-down'} size={14} />
</button>

<div class="popup" id="{id}-folders" popover="auto" bind:this={popup} onbeforetoggle={place} ontoggle={(e) => (open = (e as ToggleEvent).newState === 'open')}
     style:left="{position.left}px" style:top="{position.top}px" style:width="{position.width}px" style:height="{position.height}px">
  <FolderTree bind:selected height="0px" />
</div>

<style>
  .field { display: flex; align-items: center; gap: 10px; width: 100%; padding: 7px 12px; border: 1px solid var(--border); border-radius: 10px; background: var(--surface-2); color: var(--muted); text-align: left; }
  .field:hover, .field[aria-expanded='true'] { border-color: var(--accent); color: var(--text); }
  .folder { color: var(--gold); display: flex; opacity: 0.85; }
  .text { display: flex; flex-direction: column; flex: 1; min-width: 0; line-height: 1.25; }
  .name { color: var(--text); font-weight: 550; }
  .parent { font-size: var(--fs-xs); color: var(--faint); }
  .popup { position: fixed; inset: auto; margin: 0; padding: 8px; border: 1px solid var(--border-strong); border-radius: 12px; background: var(--surface); color: var(--text); box-shadow: var(--shadow); }
  .popup:popover-open { display: flex; flex-direction: column; }
</style>
