<script lang="ts">
  import { t } from '../lib/i18n.svelte';
  import { prefs, savePrefs } from '../lib/prefs.svelte';
  import { ui } from '../lib/stores/ui.svelte';

  const allSteps = [
    { target: 'tree', text: 'Tour Directory Tree' },
    { target: 'russel', text: 'Tour Russel Widget' },
    { target: 'slider', text: 'Tour Category Slider' },
    { target: 'bpm', text: 'Tour BPM Widget' },
    { target: 'tags', text: 'Tour Tags Widget' },
    { target: 'presets', text: 'Tour Presets Widget' },
    { target: 'table', text: 'Tour Song Table' },
    { target: 'effects', text: 'Tour Effectslist' },
    { target: 'menubar', text: 'Tour Menubar' },
  ];

  const steps = allSteps.filter((step) => document.querySelector(`[data-tour="${step.target}"]`));
  let index = $state(0);
  let rect = $state<DOMRect | null>(null);

  $effect(() => {
    const step = steps[index];
    if (!step) return finish();
    const element = document.querySelector(`[data-tour="${step.target}"]`);
    element?.scrollIntoView({ block: 'nearest' });
    rect = element?.getBoundingClientRect() ?? null;
  });

  function finish() {
    ui.tour = false;
    prefs.tourDone = true;
    savePrefs();
  }

  function onKey(event: KeyboardEvent) {
    if (event.key === 'Escape') finish();
    if (event.key === 'Enter' || event.key === 'ArrowRight') index < steps.length - 1 ? index++ : finish();
    if (event.key === 'ArrowLeft' && index > 0) index--;
  }

  const pad = 6;
  const bubble = $derived.by(() => {
    if (!rect) return { left: 40, top: 40 };
    const width = 320;
    const below = rect.bottom + 14 + 140 < window.innerHeight;
    const right = rect.right + 14 + width < window.innerWidth;
    if (rect.width < window.innerWidth * 0.5 && right) return { left: rect.right + 14, top: Math.min(Math.max(10, rect.top), Math.max(10, window.innerHeight - 190)) };
    if (below) return { left: Math.min(Math.max(10, rect.left), window.innerWidth - width - 10), top: rect.bottom + 14 };
    return { left: Math.min(Math.max(10, rect.left), window.innerWidth - width - 10), top: Math.max(10, rect.top - 160) };
  });
</script>

<svelte:window onkeydown={onKey} />

{#if steps.length && rect}
  <div class="tour" role="dialog" aria-modal="true">
    <div class="hole" style:left="{rect.left - pad}px" style:top="{rect.top - pad}px" style:width="{rect.width + pad * 2}px" style:height="{rect.height + pad * 2}px"></div>
    <div class="bubble panel" style:left="{bubble.left}px" style:top="{bubble.top}px">
      <p>{t(steps[index].text)}</p>
      <div class="actions">
        <span class="muted">{index + 1} / {steps.length}</span>
        <span class="grow"></span>
        <button class="btn" onclick={finish}>{t('Close')}</button>
        {#if index > 0}<button class="btn" onclick={() => index--}>{t('Previous')}</button>{/if}
        <button class="btn primary" onclick={() => (index < steps.length - 1 ? index++ : finish())}>{index < steps.length - 1 ? t('Next') : t('Ok')}</button>
      </div>
    </div>
  </div>
{/if}

<style>
  .tour { position: fixed; inset: 0; z-index: 1200; }
  .hole { position: fixed; border-radius: 10px; box-shadow: 0 0 0 9999px rgba(10, 12, 20, 0.6); transition: all 0.35s ease; pointer-events: none; outline: 2px solid var(--accent); }
  .bubble { position: fixed; width: 320px; padding: 14px 16px; box-shadow: var(--shadow); transition: all 0.35s ease; }
  p { margin: 0 0 12px; line-height: 1.45; white-space: pre-line; }
  .actions { display: flex; gap: 6px; align-items: center; }
  .grow { flex: 1; }
</style>
