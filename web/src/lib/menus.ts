// Application menu (former File / View / Help menus).
import { api } from './api';
import { analyze, newPlaylist, openUploadDialog, rescanLibrary, saveFavoritesAsPlaylist } from './actions';
import { t } from './i18n.svelte';
import { applyViewMode, prefs, savePrefs, type ThemeMode } from './prefs.svelte';
import { data } from './stores/data.svelte';
import { activeTab } from './stores/library.svelte';
import { openDialog, ui, type MenuItem } from './stores/ui.svelte';
import AboutDialog from '../components/dialogs/AboutDialog.svelte';
import SettingsDialog from '../components/dialogs/SettingsDialog.svelte';

export function setTheme(theme: ThemeMode) {
  prefs.theme = theme;
  savePrefs();
}

function toggle(key: 'showEffects' | 'showLights') {
  prefs[key] = !prefs[key];
  savePrefs();
}

function toggleFilter(key: keyof typeof prefs.filter) {
  prefs.filter[key] = !prefs.filter[key];
  savePrefs();
}

function setScale(scale: number) {
  prefs.fontScale = scale;
  savePrefs();
}

export function openSettings() {
  openDialog(SettingsDialog);
}

export function appMenu(): MenuItem[] {
  const tab = activeTab();
  return [
    { label: t('New Playlist…'), icon: 'playlist', action: () => newPlaylist() },
    { label: t('Save Favorites'), icon: 'heart', action: saveFavoritesAsPlaylist, disabled: !tab },
    { label: t('Upload songs…'), icon: 'upload', action: () => openUploadDialog() },
    { label: t('Analyze Directory'), icon: 'sparkles', disabled: !tab || tab.type !== 'dir' || data.settings?.voxalyzerActive === false,
      action: () => tab && analyze([tab.path]) },
    { label: t('Rescan Library'), icon: 'refresh', action: () => rescanLibrary(tab?.type === 'dir' ? tab.path : undefined) },
    { separator: true },
    { label: t('View'), icon: 'grid', children: [
      { label: t('Simple Mode'), action: () => applyViewMode('simple') },
      { label: t('Player Mode'), action: () => applyViewMode('player') },
      { label: t('Complex Mode'), action: () => applyViewMode('complex') },
      { separator: true },
      { label: t('Effects Tree'), checked: prefs.showEffects, action: () => toggle('showEffects') },
      { label: t('Lights Manager'), checked: prefs.showLights, action: () => toggle('showLights') },
      { separator: true },
      { label: t('Fullscreen'), shortcut: 'F11', action: () => (document.fullscreenElement ? document.exitFullscreen() : document.documentElement.requestFullscreen()) },
    ] },
    { label: t('Filter'), icon: 'filter', children: [
      { label: t('Presets'), checked: prefs.filter.presets, action: () => toggleFilter('presets') },
      { label: t('Circumplex model of emotion'), checked: prefs.filter.circumplex, action: () => toggleFilter('circumplex') },
      { label: t('Category Sliders'), checked: prefs.filter.sliders, action: () => toggleFilter('sliders') },
      { label: t('BPM'), checked: prefs.filter.bpm, action: () => toggleFilter('bpm') },
      { label: t('Tags'), checked: prefs.filter.tags, action: () => toggleFilter('tags') },
      { label: t('Genres'), checked: prefs.filter.genres, action: () => toggleFilter('genres') },
    ] },
    { label: t('Font Size'), icon: 'sliders', children: [
      { label: t('Smaller'), checked: prefs.fontScale < 1, shortcut: 'Ctrl -', action: () => setScale(0.9) },
      { label: t('Medium'), checked: prefs.fontScale === 1, shortcut: 'Ctrl 0', action: () => setScale(1) },
      { label: t('Larger'), checked: prefs.fontScale > 1, shortcut: 'Ctrl +', action: () => setScale(1.15) },
    ] },
    { label: t('Theme'), icon: prefs.theme === 'dark' ? 'moon' : 'sun', children: [
      { label: t('Light'), checked: prefs.theme === 'light', action: () => setTheme('light') },
      { label: t('Dark'), checked: prefs.theme === 'dark', action: () => setTheme('dark') },
    ] },
    { separator: true },
    { label: t('Settings'), icon: 'settings', action: openSettings },
    { label: t('Show Tour'), icon: 'compass', action: () => (ui.tour = true) },
    { label: t('About'), icon: 'info', action: () => openDialog(AboutDialog) },
    ...(!data.auth?.local && data.auth?.password_set
      ? [{ label: `${t('Logout')} (${data.auth.user})`, icon: 'logout', action: async () => { await api.logout(); location.reload(); } }]
      : []),
  ];
}
