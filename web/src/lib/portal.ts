/** Moves an element into `target` for as long as there is one, and back to where it was before when `target` is null. The element stays
 *  the component's own (its bindings and updates go on); only its place in the page changes. */
export function portal(node: HTMLElement, target: HTMLElement | null) {
  const home = document.createComment('');
  node.before(home);
  const move = (to: HTMLElement | null) => (to ? to.append(node) : home.after(node));
  move(target);
  return {
    update: move,
    destroy() {
      home.remove();
      node.remove();
    },
  };
}
