/**
 * Svelte action: a long press with a finger or a pen raises a `contextmenu` event on the element, so the existing right-click menus work on touch.
 * iOS Safari never sends `contextmenu` for a long press, Android browsers do; a native event that arrives anyway is not raised twice.
 */
const HOLD = 450; // ms
const SLOP = 10; // px a finger may wander before it counts as a scroll or a drag

// a press is handled by the innermost element with the action: an entry of a list with a menu of its own beats the list's menu
const claimed = new WeakSet<PointerEvent>();

export function longpress(node: HTMLElement) {
  let timer: ReturnType<typeof setTimeout> | undefined;
  let start = { x: 0, y: 0 };
  let fired = 0; // when the menu was last raised
  let swallowClick = false;

  const cancel = () => clearTimeout(timer);

  function raise(x: number, y: number) {
    fired = performance.now();
    swallowClick = true;
    navigator.vibrate?.(10);
    node.dispatchEvent(new MouseEvent('contextmenu', { bubbles: true, cancelable: true, clientX: x, clientY: y, button: 2 }));
  }

  function down(event: PointerEvent) {
    cancel();
    swallowClick = false;
    if (event.pointerType === 'mouse' || !event.isPrimary || claimed.has(event)) return;
    claimed.add(event);
    start = { x: event.clientX, y: event.clientY };
    timer = setTimeout(() => raise(start.x, start.y), HOLD);
  }

  function move(event: PointerEvent) {
    if (Math.hypot(event.clientX - start.x, event.clientY - start.y) > SLOP) cancel();
  }

  /** The browser's own long-press event comes in a moment after ours (or instead of it): handled once. */
  function native(event: MouseEvent) {
    if (performance.now() - fired < 1000 && event.isTrusted) {
      event.stopImmediatePropagation();
      event.preventDefault();
    } else if (event.isTrusted) {
      fired = performance.now();
      swallowClick = true;
      cancel();
    }
  }

  /** Letting go after the long press would click the entry under the finger (and close the menu again). */
  function click(event: MouseEvent) {
    if (!swallowClick) return;
    swallowClick = false;
    event.stopPropagation();
    event.preventDefault();
  }

  node.addEventListener('pointerdown', down);
  node.addEventListener('pointermove', move);
  node.addEventListener('pointerup', cancel);
  node.addEventListener('pointercancel', cancel);
  node.addEventListener('pointerleave', cancel);
  node.addEventListener('contextmenu', native, true);
  node.addEventListener('click', click, true);
  return {
    destroy() {
      cancel();
      node.removeEventListener('pointerdown', down);
      node.removeEventListener('pointermove', move);
      node.removeEventListener('pointerup', cancel);
      node.removeEventListener('pointercancel', cancel);
      node.removeEventListener('pointerleave', cancel);
      node.removeEventListener('contextmenu', native, true);
      node.removeEventListener('click', click, true);
    },
  };
}
