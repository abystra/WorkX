#!/usr/bin/env node
// Build a local HTML contact sheet of captured states, optionally side by side with a candidate.
//   node contact-sheet.mjs --in out/prototype [--candidate out/web] [--diff out/diff] --out out/sheet.html
import { readdir, writeFile } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { join, relative, dirname } from 'node:path';
import { STATES } from './states.mjs';

const args = Object.fromEntries(process.argv.slice(2).reduce((acc, a, i, all) => {
  if (a.startsWith('--')) acc.push([a.slice(2), all[i + 1]]);
  return acc;
}, []));
const input = args.in || 'out/prototype';
const out = args.out || 'out/contact-sheet.html';
const rel = p => relative(dirname(out), p);
const rows = [];
for (const locale of await readdir(input, { withFileTypes: true })) {
  if (!locale.isDirectory()) continue;
  for (const vp of await readdir(join(input, locale.name))) {
    for (const s of STATES) {
      const file = join(input, locale.name, vp, `${s.id}.png`);
      if (!existsSync(file)) continue;
      const cells = [file, args.candidate && join(args.candidate, locale.name, vp, `${s.id}.png`), args.diff && join(args.diff, locale.name, vp, `${s.id}.png`)]
        .filter(Boolean).map(f => existsSync(f) ? `<a href="${rel(f)}"><img loading="lazy" src="${rel(f)}" alt=""></a>` : '<div class="missing">—</div>');
      rows.push(`<section><h2>${s.id} <small>${locale.name} · ${vp} · ${s.module} → ${s.target}</small></h2><div class="cells">${cells.join('')}</div></section>`);
    }
  }
}
await writeFile(out, `<!doctype html><meta charset="utf-8"><title>WorkX UI fidelity</title>
<style>body{font:13px system-ui;margin:16px;background:#f7f7f7}section{background:#fff;border:1px solid #e5e6e8;border-radius:8px;padding:10px;margin:0 0 12px}
h2{font-size:13px;margin:0 0 8px}small{color:#8f959e;font-weight:400}.cells{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:8px}
img{width:100%;border:1px solid #e5e6e8}.missing{display:grid;place-items:center;color:#8f959e;border:1px dashed #e5e6e8;min-height:120px}</style>
<h1>WorkX UI fidelity (${rows.length} captures)</h1>${rows.join('\n')}`);
console.log('wrote', out);
