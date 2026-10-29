import { mount } from 'svelte';
import './app.css';
import App from './App.svelte';
import { t } from './lib/i18n.svelte';
import { flushSave } from './lib/stores/adventure.svelte';
import { toast } from './lib/stores/ui.svelte';
import { isMissingPart, reloadForUpdate } from './lib/updateReload';

const app = mount(App, { target: document.getElementById('app')! });

// the service worker makes the app installable and starts it from the cache (only in the build: the dev server reloads itself)
if (import.meta.env.PROD && 'serviceWorker' in navigator) {
  window.addEventListener('load', () => void navigator.serviceWorker.register('/sw.js').catch(() => undefined));
}

// the server was updated while this window was open: a part of the app that is loaded later (the notes editor, the PDF viewer) is gone from it.
// The page loads again (what waits to be saved is saved first) and has the new version.
function updated() {
  if (reloadForUpdate(flushSave)) toast(t('The app was updated. The page reloads now.'), 'info', 4000);
}
window.addEventListener('vite:preloadError', updated);
window.addEventListener('unhandledrejection', (event) => isMissingPart(event.reason) && updated());

export default app;
