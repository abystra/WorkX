#!/usr/bin/env node
// Converts the prototype's message dictionaries (workmates-prototype/dist/messages-*.js, entries [zh, en])
// into i18next resources with identical keys. Re-run when the prototype copy changes.
import { writeFile, mkdir } from 'node:fs/promises';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { dirname, join } from 'node:path';

const here = dirname(fileURLToPath(import.meta.url));
const proto = join(here, '../../../workmates-prototype/dist');
const modules = ['actions', 'secondary', 'main', 'workspace', 'ecosystem', 'team', 'connection', 'channel', 'saas', 'spaces'];
const merged = {};
// Same merge order as the prototype's i18n.js (later modules win).
for (const name of modules) {
  const mod = await import(pathToFileURL(join(proto, `messages-${name}.js`)).href);
  const dict = Object.values(mod).find(v => v && typeof v === 'object');
  Object.assign(merged, dict);
}
const zh = {}, en = {};
for (const [key, [zhText, enText]] of Object.entries(merged)) { zh[key] = zhText; en[key] = enText; }
const out = join(here, '../src/i18n/locales');
await mkdir(out, { recursive: true });
await writeFile(join(out, 'zh-CN.json'), JSON.stringify(zh, null, 1) + '\n');
await writeFile(join(out, 'en.json'), JSON.stringify(en, null, 1) + '\n');
console.log(`converted ${Object.keys(merged).length} keys`);
