// After the server was updated, the parts of the app that belong to the old build are gone from it (their names carry a hash). A window that
// was open meanwhile finds out when it loads one of them later (the notes editor, the PDF viewer, ...): "Failed to fetch dynamically imported
// module". Loading the page again fetches the new build. It happens once in a while only, so that a server that really lacks a file does not
// make the page reload in a loop.

const KEY = 'dt-update-reload';
export const RELOAD_PAUSE_MS = 30_000;

/** Whether a reload for a missing part is allowed now: not when the page reloaded for it a moment ago. */
export const mayReload = (now: number, last: number) => !(last > 0 && now - last < RELOAD_PAUSE_MS);

function lastReload(): number {
  try {
    return Number(sessionStorage.getItem(KEY) ?? 0);
  } catch {
    return 0; // no storage (private window): the pause cannot be kept, the reload happens anyway
  }
}

/** Reloads the page (once per pause) after `prepare` (it saves what is waiting to be saved). Returns whether it does. */
export function reloadForUpdate(prepare: () => Promise<unknown> = async () => undefined, reload: () => void = () => location.reload()): boolean {
  if (!mayReload(Date.now(), lastReload())) return false;
  try {
    sessionStorage.setItem(KEY, String(Date.now()));
  } catch {
    // see above
  }
  void prepare().catch(() => undefined).finally(reload);
  return true;
}

/** True for the error of an import() that could not load its file. */
export const isMissingPart = (reason: unknown) => {
  const text = reason instanceof Error ? reason.message : String(reason ?? '');
  return /Failed to fetch dynamically imported module|error loading dynamically imported module|Importing a module script failed/i.test(text);
};
