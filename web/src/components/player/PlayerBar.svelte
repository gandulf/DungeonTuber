<script lang="ts">
  import { coverUrl } from '../../lib/api';
  import { toggleFavorite } from '../../lib/actions';
  import { t } from '../../lib/i18n.svelte';
  import { prefs, savePrefs } from '../../lib/prefs.svelte';
  import { visibleRows } from '../../lib/stores/library.svelte';
  import { cycleRepeat, next, player, previous, setNormalize, toggleEffect, togglePlay, toggleShuffle } from '../../lib/stores/player.svelte';
  import { openMenu, ui } from '../../lib/stores/ui.svelte';
  import Icon from '../Icon.svelte';
  import EffectMini from './EffectMini.svelte';
  import SeekBar from './SeekBar.svelte';
  import VolumeControl from './VolumeControl.svelte';

  const canPlay = $derived(!!player.track || visibleRows().length > 0);

  // a playing effect gets its controls here while the effects panel (right side bar, on tablets its flyout) is hidden: on a desktop
  // in the right column, on a tablet as one line above the volume (the columns are narrow there); phones have no room for it
  const effectsShown = $derived(prefs.showEffects && (ui.rightOverlay ? ui.mobilePanel === 'side' : prefs.rightOpen));
  const effectHere = $derived(player.effectPlaying && !!player.effect && !effectsShown && !ui.narrow);
  // phones only get a sign that an effect plays (its name as the tooltip) and a stop button
  const effectSign = $derived(player.effectPlaying && !!player.effect && !effectsShown && ui.narrow);

  function optionsMenu(event: MouseEvent) {
    openMenu(event, [
      { label: t('Crossfade'), checked: prefs.crossfade, action: () => { prefs.crossfade = !prefs.crossfade; savePrefs(); } },
      { label: t('Normalize Volume'), checked: prefs.normalize, action: () => setNormalize(!prefs.normalize) },
    ]);
  }
</script>

<footer class="player" data-tour="player">
  <div class="now">
    <div class="art" class:vibrate={player.playing}>
      {#if player.track?.has_cover}
        <img src={coverUrl(player.track.id, 256)} alt="" />
      {:else}
        <Icon name="music" size={24} />
      {/if}
    </div>
    <div class="meta">
      {#if player.track}
        <span class="title ellipsis" title={player.track.path}>{player.track.title || player.track.name}</span>
        <span class="sub ellipsis">{player.error ?? (player.track.artist || player.track.album || player.track.file)}</span>
        {#if player.track.tags.length}
          <div class="tags">{#each player.track.tags.slice(0, 3) as tag, i (tag)}<span class="pill {i === 1 ? 'gold' : i === 2 ? 'violet' : ''}">{tag}</span>{/each}</div>
        {/if}
      {:else}
        <span class="title muted">{t('No Track Selected')}</span>
        <span class="sub">{ui.coarse ? t('Tap a song to start') : t('Double-click a song to start')}</span>
      {/if}
    </div>
    {#if player.track}
      <button class="icon-btn heart" class:on={player.track.favorite} title={t('Favorite')} onclick={() => player.track && toggleFavorite(player.track)}>
        <Icon name="heart" size={20} filled={player.track.favorite} />
      </button>
    {/if}
  </div>

  <!-- phones have no room for the cover and the details: the title of the song on a line of its own -->
  {#if ui.narrow && player.track}<div class="now-mini ellipsis" title={player.track.path}>{player.track.title || player.track.name}</div>{/if}
  <div class="center">
    <div class="controls">
      <button class="icon-btn" class:active={prefs.shuffle} title={t('Shuffle')} onclick={toggleShuffle}><Icon name="shuffle" size={18} /></button>
      <button class="icon-btn big" title="{t('Previous')} (Ctrl+B)" onclick={previous} disabled={!canPlay}><Icon name="prev" size={20} /></button>
      <button class="play" title="{t('Play')} (Ctrl+P)" onclick={togglePlay} disabled={!canPlay}>
        <Icon name={player.playing ? 'pause' : 'play'} size={22} />
      </button>
      <button class="icon-btn big" title="{t('Next')} (Ctrl+N)" onclick={() => next()} disabled={!canPlay}><Icon name="next" size={20} /></button>
      <button class="icon-btn" class:active={prefs.repeat !== 'none'} title="{t('Repeat')}: {prefs.repeat} (Ctrl+R)" onclick={cycleRepeat}>
        <Icon name={prefs.repeat === 'single' ? 'repeat-one' : 'repeat'} size={18} />
      </button>
    </div>
    <SeekBar />
  </div>

  <div class="right" class:stacked={effectHere && ui.rightOverlay}>
    {#if effectHere && ui.rightOverlay}<EffectMini inline />{/if}
    <VolumeControl />
    <button class="icon-btn" title={t('Settings')} onclick={optionsMenu}><Icon name="queue" size={19} /></button>
    {#if effectHere && !ui.rightOverlay}<EffectMini />{/if}
    {#if effectSign}
      <div class="fx-sign" role="group" aria-label={t('Effects')} title={player.effect?.title || player.effect?.name}>
        <span class="glyph"><Icon name="waves" size={15} /></span>
        <button class="icon-btn fx-stop" title={t('Stop the effect')} aria-label={t('Stop the effect')} onclick={toggleEffect}><Icon name="stop" size={14} /></button>
      </div>
    {/if}
  </div>
</footer>

<style>
  .player {
    display: grid; grid-template-columns: minmax(220px, 1fr) minmax(340px, 1.6fr) minmax(220px, 1fr); align-items: center; gap: 24px;
    padding: 12px 22px; position: relative;
    background: linear-gradient(180deg, color-mix(in srgb, var(--bg-2) 70%, transparent), var(--bg-2));
    border-top: 1px solid var(--border);
    backdrop-filter: blur(14px);
  }
  .player::before { content: ''; position: absolute; left: 0; right: 0; top: -1px; height: 1px; background: linear-gradient(90deg, transparent, rgba(var(--ambient), 0.7), transparent); }
  .now { display: flex; align-items: center; gap: 14px; min-width: 0; }
  .art { width: 66px; height: 66px; border-radius: 12px; overflow: hidden; flex: none; display: grid; place-items: center; background: var(--surface-3); color: var(--faint); box-shadow: 0 6px 24px rgba(var(--ambient), 0.35); transition: box-shadow 1s; }
  .art.vibrate { animation: vibrate 0.9s ease-in-out infinite; }
  @keyframes vibrate {
    0%, 100% { transform: translate(0, 0) rotate(0); }
    20% { transform: translate(0.6px, -0.4px) rotate(0.4deg); }
    40% { transform: translate(-0.5px, 0.5px) rotate(-0.4deg); }
    60% { transform: translate(0.5px, 0.3px) rotate(0.3deg); }
    80% { transform: translate(-0.6px, -0.3px) rotate(-0.3deg); }
  }
  @media (prefers-reduced-motion: reduce) { .art.vibrate { animation: none; } }
  .art img { width: 100%; height: 100%; object-fit: cover; }
  .meta { display: flex; flex-direction: column; min-width: 0; gap: 2px; }
  .title { font-family: var(--font-display); font-weight: 650; font-size: var(--fs-lg); }
  .sub { font-size: var(--fs-sm); color: var(--muted); }
  .tags { display: flex; gap: 5px; margin-top: 4px; }
  .heart { color: var(--faint); margin-left: 4px; }
  .heart.on { color: var(--rose); filter: drop-shadow(0 0 8px var(--rose-soft)); }
  .center { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
  .controls { display: flex; align-items: center; justify-content: center; gap: 14px; }
  .big { width: 36px; height: 36px; color: var(--text); }
  .play {
    width: 48px; height: 48px; border-radius: 50%; display: grid; place-items: center; color: #fff;
    background: linear-gradient(135deg, var(--accent), var(--accent-2));
    box-shadow: 0 0 0 6px var(--accent-soft), 0 6px 22px var(--accent-glow);
    transition: transform 0.15s, filter 0.15s;
  }
  @media (hover: hover) { .play:hover:not(:disabled) { transform: scale(1.05); filter: brightness(1.08); } }
  .right { display: flex; align-items: center; justify-content: flex-end; gap: 8px; }
  /* with the effect player the right column takes the room it needs and the main volume gets shorter */
  .player:has(.right:not(.stacked) :global(.effect)) { grid-template-columns: minmax(200px, 1fr) minmax(300px, 1.6fr) auto; }
  .right:not(.stacked):has(:global(.effect)) :global(.volume input) { width: 80px; }
  .right:not(.stacked):has(:global(.effect)) :global(.volume .pct) { display: none; }
  /* tablets: the effect on a line of its own above the volume */
  .right.stacked { flex-wrap: wrap; row-gap: 4px; }
  .right.stacked :global(.effect) { flex: 1 0 100%; min-width: 0; }
  .fx-sign { display: flex; align-items: center; gap: 2px; margin-left: auto; padding: 0 2px 0 9px; border-radius: 999px; background: var(--accent-soft); border: 1px solid var(--border); }
  .fx-sign .glyph { display: flex; color: var(--accent); animation: wave 1.6s ease-in-out infinite; }
  @keyframes wave { 50% { transform: translateY(-2px); opacity: 0.7; } }
  @media (prefers-reduced-motion: reduce) { .fx-sign .glyph { animation: none; } }
  .fx-stop { width: 30px; height: 30px; color: var(--accent); }
  .now-mini { text-align: center; font-weight: 650; font-size: var(--fs-sm); margin-bottom: -4px; min-width: 0; }
  @media (max-width: 900px) {
    .player { grid-template-columns: minmax(0, 1fr); gap: 10px; padding: 10px 14px; }
    .now { display: none; }
    .right { justify-content: center; }
  }
</style>
