import { describe, expect, it } from 'vitest';
import { inPanelZone, panelGesture, swipeOf } from './swipe';

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

describe('panelGesture', () => {
  const closed = { width: 1000, left: { open: false, border: null }, right: { open: false, border: null, available: true } };
  const docked = { width: 1000, left: { open: true, border: 260 }, right: { open: true, border: 695, available: true } };

  it('opens a closed panel with a swipe from its screen edge inwards', () => {
    expect(panelGesture(10, 'right', closed)).toEqual({ side: 'left', open: true });
    expect(panelGesture(990, 'left', closed)).toEqual({ side: 'right', open: true });
    expect(panelGesture(10, 'left', closed)).toBeNull();
    expect(panelGesture(500, 'right', closed)).toBeNull(); // not at an edge
    expect(panelGesture(990, 'left', { ...closed, right: { ...closed.right, available: false } })).toBeNull(); // nothing to show
  });

  it('closes an open docked panel with a swipe on its border towards its edge', () => {
    expect(panelGesture(270, 'left', docked)).toEqual({ side: 'left', open: false });
    expect(panelGesture(690, 'right', docked)).toEqual({ side: 'right', open: false });
    expect(panelGesture(270, 'right', docked)).toBeNull();
    expect(panelGesture(400, 'left', docked)).toBeNull();
  });

  it('knows which touches belong to the panels', () => {
    expect([inPanelZone(5, closed), inPanelZone(995, closed), inPanelZone(500, closed)]).toEqual([true, true, false]);
    expect([inPanelZone(5, docked), inPanelZone(250, docked), inPanelZone(700, docked)]).toEqual([false, true, true]);
  });
});
