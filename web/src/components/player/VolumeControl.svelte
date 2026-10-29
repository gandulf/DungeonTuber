<script lang="ts">
  import { t } from '../../lib/i18n.svelte';
  import { prefs } from '../../lib/prefs.svelte';
  import { setVolume, toggleMute } from '../../lib/stores/player.svelte';
  import Icon from '../Icon.svelte';

  /** `popup`: only a button; a tap opens a vertical volume bar above it (phones, where the slider takes too much room of the player). */
  let { volume = undefined, onchange = undefined, onmute = undefined, muted = undefined, compact = false, popup = false, short = false }: {
    volume?: number; onchange?: (v: number) => void; onmute?: () => void; muted?: boolean; compact?: boolean; popup?: boolean;
    /** A shorter slider without the percentage (the player bar next to the effect player). */
    short?: boolean;
  } = $props();

  let open = $state(false);
  let host = $state<HTMLElement | null>(null);

  // Holding the button opens the bar, and the same touch goes on sliding: moving the finger up raises the volume, down lowers it (from
  // where it was, so the volume does not jump). A short tap opens and closes the bar as a click does. After a slide the bar closes by
  // itself when nothing is touched for a moment.
  const HOLD_MS = 350;
  const SLOP = 10; // px a finger may move before the hold counts as a drag of the page, not a hold
  const AUTO_CLOSE_MS = 1500;
  let holdTimer: ReturnType<typeof setTimeout> | undefined;
  let closeTimer: ReturnType<typeof setTimeout> | undefined;
  let slide: { y: number; volume: number } | null = null;
  let swallowClick = false;
  let press: { x: number; y: number } | null = null;

  function pressStart(event: PointerEvent) {
    if (event.pointerType === 'mouse' && event.button !== 0) return;
    clearTimeout(closeTimer);
    press = { x: event.clientX, y: event.clientY };
    const [target, id, y, volume] = [event.currentTarget as HTMLElement, event.pointerId, event.clientY, shown];
    clearTimeout(holdTimer);
    holdTimer = setTimeout(() => {
      open = true;
      slide = { y, volume };
      swallowClick = true; // the click that ends this touch is not a tap
      try {
        target.setPointerCapture(id); // the finger may leave the button while it slides
      } catch {
        // the pointer is gone already
      }
      navigator.vibrate?.(10);
    }, HOLD_MS);
  }

  function pressMove(event: PointerEvent) {
    if (!slide) {
      // a finger that moves before the hold is done is not holding
      if (press && Math.hypot(event.clientX - press.x, event.clientY - press.y) > SLOP) clearTimeout(holdTimer);
      return;
    }
    const track = host?.querySelector('.upright')?.getBoundingClientRect();
    const length = Math.max(40, (track?.height ?? 150) - 18); // the thumb takes some of the bar at both ends
    const next = Math.round(Math.min(150, Math.max(0, slide.volume + ((slide.y - event.clientY) / length) * 150)));
    if (next !== shown) (onchange ?? setVolume)(next);
  }

  function pressEnd() {
    clearTimeout(holdTimer);
    press = null;
    if (slide) {
      slide = null;
      clearTimeout(closeTimer);
      closeTimer = setTimeout(() => (open = false), AUTO_CLOSE_MS);
      setTimeout(() => (swallowClick = false), 400); // in case no click follows the release
    }
  }

  function tap() {
    if (swallowClick) {
      swallowClick = false;
      return;
    }
    clearTimeout(closeTimer);
    open = !open;
  }

  /** A touch on the bar keeps it open. */
  const keepOpen = () => clearTimeout(closeTimer);

  /** A tap outside of the button and the bar closes it. */
  function outside(event: PointerEvent) {
    if (open && host && !host.contains(event.target as Node)) open = false;
  }

  const value = $derived(volume ?? prefs.volume);
  const isMuted = $derived(muted ?? prefs.muted);
  const shown = $derived(isMuted ? 0 : value);
</script>

<svelte:window onpointerdown={outside} onkeydown={(e) => e.key === 'Escape' && (open = false)} />

{#if popup}
  <div class="volume-pop" bind:this={host}>
    <button class="icon-btn hold" class:active={open} title={t('Volume')} aria-label={t('Volume')} aria-haspopup="true" aria-expanded={open}
            onpointerdown={pressStart} onpointermove={pressMove} onpointerup={pressEnd} onpointercancel={pressEnd} oncontextmenu={(e) => e.preventDefault()} onclick={tap}>
      <Icon name={isMuted || value === 0 ? 'volume-x' : 'volume'} size={18} />
    </button>
    {#if open}
      <div class="bar" role="group" aria-label={t('Volume')} onpointerdown={keepOpen}>
        <span class="pct">{shown}%</span>
        <!-- a horizontal slider turned upright: it keeps working with a finger and the keyboard -->
        <div class="upright">
          <input class="range" class:boost={value > 100} type="range" min="0" max="150" step="1" value={shown} aria-label={t('Volume')} aria-orientation="vertical"
                 style:--pct="{(shown / 150) * 100}%"
                 oninput={(e) => (onchange ?? setVolume)(Number((e.currentTarget as HTMLInputElement).value))} />
        </div>
        <button class="icon-btn" title={t('Mute')} aria-label={t('Mute')} aria-pressed={isMuted} onclick={() => (onmute ?? toggleMute)()}>
          <Icon name={isMuted || value === 0 ? 'volume-x' : 'volume'} size={16} />
        </button>
      </div>
    {/if}
  </div>
{:else}
  <div class="volume" class:compact class:short>
    <button class="icon-btn" title="{t('Mute')} (Ctrl+M)" onclick={() => (onmute ?? toggleMute)()}>
      <Icon name={isMuted || value === 0 ? 'volume-x' : 'volume'} size={18} />
    </button>
    <input class="range" class:boost={value > 100} type="range" min="0" max="150" step="1" value={shown} aria-label={t('Volume')}
           style:--pct="{(shown / 150) * 100}%"
           oninput={(e) => (onchange ?? setVolume)(Number((e.currentTarget as HTMLInputElement).value))} />
    {#if !short}<span class="pct">{shown}%</span>{/if}
  </div>
{/if}

<style>
  .volume { display: flex; align-items: center; gap: 8px; }
  input { width: 130px; }
  .compact input { width: auto; flex: 1; }
  .compact { flex: 1; }
  .short input { width: 80px; }
  input.boost { background: linear-gradient(to right, var(--accent) 0, var(--accent-2) 66.6%, var(--gold) 66.6%, var(--gold) var(--pct), var(--track) var(--pct)); }
  .volume-pop { position: relative; display: flex; }
  /* a held finger slides the volume: no scrolling, selecting or callout from the button */
  .hold { touch-action: none; user-select: none; -webkit-user-select: none; -webkit-touch-callout: none; }
  /* a slim bar like a regular slider: a thin track with the thumb, the percentage above and the mute button below, both small */
  .bar { position: absolute; bottom: calc(100% + 8px); left: 50%; transform: translateX(-50%); z-index: 20; display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 8px 4px;
         border-radius: 12px; background: var(--bg-2); border: 1px solid var(--border-strong, var(--border)); box-shadow: var(--shadow); }
  .bar .pct { width: auto; text-align: center; }
  .bar .icon-btn { width: 28px; height: 28px; min-width: 28px; min-height: 28px; }
  .upright { position: relative; width: 28px; height: 120px; }
  /* the track is 6px thick; the padding makes the touch target 28px wide, the thumb stays in the middle of the track */
  .upright input { position: absolute; left: 50%; top: 50%; box-sizing: content-box; width: 120px; height: 6px; padding: 11px 0; background-clip: content-box; transform: translate(-50%, -50%) rotate(-90deg); }
  .pct { font-size: var(--fs-xs); color: var(--muted); width: 36px; font-variant-numeric: tabular-nums; text-align: right; }
</style>
