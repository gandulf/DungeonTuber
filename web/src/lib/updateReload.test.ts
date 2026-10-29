import { afterEach, describe, expect, it, vi } from 'vitest';
import { isMissingPart, mayReload, RELOAD_PAUSE_MS, reloadForUpdate } from './updateReload';

describe('mayReload', () => {
  it('allows the first reload and one after the pause, not one right after another', () => {
    expect(mayReload(1_000_000, 0)).toBe(true);
    expect(mayReload(1_000_000, 1_000_000 - RELOAD_PAUSE_MS + 1)).toBe(false);
    expect(mayReload(1_000_000, 1_000_000 - RELOAD_PAUSE_MS - 1)).toBe(true);
  });
});

describe('isMissingPart', () => {
  it('knows the errors of browsers for a part that cannot be loaded', () => {
    expect(isMissingPart(new TypeError('Failed to fetch dynamically imported module: https://x/assets/NotesEditor-1.js'))).toBe(true);
    expect(isMissingPart(new TypeError('error loading dynamically imported module: https://x/a.js'))).toBe(true);
    expect(isMissingPart(new TypeError('Importing a module script failed.'))).toBe(true);
    expect(isMissingPart(new Error('Something else'))).toBe(false);
    expect(isMissingPart(undefined)).toBe(false);
  });
});

describe('reloadForUpdate', () => {
  afterEach(() => sessionStorage.clear());

  it('saves first, then reloads, and only once in a while', async () => {
    vi.stubGlobal('sessionStorage', (() => {
      const store = new Map<string, string>();
      return { getItem: (key: string) => store.get(key) ?? null, setItem: (key: string, value: string) => void store.set(key, value), clear: () => store.clear() };
    })());
    const order: string[] = [];
    const reload = () => order.push('reload');
    expect(reloadForUpdate(async () => void order.push('save'), reload)).toBe(true);
    await vi.waitFor(() => expect(order).toEqual(['save', 'reload']));
    expect(reloadForUpdate(async () => undefined, reload)).toBe(false); // a moment later: no loop
    vi.unstubAllGlobals();
  });
});
