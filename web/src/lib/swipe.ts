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
