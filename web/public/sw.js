// Service worker of the installable app: keeps the app shell (index.html and the hashed build assets). The page comes from
// the server when it answers (so an update is picked up at once) and from the cache otherwise; the assets always come from
// the cache once loaded. API calls, the WebSocket, songs and covers always go to the server (the HTTP cache keeps covers).
const SHELL = 'dt-shell-v1';

self.addEventListener('install', (event) => {
  event.waitUntil(caches.open(SHELL).then((cache) => cache.addAll(['/', '/manifest.webmanifest', '/icon.png'])).catch(() => undefined));
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil((async () => {
    for (const key of await caches.keys()) if (key !== SHELL) await caches.delete(key);
    await self.clients.claim();
  })());
});

/** index.html from the server when it answers (a new version drops the assets of the old one), else from the cache. */
async function page(request) {
  const cache = await caches.open(SHELL);
  try {
    const response = await fetch(request);
    if (response.ok) {
      const html = await response.clone().text();
      await cache.put('/', response.clone());
      const used = new Set([...html.matchAll(/\/assets\/[^"')\s]+/g)].map((match) => match[0]));
      for (const old of await cache.keys()) {
        const path = new URL(old.url).pathname;
        if (path.startsWith('/assets/') && !used.has(path)) await cache.delete(old);
      }
    }
    return response;
  } catch (e) {
    const fallback = await cache.match('/');
    if (fallback) return fallback;
    throw e;
  }
}

/** Build assets carry a hash in their name and never change. */
async function asset(request) {
  const cache = await caches.open(SHELL);
  const hit = await cache.match(request);
  if (hit) return hit;
  const response = await fetch(request);
  if (response.ok) await cache.put(request, response.clone());
  return response;
}

self.addEventListener('fetch', (event) => {
  const request = event.request;
  if (request.method !== 'GET') return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;
  if (request.mode === 'navigate') event.respondWith(page(request));
  else if (url.pathname.startsWith('/assets/')) event.respondWith(asset(request));
});
