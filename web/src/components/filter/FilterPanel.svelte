<script lang="ts">
  import { t } from '../../lib/i18n.svelte';
  import { prefs, savePrefs } from '../../lib/prefs.svelte';
  import { emptyFilter } from '../../lib/scoring';
  import { data, savePresets } from '../../lib/stores/data.svelte';
  import { availableGenres, availableTags, filter, onFilterChanged } from '../../lib/stores/library.svelte';
  import { askConfirm, askText, openMenu } from '../../lib/stores/ui.svelte';
  import type { Preset } from '../../lib/types';
  import Icon from '../Icon.svelte';
  import BpmDial from './BpmDial.svelte';
  import CategorySlider from './CategorySlider.svelte';
  import Circumplex from './Circumplex.svelte';

  const VALENCE = 'Valence';
  const AROUSAL = 'Arousal';

  const groups = $derived.by(() => {
    const map = new Map<string, typeof data.categories>();
    for (const category of data.categories) {
      const group = category.group || '';
      if (!map.has(group)) map.set(group, []);
      map.get(group)!.push(category);
    }
    return [...map.entries()];
  });

  let activeGroup = $state('');
  const current = $derived(groups.find(([group]) => group === activeGroup) ?? groups[0]);
  const hasCircumplex = $derived(prefs.filter.circumplex && data.categories.some((c) => c.key === VALENCE) && data.categories.some((c) => c.key === AROUSAL));
  const showSliderArea = $derived(prefs.filter.sliders || hasCircumplex || prefs.filter.bpm);
  const tags = $derived(availableTags());
  const genres = $derived(availableGenres());

  function setCategory(key: string, value: number | null) {
    filter.categories[key] = value;
    onFilterChanged();
  }

  function toggleTag(tag: string) {
    filter.tags = filter.tags.includes(tag) ? filter.tags.filter((t) => t !== tag) : [...filter.tags, tag];
    onFilterChanged();
  }

  function toggleGenre(genre: string) {
    filter.genres = filter.genres.includes(genre) ? filter.genres.filter((g) => g !== genre) : [...filter.genres, genre];
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

  function panelMenu(event: MouseEvent) {
    openMenu(event, [
      { label: t('Presets'), children: data.presets.map((p) => ({ label: p.name, action: () => applyPreset(p) })) },
      { label: t('Save as Preset'), icon: 'plus', action: savePreset },
      { label: t('Clear Values'), icon: 'close', action: clearFilter },
      { label: t('Reset Presets'), action: resetPresets },
      { separator: true },
      { label: t('Toggle Filter'), checked: !collapsed, action: () => { collapsed = !collapsed; } },
    ]);
  }

  let collapsed = $state(false);

  function onTagDragStart(event: DragEvent, tag: string) {
    event.dataTransfer?.setData('application/x-dungeontuber-tag', tag);
    if (event.dataTransfer) event.dataTransfer.effectAllowed = 'copy';
  }

  $effect(() => {
    void prefs.filter;
    savePrefs();
  });
</script>

<div class="filter" oncontextmenu={panelMenu} role="region" aria-label={t('Filter')}>
  <div class="top">
    {#if prefs.filter.presets}
      <div class="presets" data-tour="presets">
        {#each data.presets as preset (preset.name)}
          <button class="btn preset" onclick={() => applyPreset(preset)} oncontextmenu={(e) => presetMenu(e, preset)}>{preset.name}</button>
        {/each}
        <button class="icon-btn" title={t('Save as Preset')} onclick={savePreset}><Icon name="plus" size={15} /></button>
      </div>
    {/if}
    <span class="grow"></span>
    {#if !emptyFilter(filter)}
      <button class="btn clear" onclick={clearFilter}><Icon name="close" size={13} /> {t('Clear Values')}</button>
    {/if}
    {#if showSliderArea}
      <button class="icon-btn" title={t('Toggle Filter')} onclick={() => (collapsed = !collapsed)}>
        <Icon name={collapsed ? 'chevron-right' : 'chevron-down'} size={15} />
      </button>
    {/if}
  </div>

  {#if showSliderArea && !collapsed}
    {#if groups.length > 1 && prefs.filter.sliders}
      <div class="group-tabs">
        {#each groups as [group] (group)}
          <button class="group" class:active={(current?.[0] ?? '') === group} onclick={() => (activeGroup = group)}>{group || t('General')}</button>
        {/each}
      </div>
    {/if}
    <div class="sliders">
      {#if hasCircumplex && (current?.[0] ?? '') === ''}
        <div data-tour="russel">
          <Circumplex valence={filter.categories[VALENCE] ?? null} arousal={filter.categories[AROUSAL] ?? null}
                      onchange={(v, a) => { filter.categories[VALENCE] = v; filter.categories[AROUSAL] = a; onFilterChanged(); }} />
        </div>
      {/if}
      {#if prefs.filter.sliders && current}
        <div class="slider-row" data-tour="slider">
          {#each current[1] as category (category.key)}
            {#if !(hasCircumplex && (category.key === VALENCE || category.key === AROUSAL))}
              <CategorySlider {category} value={filter.categories[category.key] ?? null} onchange={(v) => setCategory(category.key, v)} />
            {/if}
          {/each}
        </div>
      {/if}
      {#if prefs.filter.bpm && (current?.[0] ?? '') === ''}
        <div data-tour="bpm"><BpmDial value={filter.bpm} onchange={(v) => { filter.bpm = v; onFilterChanged(); }} /></div>
      {/if}
    </div>
  {/if}

  {#if prefs.filter.tags && tags.length}
    <div class="chips-block" data-tour="tags">
      <span class="label-xs">{t('Tags')}</span>
      <div class="chips">
        {#each tags as tag (tag)}
          <button class="chip" class:on={filter.tags.includes(tag)} draggable="true" ondragstart={(e) => onTagDragStart(e, tag)} onclick={() => toggleTag(tag)}>{tag}</button>
        {/each}
      </div>
    </div>
  {/if}
  {#if prefs.filter.genres && genres.length}
    <div class="chips-block">
      <span class="label-xs">{t('Genres')}</span>
      <div class="chips">
        {#each genres as genre (genre)}
          <button class="chip genre" class:on={filter.genres.includes(genre)} onclick={() => toggleGenre(genre)}>{genre}</button>
        {/each}
      </div>
    </div>
  {/if}
</div>

<style>
  .filter { display: flex; flex-direction: column; gap: 8px; padding: 6px 2px 8px; max-height: 46vh; overflow-y: auto; flex: none; }
  .top { display: flex; align-items: center; gap: 6px; min-height: 28px; }
  .presets { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
  .preset { border-radius: 14px; padding: 4px 12px; font-size: var(--fs-sm); }
  .clear { border-radius: 14px; padding: 3px 10px; font-size: var(--fs-sm); }
  .grow { flex: 1; }
  .group-tabs { display: flex; gap: 4px; }
  .group { padding: 4px 12px; border-radius: 14px; color: var(--muted); font-size: var(--fs-sm); }
  .group:hover { background: var(--hover); color: var(--text); }
  .group.active { background: var(--accent-soft); color: var(--accent); font-weight: 600; }
  .sliders { display: flex; gap: 14px; align-items: stretch; overflow-x: auto; padding-bottom: 2px; }
  .slider-row { display: flex; gap: 2px; flex: 1; justify-content: flex-start; }
  .chips-block { display: flex; flex-direction: column; gap: 5px; }
  @media (max-width: 900px) { .filter { max-height: 32vh; } }
  .chips { display: flex; flex-wrap: wrap; gap: 6px; max-height: 64px; overflow-y: auto; }
</style>
