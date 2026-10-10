<script lang="ts">
  import { t } from '../../lib/i18n.svelte';
  import { closeDialog } from '../../lib/stores/ui.svelte';
  import type { MusicCategory } from '../../lib/types';
  import Modal from '../dialogs/Modal.svelte';
  import Icon from '../Icon.svelte';
  import { ICONS } from './CategorySlider.svelte';

  /** Explains how the mood sliders rank the songs and what every category and its values mean. */
  let { categories }: { categories: MusicCategory[] } = $props();

  const groups = $derived.by(() => {
    const map = new Map<string, MusicCategory[]>();
    for (const category of categories) {
      const group = category.group || '';
      if (!map.has(group)) map.set(group, []);
      map.get(group)!.push(category);
    }
    return [...map.entries()];
  });

  const levels = (category: MusicCategory) =>
    Object.entries(category.levels).map(([k, v]) => [Number(k), v] as const).sort((a, b) => a[0] - b[0]);

  /** Tips for the built-in categories (custom categories only have their description and levels). */
  function usage(category: MusicCategory): string | null {
    const key = `${category.key} Usage`;
    const text = t(key);
    return text === key ? null : text;
  }
</script>

<Modal resizable title={t('Mood Sliders')} onclose={closeDialog} width="760px">
  <div class="help">
    <section class="intro">
      <h3>{t('How the mood sliders work')}</h3>
      <p>{t('Each slider describes one property of a song on a scale from 0 to 10. The values come from the analysis or were set by hand in the song editor.')}</p>
      <ul>
        <li>{t('A slider without a value (–) is ignored. As soon as you set a value, every song gets a match score and the table is sorted by it: the lower the score, the better the song fits.')}</li>
        <li>{t('For every active slider the difference between your value and the value of the song is squared and added up. Small differences hardly count, large ones weigh heavily: a difference of 2 adds 4 points, a difference of 5 already adds 25.')}</li>
        <li>{t('Songs without a value for an active slider get 100 penalty points, so analyzed songs come first.')}</li>
        <li>{t('BPM adds the difference in beats per minute (100 if unknown). Every selected tag or genre a song lacks adds 100.')}</li>
        <li>{t('Score colors: green below 50, yellow below 100, orange below 150, red above. Category cells in the table show how far a song is from your value: close (less than 4), medium (less than 7) or far.')}</li>
        <li>{t('Combine only a few sliders: every additional one makes the match stricter. Double-click a slider or click × to remove its value.')}</li>
      </ul>
    </section>

    {#each groups as [group, list] (group)}
      <section>
        {#if groups.length > 1}<h3>{group || t('General')}</h3>{/if}
        <div class="list">
          {#each list as category (category.key)}
            <article class="category">
              <header>
                <span class="icon"><Icon name={ICONS[category.key] ?? 'sliders'} size={18} /></span>
                <h4>{category.name}</h4>
              </header>
              {#if category.description}<p>{category.description}</p>{/if}
              {#if levels(category).length}
                <div class="scale">
                  {#each levels(category) as [value, text] (value)}
                    <div class="level"><span class="num">{value}</span><span>{text}</span></div>
                  {/each}
                </div>
              {/if}
              {#if usage(category)}<p class="tip"><Icon name="sparkles" size={14} /><span>{usage(category)}</span></p>{/if}
            </article>
          {/each}
        </div>
      </section>
    {/each}
  </div>
  {#snippet footer()}
    <button class="btn primary" onclick={closeDialog}>{t('Ok')}</button>
  {/snippet}
</Modal>

<style>
  .help { display: flex; flex-direction: column; gap: 18px; }
  h3 { margin: 0 0 8px; font-size: var(--fs); font-family: var(--font-display); }
  h4 { margin: 0; font-size: var(--fs); }
  p { margin: 0; color: var(--muted); line-height: 1.5; }
  ul { margin: 8px 0 0; padding-left: 20px; color: var(--muted); line-height: 1.5; display: flex; flex-direction: column; gap: 4px; }
  .list { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(320px, 100%), 1fr)); gap: 10px; }
  .category { display: flex; flex-direction: column; gap: 8px; padding: 12px 14px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface-2); }
  .category header { display: flex; align-items: center; gap: 8px; }
  .icon { color: var(--accent); display: flex; }
  .scale { display: flex; flex-direction: column; gap: 3px; font-size: var(--fs-sm); }
  .level { display: grid; grid-template-columns: 26px 1fr; gap: 8px; }
  .num { font-weight: 650; font-variant-numeric: tabular-nums; color: var(--accent); text-align: right; }
  .tip { display: flex; gap: 6px; align-items: flex-start; font-size: var(--fs-sm); }
  .tip :global(svg) { flex: none; margin-top: 3px; color: var(--gold); }
</style>
