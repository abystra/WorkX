#!/usr/bin/env node
// Pixel-compare two capture directories (baseline vs candidate) and write diff images.
//
//   node compare.mjs --baseline out/prototype --candidate out/web --out out/diff
//
// Thresholds (share of differing pixels, per screenshot):
//   pass   <= 0.5%   identical within anti-aliasing noise
//   review <= 3%     must be inspected and either fixed or recorded as an approved deviation
//   fail   >  3%     or size mismatch or missing candidate
// Approved deviations (docs/architecture/15-UI-FIDELITY.md §5) are listed in approved-deviations.json
// and reported as "approved" instead of failing.
import { readFile, writeFile, mkdir, readdir } from 'node:fs/promises';
import { existsSync } from 'node:fs';
import { join, relative } from 'node:path';
import { PNG } from 'pngjs';
import pixelmatch from 'pixelmatch';

const args = Object.fromEntries(process.argv.slice(2).reduce((acc, a, i, all) => {
  if (a.startsWith('--')) acc.push([a.slice(2), all[i + 1]]);
  return acc;
}, []));
const baseline = args.baseline || 'out/prototype';
const candidate = args.candidate || 'out/web';
const out = args.out || 'out/diff';
const PASS = Number(args.pass ?? 0.005);
const REVIEW = Number(args.review ?? 0.03);
const deviations = existsSync(new URL('./approved-deviations.json', import.meta.url))
  ? JSON.parse(await readFile(new URL('./approved-deviations.json', import.meta.url), 'utf8')).deviations
  : [];
const approved = deviations.filter(d => d.status !== 'proposed').map(d => d.state);
const proposed = deviations.filter(d => d.status === 'proposed').map(d => d.state);

async function walk(dir) {
  const files = [];
  for (const e of await readdir(dir, { withFileTypes: true })) {
    const p = join(dir, e.name);
    if (e.isDirectory()) files.push(...await walk(p));
    else if (e.name.endsWith('.png')) files.push(p);
  }
  return files;
}

const rows = [];
for (const file of await walk(baseline)) {
  const rel = relative(baseline, file);
  const stateId = rel.split('/').pop().replace(/\.png$/, '');
  const cand = join(candidate, rel);
  if (!existsSync(cand)) { rows.push({ rel, verdict: 'fail', reason: 'missing candidate' }); continue; }
  const a = PNG.sync.read(await readFile(file));
  const b = PNG.sync.read(await readFile(cand));
  if (a.width !== b.width || a.height !== b.height) {
    rows.push({ rel, verdict: approved.includes(stateId) ? 'approved' : 'fail', reason: `size ${a.width}x${a.height} vs ${b.width}x${b.height}` });
    continue;
  }
  const diff = new PNG({ width: a.width, height: a.height });
  const n = pixelmatch(a.data, b.data, diff.data, a.width, a.height, { threshold: 0.1 });
  const ratio = n / (a.width * a.height);
  let verdict = ratio <= PASS ? 'pass' : ratio <= REVIEW ? 'review' : 'fail';
  if (verdict !== 'pass' && approved.includes(stateId)) verdict = 'approved';
  else if (verdict !== 'pass' && proposed.includes(stateId)) verdict = 'proposed';
  if (verdict !== 'pass') {
    const target = join(out, rel);
    await mkdir(join(target, '..'), { recursive: true });
    await writeFile(target, PNG.sync.write(diff));
  }
  rows.push({ rel, verdict, ratio: Number(ratio.toFixed(5)) });
}
await mkdir(out, { recursive: true });
await writeFile(join(out, 'summary.json'), JSON.stringify(rows, null, 2));
const count = v => rows.filter(r => r.verdict === v).length;
for (const r of rows.filter(r => r.verdict !== 'pass')) console.log(`${r.verdict.padEnd(9)} ${r.rel} ${r.reason || (r.ratio * 100).toFixed(2) + '%'}`);
console.log(`\n${rows.length} compared: ${count('pass')} pass, ${count('review')} review, ${count('approved')} approved deviation, ${count('proposed')} proposed deviation (awaiting review), ${count('fail')} fail`);
if (count('fail')) process.exitCode = 1;
