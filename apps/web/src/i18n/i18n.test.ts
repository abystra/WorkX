import { describe, expect, it } from 'vitest';
import en from './locales/en.json';
import zh from './locales/zh-CN.json';
import { COPY_OVERRIDES } from './overrides';
import { COPY_ADDITIONS } from './additions';
import { i18n, setLocale, tStatic } from './index';

describe('i18n port', () => {
  it('has the same keys in both languages', () => {
    expect(Object.keys(en).sort()).toEqual(Object.keys(zh).sort());
    expect(Object.keys(en).length).toBeGreaterThan(1100);
  });

  it('only overrides keys that exist in the prototype dictionaries', () => {
    for (const key of Object.keys(COPY_OVERRIDES)) expect(en).toHaveProperty([key]);
  });

  it('keeps new-state copy in its own namespace', () => {
    for (const key of Object.keys(COPY_ADDITIONS)) {
      expect(key.startsWith('web.')).toBe(true);
      expect(en).not.toHaveProperty([key]);
    }
  });

  it('interpolates {name} placeholders and leaves unknown ones as written (prototype behavior)', () => {
    setLocale('en');
    expect(tStatic('spaces.switched', { name: 'Acme' })).toContain('Acme');
    expect(tStatic('ui.moreTask', {})).toContain('{name}');
  });

  it('returns the key for unknown keys and applies approved wording', () => {
    setLocale('zh-CN');
    expect(tStatic('No such key')).toBe('No such key');
    expect(tStatic('About this prototype')).toBe('关于 WorkX');
    setLocale('en');
    expect(i18n.language).toBe('en');
  });
});
