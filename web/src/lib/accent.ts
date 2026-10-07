// Accent colours a user can pick (Settings > General). The server stores only the key; the default is the violet of app.css.
export interface Accent {
  key: string;
  name: string; // message id (translated where it is shown)
  light: [string, string]; // accent and its second gradient colour on the light theme
  dark: [string, string];
  /** Text on top of the accent colour (light/dark theme). */
  text?: [string, string];
}

export const ACCENTS: Accent[] = [
  { key: 'violet', name: 'Violet', light: ['#6a4cf5', '#9a5cf7'], dark: ['#8b6dff', '#b275ff'] },
  { key: 'blue', name: 'Blue', light: ['#2563eb', '#4f9bff'], dark: ['#5b9bff', '#7cb8ff'] },
  { key: 'teal', name: 'Teal', light: ['#0d9488', '#2bc4b8'], dark: ['#2dd4bf', '#5eead4'], text: ['#ffffff', '#0b2e2b'] },
  { key: 'green', name: 'Green', light: ['#2f9e5e', '#4fbf7a'], dark: ['#4ade80', '#86efac'], text: ['#ffffff', '#0b2e19'] },
  { key: 'amber', name: 'Amber', light: ['#c77d04', '#f2a93b'], dark: ['#fbbf24', '#fcd34d'], text: ['#ffffff', '#33250a'] },
  { key: 'orange', name: 'Orange', light: ['#e8590c', '#f58a3c'], dark: ['#ff8a4c', '#ffb27a'], text: ['#ffffff', '#3a1a08'] },
  { key: 'red', name: 'Red', light: ['#d6303f', '#ef5b6b'], dark: ['#ff6b78', '#ff9aa3'], text: ['#ffffff', '#3a0d12'] },
  { key: 'pink', name: 'Pink', light: ['#d6457a', '#ef6fa0'], dark: ['#ff7aa8', '#ffa3c4'], text: ['#ffffff', '#3a0f20'] },
];

export const DEFAULT_ACCENT = 'violet';

const VARIABLES = ['--accent', '--accent-2', '--accent-text', '--accent-soft', '--accent-hover', '--accent-glow'];

function rgb(hex: string): string {
  const value = parseInt(hex.slice(1), 16);
  return `${(value >> 16) & 255}, ${(value >> 8) & 255}, ${value & 255}`;
}

/** Sets the accent variables of the page (the default accent uses the stylesheet values). */
export function applyAccent(key: string | null | undefined, dark: boolean, root: HTMLElement = document.documentElement) {
  const accent = ACCENTS.find((candidate) => candidate.key === key);
  if (!accent || accent.key === DEFAULT_ACCENT) {
    for (const variable of VARIABLES) root.style.removeProperty(variable);
    return;
  }
  const [main, second] = dark ? accent.dark : accent.light;
  const channels = rgb(main);
  root.style.setProperty('--accent', main);
  root.style.setProperty('--accent-2', second);
  root.style.setProperty('--accent-text', accent.text?.[dark ? 1 : 0] ?? '#ffffff');
  root.style.setProperty('--accent-soft', `rgba(${channels}, ${dark ? 0.2 : 0.12})`);
  root.style.setProperty('--accent-hover', `rgba(${channels}, ${dark ? 0.11 : 0.07})`);
  root.style.setProperty('--accent-glow', `rgba(${channels}, ${dark ? 0.55 : 0.35})`);
}
