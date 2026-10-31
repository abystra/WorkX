import i18next from 'i18next';
import { initReactI18next, useTranslation } from 'react-i18next';
import en from './locales/en.json';
import zh from './locales/zh-CN.json';
import { COPY_OVERRIDES } from './overrides';
import { COPY_ADDITIONS } from './additions';

export const SUPPORTED_LOCALES = ['zh-CN', 'en'] as const;
export type Locale = (typeof SUPPORTED_LOCALES)[number];
// Same key as the prototype, so a returning user keeps their language.
export const LOCALE_STORAGE_KEY = 'workx-locale';

function initialLocale(): Locale {
  try {
    const saved = localStorage.getItem(LOCALE_STORAGE_KEY);
    if (saved && (SUPPORTED_LOCALES as readonly string[]).includes(saved)) return saved as Locale;
  } catch { /* English when storage is unavailable */ }
  return 'en';
}

function withOverrides(base: Record<string, string>, lang: Locale) {
  const result = { ...base };
  for (const [key, value] of Object.entries({ ...COPY_ADDITIONS, ...COPY_OVERRIDES })) result[key] = value[lang];
  return result;
}

void i18next.use(initReactI18next).init({
  lng: initialLocale(),
  fallbackLng: false,
  load: 'currentOnly',
  resources: {
    en: { translation: withOverrides(en as Record<string, string>, 'en') },
    'zh-CN': { translation: withOverrides(zh as Record<string, string>, 'zh-CN') },
  },
  // Prototype keys contain dots, colons and full sentences.
  keySeparator: false,
  nsSeparator: false,
  returnNull: false,
  interpolation: { escapeValue: false, prefix: '{', suffix: '}' },
  // Prototype behavior: unknown placeholders stay as written.
  missingInterpolationHandler: (_text: string, value: RegExpExecArray) => value[0],
  react: { useSuspense: false },
});

export const i18n = i18next;
export const getLocale = () => i18next.language as Locale;

export function setLocale(value: string): boolean {
  if (!(SUPPORTED_LOCALES as readonly string[]).includes(value)) return false;
  void i18next.changeLanguage(value);
  try { localStorage.setItem(LOCALE_STORAGE_KEY, value); } catch { /* session preference still works */ }
  document.documentElement.lang = value;
  return true;
}

export type TFn = (key: string, params?: Record<string, unknown>) => string;

/** Translation function with prototype semantics: missing keys return the key itself. */
export function useT(): TFn {
  const { t } = useTranslation();
  return (key, params) => String(t(key, params as never));
}

export const tStatic: TFn = (key, params) => String(i18next.t(key, params as never));

const DISPLAY_KEYS = ['Personal', 'Team', 'Third-party', 'Squads', 'Auto', 'Slides', 'Deep Research', 'Data Visualization', 'Product Prototype', 'Office', 'Image', 'No description yet'];

export function formatRelative(t: TFn, value?: string): string {
  if (['Today', 'Yesterday', 'Just now', 'Just updated'].includes(value || '')) return t(value!);
  const date = /^Oct (\d{1,2})$/.exec(value || '');
  return date && getLocale() === 'zh-CN' ? `10月${date[1]}日` : String(value || '');
}

export function displayText(t: TFn, value?: string): string {
  return DISPLAY_KEYS.includes(value || '') ? t(value!) : formatRelative(t, value);
}

export function formatSchedule(t: TFn, value?: string): string {
  const match = String(value || '').match(/^(Every weekday|Every day|Every Monday|Every Friday) at (\d{2}:\d{2})$/);
  return match ? t('sec.schedule.at', { frequency: t(match[1]), time: match[2] }) : String(value || '');
}
