<script lang="ts">
  import { onMount } from 'svelte';
  import { libraryRootsChanged } from './lib/actions';
  import { applyAccent } from './lib/accent';
  import { api, setUnauthorizedHandler } from './lib/api';
  import { t } from './lib/i18n.svelte';
  import { prefs } from './lib/prefs.svelte';
  import { data, loadAuth, loadData } from './lib/stores/data.svelte';
  import { downloads, setDownloads } from './lib/stores/downloads.svelte';
  import { loadEffects, updateEffectTrack } from './lib/stores/effects.svelte';
  import { reloadDirTabs, reloadPlaylistTabs, restoreTabs, updateTrack } from './lib/stores/library.svelte';
  import { loadLights, setLightState } from './lib/stores/lights.svelte';
  import { applyPlayerSettings, refreshCurrentTrack } from './lib/stores/player.svelte';
  import { toast, ui } from './lib/stores/ui.svelte';
  import { connectEvents, disconnectEvents, onEvent } from './lib/ws';
  import Login from './components/Login.svelte';
  import Shell from './components/Shell.svelte';

  let ready = $state(false);
  let failed = $state<string | null>(null);

  // theme & font scale
  $effect(() => {
    document.documentElement.dataset.theme = prefs.theme === 'dark' ? 'dark' : 'light';
    applyAccent(prefs.accent, prefs.theme === 'dark');
    document.documentElement.style.setProperty('--scale', String(prefs.fontScale));
  });

  async function start() {
    try {
      const auth = await loadAuth();
      if (!auth.authenticated) {
        ready = true;
        return;
      }
      await loadData();
      applyPlayerSettings(data.user.player);
      restoreTabs();
      void loadEffects();
      void api.importStatus().then(setDownloads).catch(() => undefined);
      if (data.settings?.lightsEnabled) void loadLights().catch(() => undefined);
      connectEvents();
      ready = true;
    } catch (e) {
      failed = e instanceof Error ? e.message : String(e);
    }
  }

  onMount(() => {
    setUnauthorizedHandler(() => {
      if (data.auth) data.auth.authenticated = false;
      disconnectEvents();
    });
    const unsubscribe = [
      onEvent('track.updated', (track) => {
        if (!track) return;
        updateTrack(track);
        updateEffectTrack(track);
        refreshCurrentTrack(track);
      }),
      onEvent('playlist.changed', ({ path }) => reloadPlaylistTabs(path)),
      onEvent('library.changed', ({ path }) => reloadDirTabs(path)),
      onEvent('library.roots', () => void libraryRootsChanged()),
      onEvent('lights.state', (list) => setLightState(list)),
      onEvent('analysis.progress', ({ message }) => (ui.progress = message)),
      onEvent('analysis.status', ({ pending }) => pending === 0 && (ui.progress = null)),
      onEvent('analysis.available', ({ active }) => data.settings && (data.settings.voxalyzerActive = active)),
      onEvent('analysis.error', ({ message }) => toast(message, 'error')),
      onEvent('import.items', (status) => {
        if (!setDownloads(status)) return;
        if (status.done) toast(t('Import finished: {0} songs', status.done), 'success');
        if (status.failed) toast(t('{0} songs could not be imported', status.failed), 'error');
      }),
      onEvent('import.error', ({ message }) => toast(message, 'error')),
      onEvent('connection', ({ connected }) => (ui.connected = connected)),
    ];
    void start();
    return () => unsubscribe.forEach((off) => off());
  });

  async function loggedIn() {
    ready = false;
    await start();
  }
</script>

{#if failed}
  <div class="center">
    <div class="panel box">
      <h2>Dungeon Tuber</h2>
      <p>Server not reachable: {failed}</p>
      <button class="btn primary" onclick={() => { failed = null; void start(); }}>Retry</button>
    </div>
  </div>
{:else if !ready}
  <div class="center muted">Loading…</div>
{:else if !data.auth?.authenticated}
  <Login onLogin={loggedIn} />
{:else}
  <Shell />
{/if}

<style>
  .center { height: 100%; display: grid; place-items: center; }
  .box { padding: 24px 28px; max-width: 420px; }
</style>
