<script lang="ts">
  import { t } from '../../lib/i18n.svelte';
  import { prefs } from '../../lib/prefs.svelte';
  import { player, setEffectsVolume, toggleEffect } from '../../lib/stores/player.svelte';
  import Icon from '../Icon.svelte';

  /** The playing effect in the player bar while the effects panel is hidden: its name, stop and the effects volume (a compact
   *  slider of its own: the box is narrow). */
  let muted = $state(false);
  let lastVolume = prefs.effectsVolume;

  function mute() {
    if (muted) setEffectsVolume(lastVolume);
    else {
      lastVolume = prefs.effectsVolume;
      setEffectsVolume(0);
    }
    muted = !muted;
  }

  const name = $derived(player.effect ? player.effect.title || player.effect.name : '');
  const shown = $derived(muted ? 0 : prefs.effectsVolume);
</script>

<!-- the effect's name on top, its controls below: two short rows instead of one long one -->
<div class="effect" role="group" aria-label={t('Effects')}>
  <div class="head">
    <span class="glyph" title={prefs.effectsLoop ? t('Now looping') : t('Play once')}><Icon name="waves" size={13} /></span>
    <span class="name ellipsis" title={name}>{name}</span>
  </div>
  <div class="controls">
    <button class="icon-btn stop" title="{t('Stop the effect')} (Ctrl+E)" aria-label={t('Stop the effect')} onclick={toggleEffect}><Icon name="stop" size={14} /></button>
    <button class="icon-btn mute" title={t('Mute')} aria-label={t('Mute')} onclick={mute}><Icon name={shown === 0 ? 'volume-x' : 'volume'} size={15} /></button>
    <input class="range" class:boost={shown > 100} type="range" min="0" max="150" step="1" value={shown} aria-label={t('Volume')} title="{shown}%"
           style:--pct="{(shown / 150) * 100}%" oninput={(e) => { muted = false; setEffectsVolume(Number(e.currentTarget.value)); }} />
  </div>
</div>

<style>
  .effect { display: flex; flex-direction: column; gap: 1px; flex: none; width: 168px; padding: 4px 8px 2px; margin-left: 6px; border-radius: 12px;
            background: var(--accent-soft); border: 1px solid var(--border); box-sizing: border-box; }
  .head { display: flex; align-items: center; gap: 5px; min-width: 0; padding-left: 2px; }
  .controls { display: flex; align-items: center; gap: 2px; }
  .glyph { display: flex; flex: none; color: var(--accent); animation: wave 1.6s ease-in-out infinite; }
  @keyframes wave { 50% { transform: translateY(-2px); opacity: 0.7; } }
  @media (prefers-reduced-motion: reduce) { .glyph { animation: none; } }
  .name { min-width: 0; font-size: var(--fs-xs); font-weight: 600; }
  .stop, .mute { flex: none; width: 26px; height: 26px; }
  .stop { color: var(--accent); }
  .range { flex: 1; min-width: 0; margin: 0 2px 0 4px; }
  .range.boost { background: linear-gradient(to right, var(--accent) 0, var(--accent-2) 66.6%, var(--gold) 66.6%, var(--gold) var(--pct), var(--track) var(--pct)); }
</style>
