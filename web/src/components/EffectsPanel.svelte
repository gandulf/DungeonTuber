<script lang="ts">
  import { analyze, editSong } from '../lib/actions';
  import { t } from '../lib/i18n.svelte';
  import { prefs, savePrefs } from '../lib/prefs.svelte';
  import { data, saveSettings } from '../lib/stores/data.svelte';
  import { effects, loadEffects } from '../lib/stores/effects.svelte';
  import { player, playEffect, setEffectIntensity, setEffectsVolume, toggleEffect } from '../lib/stores/player.svelte';
  import { openDialog, openMenu } from '../lib/stores/ui.svelte';
  import type { Effect } from '../lib/types';
  import SelectFolderDialog from './dialogs/SelectFolderDialog.svelte';
  import Icon from './Icon.svelte';
  import VolumeControl from './player/VolumeControl.svelte';

  let muted = $state(false);
  let lastVolume = prefs.effectsVolume;

  const list = $derived(effects.list.filter((e) => !effects.search || label(e).toLowerCase().includes(effects.search.toLowerCase())));
  const playingEffect = $derived(player.effectPlaying ? player.effect : null);

  function label(effect: Effect) {
    return prefs.effectsTitle && effect.title ? effect.title : effect.name;
  }

  function isPlaying(effect: Effect) {
    return player.effectPlaying && player.effect?.id === effect.id;
  }

  const admin = data.auth?.is_admin !== false;

  function chooseDirectory() {
    openDialog(SelectFolderDialog, {
      title: t('Select Effects Directory'),
      directory: effects.directory ?? '',
      onselect: async (dir: string) => {
        await saveSettings({ effectsDirectory: dir });
        await loadEffects();
      },
    });
  }

  function menu(event: MouseEvent, effect?: Effect) {
    const variant = effect ? effect.intensities[isPlaying(effect) ? player.effectIntensity : 0] : null;
    openMenu(event, [
      ...(effect && variant ? [
        { label: t('Play'), icon: 'play', action: () => playEffect(effect, 0) },
        { label: t('Edit Song…'), icon: 'edit', action: () => editSong(variant) },
        ...(data.settings?.voxalyzerActive !== false ? [{ label: t('Analyze'), icon: 'sparkles', action: () => analyze([variant.path]) }] : []),
        { separator: true },
      ] : []),
      ...(admin ? [{ label: t('Select Effects Directory'), icon: 'folder', action: chooseDirectory }] : []),
      { label: t('Refresh'), icon: 'refresh', action: loadEffects },
      { label: t('Use mp3 title instead of file name'), checked: prefs.effectsTitle, action: () => { prefs.effectsTitle = !prefs.effectsTitle; savePrefs(); } },
    ]);
  }

  /** Typing while the panel has the focus filters the effects (like the song table); the filter is shown as a small overlay. */
  function onKeydown(event: KeyboardEvent) {
    const target = event.target as HTMLElement;
    if (target.closest('input, textarea, select') || event.ctrlKey || event.metaKey || event.altKey) return;
    if (event.key === 'Escape' && effects.search) effects.search = '';
    else if (event.key === 'Backspace' && effects.search) effects.search = effects.search.slice(0, -1);
    else if (event.key.length === 1 && /[\p{L}\p{N} _\-]/u.test(event.key) && (event.key !== ' ' || effects.search)) effects.search += event.key;
    else return;
    event.preventDefault();
  }

  /** A space of the search must not click the focused effect when the key is released. */
  function onKeyup(event: KeyboardEvent) {
    if (event.key === ' ' && effects.search) event.preventDefault();
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

<!-- svelte-ignore a11y_no_noninteractive_tabindex, a11y_no_noninteractive_element_interactions -->
<section class="card soundscapes" data-tour="effects" role="group" tabindex="0" onkeydown={onKeydown} onkeyup={onKeyup} oncontextmenu={(e) => menu(e)} aria-label={t('Effects')}>
  <div class="head">
    <span class="glyph"><Icon name="waves" size={17} /></span>
    <h3 class="card-title">{t('Soundscapes')}</h3>
    <span class="grow"></span>
    <div class="seg mini">
      <button class:on={prefs.effectsGrid} title={t('Grid')} onclick={() => setGrid(true)}><Icon name="grid" size={13} /></button>
      <button class:on={!prefs.effectsGrid} title={t('List')} onclick={() => setGrid(false)}><Icon name="list" size={13} /></button>
    </div>
  </div>

  <div class="controls">
    <button class="playfx" class:on={player.effectPlaying} title="{t('Play')} (Ctrl+E)" disabled={!player.effect} onclick={toggleEffect}>
      <Icon name={player.effectPlaying ? 'pause' : 'play'} size={15} />
    </button>
    <div class="now-fx">
      <span class="label-xs">{t('Now looping')}</span>
      <span class="ellipsis">{playingEffect ? label(playingEffect) : t('Nothing')}</span>
    </div>
  </div>
  <VolumeControl compact volume={prefs.effectsVolume} {muted} onchange={(v) => { muted = false; setEffectsVolume(v); }} onmute={mute} />

  {#if effects.search}
    <div class="search-pill" class:none={!list.length}><Icon name="search" size={13} /> {effects.search}</div>
  {/if}

  {#if !effects.directory}
    <div class="empty">
      <p class="muted">{t('No effects directory configured.')}</p>
      {#if admin}
        <button class="btn sm" onclick={chooseDirectory}><Icon name="folder" size={14} /> {t('Select Effects Directory')}</button>
      {:else}
        <p class="muted small">{t('An administrator has to select the effects directory.')}</p>
      {/if}
    </div>
  {:else if !effects.list.length}
    <div class="empty muted">{effects.loading ? t('Loading…') : t('No MP3 files found.')}</div>
  {/if}

  <div class:grid={prefs.effectsGrid} class:list={!prefs.effectsGrid}>
    {#each list as effect (effect.id)}
      <div class="effect" class:playing={isPlaying(effect)} role="listitem" title={effect.path} oncontextmenu={(e) => { e.stopPropagation(); menu(e, effect); }}>
        <button class="hit" aria-label={label(effect)} onclick={() => playEffect(effect, isPlaying(effect) ? player.effectIntensity : 0)}>
          <span class="art">
            {#if effect.cover_url}<img src={effect.cover_url} alt="" loading="lazy" />{:else}<Icon name="waves" size={22} />{/if}
            {#if isPlaying(effect)}<span class="eq"><i></i><i></i><i></i></span>{/if}
          </span>
          <span class="label ellipsis">{label(effect)}</span>
        </button>
        {#if effect.intensities[0]?.light?.color}
          <span class="bulb" style:color={effect.intensities[0].light.color}><Icon name="bulb" size={13} filled /></span>
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
</section>

<style>
  .soundscapes { position: relative; padding: 16px; display: flex; flex-direction: column; gap: 12px; outline: none; }
  .search-pill { position: absolute; top: 12px; right: 12px; z-index: 2; padding: 4px 10px; border-radius: 10px; background: var(--surface); border: 1px solid var(--accent); box-shadow: var(--shadow); display: flex; align-items: center; gap: 6px; font-size: var(--fs-sm); }
  .search-pill.none { border-color: var(--red); }
  .head { display: flex; align-items: center; gap: 9px; }
  .glyph { width: 30px; height: 30px; border-radius: 9px; display: grid; place-items: center; background: var(--accent-soft); color: var(--accent); }
  .grow { flex: 1; }
  .seg.mini button { padding: 4px 8px; display: flex; }
  .controls { display: flex; align-items: center; gap: 12px; }
  .playfx { width: 38px; height: 38px; border-radius: 50%; display: grid; place-items: center; border: 1px solid var(--border-strong); background: var(--surface-2); color: var(--text); flex: none; }
  .playfx.on { background: linear-gradient(135deg, var(--accent), var(--accent-2)); color: #fff; border-color: transparent; box-shadow: 0 0 16px var(--accent-glow); }
  .now-fx { display: flex; flex-direction: column; min-width: 0; gap: 2px; }
  .empty { padding: 12px 6px; text-align: center; display: flex; flex-direction: column; align-items: center; gap: 8px; }
  .empty p { margin: 0; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(92px, 1fr)); gap: 10px; }
  .list { display: flex; flex-direction: column; gap: 2px; }
  .effect { position: relative; }
  .hit { display: flex; width: 100%; text-align: left; }
  .grid .hit { flex-direction: column; gap: 6px; align-items: center; }
  .art { position: relative; display: grid; place-items: center; overflow: hidden; background: var(--surface-3); color: var(--faint); }
  .grid .art { width: 100%; aspect-ratio: 1; border-radius: 12px; border: 2px solid transparent; transition: border-color 0.15s, box-shadow 0.15s, transform 0.15s; }
  .grid .hit:hover .art { transform: translateY(-2px); }
  .art img { width: 100%; height: 100%; object-fit: cover; }
  .grid .label { font-size: var(--fs-sm); color: var(--muted); max-width: 100%; }
  .effect.playing .art { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-soft), 0 6px 20px var(--accent-glow); }
  .effect.playing .label { color: var(--accent); font-weight: 600; }
  .list .hit { align-items: center; gap: 10px; padding: 5px 6px; border-radius: 9px; }
  .list .hit:hover { background: var(--hover); }
  .list .art { width: 34px; height: 34px; border-radius: 8px; flex: none; }
  .list .label { flex: 1; }
  .list .effect.playing .hit { background: var(--accent-soft); }
  .bulb { position: absolute; top: 6px; right: 6px; filter: drop-shadow(0 0 3px rgba(0,0,0,.8)); }
  .list .bulb { top: 12px; right: 62px; }
  .intensities { position: absolute; top: 5px; left: 5px; display: flex; gap: 3px; }
  .list .intensities { left: auto; right: 6px; top: 10px; }
  .lvl { width: 19px; height: 19px; border-radius: 5px; font-size: 10px; font-weight: 700; background: rgba(10, 8, 20, 0.6); color: #fff; border: 1px solid rgba(255,255,255,.3); backdrop-filter: blur(4px); }
  .lvl.on { background: var(--accent); border-color: var(--accent); }
  .eq { position: absolute; bottom: 6px; right: 6px; display: flex; gap: 2px; align-items: flex-end; height: 14px; padding: 2px 3px; border-radius: 4px; background: rgba(10, 8, 20, 0.55); }
  .eq i { width: 3px; background: #fff; animation: eq 0.8s ease-in-out infinite alternate; }
  .eq i:nth-child(2) { animation-delay: 0.2s; }
  .eq i:nth-child(3) { animation-delay: 0.4s; }
  @keyframes eq { from { height: 3px; } to { height: 10px; } }
</style>
