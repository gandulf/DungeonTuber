<script lang="ts">
  import { t } from '../lib/i18n.svelte';
  import { discoverLights, lights, patchSelected, renameLight } from '../lib/stores/lights.svelte';
  import { askText, openMenu } from '../lib/stores/ui.svelte';
  import type { Light } from '../lib/types';
  import Icon from './Icon.svelte';

  const selectedLights = $derived(lights.list.filter((light) => lights.selected.includes(light.mac)));
  const current = $derived(selectedLights[0] ?? null);

  function select(event: MouseEvent, light: Light) {
    if (event.ctrlKey || event.metaKey) {
      lights.selected = lights.selected.includes(light.mac) ? lights.selected.filter((m) => m !== light.mac) : [...lights.selected, light.mac];
    } else {
      lights.selected = [light.mac];
    }
  }

  async function rename(light: Light) {
    const name = await askText(t('Name'), '', light.name);
    if (name) await renameLight(light.mac, name);
  }

  function kelvinLabel(k: number | null) {
    return k ? `${(k / 1000).toFixed(1)}K` : '–';
  }

  let pending: ReturnType<typeof setTimeout> | null = null;
  function debounced(patch: Partial<Light>) {
    if (current) Object.assign(current, patch);
    if (pending) clearTimeout(pending);
    pending = setTimeout(() => patchSelected(patch), 150);
  }
</script>

<section class="lights">
  <div class="section-title">
    <Icon name="bulb" size={16} /> {t('Lights')}
    <span class="grow"></span>
    <button class="icon-btn" title={t('Refresh')} disabled={lights.discovering} onclick={discoverLights}>
      <Icon name="refresh" size={15} class={lights.discovering ? 'spin' : ''} />
    </button>
  </div>

  <div class="panel grid">
    {#if !lights.list.length}
      <div class="empty muted">
        {lights.discovering ? t('Searching for bulbs…') : t('No lights found.')}
        {#if !lights.discovering}<button class="btn" onclick={discoverLights}>{t('Search')}</button>{/if}
      </div>
    {/if}
    {#each lights.list as light (light.mac)}
      <button class="bulb" class:selected={lights.selected.includes(light.mac)} class:off={!light.state || !light.online}
              title="{light.name} · {light.mac}{light.online ? '' : ' (offline)'}"
              onclick={(e) => select(e, light)} ondblclick={() => rename(light)}
              oncontextmenu={(e) => openMenu(e, [{ label: t('Rename'), icon: 'edit', action: () => rename(light) }])}>
        <span class="glow" style:color={light.state ? light.color ?? '#f5c542' : 'var(--muted)'}><Icon name="bulb" size={26} filled={light.state} /></span>
        <span class="name ellipsis">{light.name}</span>
      </button>
    {/each}
  </div>

  {#if current}
    <div class="settings">
      <div class="row">
        <span class="ellipsis strong">{selectedLights.length > 1 ? t('{0} lights', selectedLights.length) : current.name}</span>
        <span class="grow"></span>
        <label class="switch" title={t('Enabled')}>
          <input type="checkbox" checked={current.state} onchange={(e) => patchSelected({ state: (e.currentTarget as HTMLInputElement).checked })} />
          <span></span>
        </label>
      </div>

      <label class="field">
        <span class="lbl">{t('Brightness')} <span class="muted">{Math.round(((current.brightness ?? 255) / 255) * 100)}%</span></span>
        <input type="range" class="brightness" min="10" max="255" value={current.brightness ?? 255}
               oninput={(e) => debounced({ brightness: Number((e.currentTarget as HTMLInputElement).value) })} />
      </label>

      <label class="field">
        <span class="lbl">{t('Temperature')} <span class="muted">{kelvinLabel(current.temperature)}</span></span>
        <input type="range" class="temperature" min={current.temperature_min || 2200} max={current.temperature_max || 6500} step="100"
               value={current.temperature ?? current.temperature_min ?? 2700}
               oninput={(e) => debounced({ temperature: Number((e.currentTarget as HTMLInputElement).value) })} />
      </label>

      <div class="field">
        <span class="lbl">{t('Color')}</span>
        <div class="color-row">
          <input type="color" value={current.color ?? '#ffffff'} onchange={(e) => patchSelected({ color: (e.currentTarget as HTMLInputElement).value })} />
          {#each ['#ff3b30', '#ff9500', '#ffd60a', '#34c759', '#0a84ff', '#5e5ce6', '#bf5af2'] as swatch (swatch)}
            <button class="swatch" style:background={swatch} aria-label={swatch} onclick={() => patchSelected({ color: swatch })}></button>
          {/each}
        </div>
      </div>

      <label class="field">
        <span class="lbl">{t('Scene')}</span>
        <select value={current.scene ?? ''} onchange={(e) => patchSelected({ scene: (e.currentTarget as HTMLSelectElement).value })}>
          <option value="">{t('None')}</option>
          {#each current.scenes ?? lights.scenes as scene (scene)}<option value={scene}>{scene}</option>{/each}
        </select>
      </label>

      <label class="check">
        <input type="checkbox" checked={current.scenable} onchange={(e) => patchSelected({ scenable: (e.currentTarget as HTMLInputElement).checked })} />
        {t('Controlled by Songs')}
      </label>
    </div>
  {/if}
</section>

<style>
  .lights { display: flex; flex-direction: column; gap: 6px; }
  .grow { flex: 1; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(76px, 1fr)); gap: 4px; padding: 6px; max-height: 190px; overflow: auto; }
  .empty { grid-column: 1 / -1; padding: 12px; text-align: center; display: flex; flex-direction: column; gap: 8px; align-items: center; }
  .bulb { display: flex; flex-direction: column; align-items: center; gap: 3px; padding: 8px 4px; border-radius: var(--radius-sm); }
  .bulb:hover { background: var(--hover); }
  .bulb.selected { background: var(--accent-soft); }
  .bulb.off .glow { opacity: 0.55; }
  .glow { display: flex; filter: drop-shadow(0 0 6px currentColor); }
  .bulb.off .glow { filter: none; }
  .name { font-size: var(--fs-xs); max-width: 100%; }
  .settings { display: flex; flex-direction: column; gap: 10px; padding: 4px 2px; }
  .row { display: flex; align-items: center; gap: 8px; }
  .strong { font-weight: 600; }
  .field { display: flex; flex-direction: column; gap: 5px; }
  .lbl { display: flex; justify-content: space-between; font-size: var(--fs-sm); }
  input[type='range'] { width: 100%; appearance: none; height: 12px; border-radius: 6px; border: 1px solid var(--border); }
  input[type='range']::-webkit-slider-thumb { appearance: none; width: 16px; height: 16px; border-radius: 50%; background: var(--surface); border: 3px solid var(--accent); box-shadow: 0 1px 3px rgba(0,0,0,.3); }
  .brightness { background: linear-gradient(to right, #111, #fff); }
  .temperature { background: linear-gradient(to right, #ff9329, #fffffb, #c9daff); }
  .color-row { display: flex; gap: 5px; align-items: center; flex-wrap: wrap; }
  input[type='color'] { width: 34px; height: 26px; border: 1px solid var(--border); border-radius: 6px; padding: 1px; background: var(--surface); }
  .swatch { width: 20px; height: 20px; border-radius: 50%; border: 2px solid var(--surface); box-shadow: 0 0 0 1px var(--border); }
  .check { display: flex; align-items: center; gap: 8px; font-size: var(--fs-sm); }
  .switch { position: relative; display: inline-block; width: 36px; height: 20px; }
  .switch input { opacity: 0; width: 0; height: 0; }
  .switch span { position: absolute; inset: 0; border-radius: 10px; background: var(--border-strong); transition: 0.2s; cursor: pointer; }
  .switch span::before { content: ''; position: absolute; width: 14px; height: 14px; left: 3px; top: 3px; border-radius: 50%; background: white; transition: 0.2s; }
  .switch input:checked + span { background: var(--accent); }
  .switch input:checked + span::before { transform: translateX(16px); }
  :global(.spin) { animation: spin 0.9s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
