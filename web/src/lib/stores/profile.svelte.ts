// The view preferences a user takes along to every device (panels, filter widgets, song table layout, effects list, import options).
// They are kept on the server with the user profile; what only fits one device (theme, font size, panel widths, folder tree state) stays in the browser.
import { api } from '../api';
import { prefs, savePrefs } from '../prefs.svelte';
import type { ViewSettings } from '../types';

const currentView = (): ViewSettings => ({
  showEffects: prefs.showEffects, showLights: prefs.showLights, filter: prefs.filter, moodCollapsed: prefs.moodCollapsed, showMoodMap: prefs.showMoodMap,
  columns: prefs.columns, columnWidths: prefs.columnWidths, hiddenCategories: prefs.hiddenCategories, titleInsteadOfFile: prefs.titleInsteadOfFile,
  summaryUnderTitle: prefs.summaryUnderTitle, rowStyle: prefs.rowStyle, effectsGrid: prefs.effectsGrid, effectsTitle: prefs.effectsTitle, importOptions: prefs.importOptions,
});
let known = ''; // what the server has (or is being sent)
let loaded = $state(false);

/** Applies the view saved in the profile; a profile without it keeps (and from then on saves) what this browser has. */
export function applyViewSettings(saved: Partial<ViewSettings> | null) {
  if (saved) {
    const { filter, columns, columnWidths, importOptions, ...rest } = saved;
    Object.assign(prefs, rest);
    if (filter) prefs.filter = { ...prefs.filter, ...filter };
    if (columns) prefs.columns = { ...prefs.columns, ...columns };
    if (columnWidths) prefs.columnWidths = { ...columnWidths };
    if (importOptions) prefs.importOptions = { ...prefs.importOptions, ...importOptions };
    known = JSON.stringify(currentView());
    savePrefs();
  }
  loaded = true;
}

$effect.root(() => {
  $effect(() => {
    const serialized = JSON.stringify(currentView());
    if (!loaded || serialized === known) return;
    const timer = setTimeout(() => {
      known = serialized;
      void api.putUserState({ view: JSON.parse(serialized) }).catch(() => undefined);
    }, 800);
    return () => clearTimeout(timer);
  });
});
