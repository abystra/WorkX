// Browser check for Knowledge (Q-15) against the development adapter (pnpm dev:fidelity).
// Usage: node tests/e2e/knowledge.mjs [--base http://127.0.0.1:5173] [--shots <dir>]
import { createRequire } from 'node:module';
import { mkdir } from 'node:fs/promises';
import { join } from 'node:path';

const { chromium } = createRequire(import.meta.url)('playwright');
const args = Object.fromEntries(process.argv.slice(2).reduce((acc, value, i, all) => (value.startsWith('--') ? [...acc, [value.slice(2), all[i + 1]]] : acc), []));
const base = args.base || 'http://127.0.0.1:5173';
const shots = args.shots;
const VIEWPORTS = { desktop: { width: 1440, height: 900 }, laptop: { width: 1280, height: 800 } };
let passed = 0, total = 0;
const expect = (name, ok, detail = '') => { total++; if (ok) passed++; console.log(`${ok ? 'ok  ' : 'FAIL'} ${name}${ok ? '' : ' ' + detail}`); if (!ok) process.exitCode = 1; };

const browser = await chromium.launch();
for (const [vpName, viewport] of Object.entries(VIEWPORTS)) {
  for (const locale of ['en', 'zh-CN']) {
    const context = await browser.newContext({ viewport, locale: locale === 'en' ? 'en-US' : 'zh-CN' });
    await context.addInitScript(value => { try { localStorage.setItem('workx-locale', value); } catch { /* ignore */ } }, locale);
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', e => errors.push(e.message));
    const tag = `${locale} ${vpName}`;
    const shot = async name => {
      if (!shots) return;
      const dir = join(shots, locale, vpName);
      await mkdir(dir, { recursive: true });
      await page.screenshot({ path: join(dir, `${name}.png`) });
    };
    await page.goto(`${base}/__test__/seed?fixture=prototype&next=${encodeURIComponent('/t/wx-demo/detail/a1')}`);
    await page.waitForSelector('.app-layout');
    await page.click('[data-action="detail-tab"][data-tab="Work Context"]');
    await page.waitForSelector('.wx-knowledge');
    expect(`${tag}: work context shows the empty knowledge section`, await page.isVisible('.wx-knowledge-empty'));
    await shot('knowledge-empty');
    await page.click('[data-action="knowledge-attach"]');
    await page.waitForSelector('#knowledge-form');
    await shot('knowledge-attach-dialog');
    const boxes = page.locator('#knowledge-form input[name="files"]');
    expect(`${tag}: dialog lists library files`, (await boxes.count()) > 1);
    await boxes.nth(0).check();
    await boxes.nth(1).check();
    await page.click('[data-action="knowledge-save"]');
    await page.waitForSelector('.wx-knowledge-row');
    expect(`${tag}: two sources attached and processing`, (await page.locator('.wx-knowledge-row .is-running').count()) === 2);
    await shot('knowledge-processing');
    await page.waitForSelector('.wx-knowledge-row .is-delivered', { timeout: 5000 });
    await page.waitForTimeout(300);
    expect(`${tag}: sources become ready`, (await page.locator('.wx-knowledge-row .is-delivered').count()) === 2);
    await page.waitForTimeout(3300); // let the toast clear before the review screenshot
    await shot('knowledge-ready');
    await page.click('[data-action="nav"][data-page="library"]');
    await page.click('[data-action="library-filter"][data-filter="knowledge"]');
    expect(`${tag}: library knowledge filter shows the two files`, (await page.locator('.sw-file-card').count()) === 2);
    expect(`${tag}: library cards carry the status tag`, (await page.locator('.sw-file-card .wx-knowledge-status').count()) === 2);
    await shot('library-knowledge');
    await page.goto(`${base}/t/wx-demo/detail/a1`);
    await page.click('[data-action="detail-tab"][data-tab="Work Context"]');
    await page.locator('[data-action="knowledge-remove"]').first().click();
    await page.waitForTimeout(300);
    expect(`${tag}: removing detaches one source`, (await page.locator('.wx-knowledge-row').count()) === 1);
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth > innerWidth);
    expect(`${tag}: no horizontal overflow`, !overflow);
    expect(`${tag}: no page errors`, errors.length === 0, errors.join(' | '));
    await context.close();
  }
}
await browser.close();
console.log(`\n${passed}/${total} checks passed`);
