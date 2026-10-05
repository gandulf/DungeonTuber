<script lang="ts">
  import { prefs, savePrefs } from '../lib/prefs.svelte';
  import { activeTab, library } from '../lib/stores/library.svelte';
  import { cycleRepeat, next, player, previous, setVolume, toggleEffect, toggleMute, togglePlay } from '../lib/stores/player.svelte';
  import { closeMenu, ui } from '../lib/stores/ui.svelte';
  import MenuBar from './MenuBar.svelte';
  import Sidebar from './Sidebar.svelte';
  import FilterPanel from './filter/FilterPanel.svelte';
  import Tabs from './Tabs.svelte';
  import SongTable from './table/SongTable.svelte';
  import Welcome from './Welcome.svelte';
  import PlayerBar from './player/PlayerBar.svelte';
  import EffectsPanel from './EffectsPanel.svelte';
  import LightsPanel from './LightsPanel.svelte';
  import ContextMenu from './ContextMenu.svelte';
  import Toasts from './Toasts.svelte';
  import PromptDialog from './dialogs/PromptDialog.svelte';
  import ConfirmDialog from './dialogs/ConfirmDialog.svelte';
  import Splitter from './Splitter.svelte';
  import Tour from './Tour.svelte';
  import { data } from '../lib/stores/data.svelte';
  import { lights } from '../lib/stores/lights.svelte';

  const tab = $derived(activeTab());
  const showRight = $derived(prefs.showEffects || (prefs.showLights && data.settings?.lightsWidget !== false && lights.list.length > 0));

  $effect(() => {
    if (!prefs.tourDone) setTimeout(() => (ui.tour = true), 600);
  });

  function typing(event: KeyboardEvent): boolean {
    const target = event.target as HTMLElement;
    return target.isContentEditable || ['INPUT', 'TEXTAREA', 'SELECT'].includes(target.tagName);
  }

  function onKeydown(event: KeyboardEvent) {
    if (event.key === 'F11') {
      event.preventDefault();
      if (document.fullscreenElement) void document.exitFullscreen();
      else void document.documentElement.requestFullscreen();
      return;
    }
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

  function setScale(scale: number) {
    prefs.fontScale = Math.round(Math.max(0.8, Math.min(1.5, scale)) * 10) / 10;
    savePrefs();
  }

  $effect(() => {
    document.title = player.track ? `${player.playing ? '▶ ' : ''}${player.track.title || player.track.name} · Dungeon Tuber` : 'Dungeon Tuber';
  });
</script>

<svelte:window onkeydown={onKeydown} onclick={closeMenu} onblur={closeMenu} />

<div class="app">
  <MenuBar />
  <div class="main">
    {#if ui.narrow}
      {#if ui.mobilePanel}
        <div class="scrim" role="presentation" onclick={() => (ui.mobilePanel = null)}></div>
        <aside class="drawer" class:right-drawer={ui.mobilePanel === 'side'}>
          {#if ui.mobilePanel === 'tree'}<Sidebar />{:else}
            {#if prefs.showEffects}<EffectsPanel />{/if}
            {#if prefs.showLights && data.settings?.lightsWidget !== false}<LightsPanel />{/if}
          {/if}
        </aside>
      {/if}
    {:else if prefs.showTree}
      <aside class="left" style:width="{prefs.leftWidth}px" data-tour="tree">
        <Sidebar />
      </aside>
      <Splitter bind:size={prefs.leftWidth} min={180} max={520} onchange={savePrefs} />
    {/if}

    <section class="center">
      <FilterPanel />
      {#if library.tabs.length}
        <Tabs />
        <div class="table-wrap" data-tour="table">
          {#if tab}<SongTable {tab} />{/if}
        </div>
      {:else}
        <Welcome />
      {/if}
    </section>

    {#if showRight && !ui.narrow}
      <Splitter bind:size={prefs.rightWidth} min={220} max={520} invert onchange={savePrefs} />
      <aside class="right" style:width="{prefs.rightWidth}px">
        {#if prefs.showEffects}<EffectsPanel />{/if}
        {#if prefs.showLights && data.settings?.lightsWidget !== false}<LightsPanel />{/if}
      </aside>
    {/if}
  </div>
  <PlayerBar />
  {#if ui.progress || !ui.connected}
    <div class="status">
      {#if !ui.connected}<span class="offline">● offline – reconnecting…</span>{/if}
      {#if ui.progress}<span class="spinner"></span><span class="ellipsis">{ui.progress}</span>{/if}
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
  .app { height: 100%; display: flex; flex-direction: column; }
  .main { flex: 1; display: flex; min-height: 0; padding: 0 10px; gap: 0; }
  .left, .right { flex: none; display: flex; flex-direction: column; min-height: 0; gap: 10px; padding: 4px 0 10px; }
  .center { flex: 1; min-width: 0; display: flex; flex-direction: column; padding: 4px 0 10px; }
  .table-wrap { flex: 1; min-height: 0; display: flex; }
  .scrim { position: fixed; inset: 0; background: rgba(0, 0, 0, 0.35); z-index: 50; }
  .drawer { position: fixed; top: 0; bottom: 0; left: 0; width: min(340px, 88vw); z-index: 51; background: var(--bg); padding: 12px; display: flex; flex-direction: column; gap: 10px; box-shadow: var(--shadow); overflow: auto; }
  .drawer.right-drawer { left: auto; right: 0; }
  @media (max-width: 900px) {
    .main { padding: 0 6px; }
  }
  .status { display: flex; align-items: center; gap: 8px; padding: 3px 14px; font-size: var(--fs-sm); color: var(--muted); border-top: 1px solid var(--border); background: var(--surface); }
  .offline { color: var(--red); }
  .spinner { width: 10px; height: 10px; border: 2px solid var(--accent); border-right-color: transparent; border-radius: 50%; animation: spin 0.8s linear infinite; flex: none; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
