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
  { key: 'darkred', name: 'Dark Red', light: ['#8b0000', '#b22222'], dark: ['#c62828', '#e55b5b'] },
  { key: 'pink', name: 'Pink', light: ['#d6457a', '#ef6fa0'], dark: ['#ff7aa8', '#ffa3c4'], text: ['#ffffff', '#3a0f20'] },
];

export const DEFAULT_ACCENT = 'violet';

const ACCENT_VARIABLES = ['--accent', '--accent-2', '--accent-text', '--accent-soft', '--accent-hover', '--accent-glow', '--accent-rgb'];
const SURFACE_VARIABLES = ['--bg', '--bg-2', '--surface', '--surface-2', '--surface-3', '--border', '--border-strong', '--text', '--muted', '--faint', '--hover', '--shadow', '--shadow-sm'];
const VARIABLES = [...ACCENT_VARIABLES, ...SURFACE_VARIABLES];

function hue(hex: string): number {
  const value = parseInt(hex.slice(1), 16);
  const r = ((value >> 16) & 255) / 255, g = ((value >> 8) & 255) / 255, b = (value & 255) / 255;
  const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min;
  if (d === 0) return 0;
  const h = max === r ? ((g - b) / d) % 6 : max === g ? (b - r) / d + 2 : (r - g) / d + 4;
  return Math.round((h * 60 + 360) % 360);
}

/** The backgrounds, borders and greys tinted with the hue of the accent, in the same lightness steps as the violet default of app.css. */
function surfaces(h: number, dark: boolean): Record<string, string> {
  if (dark) {
    return {
      '--bg': `hsl(${h}, 30%, 7%)`, '--bg-2': `hsl(${h}, 30%, 10%)`, '--surface': `hsl(${h}, 26%, 12.5%)`, '--surface-2': `hsl(${h}, 27%, 15.5%)`, '--surface-3': `hsl(${h}, 27%, 19.5%)`,
      '--text': `hsl(${h}, 40%, 94%)`, '--muted': `hsl(${h}, 16%, 66%)`, '--faint': `hsl(${h}, 13%, 46%)`,
      '--shadow': '0 16px 44px rgba(0, 0, 0, 0.55)', '--shadow-sm': '0 2px 12px rgba(0, 0, 0, 0.35)',
    };
  }
  return {
    '--bg': `hsl(${h}, 34%, 96%)`, '--bg-2': `hsl(${h}, 36%, 94.5%)`, '--surface': '#ffffff', '--surface-2': `hsl(${h}, 55%, 97.5%)`, '--surface-3': `hsl(${h}, 45%, 93.5%)`,
    '--border': `hsl(${h}, 30%, 91%)`, '--border-strong': `hsl(${h}, 28%, 83%)`, '--text': `hsl(${h}, 25%, 13%)`, '--muted': `hsl(${h}, 11%, 46%)`, '--faint': `hsl(${h}, 10%, 64%)`,
    '--hover': `hsla(${h}, 50%, 20%, 0.05)`,
    '--shadow': `0 10px 34px hsla(${h}, 55%, 22%, 0.14)`, '--shadow-sm': `0 2px 10px hsla(${h}, 55%, 22%, 0.06)`,
  };
}

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
  root.style.setProperty('--accent-rgb', channels);
  for (const variable of SURFACE_VARIABLES) root.style.removeProperty(variable); // what the theme does not tint (e.g. the borders of the dark theme) comes from the stylesheet
  for (const [variable, value] of Object.entries(surfaces(hue(accent.light[0]), dark))) root.style.setProperty(variable, value);
}
