<script lang="ts">
  import { untrack } from 'svelte';
  import { api } from '../lib/api';
  import { editSong, openImportDialog, openUploadDialog, trackMenu, uploadTarget } from '../lib/actions';
  import { t } from '../lib/i18n.svelte';
  import { prefs, savePrefs } from '../lib/prefs.svelte';
  import { tourInfo } from '../lib/tourSteps';
  import { assistant } from '../lib/stores/assistant.svelte';
  import { data } from '../lib/stores/data.svelte';
  import { visibleRows } from '../lib/stores/library.svelte';
  import Icon from './Icon.svelte';
  import { appMenu } from '../lib/menus';
  import type { UserState } from '../lib/types';
  import { closeDialog, closeMenu, openMenu, ui } from '../lib/stores/ui.svelte';

  /** `news`: the ids of the steps to show (the "What's new" tour), otherwise the whole tour is shown. */
  let { news = null }: { news?: string[] | null } = $props();

  interface Step {
    /** Stable name of the step; the ids of the steps a user has seen are stored, so new steps can be announced later. Never reuse or rename one. */
    id: string;
    target: string;
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
    item?.click();
  }

  const hasFolder = () => !!document.querySelector('[data-tour="tree"] button.row') && !!uploadTarget();

  const allSteps: Step[] = [
    { target: 'tree', id: 'tree' },
    { target: 'tree', id: 'upload' },
    { target: 'menu-upload', id: 'menu-upload', when: hasFolder, open: openTreeMenu },
    { target: 'upload-drop', id: 'upload-dialog', when: () => !!uploadTarget(), open: () => openUploadDialog() },
    { target: 'menu-import', id: 'menu-import', when: hasFolder, open: openTreeMenu },
    { target: 'import-url', id: 'import-dialog', when: () => !!uploadTarget(), open: () => openImportDialog() },
    { target: 'table', id: 'table' },
    { target: 'menu-edit', id: 'menu-edit', when: () => !!firstTrack(), open: openTrackMenu },
    { target: 'edit-form', id: 'edit-song', when: () => !!firstTrack(), open: () => firstTrack() && editSong(firstTrack()!) },
    { target: 'menu-analyze', id: 'analyze', when: () => !!firstTrack() && data.settings?.voxalyzerActive !== false, open: openTrackMenu },
    { target: 'russel', id: 'russel' },
    { target: 'slider', id: 'slider' },
    { target: 'bpm', id: 'bpm' },
    { target: 'tags', id: 'tags' },
    { target: 'presets', id: 'presets' },
    { target: 'player', id: 'player' },
    { target: 'effects', id: 'effects' },
    { target: 'lights', id: 'lights' },
    { target: 'tabs', id: 'tabs' },
    { target: 'search', id: 'search' },
    { target: 'global-search', id: 'global-search' },
    { target: 'assistant-chat', id: 'assistant', when: () => !!find('assistant'), open: () => { assistant.open = true; } },
    { target: 'menubar', id: 'menubar' },
    { target: 'menu-view-sub', id: 'view-modes', when: () => !!find('menubar'), open: openViewMenu },
  ];

  const find = (target: string) => document.querySelector<HTMLElement>(`[data-tour="${target}"]`);
  // svelte-ignore state_referenced_locally
  const steps = allSteps.filter((step) => (!news || news.includes(step.id)) && (step.when ? step.when() : find(step.target)));
  let dontShow = $state(false);
  let index = $state(0);
  let rect = $state<DOMRect | null>(null);
  let dialog = $state<HTMLDialogElement | null>(null);
  let nextButton = $state<HTMLButtonElement | null>(null);
  let direction = 1;
  const seen = new Set<string>(); // the steps shown so far
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
    assistant.open = false;
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
    seen.add(step.id);
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
    assistant.open = false;
    ui.tour = false;
    prefs.tourDone = true;
    savePrefs();
    data.user.tour_done = true;
    // the news count as seen even when closed early, so they are not announced again
    data.user.tour_seen = [...new Set([...data.user.tour_seen, ...seen, ...(news ?? [])])];
    const state: Partial<UserState> = { tour_done: true, tour_seen: data.user.tour_seen };
    if (news && dontShow) {
      data.user.news_off = true;
      state.news_off = true;
    }
    ui.tourNews = null;
    void api.putUserState(state).catch(() => undefined);
  }

  function onKey(event: KeyboardEvent) {
    if (event.key === 'Enter' || event.key === 'ArrowRight') go(1);
    else if (event.key === 'ArrowLeft' && index > 0) go(-1);
    else return;
    event.preventDefault(); // a focused button must not click as well
  }

  const info = $derived(tourInfo(steps[index]?.id));
  const pad = 6;
  let viewW = $state(window.innerWidth);
  let viewH = $state(window.innerHeight);
  let bubbleHeight = $state(190); // measured, the text and the optional checkbox make it vary
  const bubbleWidth = $derived(Math.min(320, viewW - 20));
  const bubble = $derived.by(() => {
    const width = bubbleWidth;
    const height = bubbleHeight;
    // always keep the whole bubble (and with it its buttons) on screen
    const fit = (left: number, top: number) => ({
      left: Math.min(Math.max(10, left), Math.max(10, viewW - width - 10)),
      top: Math.min(Math.max(10, top), Math.max(10, viewH - height - 10)),
    });
    if (!rect) return fit(40, 40);
    const below = rect.bottom + 14 + height < viewH;
    const above = rect.top - 14 - height > 0;
    const right = rect.right + 14 + width < viewW;
    const left = rect.left - 14 - width > 0;
    const wide = rect.width >= viewW * 0.5;
    if (!wide && right) return fit(rect.right + 14, rect.top);
    if (!wide && left) return fit(rect.left - 14 - width, rect.top); // e.g. the assistant popup at the right edge
    if (below) return fit(rect.left, rect.bottom + 14);
    if (above) return fit(rect.left, rect.top - 14 - height);
    return fit(rect.left, viewH - height - 10); // nothing fits around the target: the bottom edge, as little over it as possible
  });

  // swipe left for the next step, right for the previous one
  let swipe: { x: number; y: number } | null = null;
  function swipeStart(event: TouchEvent) {
    const touch = event.touches[0];
    swipe = event.touches.length === 1 && touch ? { x: touch.clientX, y: touch.clientY } : null;
  }
  function swipeEnd(event: TouchEvent) {
    const touch = event.changedTouches[0];
    const start = swipe;
    swipe = null;
    if (!start || !touch) return;
    const dx = touch.clientX - start.x;
    const dy = touch.clientY - start.y;
    if (Math.abs(dx) < 50 || Math.abs(dx) < Math.abs(dy) * 1.5) return;
    if (dx < 0) go(1);
    else if (index > 0) go(-1);
  }
</script>

<svelte:window onkeydown={onKey} bind:innerWidth={viewW} bind:innerHeight={viewH} />

<dialog class="tour" bind:this={dialog} oncancel={(e) => { e.preventDefault(); finish(); }} aria-label={t('Show Tour')} ontouchstart={swipeStart} ontouchend={swipeEnd}>
  {#if steps.length && rect}
    <div class="hole" style:left="{rect.left - pad}px" style:top="{rect.top - pad}px" style:width="{rect.width + pad * 2}px" style:height="{rect.height + pad * 2}px"></div>
    <div class="bubble panel" bind:offsetHeight={bubbleHeight} style:left="{bubble.left}px" style:top="{bubble.top}px" style:width="{bubbleWidth}px">
      {#if news}<span class="kicker muted">{t("What's new")}</span>{/if}
      <h3>{t(info?.title ?? '')}</h3>
      <p>{@html t(info?.text ?? '')}</p>
      {#if news}
        <label class="check"><input type="checkbox" bind:checked={dontShow} /> {t('Do not show this again')}</label>
      {/if}
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
  .tour { position: fixed; inset: 0; width: 100%; height: 100%; max-width: none; max-height: none; touch-action: pan-y; margin: 0; padding: 0; border: 0; background: transparent; color: inherit; overflow: hidden; }
  .tour::backdrop { background: transparent; }
  .hole { position: fixed; border-radius: 10px; box-shadow: 0 0 0 9999px rgba(10, 12, 20, 0.6); transition: all 0.35s ease; pointer-events: none; outline: 2px solid var(--accent); }
  .bubble { position: fixed; max-height: calc(100% - 20px); overflow-y: auto; padding: 14px 16px; box-shadow: var(--shadow); transition: all 0.35s ease; }
  h3 { margin: 0 0 4px; font-size: var(--fs-md, 1em); }
  .kicker { display: block; font-size: var(--fs-sm); text-transform: uppercase; letter-spacing: 0.04em; }
  .check { display: flex; align-items: center; gap: 8px; margin: 0 0 12px; font-size: var(--fs-sm); }
  p { margin: 0 0 12px; line-height: 1.45; white-space: pre-line; }
  .actions { display: flex; gap: 6px; align-items: center; }
  .grow { flex: 1; }
  .btn.icon { padding-inline: 10px; display: inline-flex; align-items: center; }
</style>
