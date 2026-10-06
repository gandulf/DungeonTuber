// core/locales/*.json are the single source of truth, shared with the server.
import de from '../../../core/locales/de.json';
import en from '../../../core/locales/en.json';

const catalogs: Record<string, Record<string, string>> = { de, en };

const state = $state({ locale: detectLocale() });

function detectLocale(): string {
  const lang = (navigator.language || 'en').slice(0, 2);
  return lang in catalogs ? lang : 'en';
}

export function setLocale(locale: string | null | undefined) {
  state.locale = locale && locale in catalogs ? locale : detectLocale();
  document.documentElement.lang = state.locale;
}

export function locale(): string {
  return state.locale;
}

/** Translates a message id (the English text) and fills {0}, {1}, ... placeholders. */
export function t(key: string, ...args: (string | number)[]): string {
  const text = catalogs[state.locale]?.[key] ?? catalogs.en[key] ?? key;
  return args.length ? text.replace(/\{(\d+)\}/g, (_, i) => String(args[Number(i)] ?? '')) : text;
}
