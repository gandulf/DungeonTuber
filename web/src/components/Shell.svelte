<script lang="ts">
  import { coverUrl } from '../lib/api';
  import { applyAmbient } from '../lib/ambient';
  import { prefs, savePrefs } from '../lib/prefs.svelte';
  import { openDownloadsDialog } from '../lib/actions';
  import { t } from '../lib/i18n.svelte';
  import { data } from '../lib/stores/data.svelte';
  import { downloads } from '../lib/stores/downloads.svelte';
  import { effects } from '../lib/stores/effects.svelte';
  import { activeTab, library } from '../lib/stores/library.svelte';
  import { cycleRepeat, next, player, previous, setVolume, toggleEffect, toggleMute, togglePlay } from '../lib/stores/player.svelte';
  import { closeMenu, ui } from '../lib/stores/ui.svelte';
  import ConfirmDialog from './dialogs/ConfirmDialog.svelte';
  import PromptDialog from './dialogs/PromptDialog.svelte';
  import ContextMenu from './ContextMenu.svelte';
  import FilterPanel from './filter/FilterPanel.svelte';
  import TagBar from './filter/TagBar.svelte';
  import MenuBar from './MenuBar.svelte';
  import PlayerBar from './player/PlayerBar.svelte';
  import RightPanel from './RightPanel.svelte';
  import Sidebar from './Sidebar.svelte';
  import Splitter from './Splitter.svelte';
  import SongTable from './table/SongTable.svelte';
  import Toasts from './Toasts.svelte';
  import Tour from './Tour.svelte';
  import Welcome from './Welcome.svelte';

  const tab = $derived(activeTab());
  const showRight = $derived(prefs.showEffects || (prefs.showLights && data.settings?.lightsEnabled !== false));

  $effect(() => {
    // the server remembers it per user: the desktop app gets a new port (and so an empty browser storage) on every start
    if (!prefs.tourDone && !data.user.tour_done) setTimeout(() => (ui.tour = true), 600);
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

<svelte:window onkeydown={onKeydown} onclick={closeMenu} onblur={closeMenu} />

<div class="app">
  <div class="aura" aria-hidden="true"></div>
  <div class="body">
    {#if ui.narrow}
      {#if ui.mobilePanel}
        <div class="scrim" role="presentation" onclick={() => (ui.mobilePanel = null)}></div>
        <aside class="drawer" class:right-drawer={ui.mobilePanel === 'side'}>
          {#if ui.mobilePanel === 'tree'}<Sidebar />{:else}<RightPanel />{/if}
        </aside>
      {/if}
    {:else}
      <aside class="sidebar" style:width="{prefs.leftWidth}px" data-tour="tree"><Sidebar /></aside>
      <Splitter bind:size={prefs.leftWidth} min={200} max={480} onchange={savePrefs} />
    {/if}

    <main class="main">
      <MenuBar />
      <FilterPanel />
      <TagBar />
      {#if library.tabs.length && tab}
        <div class="table-wrap" data-tour="table"><SongTable {tab} /></div>
      {:else}
        <Welcome />
      {/if}
    </main>

    {#if showRight && !ui.narrow}
      <Splitter bind:size={prefs.rightWidth} min={260} max={480} invert onchange={savePrefs} />
      <aside class="right" style:width="{prefs.rightWidth}px"><RightPanel /></aside>
    {/if}
  </div>

  <PlayerBar />
  {#if ui.progress || !ui.connected || downloads.pending}
    <div class="status">
      {#if !ui.connected}<span class="offline">● offline – reconnecting…</span>{/if}
      {#if ui.progress}<span class="spinner"></span><span class="ellipsis">{ui.progress}</span>{/if}
      {#if downloads.pending}
        {@const current = downloads.items.find((item) => item.state === 'downloading')}
        <button class="downloads" onclick={openDownloadsDialog} title={t('Show downloads')}>
          <span class="spinner"></span>
          <span class="ellipsis">{t('Downloads: {0} remaining', downloads.pending)}{current ? ` · ${current.title} ${current.percent}%` : ''}</span>
        </button>
      {/if}
    </div>
  {/if}
</div>

<ContextMenu />
<Toasts />
<PromptDialog />
<ConfirmDialog />
{#if ui.dialog}
  {@const Dialog = ui.dialog.component}
  <Dialog {...ui.dialog.props} />
{/if}
{#if ui.tour}<Tour />{/if}

<style>
  .app { height: 100%; display: flex; flex-direction: column; position: relative; isolation: isolate; }
  .aura {
    position: absolute; inset: 0; z-index: -1; pointer-events: none;
    background:
      radial-gradient(1200px 520px at 50% 115%, rgba(var(--ambient), 0.22), transparent 70%),
      radial-gradient(700px 400px at 100% 0%, rgba(var(--ambient), 0.08), transparent 70%);
    transition: background 1.2s ease;
  }
  .body { flex: 1; display: flex; min-height: 0; }
  .sidebar { flex: none; display: flex; flex-direction: column; min-height: 0; background: var(--bg-2); border-right: 1px solid var(--border); }
  .right { flex: none; display: flex; flex-direction: column; min-height: 0; padding: 14px 14px 14px 0; overflow-y: auto; }
  .main { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 12px; padding: 12px 0 12px; }
  .table-wrap { flex: 1; min-height: 0; display: flex; }
  .scrim { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.45); z-index: 50; }
  .drawer { position: fixed; top: 0; bottom: 0; left: 0; width: min(340px, 88vw); z-index: 51; background: var(--bg-2); display: flex; flex-direction: column; box-shadow: var(--shadow); overflow: auto; }
  .drawer.right-drawer { left: auto; right: 0; padding: 12px; }
  .status { display: flex; align-items: center; gap: 8px; padding: 4px 16px; font-size: var(--fs-sm); color: var(--muted); background: var(--bg-2); border-top: 1px solid var(--border); }
  .offline { color: var(--red); }
  .downloads { display: flex; align-items: center; gap: 8px; min-width: 0; margin-left: auto; padding: 0 6px; border-radius: 6px; color: inherit; font: inherit; cursor: pointer; }
  .downloads:hover { background: var(--accent-soft); }
  .spinner { width: 10px; height: 10px; border: 2px solid var(--accent); border-right-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite; flex: none; }
  @keyframes spin { to { transform: rotate(360deg); } }
  @media (max-width: 900px) { .main { padding: 8px 0; gap: 8px; } }
</style>
