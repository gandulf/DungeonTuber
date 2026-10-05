<script lang="ts">
  import { coverUrl } from '../../lib/api';
  import { t } from '../../lib/i18n.svelte';
  import { prefs, savePrefs } from '../../lib/prefs.svelte';
  import { cycleRepeat, next, player, previous, setNormalize, togglePlay } from '../../lib/stores/player.svelte';
  import { visibleRows } from '../../lib/stores/library.svelte';
  import { openMenu } from '../../lib/stores/ui.svelte';
  import Icon from '../Icon.svelte';
  import SeekBar from './SeekBar.svelte';
  import VolumeControl from './VolumeControl.svelte';

  const canPlay = $derived(!!player.track || visibleRows().length > 0);

  function optionsMenu(event: MouseEvent) {
    openMenu(event, [
      { label: t('Crossfade'), checked: prefs.crossfade, action: () => { prefs.crossfade = !prefs.crossfade; savePrefs(); } },
      { label: t('Normalize Volume'), checked: prefs.normalize, action: () => setNormalize(!prefs.normalize) },
    ]);
  }
</script>

<footer class="player">
  <div class="now">
    {#if player.track?.has_cover}
      <img src={coverUrl(player.track.id, 128)} alt="" />
    {:else}
      <div class="placeholder"><Icon name="music" size={22} /></div>
    {/if}
    <div class="meta">
      {#if player.track}
        <span class="title ellipsis" title={player.track.path}>{player.track.title || player.track.name}</span>
        <span class="sub ellipsis">{player.error ?? (player.track.artist || player.track.summary || player.track.file)}</span>
      {:else}
        <span class="title muted">{t('No Track Selected')}</span>
      {/if}
    </div>
  </div>

  <div class="center">
    <div class="controls">
      <button class="icon-btn" title="{t('Previous')} (Ctrl+B)" onclick={previous} disabled={!canPlay}><Icon name="prev" size={18} /></button>
      <button class="play" title="{t('Play')} (Ctrl+P)" onclick={togglePlay} disabled={!canPlay}>
        <Icon name={player.playing ? 'pause' : 'play'} size={20} />
      </button>
      <button class="icon-btn" title="{t('Next')} (Ctrl+N)" onclick={() => next()} disabled={!canPlay}><Icon name="next" size={18} /></button>
      <button class="icon-btn" class:active={prefs.repeat !== 'none'} title="{t('Repeat')}: {prefs.repeat} (Ctrl+R)" onclick={cycleRepeat}>
        <Icon name={prefs.repeat === 'single' ? 'repeat-one' : 'repeat'} size={17} />
      </button>
    </div>
    <SeekBar />
  </div>

  <div class="right">
    <VolumeControl />
    <button class="icon-btn" title={t('Settings')} onclick={optionsMenu}><Icon name="more" size={18} /></button>
  </div>
</footer>

<style>
  .player { display: grid; grid-template-columns: minmax(180px, 1fr) minmax(320px, 2.2fr) minmax(180px, 1fr); align-items: center; gap: 18px; padding: 10px 16px; background: var(--surface); border-top: 1px solid var(--border); }
  .now { display: flex; align-items: center; gap: 12px; min-width: 0; }
  .now img, .placeholder { width: 48px; height: 48px; border-radius: 8px; object-fit: cover; flex: none; }
  .placeholder { display: grid; place-items: center; background: var(--surface-3); color: var(--muted); }
  .meta { display: flex; flex-direction: column; min-width: 0; }
  .title { font-weight: 600; }
  .sub { font-size: var(--fs-sm); color: var(--muted); }
  .center { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
  .controls { display: flex; align-items: center; justify-content: center; gap: 10px; }
  .play { width: 40px; height: 40px; border-radius: 50%; background: var(--accent); color: var(--accent-text); display: grid; place-items: center; box-shadow: 0 2px 8px color-mix(in srgb, var(--accent) 40%, transparent); }
  .play:hover:not(:disabled) { filter: brightness(1.08); }
  .right { display: flex; align-items: center; justify-content: flex-end; gap: 6px; }
  @media (max-width: 760px) {
    .player { grid-template-columns: 1fr; gap: 8px; }
    .right { justify-content: center; }
  }
</style>
