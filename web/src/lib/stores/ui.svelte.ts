import type { Component } from 'svelte';

export interface Toast {
  id: number;
  message: string;
  kind: 'info' | 'error' | 'success';
}

export interface MenuItem {
  label?: string;
  icon?: string;
  shortcut?: string;
  action?: () => void;
  checked?: boolean;
  disabled?: boolean;
  separator?: boolean;
  children?: MenuItem[];
  /** Anchor for the guided tour. */
  tour?: string;
}

/** Tablets (and smaller screens): the same query hides the footer of the sidebar (Sidebar.svelte). */
const TABLET = '(max-width: 1024px), (pointer: coarse) and (max-width: 1366px)';

export const ui = $state({
  toasts: [] as Toast[],
  progress: null as string | null,
  /** Stops the running task of `progress` (a cancel button next to it), null when it cannot be stopped. */
  progressCancel: null as (() => void) | null,
  menu: null as { x: number; y: number; items: MenuItem[] } | null,
  dialog: null as { component: Component<any>; props: Record<string, unknown> } | null,
  connected: true,
  tour: false,
  /** Ids of the tour steps to show instead of the whole tour (the "What's new" tour of the steps a user has not seen yet). */
  tourNews: null as string[] | null,
  /** Phones: both side panels are flyouts over the page. */
  narrow: window.matchMedia('(max-width: 900px)').matches,
  /** Tablets and phones: the effects and lights panel is a flyout over the page (on tablets the library stays beside it). */
  rightOverlay: window.matchMedia(TABLET).matches,
  /** A finger is the main pointer: dragging is off there (a long press opens the menu instead). */
  coarse: window.matchMedia('(pointer: coarse)').matches,
  mobilePanel: null as 'tree' | 'side' | null,
});

window.matchMedia('(max-width: 900px)').addEventListener('change', (e) => {
  ui.narrow = e.matches;
  ui.mobilePanel = null;
});

window.matchMedia(TABLET).addEventListener('change', (e) => {
  ui.rightOverlay = e.matches;
  ui.mobilePanel = null;
});

let toastId = 0;

export function toast(message: string, kind: Toast['kind'] = 'info', timeout = 4000) {
  const id = ++toastId;
  ui.toasts.push({ id, message, kind });
  setTimeout(() => dismissToast(id), kind === 'error' ? timeout * 2 : timeout);
}

export function dismissToast(id: number) {
  const index = ui.toasts.findIndex((t) => t.id === id);
  if (index >= 0) ui.toasts.splice(index, 1);
}

export function errorToast(error: unknown) {
  toast(error instanceof Error ? error.message : String(error), 'error');
}

export function openMenu(event: MouseEvent | { clientX: number; clientY: number }, items: MenuItem[]) {
  if ('preventDefault' in event) {
    event.preventDefault();
    event.stopPropagation();
  }
  ui.menu = { x: event.clientX, y: event.clientY, items };
}

export function closeMenu() {
  ui.menu = null;
}

export function openDialog<P extends Record<string, unknown>>(component: Component<P>, props: P = {} as P) {
  ui.dialog = { component, props };
}

export function closeDialog() {
  ui.dialog = null;
}

/** Simple text prompt rendered by PromptDialog. */
export const prompt = $state({
  open: false,
  title: '',
  label: '',
  value: '',
  resolve: null as ((value: string | null) => void) | null,
});

export function askText(title: string, label = '', value = ''): Promise<string | null> {
  return new Promise((resolve) => {
    Object.assign(prompt, { open: true, title, label, value, resolve });
  });
}

export const confirmState = $state({ open: false, message: '', resolve: null as ((ok: boolean) => void) | null });

export function askConfirm(message: string): Promise<boolean> {
  return new Promise((resolve) => Object.assign(confirmState, { open: true, message, resolve }));
}
