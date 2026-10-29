// Touch screens: the side panels open with a swipe from the edge of the screen and close with a swipe on their border towards their edge.
// (The flyouts of tablets and phones close with a swipe of their own, see Shell.svelte.)
import { prefs, savePrefs } from './prefs.svelte';
import { data } from './stores/data.svelte';
import { ui } from './stores/ui.svelte';
import { inPanelZone, panelGesture, swipeOf, type PanelGesture, type PanelLayout } from './swipe';

/** The panels as the app shows them right now: docked on a wide screen, flyouts on tablets (the right one) and phones (both). */
export function currentLayout(): PanelLayout {
  const width = window.innerWidth;
  const available = prefs.showEffects || (prefs.showLights && data.settings?.lightsEnabled !== false);
  const leftDocked = !ui.narrow;
  const rightDocked = !ui.rightOverlay;
  const leftOpen = leftDocked ? prefs.leftOpen : ui.mobilePanel === 'tree';
  const rightOpen = rightDocked ? prefs.rightOpen && available : ui.mobilePanel === 'side';
  return {
    width,
    left: { open: leftOpen, border: leftDocked && leftOpen ? prefs.leftWidth : null },
    // the right panel has the splitter (10 px) in front of it
    right: { open: rightOpen, border: rightDocked && rightOpen ? width - prefs.rightWidth - 5 : null, available },
  };
}

/** Whether a touch at `x` starts a panel swipe now (other swipes, like those of play mode, leave it alone). */
export function startsPanelSwipe(x: number): boolean {
  return !ui.mobilePanel && inPanelZone(x, currentLayout());
}

/** Opens or closes a panel the way the layout shows it (docked or as a flyout). */
export function applyPanelGesture(gesture: NonNullable<PanelGesture>) {
  if (gesture.side === 'left' && ui.narrow) ui.mobilePanel = gesture.open ? 'tree' : null;
  else if (gesture.side === 'right' && ui.rightOverlay) ui.mobilePanel = gesture.open ? 'side' : null;
  else {
    prefs[gesture.side === 'left' ? 'leftOpen' : 'rightOpen'] = gesture.open;
    savePrefs();
  }
}

let start: { x: number; y: number; time: number } | null = null;

export function panelTouchStart(event: TouchEvent) {
  start = null;
  const touch = event.touches[0];
  if (event.touches.length !== 1 || !touch || ui.dialog || ui.menu || ui.tour) return;
  if ((event.target as Element | null)?.closest?.('input, textarea, select, [contenteditable], [role="slider"]')) return;
  if (startsPanelSwipe(touch.clientX)) start = { x: touch.clientX, y: touch.clientY, time: Date.now() };
}

export function panelTouchEnd(event: TouchEvent) {
  const [from, touch] = [start, event.changedTouches[0]];
  start = null;
  if (!from || !touch) return;
  const gesture = panelGesture(from.x, swipeOf(touch.clientX - from.x, touch.clientY - from.y, Date.now() - from.time), currentLayout());
  if (gesture) applyPanelGesture(gesture);
}
