import { saasMessages } from './messages-saas.js';
import { mainMessages } from './messages-main.js';
import { actionMessages } from './messages-actions.js';
import { secondaryMessages } from './messages-secondary.js';
import { workspaceMessages } from './messages-workspace.js';
import { ecosystemMessages } from './messages-ecosystem.js';
import { teamMessages } from './messages-team.js';
import { connectionMessages } from './messages-connection.js';
import { channelMessages } from './messages-channel.js';

export const SUPPORTED_LOCALES = ['zh-CN', 'en'];
export const LOCALE_STORAGE_KEY = 'workx-locale';
export const messages = { ...actionMessages, ...secondaryMessages, ...mainMessages, ...workspaceMessages, ...ecosystemMessages, ...teamMessages, ...connectionMessages, ...channelMessages, ...saasMessages };
let locale = 'zh-CN';
try {
  const saved = localStorage.getItem(LOCALE_STORAGE_KEY);
  if (SUPPORTED_LOCALES.includes(saved)) locale = saved;
} catch { /* Keep Chinese when storage is unavailable. */ }
export const getLocale = () => locale;
export function setLocale(value) {
  if (!SUPPORTED_LOCALES.includes(value)) return false;
  locale = value;
  try { localStorage.setItem(LOCALE_STORAGE_KEY, value); } catch { /* Session preference still works. */ }
  return true;
}
export function t(key, params = {}) {
  const text = messages[key]?.[locale === 'en' ? 1 : 0] ?? key;
  return String(text).replace(/\{(\w+)\}/g, (match, name) => Object.hasOwn(params, name) ? String(params[name]) : match);
}
export function formatSchedule(value) {
  const match = String(value || '').match(/^(Every weekday|Every day|Every Monday|Every Friday) at (\d{2}:\d{2})$/);
  return match ? t('sec.schedule.at', {frequency:t(match[1]),time:match[2]}) : String(value || '');
}
export function formatRelative(value) {
  if (['Today','Yesterday','Just now','Just updated'].includes(value)) return t(value);
  const date = /^Oct (\d{1,2})$/.exec(value || '');
  return date && locale === 'zh-CN' ? `10月${date[1]}日` : String(value || '');
}
