import { beforeEach, describe, expect, it } from 'vitest';
import { cached, cachedFirst, clearCache, remember, setCacheScope } from './cache';

describe('cached', () => {
  beforeEach(async () => {
    setCacheScope('');
    await clearCache();
  });

  it('shows the fetched value when nothing is cached', async () => {
    const shown: number[] = [];
    expect(await cached('a', async () => 1, (v) => shown.push(v))).toBe(1);
    expect(shown).toEqual([1]);
  });

  it('shows the cached value first and the new one only when it differs', async () => {
    await cached('a', async () => ({ n: 1 }), () => undefined);
    const shown: unknown[] = [];
    await cached('a', async () => ({ n: 1 }), (v) => shown.push(v));
    expect(shown).toEqual([{ n: 1 }]);
    await cached('a', async () => ({ n: 2 }), (v) => shown.push(v));
    expect(shown).toEqual([{ n: 1 }, { n: 1 }, { n: 2 }]);
  });

  it('keeps the cached value when the server cannot be reached', async () => {
    await cached('a', async () => 1, () => undefined);
    const shown: number[] = [];
    expect(await cached('a', () => Promise.reject(new Error('offline')), (v: number) => shown.push(v))).toBeUndefined();
    expect(shown).toEqual([1]);
  });

  it('throws when the server cannot be reached and nothing is cached', async () => {
    await expect(cached('a', () => Promise.reject(new Error('offline')), () => undefined)).rejects.toThrow('offline');
  });

  it('cachedFirst resolves with the cached value before the server answers', async () => {
    await cached('a', async () => 1, () => undefined);
    let answer: (value: number) => void = () => undefined;
    const shown: number[] = [];
    await cachedFirst('a', () => new Promise<number>((resolve) => (answer = resolve)), (v) => shown.push(v));
    expect(shown).toEqual([1]);
    answer(2);
    await new Promise((resolve) => setTimeout(resolve));
    expect(shown).toEqual([1, 2]);
  });

  it('cachedFirst throws when the server cannot be reached and nothing is cached', async () => {
    await expect(cachedFirst('a', () => Promise.reject(new Error('offline')), () => undefined)).rejects.toThrow('offline');
  });

  it('remember stores a value changed in the app', async () => {
    remember('a', { saved: true });
    const shown: unknown[] = [];
    await cached('a', () => Promise.reject(new Error('offline')), (v) => shown.push(v));
    expect(shown).toEqual([{ saved: true }]);
  });

  it('keeps the entries of every user apart', async () => {
    setCacheScope('alice');
    await cached('a', async () => 'secret', () => undefined);
    setCacheScope('bob');
    const shown: string[] = [];
    await cached('a', async () => 'public', (v) => shown.push(v));
    expect(shown).toEqual(['public']);
  });
});
