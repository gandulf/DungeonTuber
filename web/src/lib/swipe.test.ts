import { describe, expect, it } from 'vitest';
import { swipeOf } from './swipe';

describe('swipeOf', () => {
  it('takes a long, quick, horizontal movement as a swipe', () => {
    expect(swipeOf(-120, 10, 200)).toBe('left');
    expect(swipeOf(90, -20, 300)).toBe('right');
  });

  it('ignores short, slow or mostly vertical movements', () => {
    expect(swipeOf(-30, 0, 100)).toBeNull(); // too short
    expect(swipeOf(-120, 0, 900)).toBeNull(); // too slow: a drag
    expect(swipeOf(-100, 90, 200)).toBeNull(); // a diagonal scroll
    expect(swipeOf(0, 200, 200)).toBeNull();
  });
});
