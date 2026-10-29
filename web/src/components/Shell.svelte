<script lang="ts">
  import { onDestroy } from 'svelte';
  import { cubicOut } from 'svelte/easing';
  import { prefersReducedMotion } from 'svelte/motion';
  import { fade, fly, slide as widthSlide } from 'svelte/transition';
  import { api, coverUrl } from '../lib/api';
  import { applyAmbient } from '../lib/ambient';
  import { prefs, savePrefs } from '../lib/prefs.svelte';
  import { openDownloadsDialog } from '../lib/actions';
  import { panelTouchEnd, panelTouchStart } from '../lib/panelSwipe';
  import { locale, t } from '../lib/i18n.svelte';
  import Icon from './Icon.svelte';
  import { data } from '../lib/stores/data.svelte';
  import { adventures, endSongSearch, flushSave, openAdventure, pickBlock } from '../lib/stores/adventure.svelte';
  import { assistant } from '../lib/stores/assistant.svelte';
  import { analysis, downloads, type JobKind } from '../lib/stores/downloads.svelte';
  import { effects } from '../lib/stores/effects.svelte';
  import { activeTab, library } from '../lib/stores/library.svelte';
  import { cycleRepeat, next, player, previous, setVolume, toggleEffect, toggleMute, togglePlay } from '../lib/stores/player.svelte';
  import { closeMenu, openDialog, ui } from '../lib/stores/ui.svelte';
  import { unseenTourSteps } from '../lib/tourSteps';
  import { nextVideo } from '../lib/videos';
  import VideoDialog from './dialogs/VideoDialog.svelte';
  import AdventureView from './adventure/AdventureView.svelte';
  import AssistantChat from './AssistantChat.svelte';
  import ConfirmDialog from './dialogs/ConfirmDialog.svelte';
  import PromptDialog from './dialogs/PromptDialog.svelte';
  import ContextMenu from './ContextMenu.svelte';
  import FilterPanel from './filter/FilterPanel.svelte';
  import MenuBar from './MenuBar.svelte';
  import PlayerBar from './player/PlayerBar.svelte';
  import RightPanel from './RightPanel.svelte';
  import Sidebar from './Sidebar.svelte';
  import SidebarToggle from './SidebarToggle.svelte';
  import Splitter from './Splitter.svelte';
  import SongTable from './table/SongTable.svelte';
  import Toasts from './Toasts.svelte';
  import Tour from './Tour.svelte';
  import Welcome from './Welcome.svelte';

  const tab = $derived(activeTab());
  const adventureTab = $derived(tab?.type === 'adventure' ? tab : null);

  // the music of a block is searched in the whole library; leaving that mode in any other way ends the search
  const searchingFor = $derived(library.global ? pickBlock() : null);
  $effect(() => {
    if (!library.global && adventures.pickFor) adventures.pickFor = null;
  });

  // the adventure of the active tab is loaded when its tab is shown, and saved when another tab takes over
  $effect(() => {
    if (adventureTab) {
      if (adventures.current?.id !== adventureTab.path) void openAdventure(adventureTab.path);
    } else {
      void flushSave();
    }
  });
  // the side panel has something to show; on a desktop it is also switched on (rightOpen), on tablets and phones it opens as a flyout
  const hasRight = $derived(prefs.showEffects || (prefs.showLights && data.settings?.lightsEnabled !== false));
  const showRight = $derived(prefs.rightOpen && hasRight);

  // a flyout slides in from its own edge and back out to it
  const slide = (node: HTMLElement, x: string) => fly(node, { x, opacity: 1, duration: prefersReducedMotion.current ? 0 : 240, easing: cubicOut });
  const scrimFade = (node: HTMLElement) => fade(node, { duration: prefersReducedMotion.current ? 0 : 200 });
  // on a wide screen a side panel grows from and shrinks to its edge; its content keeps its width, so it is uncovered instead of squeezed
  const panelSlide = (node: HTMLElement) => widthSlide(node, { axis: 'x', duration: prefersReducedMotion.current ? 0 : 220, easing: cubicOut });

  // a flyout closes with a swipe towards its own edge
  let swipeStart: { x: number; y: number } | null = null;
  function drawerDown(event: PointerEvent) {
    swipeStart = event.pointerType === 'mouse' ? null : { x: event.clientX, y: event.clientY };
  }
  function drawerUp(event: PointerEvent) {
    const start = swipeStart;
    swipeStart = null;
    if (!start) return;
    const dx = event.clientX - start.x;
    const dy = event.clientY - start.y;
    if (Math.abs(dx) < 60 || Math.abs(dx) < Math.abs(dy) * 1.5) return;
    if ((ui.mobilePanel === 'side') === (dx > 0)) ui.mobilePanel = null;
  }

  let newsChecked = false; // the "What's new" popup is offered once per page load

  $effect(() => {
    // the server remembers it per user: the desktop app gets a new port (and so an empty browser storage) on every start
    if (!prefs.tourDone && !data.user.tour_done) {
      newsChecked = true; // the tour shows everything
      tourTimer = setTimeout(() => (ui.tour = true), 600);
    } else if (!newsChecked && data.user.tour_done) {
      newsChecked = true;
      const news = data.user.news_off ? [] : unseenTourSteps();
      if (news.length) {
        tourTimer = setTimeout(() => {
          if (ui.tour || ui.dialog) return;
          ui.tourNews = news.map((step) => step.id);
          ui.tour = true;
        }, 800);
      }
    }
  });
  let tourTimer: ReturnType<typeof setTimeout> | undefined;
  onDestroy(() => clearTimeout(tourTimer)); // logged out before the tour came up

  let videoShown = false; // an announced video (lib/videos.ts) is shown once per user, at most one per page load

  $effect(() => {
    // after the tour and the "What's new" popup, when nothing else is open
    if (videoShown || !data.user.tour_done || ui.tour || ui.dialog) return;
    const video = nextVideo(data.user, locale());
    if (!video) return;
    const timer = setTimeout(() => {
      if (videoShown || ui.tour || ui.dialog) return;
      videoShown = true;
      data.user.videos_seen = [...data.user.videos_seen, video.key];
      void api.putUserState({ videos_seen: data.user.videos_seen }).catch(() => undefined);
      openDialog(VideoDialog, { youtube: video.id, title: video.title, text: video.text });
    }, 1500);
    return () => clearTimeout(timer);
  });

  $effect(() => {
    const track = player.track;
    void applyAmbient(track?.has_cover ? coverUrl(track.id, 64) : null);
  });

  function typing(event: KeyboardEvent): boolean {
    const target = event.target as HTMLElement;
    return target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName);
  }

  /** While a search typed into the song table or the effects list is running, its keys (the space included) belong to the search. */
  function searching(event: KeyboardEvent): boolean {
    const target = event.target as HTMLElement;
    return (!!library.search && !!target.closest('[data-tour="table"]')) || (!!effects.search && !!target.closest('[data-tour="effects"]'));
  }

  function setScale(scale: number) {
    prefs.fontScale = Math.round(Math.max(0.8, Math.min(1.5, scale)) * 10) / 10;
    savePrefs();
  }

  function onKeydown(event: KeyboardEvent) {
    if (event.key === 'F11') {
      event.preventDefault();
      if (document.fullscreenElement) void document.exitFullscreen();
      else void document.documentElement.requestFullscreen();
      return;
    }
    if (searching(event)) return;
    if (!(event.ctrlKey || event.metaKey) || typing(event)) {
      if (event.key === ' ' && !typing(event) && !(event.target as HTMLElement).closest('button')) {
        event.preventDefault();
        togglePlay();
      }
      return;
    }
    const handlers: Record<string, () => void> = {
      p: togglePlay,
      n: () => next(),
      b: previous,
      r: cycleRepeat,
      m: toggleMute,
      e: toggleEffect,
      ArrowUp: () => setVolume(prefs.volume + 5),
      ArrowDown: () => setVolume(prefs.volume - 5),
      '+': () => setScale(prefs.fontScale + 0.1),
      '=': () => setScale(prefs.fontScale + 0.1),
      '-': () => setScale(prefs.fontScale - 0.1),
      '0': () => setScale(1),
    };
    const handler = handlers[event.key];
    if (handler) {
      event.preventDefault();
      handler();
    }
  }

  $effect(() => {
    document.title = player.track ? `${player.playing ? '▶ ' : ''}${player.track.title || player.track.name} · Dungeon Tuber` : 'Dungeon Tuber';
  });
</script>

<!-- touch screens: a swipe from a screen edge opens its side panel, one on the border of an open panel closes it (lib/panelSwipe.ts) -->
<svelte:window onkeydown={onKeydown} onclick={closeMenu} onblur={closeMenu} ontouchstart={panelTouchStart} ontouchend={panelTouchEnd} />

<div class="app">
  <div class="aura" aria-hidden="true"></div>
  <div class="body">
    {#if (ui.narrow && ui.mobilePanel === 'tree') || (ui.rightOverlay && ui.mobilePanel === 'side' && hasRight)}
      <div class="scrim" role="presentation" transition:scrimFade onclick={() => (ui.mobilePanel = null)}></div>
    {/if}
    {#if ui.rightOverlay && ui.mobilePanel === 'side' && hasRight}
      <aside class="drawer right-drawer" transition:slide={'100%'} onpointerdown={drawerDown} onpointerup={drawerUp} onpointercancel={() => (swipeStart = null)}><RightPanel /></aside>
    {/if}
    {#if ui.narrow}
      {#if ui.mobilePanel === 'tree'}
        <aside class="drawer" transition:slide={'-100%'} onpointerdown={drawerDown} onpointerup={drawerUp} onpointercancel={() => (swipeStart = null)}><Sidebar /></aside>
      {/if}
    {:else}
      {#if prefs.leftOpen}
        <aside class="sidebar" style:width="{prefs.leftWidth}px" data-tour="tree" transition:panelSlide>
          <div class="panel-inner" style:width="{prefs.leftWidth}px"><Sidebar /></div>
        </aside>
        <Splitter bind:size={prefs.leftWidth} min={200} max={480} onchange={savePrefs} />
      {/if}
    {/if}

    <main class="main">
      <MenuBar />
      {#if adventureTab}
        {#if adventures.current?.id === adventureTab.path}<AdventureView />{:else}<span class="loading muted">{t('Loading…')}</span>{/if}
      {:else}
        {#if searchingFor}
          <div class="pick-bar">
            <Icon name="mask" size={16} />
            <span class="ellipsis">{t('Find music for the block "{0}": + adds a song to it.', searchingFor.title || t('Untitled'))}</span>
            <span class="muted count">{t('{0} song(s) in the block', searchingFor.music.length)}</span>
            <button class="btn sm primary" onclick={() => void endSongSearch()}><Icon name="back" size={13} />{t('Back to the adventure')}</button>
          </div>
        {/if}
        <FilterPanel />
        {#if tab}
          <div class="table-wrap" data-tour="table"><SongTable {tab} /></div>
        {:else}
          <Welcome />
        {/if}
      {/if}
    </main>

    {#if showRight && !ui.rightOverlay}
      <Splitter bind:size={prefs.rightWidth} min={260} max={480} invert onchange={savePrefs} />
      <aside class="right" style:width="{prefs.rightWidth}px" transition:panelSlide>
        <div class="panel-inner end" style:width="{prefs.rightWidth - 14}px"><RightPanel /></div>
      </aside>
    {/if}
    <!-- wide screens: the buttons that open and close the side panels sit on their borders (tablets and phones use the top bar) -->
    {#if !ui.narrow}<SidebarToggle side="left" />{/if}
    {#if !ui.rightOverlay && hasRight}<SidebarToggle side="right" />{/if}
  </div>

  <PlayerBar />
{#snippet job(kind: JobKind)}
  {@const status = kind === 'downloads' ? downloads : analysis}
  {#if status.pending}
    {@const current = status.items.find((item) => item.state === 'downloading' || item.state === 'running')}
    {@const label = kind === 'downloads' ? t('Downloads: {0} remaining', status.pending) : t('Analysis: {0} remaining', status.pending)}
    <button class="job" onclick={() => openDownloadsDialog(kind)} title={kind === 'downloads' ? t('Show downloads') : t('Show analysis')}>
      <span class="spinner"></span>
      <span class="ellipsis">{label}{current ? ` · ${current.title}${kind === 'downloads' ? ` ${current.percent}%` : ''}` : ''}</span>
    </button>
  {/if}
{/snippet}
  {#if ui.progress || !ui.connected || downloads.pending || analysis.pending}
    <div class="status">
      {#if !ui.connected}<span class="offline">● offline – reconnecting…</span>{/if}
      {#if ui.progress}<span class="spinner"></span><span class="ellipsis">{ui.progress}</span>{/if}
      {#if ui.progress && ui.progressCancel}
        <button class="icon-btn mini" title={t('Cancel')} aria-label={t('Cancel')} onclick={() => ui.progressCancel?.()}><Icon name="close" size={12} /></button>
      {/if}
      <span class="grow"></span>
      {@render job('analysis')}
      {@render job('downloads')}
    </div>
  {/if}
</div>

{#if assistant.open}<AssistantChat />{/if}
<ContextMenu />
<Toasts />
<PromptDialog />
<ConfirmDialog />
{#if ui.dialog}
  {@const Dialog = ui.dialog.component}
  <!-- a new dialog is a new instance, also of the same component (dialogs take their props into their own state once) -->
  {#key ui.dialog}<Dialog {...ui.dialog.props} />{/key}
{/if}
{#if ui.tour}<Tour news={ui.tourNews} />{/if}

<style>
  .app { height: 100%; display: flex; flex-direction: column; position: relative; isolation: isolate; }
  .aura {
    position: absolute; inset: 0; z-index: -1; pointer-events: none;
    background:
      radial-gradient(1200px 520px at 50% 115%, rgba(var(--ambient), 0.22), transparent 70%),
      radial-gradient(700px 400px at 100% 0%, rgba(var(--ambient), 0.08), transparent 70%);
    transition: background 1.2s ease;
  }
  .body { flex: 1; display: flex; min-height: 0; position: relative; }
  .sidebar { flex: none; display: flex; flex-direction: column; min-height: 0; background: var(--bg-2); border-right: 1px solid var(--border); }
  .right { flex: none; display: flex; flex-direction: column; min-height: 0; padding: 14px 14px 14px 0; overflow-y: auto; }
  .panel-inner { flex: 1 0 auto; display: flex; flex-direction: column; min-height: 0; }
  .sidebar .panel-inner { flex: 1; }
  .panel-inner.end { align-self: flex-end; }
  .main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 12px; padding: 12px 0 12px; }
  .pick-bar { display: flex; align-items: center; gap: 10px; margin: 0 16px; padding: 8px 12px; border-radius: 12px; background: var(--accent-soft); color: var(--accent); font-weight: 600; }
  .pick-bar .ellipsis { flex: 1; min-width: 0; }
  .pick-bar .count { font-size: var(--fs-xs); font-weight: 400; flex: none; }
  .pick-bar .btn { display: inline-flex; align-items: center; gap: 6px; flex: none; }
  .loading { padding: 24px 16px; }
  .table-wrap { flex: 1; min-height: 0; display: flex; }
  .scrim { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.45); z-index: 50; }
  .drawer { position: fixed; top: 0; bottom: 0; left: 0; width: min(340px, 88vw); z-index: 51; touch-action: pan-y; background: var(--bg-2); display: flex; flex-direction: column; box-shadow: var(--shadow); overflow: auto; }
  .drawer.right-drawer { left: auto; right: 0; padding: 12px; }
  .status { display: flex; align-items: center; gap: 8px; padding: 4px 16px; font-size: var(--fs-sm); color: var(--muted); background: var(--bg-2); border-top: 1px solid var(--border); }
  .offline { color: var(--red); }
  .grow { flex: 1; }
  .job { display: flex; align-items: center; gap: 8px; min-width: 0; padding: 0 6px; border-radius: 6px; color: inherit; font: inherit; cursor: pointer; }
  .job:hover { background: var(--accent-soft); }
  .spinner { width: 10px; height: 10px; border: 2px solid var(--accent); border-right-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite; flex: none; }
  @keyframes spin { to { transform: rotate(360deg); } }
  @media (max-width: 900px) { .main { padding: 8px 0; gap: 8px; } }
</style>
