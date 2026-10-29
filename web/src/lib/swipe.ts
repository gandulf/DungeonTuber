/** A finger movement from `dx`, `dy` pixels in `ms` milliseconds as a swipe: 'left' or 'right' when it is long enough, clearly more horizontal
 *  than vertical (so scrolling the notes is no swipe) and quick (a slow drag is a selection or a scroll), else null. */
export function swipeOf(dx: number, dy: number, ms: number): 'left' | 'right' | null {
  const MIN_DISTANCE = 60;
  const MAX_MS = 700;
  const HORIZONTAL = 1.5; // how much longer the horizontal movement has to be than the vertical one
  if (Math.abs(dx) < MIN_DISTANCE || Math.abs(dx) < Math.abs(dy) * HORIZONTAL || ms > MAX_MS) return null;
  return dx < 0 ? 'left' : 'right';
}

/** Whether `from` or one of its parents up to `root` scrolls sideways (a table, a code block): a swipe on it moves its content. */
export function scrollsSideways(from: Element | null, root: Element): boolean {
  for (let element = from; element && element !== root; element = element.parentElement) {
    if (element.scrollWidth > element.clientWidth + 1 && /auto|scroll/.test(getComputedStyle(element).overflowX)) return true;
  }
  return false;
}

/** How close to the screen edge (or to the border of an open panel) a swipe has to start, in px. */
export const EDGE_ZONE = 28;

export type PanelSide = 'left' | 'right';

/** The side panels as a swipe sees them: whether each can open, and where the border of an open docked panel is (null: closed, or a
 *  flyout, which handles its own swipes). */
export interface PanelLayout {
  width: number;
  left: { open: boolean; border: number | null };
  right: { open: boolean; border: number | null; available: boolean };
}

export type PanelGesture = { side: PanelSide; open: boolean } | null;

/** Whether a touch at `x` belongs to the side panels: at a screen edge with its panel closed, or on the border of an open docked panel. */
export function inPanelZone(x: number, layout: PanelLayout): boolean {
  const { width, left, right } = layout;
  return (!left.open && x <= EDGE_ZONE) || (!right.open && right.available && x >= width - EDGE_ZONE)
    || (left.border !== null && Math.abs(x - left.border) <= EDGE_ZONE) || (right.border !== null && Math.abs(x - right.border) <= EDGE_ZONE);
}

/** What a swipe that started at `x` does: from the left edge to the right opens the left panel, from the right edge to the left opens the
 *  right one; on the border of an open panel, towards its edge, closes it. */
export function panelGesture(x: number, direction: 'left' | 'right' | null, layout: PanelLayout): PanelGesture {
  const { width, left, right } = layout;
  if (direction === 'right' && !left.open && x <= EDGE_ZONE) return { side: 'left', open: true };
  if (direction === 'left' && !right.open && right.available && x >= width - EDGE_ZONE) return { side: 'right', open: true };
  if (direction === 'left' && left.border !== null && Math.abs(x - left.border) <= EDGE_ZONE) return { side: 'left', open: false };
  if (direction === 'right' && right.border !== null && Math.abs(x - right.border) <= EDGE_ZONE) return { side: 'right', open: false };
  return null;
}
