<script lang="ts">
  import { t } from '../../lib/i18n.svelte';
  import { lights } from '../../lib/stores/lights.svelte';
  import type { LightSetting } from '../../lib/types';

  let { value = $bindable() }: { value: LightSetting | null } = $props();

  const mode = $derived(value === null ? 'none' : value.scene ? 'scene' : value.temperature ? 'temperature' : 'color');

  function setMode(next: string) {
    const brightness = value?.brightness ?? 255;
    if (next === 'none') value = null;
    else if (next === 'color') value = { brightness, color: value?.color ?? '#ff8800', temperature: null, scene: null };
    else if (next === 'temperature') value = { brightness, color: null, temperature: value?.temperature ?? 3000, scene: null };
    else value = { brightness, color: null, temperature: null, scene: value?.scene ?? lights.scenes[0] ?? 'Ocean' };
  }
</script>

<div class="light-editor">
  <div class="modes">
    {#each [['none', t('None')], ['color', t('Color')], ['temperature', t('Temperature')], ['scene', t('Scene')]] as [key, label] (key)}
      <button type="button" class="chip" class:on={mode === key} onclick={() => setMode(key)}>{label}</button>
    {/each}
  </div>
  {#if value}
    <label class="field">
      <span>{t('Brightness')} <span class="muted">{Math.round(((value.brightness ?? 255) / 255) * 100)}%</span></span>
      <input type="range" min="10" max="255" bind:value={value.brightness} />
    </label>
    {#if mode === 'color'}
      <label class="field"><span>{t('Color')}</span><input type="color" bind:value={value.color} /></label>
    {:else if mode === 'temperature'}
      <label class="field"><span>{t('Temperature')} <span class="muted">{value.temperature}K</span></span>
        <input type="range" min="2200" max="6500" step="100" bind:value={value.temperature} /></label>
    {:else if mode === 'scene'}
      <label class="field"><span>{t('Scene')}</span>
        <select bind:value={value.scene}>
          {#each lights.scenes.length ? lights.scenes : ['Ocean', 'Romance', 'Sunset', 'Party', 'Fireplace', 'Cozy', 'Forest', 'Pastel colors', 'Wake up', 'Bedtime', 'Warm white', 'Daylight', 'Cool white', 'Night light', 'Focus', 'Relax', 'True colors', 'TV time', 'Plantgrowth', 'Spring', 'Summer', 'Fall', 'Deepdive', 'Jungle', 'Mojito', 'Club', 'Christmas', 'Halloween', 'Candlelight', 'Golden white', 'Pulse', 'Steampunk'] as scene (scene)}
            <option value={scene}>{scene}</option>
          {/each}
        </select>
      </label>
    {/if}
  {/if}
</div>

<style>
  .light-editor { display: flex; flex-direction: column; gap: 10px; }
  .modes { display: flex; gap: 6px; flex-wrap: wrap; }
  .field { display: flex; flex-direction: column; gap: 4px; }
  .field > span { display: flex; justify-content: space-between; font-size: var(--fs-sm); }
  input[type='color'] { width: 60px; height: 30px; border: 1px solid var(--border); border-radius: 6px; padding: 2px; background: var(--surface); }
</style>
