<script lang="ts">
  import { prefs, toggleSection } from '../lib/prefs.svelte';
  import Icon from './Icon.svelte';

  /** The heading of a sidebar section: a click folds the section to it, or unfolds it (remembered per device). */
  let { name, label }: { name: string; label: string } = $props();

  const open = $derived(!prefs.collapsedSections.includes(name));
</script>

<button type="button" class="toggle" aria-expanded={open} onclick={() => toggleSection(name)}>
  <Icon name={open ? 'chevron-down' : 'chevron-right'} size={12} />
  <span class="label-xs">{label}</span>
</button>

<style>
  .toggle { display: flex; align-items: center; gap: 4px; min-width: 0; padding: 4px 8px 6px 4px; border-radius: 7px; color: var(--faint); text-align: left; -webkit-tap-highlight-color: transparent; }
  .toggle .label-xs { padding: 0; }
  @media (hover: hover) { .toggle:hover { color: var(--text); } }
  @media (pointer: coarse) { .toggle { min-height: 40px; padding-top: 0; padding-bottom: 0; } }
</style>
