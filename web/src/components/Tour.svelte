<script lang="ts">
  import { untrack } from 'svelte';
  import { api } from '../lib/api';
  import { editSong, openImportDialog, openUploadDialog, trackMenu, uploadTarget } from '../lib/actions';
  import { t } from '../lib/i18n.svelte';
  import { prefs, savePrefs } from '../lib/prefs.svelte';
  import { data } from '../lib/stores/data.svelte';
  import { visibleRows } from '../lib/stores/library.svelte';
  import Icon from './Icon.svelte';
  import { appMenu } from '../lib/menus';
  import { closeDialog, closeMenu, openMenu, ui } from '../lib/stores/ui.svelte';

  interface Step {
    target: string;
    text: string;
    /** Steps that show something which is not on screen yet are available only when this returns true. */
    when?: () => boolean;
    /** Opens the dialog or menu that contains the target. */
    open?: () => void | Promise<void>;
  }

  const firstTrack = () => visibleRows()[0]?.track;

  function openTrackMenu() {
    const track = firstTrack();
    const table = document.querySelector('[data-tour="table"]')?.getBoundingClientRect();
    if (track && table) openMenu({ clientX: table.left + 120, clientY: table.top + 80 }, trackMenu([track]));
  }

  /** Opens the context menu of the first folder in the tree, the way a right-click would. */
  function openTreeMenu() {
    const row = document.querySelector<HTMLElement>('[data-tour="tree"] button.row');
    const rect = row?.getBoundingClientRect();
    if (row && rect) row.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: rect.left + 60, clientY: rect.top + rect.height / 2 }));
  }

  /** Opens the main menu and unfolds its View submenu. */
  async function openViewMenu() {
    const button = document.querySelector('[data-tour="menubar"]')?.getBoundingClientRect();
    if (!button) return;
    openMenu({ clientX: button.right - 240, clientY: button.bottom + 6 }, appMenu());
    const item = await waitFor('menu-view');
    item?.parentElement?.dispatchEvent(new MouseEvent('mouseenter'));
  }

  const hasFolder = () => !!document.querySelector('[data-tour="tree"] button.row') && !!uploadTarget();

  const allSteps: Step[] = [
    { target: 'tree', text: 'Tour Directory Tree' },
    { target: 'tree', text: 'Tour Upload' },
    { target: 'menu-upload', text: 'Tour Menu Upload', when: hasFolder, open: openTreeMenu },
    { target: 'upload-drop', text: 'Tour Upload Dialog', when: () => !!uploadTarget(), open: () => openUploadDialog() },
    { target: 'menu-import', text: 'Tour Menu Import', when: hasFolder, open: openTreeMenu },
    { target: 'import-url', text: 'Tour Import Dialog', when: () => !!uploadTarget(), open: () => openImportDialog() },
    { target: 'table', text: 'Tour Song Table' },
    { target: 'menu-edit', text: 'Tour Menu Edit', when: () => !!firstTrack(), open: openTrackMenu },
    { target: 'edit-form', text: 'Tour Edit Song', when: () => !!firstTrack(), open: () => firstTrack() && editSong(firstTrack()!) },
    { target: 'menu-analyze', text: 'Tour Analyze', when: () => !!firstTrack() && data.settings?.voxalyzerActive !== false, open: openTrackMenu },
    { target: 'russel', text: 'Tour Russel Widget' },
    { target: 'slider', text: 'Tour Category Slider' },
    { target: 'bpm', text: 'Tour BPM Widget' },
    { target: 'tags', text: 'Tour Tags Widget' },
    { target: 'presets', text: 'Tour Presets Widget' },
    { target: 'player', text: 'Tour Player' },
    { target: 'effects', text: 'Tour Effectslist' },
    { target: 'lights', text: 'Tour Lights' },
    { target: 'tabs', text: 'Tour Tabs' },
    { target: 'search', text: 'Tour Search' },
    { target: 'menubar', text: 'Tour Menubar' },
    { target: 'menu-view-sub', text: 'Tour View Modes', when: () => !!find('menubar'), open: openViewMenu },
  ];

  const find = (target: string) => document.querySelector<HTMLElement>(`[data-tour="${target}"]`);
  const steps = allSteps.filter((step) => (step.when ? step.when() : find(step.target)));
  let index = $state(0);
  let rect = $state<DOMRect | null>(null);
  let dialog = $state<HTMLDialogElement | null>(null);
  let nextButton = $state<HTMLButtonElement | null>(null);
  let direction = 1;
  let run = 0;

  /** The target is ready once it is rendered and visible (a menu is hidden until it has been measured) and, inside a dialog, that dialog is open. */
  function ready(element: HTMLElement | null): element is HTMLElement {
    if (!element) return false;
    const parent = element.closest('dialog');
    return (!parent || parent.open) && getComputedStyle(element).visibility === 'visible';
  }

  async function waitFor(target: string): Promise<HTMLElement | null> {
    const deadline = performance.now() + 1500;
    for (;;) {
      const element = find(target);
      if (ready(element)) return element;
      if (performance.now() > deadline) return null;
      await new Promise((resolve) => setTimeout(resolve, 40));
    }
  }

  /** The tour is a modal dialog itself, so it is opened again to lie above a dialog that the step has just opened. */
  function raise() {
    if (!dialog) return;
    if (dialog.open) dialog.close();
    dialog.showModal();
    nextButton?.focus();
  }

  async function show(position: number) {
    const current = ++run;
    const step = steps[position];
    if (!step) return finish();
    closeDialog();
    closeMenu();
    await step.open?.();
    const element = await waitFor(step.target);
    if (current !== run) return;
    if (!element) { // the target could not be shown: go on in the direction of travel
      const next = position + direction;
      if (next < 0) direction = 1;
      if (next >= steps.length) return finish();
      index = Math.max(0, next);
      return;
    }
    element.scrollIntoView({ block: 'nearest' });
    rect = element.getBoundingClientRect();
    raise();
    follow(element, current);
  }

  /** Dialogs and lists are still laid out when the target is found (folders load, the dialog grows), so the highlight follows the element while the step is shown. */
  function follow(element: HTMLElement, current: number) {
    if (current !== run || !element.isConnected) return;
    const next = element.getBoundingClientRect();
    if (!rect || next.left !== rect.left || next.top !== rect.top || next.width !== rect.width || next.height !== rect.height) rect = next;
    setTimeout(() => follow(element, current), 60);
  }

  $effect(() => {
    if (!dialog) return;
    const position = index;
    // opening a dialog reads and writes shared state; only the step itself may trigger this effect again
    untrack(() => void show(position));
  });

  function go(delta: number) {
    direction = delta;
    if (index + delta >= steps.length) return finish();
    index = Math.max(0, index + delta);
  }

  function finish() {
    run++;
    closeDialog();
    closeMenu();
    ui.tour = false;
    prefs.tourDone = true;
    savePrefs();
    data.user.tour_done = true;
    void api.putUserState({ tour_done: true }).catch(() => undefined);
  }

  function onKey(event: KeyboardEvent) {
    if (event.key === 'Enter' || event.key === 'ArrowRight') go(1);
    else if (event.key === 'ArrowLeft' && index > 0) go(-1);
    else return;
    event.preventDefault(); // a focused button must not click as well
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

<dialog class="tour" bind:this={dialog} oncancel={(e) => { e.preventDefault(); finish(); }} aria-label={t('Show Tour')}>
  {#if steps.length && rect}
    <div class="hole" style:left="{rect.left - pad}px" style:top="{rect.top - pad}px" style:width="{rect.width + pad * 2}px" style:height="{rect.height + pad * 2}px"></div>
    <div class="bubble panel" style:left="{bubble.left}px" style:top="{bubble.top}px">
      <p>{@html t(steps[index].text)}</p>
      <div class="actions">
        <span class="muted">{index + 1} / {steps.length}</span>
        <span class="grow"></span>
        {#if index < steps.length - 1}<button class="btn" onclick={finish}>{t('Close')}</button>{/if}
        {#if index > 0}<button class="btn icon" title={t('Previous')} aria-label={t('Previous')} onclick={() => go(-1)}><Icon name="chevron-left" size={16} /></button>{/if}
        {#if index < steps.length - 1}
          <button class="btn primary icon" bind:this={nextButton} title={t('Next')} aria-label={t('Next')} onclick={() => go(1)}><Icon name="chevron-right" size={16} /></button>
        {:else}
          <button class="btn primary" bind:this={nextButton} onclick={finish}>{t('Ok')}</button>
        {/if}
      </div>
    </div>
  {/if}
</dialog>

<style>
  .tour { position: fixed; inset: 0; width: 100vw; height: 100vh; max-width: none; max-height: none; margin: 0; padding: 0; border: 0; background: transparent; color: inherit; overflow: hidden; }
  .tour::backdrop { background: transparent; }
  .hole { position: fixed; border-radius: 10px; box-shadow: 0 0 0 9999px rgba(10, 12, 20, 0.6); transition: all 0.35s ease; pointer-events: none; outline: 2px solid var(--accent); }
  .bubble { position: fixed; width: 320px; padding: 14px 16px; box-shadow: var(--shadow); transition: all 0.35s ease; }
  p { margin: 0 0 12px; line-height: 1.45; white-space: pre-line; }
  .actions { display: flex; gap: 6px; align-items: center; }
  .grow { flex: 1; }
  .btn.icon { padding-inline: 10px; display: inline-flex; align-items: center; }
</style>
