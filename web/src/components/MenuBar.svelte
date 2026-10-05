<script lang="ts">
  import { api } from '../lib/api';
  import { analyze, newPlaylist, saveFavoritesAsPlaylist, uploadFiles } from '../lib/actions';
  import { t } from '../lib/i18n.svelte';
  import { applyViewMode, prefs, savePrefs, type ThemeMode } from '../lib/prefs.svelte';
  import { data } from '../lib/stores/data.svelte';
  import { activeTab } from '../lib/stores/library.svelte';
  import { openDialog, openMenu, ui, type MenuItem } from '../lib/stores/ui.svelte';
  import SettingsDialog from './dialogs/SettingsDialog.svelte';
  import AboutDialog from './dialogs/AboutDialog.svelte';
  import Icon from './Icon.svelte';

  let fileInput = $state<HTMLInputElement | null>(null);

  function uploadTarget(): string | null {
    const tab = activeTab();
    return tab?.type === 'dir' ? tab.path : prefs.treeRoot;
  }

  function toggle(key: 'showTree' | 'showEffects' | 'showLights') {
    prefs[key] = !prefs[key];
    savePrefs();
  }

  function toggleFilter(key: keyof typeof prefs.filter) {
    prefs.filter[key] = !prefs.filter[key];
    savePrefs();
  }

  function setTheme(theme: ThemeMode) {
    prefs.theme = theme;
    savePrefs();
  }

  function setScale(scale: number) {
    prefs.fontScale = scale;
    savePrefs();
  }

  function fileMenu(): MenuItem[] {
    const tab = activeTab();
    return [
      { label: t('<New Playlist>'), icon: 'playlist', action: () => newPlaylist() },
      { label: t('Save Favorites'), icon: 'star', action: saveFavoritesAsPlaylist, disabled: !tab },
      { label: t('Upload songs…'), icon: 'upload', action: () => fileInput?.click(), disabled: !uploadTarget() },
      { separator: true },
      { label: t('Analyze Directory'), icon: 'sparkles', disabled: !tab || tab.type !== 'dir' || data.settings?.voxalyzerActive === false,
        action: () => tab && analyze([tab.path]) },
      { separator: true },
      { label: t('Settings'), icon: 'settings', action: () => openDialog(SettingsDialog) },
      ...(!data.auth?.local && data.auth?.password_set
        ? [{ label: t('Logout'), icon: 'logout', action: async () => { await api.logout(); location.reload(); } }]
        : []),
    ];
  }

  function viewMenu(): MenuItem[] {
    return [
      { label: t('Simple Mode'), action: () => applyViewMode('simple') },
      { label: t('Player Mode'), action: () => applyViewMode('player') },
      { label: t('Complex Mode'), action: () => applyViewMode('complex') },
      { separator: true },
      { label: t('Filter'), icon: 'filter', children: [
        { label: t('Presets'), checked: prefs.filter.presets, action: () => toggleFilter('presets') },
        { label: t('Circumplex model of emotion'), checked: prefs.filter.circumplex, action: () => toggleFilter('circumplex') },
        { label: t('Category Sliders'), checked: prefs.filter.sliders, action: () => toggleFilter('sliders') },
        { label: t('BPM'), checked: prefs.filter.bpm, action: () => toggleFilter('bpm') },
        { label: t('Tags'), checked: prefs.filter.tags, action: () => toggleFilter('tags') },
        { label: t('Genres'), checked: prefs.filter.genres, action: () => toggleFilter('genres') },
      ] },
      { label: t('Directory Tree'), checked: prefs.showTree, action: () => toggle('showTree') },
      { label: t('Effects Tree'), checked: prefs.showEffects, action: () => toggle('showEffects') },
      { label: t('Lights Manager'), checked: prefs.showLights, action: () => toggle('showLights') },
      { separator: true },
      { label: t('Font Size'), children: [
        { label: t('Smaller'), checked: prefs.fontScale < 1, shortcut: 'Ctrl -', action: () => setScale(0.9) },
        { label: t('Medium'), checked: prefs.fontScale === 1, shortcut: 'Ctrl 0', action: () => setScale(1) },
        { label: t('Larger'), checked: prefs.fontScale > 1, shortcut: 'Ctrl +', action: () => setScale(1.15) },
      ] },
      { label: t('Theme'), children: [
        { label: t('Light'), checked: prefs.theme === 'light', action: () => setTheme('light') },
        { label: t('Dark'), checked: prefs.theme === 'dark', action: () => setTheme('dark') },
      ] },
      { label: t('Fullscreen'), shortcut: 'F11', action: () => document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen() },
    ];
  }

  function helpMenu(): MenuItem[] {
    return [
      { label: t('Show Tour'), icon: 'info', action: () => (ui.tour = true) },
      { label: t('About'), icon: 'info', action: () => openDialog(AboutDialog) },
    ];
  }

  function show(event: MouseEvent, items: () => MenuItem[]) {
    const rect = (event.currentTarget as HTMLElement).getBoundingClientRect();
    event.stopPropagation();
    openMenu({ clientX: rect.left, clientY: rect.bottom + 4 }, items());
  }

  function onFiles(event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    const target = uploadTarget();
    if (target && input.files?.length) void uploadFiles(target, [...input.files]);
    input.value = '';
  }

  function cycleTheme() {
    setTheme(prefs.theme === 'light' ? 'dark' : 'light');
  }
</script>

<header class="bar" data-tour="menubar">
  {#if ui.narrow}
    <button class="icon-btn" title={t('Files')} onclick={(e) => { e.stopPropagation(); ui.mobilePanel = ui.mobilePanel === 'tree' ? null : 'tree'; }}><Icon name="folder" size={17} /></button>
  {/if}
  <img src="/icon.png" alt="" width="20" height="20" />
  <button class="menu-btn" onclick={(e) => show(e, fileMenu)}>{t('File')}</button>
  <button class="menu-btn" onclick={(e) => show(e, viewMenu)}>{t('View')}</button>
  <button class="menu-btn" onclick={(e) => show(e, helpMenu)}>{t('Help')}</button>
  <span class="grow"></span>
  {#if data.version?.newer}
    <a class="update" href={data.version.download} target="_blank" rel="noreferrer">{t('Newer version available {0}', data.version.latest ?? '')}</a>
  {/if}
  <button class="icon-btn" title={t('Theme')} onclick={cycleTheme}>
    <Icon name={prefs.theme === 'dark' ? 'moon' : 'sun'} size={16} />
  </button>
  <button class="icon-btn" title={t('Settings')} onclick={() => openDialog(SettingsDialog)}><Icon name="settings" size={16} /></button>
  {#if ui.narrow}
    <button class="icon-btn" title={t('Effects')} onclick={(e) => { e.stopPropagation(); ui.mobilePanel = ui.mobilePanel === 'side' ? null : 'side'; }}><Icon name="waves" size={17} /></button>
  {/if}
  <input bind:this={fileInput} type="file" accept=".mp3,audio/mpeg" multiple hidden onchange={onFiles} />
</header>

<style>
  .bar { display: flex; align-items: center; gap: 2px; padding: 6px 12px; min-height: 40px; }
  .bar img { margin-right: 8px; border-radius: 4px; }
  .menu-btn { padding: 5px 10px; border-radius: var(--radius-sm); }
  .menu-btn:hover { background: var(--hover); }
  .grow { flex: 1; }
  .update { color: var(--accent); font-size: var(--fs-sm); margin-right: 10px; }
</style>
