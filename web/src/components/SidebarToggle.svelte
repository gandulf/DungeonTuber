<script lang="ts">
  import { onDestroy } from 'svelte';
  import { t } from '../lib/i18n.svelte';
  import { prefs, savePrefs } from '../lib/prefs.svelte';
  import { ui } from '../lib/stores/ui.svelte';
  import Icon from './Icon.svelte';

  /** The button that opens and closes a side panel on a wide screen. With the panel open it sits on the panel's border (and follows it
   *  when the panel is resized); with the panel closed it slides in from the screen edge once the pointer has stayed near that edge for
   *  a moment (touch screens have no pointer to wait for: there it stays visible at the edge). The caret points where the panel goes. */
  let { side }: { side: 'left' | 'right' } = $props();

  const EDGE = 14; // px from the screen edge where the pointer wakes the button
  const LEAVE = 90; // px from the edge where it hides again
  const DWELL = 350; // ms the pointer has to stay at the edge
  const SLIDE = 240; // ms of the panel animation (Shell.svelte), followed by the button

  const key = $derived(side === 'left' ? 'leftOpen' : 'rightOpen');
  const open = $derived(prefs[key]);
  // the middle of the border: the left panel ends at its width, the right one has the splitter (10 px) in front of it
  const offset = $derived(open ? (side === 'left' ? prefs.leftWidth : prefs.rightWidth + 5) : 0);

  let near = $state(false);
  let moving = $state(false); // the button glides only while the panel opens or closes, not while the splitter is dragged
  let dwell: ReturnType<typeof setTimeout> | null = null;
  let glide: ReturnType<typeof setTimeout> | null = null;

  function onPointerMove(event: PointerEvent) {
    if (open || event.pointerType !== 'mouse') return;
    const distance = side === 'left' ? event.clientX : window.innerWidth - event.clientX;
    if (distance <= EDGE) {
      dwell ??= setTimeout(() => (near = true), DWELL);
    } else {
      if (dwell) clearTimeout(dwell);
      dwell = null;
      if (distance > LEAVE) near = false;
    }
  }

  function toggle() {
    prefs[key] = !open;
    savePrefs();
    near = false;
    moving = true;
    if (glide) clearTimeout(glide);
    glide = setTimeout(() => (moving = false), SLIDE + 40);
  }

  onDestroy(() => {
    if (dwell) clearTimeout(dwell);
    if (glide) clearTimeout(glide);
  });

  const label = $derived(side === 'left' ? (open ? t('Hide the library') : t('Show the library')) : open ? t('Hide effects and lights') : t('Show effects and lights'));
  // the caret points to where the panel moves: away into its edge when it is open, out of it when it is closed
  const pointsLeft = $derived(side === 'left' ? open : !open);
</script>

<svelte:window onpointermove={onPointerMove} onblur={() => (near = false)} />

<button type="button" class="toggle {side}" class:open class:shown={open || near || ui.coarse} class:moving title={label} aria-label={label} aria-pressed={open}
        style:--offset="{offset}px" onclick={toggle}>
  <span class="caret" class:flip={!pointsLeft}><Icon name="chevron-left" size={15} /></span>
</button>

<style>
  .toggle {
    position: absolute; top: 50%; z-index: 20; display: grid; place-items: center; width: 22px; height: 44px; padding: 0;
    border-radius: 999px; border: 1px solid var(--border-strong, var(--border)); background: var(--bg-2); color: var(--muted); box-shadow: var(--shadow);
    cursor: pointer; opacity: 0; pointer-events: none;
    transition: opacity 0.2s ease, transform 0.2s ease, color 0.15s, background 0.15s, border-color 0.15s;
  }
  /* open: centred on the panel's border; closed: half a button inside the screen edge */
  .toggle.left { left: var(--offset); transform: translate(-50%, -50%); }
  .toggle.right { right: var(--offset); transform: translate(50%, -50%); }
  .toggle.left:not(.open) { transform: translate(-100%, -50%); }
  .toggle.right:not(.open) { transform: translate(100%, -50%); }
  .toggle.left:not(.open).shown { transform: translate(2px, -50%); border-radius: 0 999px 999px 0; }
  .toggle.right:not(.open).shown { transform: translate(-2px, -50%); border-radius: 999px 0 0 999px; }
  .toggle.shown { opacity: 1; pointer-events: auto; }
  /* the open toggle stays quiet until the pointer comes near it */
  .toggle.open { opacity: 0.55; }
  .toggle:hover, .toggle:focus-visible { opacity: 1; color: var(--accent); border-color: var(--accent); background: var(--surface, var(--bg-2)); }
  .toggle.moving { transition: left 0.24s cubic-bezier(0.33, 1, 0.68, 1), right 0.24s cubic-bezier(0.33, 1, 0.68, 1), opacity 0.2s ease, transform 0.2s ease; }
  .caret { display: flex; transition: transform 0.24s ease; }
  .caret.flip { transform: rotate(180deg); }
  @media (prefers-reduced-motion: reduce) {
    .toggle, .toggle.moving, .caret { transition: none; }
  }
</style>
