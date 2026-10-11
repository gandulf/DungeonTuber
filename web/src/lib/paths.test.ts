import { describe, expect, it } from 'vitest';
import { affectsDirectory } from './paths';

describe('effects sync', () => {
  it('reloads for changes in or around the effects directory only', () => {
    const effects = (path: string) => affectsDirectory(path, 'Music/Effekte');
    expect(effects('Music/Effekte')).toBe(true);
    expect(effects('Music/Effekte/Rain')).toBe(true);
    expect(effects('Music')).toBe(true); // the directory itself was renamed or deleted
    expect(effects('Music/Effekte2')).toBe(false);
    expect(effects('Music/Battle')).toBe(false);
    expect(affectsDirectory('Music/Effekte', null)).toBe(false);
  });
});
