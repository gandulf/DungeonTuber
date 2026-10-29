import { afterEach, describe, expect, it, vi } from 'vitest';
import { api, ApiError, pathToId } from './api';
import { volumeToGain } from './audio/engine';

describe('pathToId', () => {
  it('matches server.paths.path_to_id', () => {
    // python -c "from server.paths import path_to_id; print(path_to_id('C:/Musik/Söldner Ehre?/a+b.mp3'))"
    expect(pathToId('C:/Musik/Söldner Ehre?/a+b.mp3')).toBe('QzovTXVzaWsvU8O2bGRuZXIgRWhyZT8vYStiLm1wMw');
  });
});

describe('volumeToGain', () => {
  it('uses the desktop volume curve', () => {
    expect(volumeToGain(100)).toBe(1);
    expect(volumeToGain(150)).toBeCloseTo(2.25);
    expect(volumeToGain(70)).toBeCloseTo(0.49);
    expect(volumeToGain(80, true)).toBe(0);
    expect(volumeToGain(400)).toBeCloseTo(2.25);
  });
});

describe('errors', () => {
  afterEach(() => vi.unstubAllGlobals());
  const answer = (status: number, statusText: string, body: string) =>
    vi.stubGlobal('fetch', vi.fn(async () => new Response(body, { status, statusText, headers: { 'Content-Type': 'application/json' } })));

  it('carries the detail of the server, else the status text', async () => {
    answer(404, 'Not Found', JSON.stringify({ detail: 'Adventure not found' }));
    await expect(api.adventure('x')).rejects.toMatchObject({ status: 404, message: 'Adventure not found' });
    answer(500, 'Internal Server Error', JSON.stringify({ error: 'boom' }));
    const error = await api.adventure('x').catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).message).toBe('Internal Server Error');
  });
});
