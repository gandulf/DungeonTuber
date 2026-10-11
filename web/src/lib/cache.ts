// A cache of the library listings (folder tree, songs of folders and playlists) kept in the browser (IndexedDB): what was
// seen before shows at once, also after a restart, and the server is asked in the background (stale-while-revalidate).
// The entries belong to the signed in user (private playlists) and are dropped on logout.

const DB_NAME = 'dungeontuber-cache';
const STORE = 'entries';
/** Entries not used for this long are dropped on start. */
const MAX_AGE = 30 * 24 * 3600 * 1000;

interface Entry {
  json: string;
  at: number;
}

let scope = '';
const memory = new Map<string, string>();
let database: Promise<IDBDatabase | null> | null = null;

function done<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });
}

/** The database, or null where the browser has none (private mode, tests): then only the memory cache is used. */
function db(): Promise<IDBDatabase | null> {
  database ??= new Promise((resolve) => {
    try {
      const request = indexedDB.open(DB_NAME, 1);
      request.onupgradeneeded = () => request.result.createObjectStore(STORE);
      request.onsuccess = () => {
        resolve(request.result);
        void prune(request.result);
      };
      request.onerror = () => resolve(null);
    } catch {
      resolve(null);
    }
  });
  return database;
}

async function prune(handle: IDBDatabase) {
  try {
    const store = handle.transaction(STORE, 'readwrite').objectStore(STORE);
    const entries = await done(store.getAll());
    const keys = await done(store.getAllKeys());
    const now = Date.now();
    entries.forEach((entry: Entry, index) => now - entry.at > MAX_AGE && store.delete(keys[index]));
  } catch { /* the cache is optional */ }
}

async function read(key: string): Promise<string | undefined> {
  const handle = await db();
  if (!handle) return undefined;
  try {
    const entry: Entry | undefined = await done(handle.transaction(STORE).objectStore(STORE).get(key));
    return entry?.json;
  } catch {
    return undefined;
  }
}

async function write(key: string, json: string) {
  const handle = await db();
  if (!handle) return;
  try {
    handle.transaction(STORE, 'readwrite').objectStore(STORE).put({ json, at: Date.now() } satisfies Entry, key);
  } catch { /* quota exceeded or storage unavailable: the cache is optional */ }
}

/** The signed in user: every user has entries of their own. */
export function setCacheScope(user: string | null | undefined) {
  if ((user ?? '') === scope) return;
  scope = user ?? '';
  memory.clear();
}

/** Drops every entry (on logout). */
export async function clearCache() {
  memory.clear();
  const handle = await db();
  if (!handle) return;
  try {
    await done(handle.transaction(STORE, 'readwrite').objectStore(STORE).clear());
  } catch { /* nothing to drop */ }
}

/**
 * Hands the cached value to `show` at once (if there is one), then fetches the current one and hands it over as well
 * when it differs. Resolves with the current value; when the server cannot be reached, the cached value stays and the
 * error is only thrown if there was nothing cached.
 */
export async function cached<T>(key: string, fetch: () => Promise<T>, show: (value: T) => void): Promise<T | undefined> {
  const full = `${scope}\u0000${key}`;
  const pending = fetch(); // already on its way while the cache is read
  pending.catch(() => undefined); // handled below; keeps the browser from reporting it before that
  const shown = memory.get(full) ?? (await read(full));
  if (shown !== undefined) {
    memory.set(full, shown);
    show(JSON.parse(shown));
  }
  let value: T;
  try {
    value = await pending;
  } catch (e) {
    if (shown === undefined) throw e;
    return undefined;
  }
  const json = JSON.stringify(value);
  if (json !== shown) show(value);
  if (json !== memory.get(full)) {
    memory.set(full, json);
    void write(full, json);
  }
  return value;
}
