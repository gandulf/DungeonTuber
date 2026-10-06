<script lang="ts">
  import { prefs } from '../lib/prefs.svelte';
  import { data } from '../lib/stores/data.svelte';
  import EffectsPanel from './EffectsPanel.svelte';
  import LightsPanel from './LightsPanel.svelte';
</script>

<div class="right-panel">
  {#if prefs.showLights && data.settings?.lightsEnabled !== false}<LightsPanel />{/if}
  {#if prefs.showEffects}<EffectsPanel />{/if}
</div>

<style>
  .right-panel { display: flex; flex-direction: column; gap: 14px; min-height: 0; }
</style>
