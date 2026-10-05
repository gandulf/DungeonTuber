<script lang="ts">
  import { editSong, analyze } from '../lib/actions';
  import { t } from '../lib/i18n.svelte';
  import { prefs, savePrefs } from '../lib/prefs.svelte';
  import { data, saveSettings } from '../lib/stores/data.svelte';
  import { effects, loadEffects } from '../lib/stores/effects.svelte';
  import { player, playEffect, setEffectIntensity, setEffectsVolume, toggleEffect } from '../lib/stores/player.svelte';
  import { askText, openMenu } from '../lib/stores/ui.svelte';
  import type { Effect } from '../lib/types';
  import Icon from './Icon.svelte';
  import VolumeControl from './player/VolumeControl.svelte';

  let muted = $state(false);
  let lastVolume = prefs.effectsVolume;

  const list = $derived(effects.list.filter((e) => !effects.search || label(e).toLowerCase().includes(effects.search.toLowerCase())));

  function label(effect: Effect) {
    return prefs.effectsTitle && effect.title ? effect.title : effect.name;
  }

  function isPlaying(effect: Effect) {
    return player.effectPlaying && player.effect?.id === effect.id;
  }

  async function chooseDirectory() {
    const dir = await askText(t('Select Effects Directory'), t('Path on the server'), data.settings?.effectsDirectory ?? '');
    if (dir === null) return;
    await saveSettings({ effectsDirectory: dir });
    await loadEffects();
  }

  function menu(event: MouseEvent, effect?: Effect) {
    const variant = effect ? effect.intensities[isPlaying(effect) ? player.effectIntensity : 0] : null;
    openMenu(event, [
      ...(effect && variant ? [
        { label: t('Play'), icon: 'play', action: () => playEffect(effect, 0) },
        { label: t('Edit Song'), icon: 'edit', action: () => editSong(variant) },
        { label: t('Analyze'), icon: 'sparkles', action: () => analyze([variant.path]) },
        { separator: true },
      ] : []),
      { label: t('Select Effects Directory'), icon: 'folder', action: chooseDirectory },
      { label: t('Refresh'), icon: 'refresh', action: loadEffects },
      { label: t('Use mp3 title instead of file name'), checked: prefs.effectsTitle, action: () => { prefs.effectsTitle = !prefs.effectsTitle; savePrefs(); } },
    ]);
  }

  function setGrid(grid: boolean) {
    prefs.effectsGrid = grid;
    savePrefs();
  }

  function mute() {
    if (muted) setEffectsVolume(lastVolume);
    else {
      lastVolume = prefs.effectsVolume;
      setEffectsVolume(0);
    }
    muted = !muted;
  }
</script>

<section class="effects" data-tour="effects">
  <div class="section-title">
    <Icon name="waves" size={16} /> {t('Effects')}
    <span class="grow"></span>
    <button class="icon-btn" class:active={!prefs.effectsGrid} title={t('List')} onclick={() => setGrid(false)}><Icon name="list" size={15} /></button>
    <button class="icon-btn" class:active={prefs.effectsGrid} title={t('Grid')} onclick={() => setGrid(true)}><Icon name="grid" size={15} /></button>
  </div>
  <div class="controls">
    <button class="icon-btn play" title="{t('Play')} (Ctrl+E)" disabled={!player.effect} onclick={toggleEffect}>
      <Icon name={player.effectPlaying ? 'pause' : 'play'} size={16} />
    </button>
    <VolumeControl volume={prefs.effectsVolume} {muted} onchange={(v) => { muted = false; setEffectsVolume(v); }} onmute={mute} />
  </div>
  {#if effects.list.length > 6}
    <input type="search" placeholder={t('Filter songs...')} bind:value={effects.search} />
  {/if}
  <div class="panel body" oncontextmenu={(e) => menu(e)} role="list">
    {#if !effects.directory}
      <div class="empty">
        <p class="muted">{t('No effects directory configured.')}</p>
        <button class="btn" onclick={chooseDirectory}><Icon name="folder" size={15} /> {t('Select Effects Directory')}</button>
      </div>
    {:else if !effects.list.length}
      <div class="empty muted">{effects.loading ? t('Loading…') : t('No MP3 files found.')}</div>
    {/if}
    <div class:grid={prefs.effectsGrid} class:list={!prefs.effectsGrid}>
      {#each list as effect (effect.id)}
        <div class="effect" class:playing={isPlaying(effect)} role="listitem" title={effect.path}
             ondblclick={() => playEffect(effect, isPlaying(effect) ? player.effectIntensity : 0)}
             oncontextmenu={(e) => menu(e, effect)}>
          <button class="hit" aria-label={label(effect)} onclick={() => playEffect(effect, isPlaying(effect) ? player.effectIntensity : 0)}>
            {#if effect.cover_url}<img src={effect.cover_url} alt="" loading="lazy" />{:else}<div class="noimg"><Icon name="waves" size={22} /></div>{/if}
            <span class="label ellipsis">{label(effect)}</span>
            {#if isPlaying(effect)}<span class="eq"><i></i><i></i><i></i></span>{/if}
          </button>
          {#if effect.intensities[0]?.light?.color}
            <span class="bulb" style:color={effect.intensities[0].light.color}><Icon name="bulb" size={14} filled /></span>
          {/if}
          {#if effect.intensities.length > 1}
            <div class="intensities">
              {#each effect.intensities as _, i (i)}
                <button class="lvl" class:on={isPlaying(effect) && player.effectIntensity === i}
                        onclick={(e) => { e.stopPropagation(); if (isPlaying(effect)) setEffectIntensity(i); else playEffect(effect, i); }}>{i + 1}</button>
              {/each}
            </div>
          {/if}
        </div>
      {/each}
    </div>
  </div>
</section>

<style>
  .effects { display: flex; flex-direction: column; gap: 6px; flex: 1; min-height: 160px; }
  .grow { flex: 1; }
  .controls { display: flex; align-items: center; gap: 8px; }
  .play { border: 1px solid var(--border); border-radius: 50%; width: 32px; height: 32px; color: var(--text); }
  .body { flex: 1; overflow: auto; padding: 6px; }
  .empty { padding: 20px 10px; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 8px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: 6px; }
  .list { display: flex; flex-direction: column; gap: 2px; }
  .effect { position: relative; border-radius: var(--radius-sm); overflow: hidden; }
  .hit { display: flex; width: 100%; text-align: left; position: relative; }
  .grid .hit { flex-direction: column; aspect-ratio: 4 / 3; background: var(--surface-3); }
  .grid img, .grid .noimg { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
  .grid .noimg { display: grid; place-items: center; color: var(--muted); }
  .grid .label { position: absolute; left: 0; right: 0; bottom: 0; padding: 16px 8px 5px; color: white; font-weight: 600; font-size: var(--fs-sm); background: linear-gradient(transparent, rgba(0,0,0,.75)); }
  .list .hit { align-items: center; gap: 8px; padding: 4px 6px; border-radius: var(--radius-sm); }
  .list .hit:hover { background: var(--hover); }
  .list img, .list .noimg { width: 28px; height: 28px; border-radius: 5px; object-fit: cover; flex: none; display: grid; place-items: center; color: var(--muted); }
  .list .label { flex: 1; }
  .effect.playing { box-shadow: 0 0 0 2px var(--accent); }
  .list .effect.playing { box-shadow: none; background: var(--accent-soft); }
  .bulb { position: absolute; top: 5px; right: 6px; filter: drop-shadow(0 0 2px rgba(0,0,0,.6)); }
  .list .bulb { top: 9px; right: 60px; }
  .intensities { position: absolute; top: 4px; left: 4px; display: flex; gap: 3px; }
  .list .intensities { position: absolute; top: 6px; left: auto; right: 6px; }
  .lvl { width: 18px; height: 18px; border-radius: 4px; font-size: 10px; font-weight: 700; background: rgba(0,0,0,.45); color: white; border: 1px solid rgba(255,255,255,.4); }
  .lvl.on { background: var(--accent); border-color: var(--accent); }
  .eq { position: absolute; top: 6px; right: 26px; display: flex; gap: 2px; align-items: flex-end; height: 12px; }
  .list .eq { position: static; }
  .eq i { width: 3px; background: var(--accent); animation: eq 0.8s ease-in-out infinite alternate; }
  .eq i:nth-child(2) { animation-delay: 0.2s; }
  .eq i:nth-child(3) { animation-delay: 0.4s; }
  @keyframes eq { from { height: 3px; } to { height: 12px; } }
</style>
