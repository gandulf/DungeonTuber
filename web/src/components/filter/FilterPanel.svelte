<script lang="ts">
  import { t } from '../../lib/i18n.svelte';
  import { prefs, savePrefs } from '../../lib/prefs.svelte';
  import { emptyFilter } from '../../lib/scoring';
  import { data, savePresets } from '../../lib/stores/data.svelte';
  import { filter, onFilterChanged } from '../../lib/stores/library.svelte';
  import { askConfirm, askText, openMenu } from '../../lib/stores/ui.svelte';
  import type { MusicCategory, Preset } from '../../lib/types';
  import Icon from '../Icon.svelte';
  import BpmDial from './BpmDial.svelte';
  import CategorySlider from './CategorySlider.svelte';
  import Circumplex from './Circumplex.svelte';

  const VALENCE = 'Valence';
  const AROUSAL = 'Arousal';

  const hasCircumplex = $derived(prefs.filter.circumplex && data.categories.some((c) => c.key === VALENCE) && data.categories.some((c) => c.key === AROUSAL));
  const visible = $derived(prefs.filter.presets || prefs.filter.sliders || hasCircumplex || prefs.filter.bpm);
  const showMap = $derived(prefs.showMoodMap && hasCircumplex);

  const groups = $derived.by(() => {
    const map = new Map<string, MusicCategory[]>();
    for (const category of data.categories) {
      if (showMap && (category.key === VALENCE || category.key === AROUSAL)) continue;
      const group = category.group || '';
      if (!map.has(group)) map.set(group, []);
      map.get(group)!.push(category);
    }
    return [...map.entries()];
  });
  let activeGroup = $state<string | null>(null);
  const current = $derived<[string, MusicCategory[]] | undefined>(groups.find(([group]) => group === activeGroup) ?? groups[0]);
  const active = $derived(!emptyFilter(filter));

  function setCategory(key: string, value: number | null) {
    filter.categories[key] = value;
    onFilterChanged();
  }

  function clearFilter() {
    filter.categories = {};
    filter.tags = [];
    filter.genres = [];
    filter.bpm = null;
    onFilterChanged();
  }

  function applyPreset(preset: Preset) {
    filter.categories = { ...preset.categories };
    filter.tags = [...preset.tags];
    filter.genres = [...preset.genres];
    filter.bpm = preset.bpm;
    onFilterChanged();
  }

  async function savePreset() {
    const name = await askText(t('Save as Preset'), t('Name'));
    if (!name) return;
    const preset: Preset = {
      name,
      categories: Object.fromEntries(Object.entries(filter.categories).filter(([, v]) => v !== null && v !== undefined && v >= 0)) as Record<string, number>,
      tags: [...filter.tags],
      genres: [...filter.genres],
      bpm: filter.bpm,
    };
    await savePresets([...data.presets.filter((p) => p.name !== name), preset]);
  }

  async function resetPresets() {
    if (await askConfirm(t('Reset Presets') + '?')) await savePresets([]);
  }

  function presetMenu(event: MouseEvent, preset: Preset) {
    openMenu(event, [
      { label: t('Remove'), icon: 'trash', action: () => savePresets(data.presets.filter((p) => p.name !== preset.name)) },
      { label: t('Reset Presets'), action: resetPresets },
    ]);
  }

  function toggleMap() {
    prefs.showMoodMap = !prefs.showMoodMap;
    prefs.moodCollapsed = false;
    savePrefs();
  }

  function toggleCollapsed() {
    prefs.moodCollapsed = !prefs.moodCollapsed;
    savePrefs();
  }
</script>

{#snippet sliders(list: MusicCategory[])}
  <div class="slider-list" class:wide={!showMap}>
    {#each list as category (category.key)}
      <CategorySlider {category} value={filter.categories[category.key] ?? null} onchange={(v) => setCategory(category.key, v)} />
    {/each}
    {#if prefs.filter.bpm && (current?.[0] ?? '') === ''}
      <div data-tour="bpm"><BpmDial value={filter.bpm} onchange={(v) => { filter.bpm = v; onFilterChanged(); }} /></div>
    {/if}
  </div>
{/snippet}

{#if visible}
  <section class="mood" aria-label={t('Filter')}>
    <div class="head">
      {#if hasCircumplex}
        <button class="btn sm map-toggle" class:on={prefs.showMoodMap} aria-pressed={prefs.showMoodMap} onclick={toggleMap}>
          <Icon name="compass" size={14} /> {t('Mood Explorer')}
        </button>
      {:else}
        <span class="card-title">{t('Mood')}</span>
      {/if}

      {#if prefs.filter.presets}
        <div class="presets" data-tour="presets">
          {#each data.presets as preset (preset.name)}
            <button class="preset" onclick={() => applyPreset(preset)} oncontextmenu={(e) => presetMenu(e, preset)} title={t('Presets')}>
              <Icon name="bookmark" size={13} /> {preset.name}
            </button>
          {/each}
        </div>
      {/if}
      <span class="grow"></span>
      {#if active}
        <button class="btn sm ghost" onclick={clearFilter}><Icon name="refresh" size={13} /> {t('Reset')}</button>
      {/if}
      <button class="icon-btn" title={t('Toggle Filter')} onclick={toggleCollapsed}>
        <Icon name={prefs.moodCollapsed ? 'chevron-down' : 'chevron-up'} size={16} />
      </button>
    </div>

    {#if !prefs.moodCollapsed && (prefs.filter.sliders || hasCircumplex || prefs.filter.bpm)}
      <div class="cards" class:single={!showMap}>
        {#if showMap}
          <div class="card vibe" data-tour="russel">
            <div class="card-head">
              <div>
                <h3 class="card-title">{t('Select the vibe')}</h3>
                <p class="card-sub">{t('Drag in the mood map')}</p>
              </div>
            </div>
            <Circumplex valence={filter.categories[VALENCE] ?? null} arousal={filter.categories[AROUSAL] ?? null}
                        onchange={(v, a) => { filter.categories[VALENCE] = v; filter.categories[AROUSAL] = a; onFilterChanged(); }} />
          </div>
        {/if}
        {#if prefs.filter.sliders || prefs.filter.bpm}
          <div class="card fine" data-tour="slider">
            <div class="card-head">
              <div>
                <h3 class="card-title">{t('Mood Sliders')}</h3>
                <p class="card-sub">{t('Fine tune the sound')}</p>
              </div>
              {#if groups.length > 1}
                <div class="seg small">
                  {#each groups as [group] (group)}
                    <button class:on={(current?.[0] ?? '') === group} onclick={() => (activeGroup = group)}>{group || t('General')}</button>
                  {/each}
                </div>
              {/if}
            </div>
            {#if current}{@render sliders(prefs.filter.sliders ? current[1] : [])}{/if}
            <div class="card-foot">
              <button class="btn sm" onclick={savePreset}><Icon name="bookmark" size={14} /> {t('Save as Preset')}</button>
              {#if active}<button class="btn sm ghost" onclick={clearFilter}>{t('Reset')}</button>{/if}
            </div>
          </div>
        {/if}
      </div>
    {/if}
  </section>
{/if}

<style>
  .mood { display: flex; flex-direction: column; gap: 10px; flex: none; padding-right: 2px; }
  .head { display: flex; align-items: center; gap: 10px; min-height: 36px; flex-wrap: wrap; }
  .presets { display: flex; gap: 6px; flex-wrap: wrap; align-items: center; }
  .preset { display: inline-flex; align-items: center; gap: 5px; height: 28px; padding: 0 11px; border-radius: 9px; font-size: var(--fs-sm); color: var(--gold); background: var(--gold-soft); border: 1px solid transparent; }
  .preset:hover { border-color: var(--gold); }
  .grow { flex: 1; }
  .cards { display: grid; grid-template-columns: minmax(280px, 0.95fr) minmax(320px, 1.2fr); gap: 12px; height: min(36vh, 290px); }
  .cards.single { grid-template-columns: 1fr; }
  .card { padding: 14px 18px; display: flex; flex-direction: column; gap: 10px; min-height: 0; overflow: hidden; }
  .card-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
  .map-toggle.on { background: var(--accent-soft); color: var(--accent); border-color: var(--accent); }
  .seg.small button { padding: 3px 10px; font-size: var(--fs-xs); }
  .slider-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(250px, 1fr)); column-gap: 26px; row-gap: 2px; overflow-y: auto; padding-right: 4px; align-content: start; }
  .slider-list.wide { grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); }
  .card-foot { display: flex; gap: 8px; margin-top: auto; padding-top: 4px; }
  @media (max-width: 1100px) { .cards { grid-template-columns: 1fr; } .vibe { display: none; } }
  @media (max-width: 900px) { .cards { max-height: 30vh; } }
</style>
