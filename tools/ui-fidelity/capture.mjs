#!/usr/bin/env node
// Capture every catalog state from a target UI at fixed viewports and locales.
//
//   node capture.mjs --target prototype --base http://127.0.0.1:4173 --out out/prototype
//   node capture.mjs --target web --base http://127.0.0.1:5173 --out out/web
//
// Scope: desktop web only (product decision 2026-10-31). Mobile viewport kept for optional local runs.
//
// Options: --viewports desktop,mobile  --locales en,zh-CN  --only id1,id2
// Writes <out>/<locale>/<viewport>/<state>.png and <out>/report.json (errors, overflow, failed steps).
import { chromium } from 'playwright';
import { mkdir, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { STATES, VIEWPORTS } from './states.mjs';
import { TARGETS } from './targets.mjs';

const args = Object.fromEntries(process.argv.slice(2).reduce((acc, a, i, all) => {
  if (a.startsWith('--')) acc.push([a.slice(2), all[i + 1]]);
  return acc;
}, []));
const target = TARGETS[args.target || 'prototype'];
if (!target) throw new Error(`Unknown target ${args.target}`);
const base = (args.base || target.defaultBase).replace(/\/$/, '');
const out = args.out || `out/${args.target || 'prototype'}`;
const viewports = (args.viewports || 'desktop').split(',');
const locales = (args.locales || 'en,zh-CN').split(',');
const only = args.only ? new Set(args.only.split(',')) : null;
const FIXED_TIME = new Date('2026-10-30T09:00:00+08:00');

function locatorFor(page, ref, attrs = {}) {
  let sel;
  if (ref.startsWith('a:')) {
    sel = `[data-action="${ref.slice(2)}"]` + Object.entries(attrs).map(([k, v]) => `[data-${k}="${v}"]`).join('');
  } else if (ref.startsWith('css:')) sel = ref.slice(4);
  else throw new Error(`Bad selector ${ref}`);
  return page.locator(sel).locator('visible=true').first();
}

async function runStep(page, step) {
  const [kind, a, b] = step;
  if (kind === 'click') await locatorFor(page, a, b && typeof b === 'object' ? b : {}).click({ timeout: 3000 });
  else if (kind === 'hover') await locatorFor(page, a).hover({ timeout: 3000 });
  else if (kind === 'fill') await locatorFor(page, a).fill(b, { timeout: 3000 });
  else if (kind === 'press') await page.keyboard.press(a);
  else if (kind === 'wait') await page.waitForTimeout(a);
  else throw new Error(`Unknown step ${kind}`);
  await page.waitForTimeout(120);
}

const browser = await chromium.launch();
const report = { target: args.target || 'prototype', base, capturedAt: new Date().toISOString(), results: [] };
for (const locale of locales) {
  for (const vp of viewports) {
    const dir = join(out, locale, vp);
    await mkdir(dir, { recursive: true });
    for (const state of STATES) {
      if (only && !only.has(state.id)) continue;
      if (state.only && !state.only.includes(vp)) continue;
      const context = await browser.newContext({ viewport: VIEWPORTS[vp], reducedMotion: 'reduce', deviceScaleFactor: 1, locale });
      const page = await context.newPage();
      await page.clock.setFixedTime(FIXED_TIME);
      const errors = [];
      page.on('pageerror', e => errors.push(`pageerror: ${e.message}`));
      page.on('console', m => { if (m.type() === 'error') errors.push(`console: ${m.text()}`); });
      const result = { id: state.id, locale, viewport: vp, ok: true, errors, failedStep: null };
      try {
        await target.prepare(page, { base, locale });
        await target.open(page, { base, state });
        for (const step of (state.targetSteps?.[report.target] || state.steps || [])) await runStep(page, step);
        await page.waitForTimeout(200);
        result.horizontalOverflow = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1);
        await page.screenshot({ path: join(dir, `${state.id}.png`), fullPage: !!state.full && !page.url().includes('overlay') });
      } catch (e) {
        result.ok = false;
        result.failedStep = String(e.message || e).split('\n')[0];
        if (!state.optional) process.exitCode = 1;
      }
      report.results.push(result);
      const flag = result.ok ? (result.horizontalOverflow ? 'OVERFLOW' : 'ok') : (state.optional ? 'skip' : 'FAIL');
      console.log(`${flag.padEnd(8)} ${locale.padEnd(6)} ${vp.padEnd(8)} ${state.id}${result.failedStep ? '  — ' + result.failedStep : ''}${errors.length ? `  (${errors.length} errors)` : ''}`);
      await context.close();
    }
  }
}
await browser.close();
await writeFile(join(out, 'report.json'), JSON.stringify(report, null, 2));
const failed = report.results.filter(r => !r.ok).length;
console.log(`\n${report.results.length} captures, ${failed} failed/skipped, ${report.results.filter(r => r.horizontalOverflow).length} with horizontal overflow, ${report.results.filter(r => r.errors.length).length} with console errors`);
