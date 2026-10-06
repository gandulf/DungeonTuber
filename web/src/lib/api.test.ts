import { describe, expect, it } from 'vitest';
import { pathToId } from './api';
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
