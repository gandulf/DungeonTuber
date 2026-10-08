<script lang="ts">
  import { api } from '../lib/api';
  import { t } from '../lib/i18n.svelte';
  import { discoverLights, lights, patchSelected, renameLight } from '../lib/stores/lights.svelte';
  import { askText, errorToast, openMenu } from '../lib/stores/ui.svelte';
  import type { Light } from '../lib/types';
  import Icon from './Icon.svelte';

  const SWATCHES = ['#ff7a1a', '#e2725b', '#f6d58e', '#5ad1e8', '#8b6dff', '#e86bb4', '#ff3b30', '#34c759'];

  const selectedLights = $derived(lights.list.filter((light) => lights.selected.includes(light.mac)));
  const current = $derived(selectedLights[0] ?? null);
  const followMusic = $derived(lights.list.length > 0 && lights.list.every((light) => light.scenable));

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

  async function setFollow(value: boolean) {
    for (const light of lights.list) {
      try {
        const updated = await api.patchLight(light.mac, { scenable: value });
        Object.assign(light, updated);
      } catch (e) {
        errorToast(e);
      }
    }
  }

  let pending: ReturnType<typeof setTimeout> | null = null;
  function debounced(patch: Partial<Light>) {
    if (current) Object.assign(current, patch);
    if (pending) clearTimeout(pending);
    pending = setTimeout(() => patchSelected(patch), 150);
  }

  const brightnessPct = $derived(current ? Math.round(((current.brightness ?? 255) / 255) * 100) : 0);
  const tempMin = $derived(current?.temperature_min || 2200);
  const tempMax = $derived(current?.temperature_max || 6500);
  const temp = $derived(current?.temperature ?? tempMin);
</script>

<section class="card lighting" data-tour="lights">
  <div class="head">
    <span class="glyph"><Icon name="bulb" size={17} /></span>
    <h3 class="card-title">{t('Lighting')}</h3>
    <span class="grow"></span>
    <button class="icon-btn" title={t('Refresh')} disabled={lights.discovering} onclick={discoverLights}>
      <Icon name="refresh" size={15} class={lights.discovering ? 'spin' : ''} />
    </button>
  </div>

  <label class="follow">
    <div>
      <span class="follow-title"><Icon name="sparkles" size={15} /> {t('Lights follow music')}</span>
      <span class="card-sub">{t('Lighting reacts to the current song and its markers.')}</span>
    </div>
    <span class="switch">
      <input type="checkbox" checked={followMusic} disabled={!lights.list.length} onchange={(e) => setFollow((e.currentTarget as HTMLInputElement).checked)} />
      <span></span>
    </span>
  </label>

  {#if !lights.list.length}
    <div class="empty">
      <span class="muted">{lights.discovering ? t('Searching for bulbs…') : t('No lights found.')}</span>
      {#if !lights.discovering}<button class="btn sm" onclick={discoverLights}><Icon name="search" size={14} /> {t('Search')}</button>{/if}
    </div>
  {:else}
    <div class="bulbs">
      {#each lights.list as light (light.mac)}
        <button class="bulb" class:selected={lights.selected.includes(light.mac)} class:off={!light.state || !light.online}
                title="{light.name} · {light.mac}{light.online ? '' : ' (offline)'}"
                onclick={(e) => select(e, light)} ondblclick={() => rename(light)}
                oncontextmenu={(e) => openMenu(e, [{ label: t('Rename'), icon: 'edit', action: () => rename(light) }])}>
          <span class="orb" style:--c={light.state ? light.color ?? '#f5c542' : 'transparent'}><Icon name="bulb" size={18} filled={light.state} /></span>
          <span class="name ellipsis">{light.name}</span>
        </button>
      {/each}
    </div>
  {/if}

  {#if current}
    <div class="active">
      <div class="swatch-big" style:--c={current.color ?? '#f5c542'}></div>
      <div class="active-info">
        <span class="label-xs">{t('Active light')}</span>
        <span class="active-name ellipsis">{selectedLights.length > 1 ? t('{0} lights', selectedLights.length) : current.name}</span>
        {#if current.scene}<span class="pill gold">{current.scene}</span>{/if}
      </div>
      <span class="switch">
        <input type="checkbox" checked={current.state} onchange={(e) => patchSelected({ state: (e.currentTarget as HTMLInputElement).checked })} />
        <span></span>
      </span>
    </div>

    <div class="field">
      <span class="lbl"><Icon name="sun" size={14} /> {t('Brightness')}<span class="grow"></span><span class="val">{brightnessPct}%</span></span>
      <input type="range" class="range" min="10" max="255" value={current.brightness ?? 255} style:--pct="{brightnessPct}%"
             oninput={(e) => debounced({ brightness: Number((e.currentTarget as HTMLInputElement).value) })} />
    </div>

    <div class="field">
      <span class="lbl"><Icon name="flame" size={14} /> {t('Temperature')}<span class="grow"></span><span class="val">{current.temperature ? `${current.temperature}K` : '–'}</span></span>
      <input type="range" class="range temperature" min={tempMin} max={tempMax} step="100" value={temp}
             oninput={(e) => debounced({ temperature: Number((e.currentTarget as HTMLInputElement).value) })} />
    </div>

    <div class="field">
      <span class="lbl">{t('Colors')}</span>
      <div class="swatches">
        {#each SWATCHES as swatch (swatch)}
          <button class="swatch" class:on={current.color === swatch} style:background={swatch} aria-label={swatch} onclick={() => patchSelected({ color: swatch })}></button>
        {/each}
        <label class="swatch custom" title={t('Color')}>
          <Icon name="plus" size={14} />
          <input type="color" value={current.color ?? '#ffffff'} onchange={(e) => patchSelected({ color: (e.currentTarget as HTMLInputElement).value })} />
        </label>
      </div>
    </div>

    <label class="field">
      <span class="lbl">{t('Scene')}</span>
      <select value={current.scene ?? ''} onchange={(e) => patchSelected({ scene: (e.currentTarget as HTMLSelectElement).value })}>
        <option value="">{t('None')}</option>
        {#each current.scenes ?? lights.scenes as scene (scene)}<option value={scene}>{scene}</option>{/each}
      </select>
    </label>
  {/if}
</section>

<style>
  .lighting { padding: 16px; display: flex; flex-direction: column; gap: 14px; }
  .head { display: flex; align-items: center; gap: 9px; }
  .glyph { width: 30px; height: 30px; border-radius: 9px; display: grid; place-items: center; background: var(--gold-soft); color: var(--gold); }
  .grow { flex: 1; }
  .follow { display: flex; align-items: center; gap: 12px; padding: 12px 14px; border-radius: 12px; background: var(--surface-2); border: 1px solid var(--border); cursor: pointer; }
  .follow > div { flex: 1; display: flex; flex-direction: column; gap: 3px; }
  .follow-title { display: flex; align-items: center; gap: 7px; font-weight: 600; }
  .empty { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 10px; text-align: center; }
  .bulbs { display: flex; gap: 6px; overflow-x: auto; padding-bottom: 2px; }
  .bulb { display: flex; flex-direction: column; align-items: center; gap: 5px; padding: 8px 6px; min-width: 70px; border-radius: 12px; border: 1px solid transparent; }
  .bulb:hover { background: var(--hover); }
  .bulb.selected { background: var(--accent-soft); border-color: color-mix(in srgb, var(--accent) 40%, transparent); }
  .orb { width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center; color: var(--c); background: radial-gradient(circle, color-mix(in srgb, var(--c) 35%, transparent), transparent 70%); filter: drop-shadow(0 0 8px var(--c)); }
  .bulb.off .orb { color: var(--faint); filter: none; background: var(--surface-3); }
  .name { font-size: var(--fs-xs); max-width: 70px; color: var(--muted); }
  .active { display: flex; align-items: center; gap: 12px; padding: 10px; border-radius: 14px; background: var(--surface-2); border: 1px solid var(--border); }
  .swatch-big { width: 52px; height: 52px; border-radius: 12px; flex: none; background: radial-gradient(circle at 35% 30%, color-mix(in srgb, var(--c) 30%, white), var(--c) 60%, color-mix(in srgb, var(--c) 60%, black)); box-shadow: 0 0 22px color-mix(in srgb, var(--c) 55%, transparent); }
  .active-info { flex: 1; display: flex; flex-direction: column; gap: 3px; min-width: 0; align-items: flex-start; }
  .active-name { font-family: var(--font-display); font-weight: 650; font-size: var(--fs-lg); max-width: 100%; }
  .field { display: flex; flex-direction: column; gap: 8px; }
  .lbl { display: flex; align-items: center; gap: 7px; font-size: var(--fs-sm); font-weight: 600; }
  .val { color: var(--muted); font-weight: 500; font-variant-numeric: tabular-nums; }
  .range.temperature { background: linear-gradient(to right, #ff8a1f, #ffd9a3 45%, #fffaf0 60%, #c9daff); }
  .swatches { display: flex; gap: 8px; flex-wrap: wrap; }
  .swatch { width: 26px; height: 26px; border-radius: 50%; border: 2px solid var(--surface); box-shadow: 0 0 0 1px var(--border-strong); transition: transform 0.12s; }
  .swatch:hover { transform: scale(1.12); }
  .swatch.on { box-shadow: 0 0 0 2px var(--text); }
  .custom { display: grid; place-items: center; background: var(--surface-2); color: var(--muted); cursor: pointer; position: relative; overflow: hidden; }
  .custom input { position: absolute; inset: 0; opacity: 0; cursor: pointer; }
  :global(.spin) { animation: spin 0.9s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
